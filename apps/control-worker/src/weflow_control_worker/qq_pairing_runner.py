"""Bounded read-only QQ Gateway runner for first-group pairing."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from weflow_control_kernel.qq_pairing import (
    QQGroupPairingConfig,
    QQGroupPairingController,
    QQPairingEventRejected,
    QQPairingJournalError,
    SQLiteQQPairingJournal,
    build_pairing_report,
    create_pairing_challenge,
)
from weflow_control_kernel.qq_sandbox import QQTransportError
from weflow_control_kernel.qq_transport import (
    QQGatewayTransport,
    QQTokenTransport,
    QQWebSocketConnection,
    QQWebSocketTransport,
)

from .qq_adapter import (
    QQ_GROUP_INTENT,
    BoundedQQHTTPClient,
    RealQQGatewayTransport,
    RealQQTokenTransport,
    RealQQWebSocketTransport,
)

MAX_RECONNECTS = 3
RECEIVE_TIMEOUT_SECONDS = 60.0


class QQGroupPairingRunner:
    def __init__(
        self,
        *,
        config: QQGroupPairingConfig,
        controller: QQGroupPairingController,
        token_transport: QQTokenTransport,
        gateway_transport: QQGatewayTransport,
        websocket_transport: QQWebSocketTransport,
        contract_root: Path,
        evidence_mode: str = "fake",
    ) -> None:
        if evidence_mode not in {"fake", "live"}:
            raise ValueError("pairing_evidence_mode_invalid")
        if evidence_mode == "live" and not (
            isinstance(token_transport, RealQQTokenTransport)
            and isinstance(gateway_transport, RealQQGatewayTransport)
            and isinstance(websocket_transport, RealQQWebSocketTransport)
        ):
            raise ValueError("pairing_live_evidence_requires_real_adapters")
        self.config = config
        self.controller = controller
        self.token_transport = token_transport
        self.gateway_transport = gateway_transport
        self.websocket_transport = websocket_transport
        self.contract_root = contract_root
        self.evidence_mode = evidence_mode

    @property
    def challenge_text(self) -> str:
        return self.controller.challenge.plaintext

    def _require_active_challenge(self) -> float:
        remaining = self.controller.remaining_deadline_seconds()
        if remaining <= 0:
            self.controller.expire()
            raise QQTransportError("pairing_challenge_expired")
        return remaining

    async def _authenticate(
        self,
        connection: QQWebSocketConnection,
        access_token: str,
        session_id: str | None,
        sequence: int | None,
    ) -> int:
        remaining = self._require_active_challenge()
        try:
            hello = dict(
                await asyncio.wait_for(
                    connection.receive(), min(RECEIVE_TIMEOUT_SECONDS, remaining)
                )
            )
        except TimeoutError as error:
            self._require_active_challenge()
            raise QQTransportError("pairing_gateway_hello_timeout") from error
        data = hello.get("d")
        heartbeat = data.get("heartbeat_interval") if isinstance(data, dict) else None
        if (
            hello.get("op") != 10
            or not isinstance(heartbeat, int)
            or not 1_000 <= heartbeat <= 120_000
        ):
            raise QQTransportError("pairing_gateway_hello_invalid")
        token = f"QQBot {access_token}"
        if session_id is not None and sequence is not None:
            await connection.send(
                {"op": 6, "d": {"token": token, "session_id": session_id, "seq": sequence}}
            )
        else:
            await connection.send(
                {
                    "op": 2,
                    "d": {
                        "token": token,
                        "intents": QQ_GROUP_INTENT,
                        "shard": [0, 1],
                        "properties": {
                            "$os": "weflow",
                            "$browser": "weflow-pairing",
                            "$device": "weflow",
                        },
                    },
                }
            )
        return heartbeat

    async def run_one(self, *, on_listening: Callable[[str], None] | None = None) -> dict[str, Any]:
        self._require_active_challenge()
        try:
            token = self.token_transport.fetch(
                app_id=self.config.app_id, client_secret=self.config.client_secret
            )
        except QQTransportError as error:
            if error.reason_code == "qq_provider_outcome_unknown":
                raise QQTransportError("pairing_token_transport_unreachable") from error
            raise
        self._require_active_challenge()
        try:
            gateway = self.gateway_transport.fetch(access_token=token.value)
        except QQTransportError as error:
            if error.reason_code == "qq_provider_outcome_unknown":
                raise QQTransportError("pairing_gateway_transport_unreachable") from error
            raise
        session_id: str | None = None
        sequence: int | None = None
        reconnects = 0
        observed = 0
        rejected = 0
        challenge_announced = False
        while reconnects <= MAX_RECONNECTS:
            self._require_active_challenge()
            connection = await self.websocket_transport.connect(
                endpoint=gateway.url, open_timeout_seconds=10.0
            )
            try:
                heartbeat = await self._authenticate(connection, token.value, session_id, sequence)
                loop = asyncio.get_running_loop()
                next_heartbeat = loop.time() + heartbeat / 1000
                while True:
                    remaining = self._require_active_challenge()
                    heartbeat_wait = next_heartbeat - loop.time()
                    if heartbeat_wait <= 0:
                        await connection.send({"op": 1, "d": sequence})
                        next_heartbeat = loop.time() + heartbeat / 1000
                        continue
                    timeout = min(RECEIVE_TIMEOUT_SECONDS, heartbeat_wait, remaining)
                    try:
                        frame = dict(await asyncio.wait_for(connection.receive(), timeout))
                    except TimeoutError:
                        self._require_active_challenge()
                        await connection.send({"op": 1, "d": sequence})
                        next_heartbeat = loop.time() + heartbeat / 1000
                        continue
                    if loop.time() >= next_heartbeat:
                        await connection.send({"op": 1, "d": sequence})
                        next_heartbeat = loop.time() + heartbeat / 1000
                    value = frame.get("s")
                    if isinstance(value, int) and not isinstance(value, bool):
                        sequence = value
                    if frame.get("op") in {7, 9}:
                        raise QQTransportError("pairing_gateway_reconnect_requested")
                    if frame.get("op") != 0:
                        continue
                    if frame.get("t") == "READY":
                        data = frame.get("d")
                        ready = data.get("session_id") if isinstance(data, dict) else None
                        if not isinstance(ready, str) or not ready:
                            raise QQTransportError("pairing_gateway_ready_invalid")
                        session_id = ready
                        if not challenge_announced:
                            if on_listening is not None:
                                on_listening(self.challenge_text)
                            challenge_announced = True
                        continue
                    if frame.get("t") != "GROUP_AT_MESSAGE_CREATE":
                        rejected += 1
                        continue
                    observed += 1
                    try:
                        completion = self.controller.accept(frame, session_id=session_id)
                    except (QQPairingEventRejected, QQPairingJournalError):
                        rejected += 1
                        continue
                    return build_pairing_report(
                        completion,
                        mode="qq-sandbox-live" if self.evidence_mode == "live" else "offline-fake",
                        observed=observed,
                        rejected=rejected,
                        contract_root=self.contract_root,
                    )
            except QQTransportError as error:
                if error.reason_code == "pairing_challenge_expired":
                    raise
                reconnects += 1
                if reconnects > MAX_RECONNECTS:
                    raise QQTransportError("pairing_gateway_reconnect_exhausted")
            finally:
                await connection.close()
        raise QQTransportError("pairing_gateway_reconnect_exhausted")


def build_real_qq_pairing_runner(
    *,
    config: QQGroupPairingConfig,
    contract_root: Path,
    token_factory: Callable[[], str] | None = None,
) -> QQGroupPairingRunner:
    client = BoundedQQHTTPClient()
    journal = SQLiteQQPairingJournal(config.store_path, contract_root=contract_root)
    journal.purge_expired()
    challenge = create_pairing_challenge(
        config, token_factory=token_factory, contract_root=contract_root
    )
    controller = QQGroupPairingController(config, journal, challenge)
    return QQGroupPairingRunner(
        config=config,
        controller=controller,
        token_transport=RealQQTokenTransport(client),
        gateway_transport=RealQQGatewayTransport(client),
        websocket_transport=RealQQWebSocketTransport(),
        contract_root=contract_root,
        evidence_mode="live",
    )
