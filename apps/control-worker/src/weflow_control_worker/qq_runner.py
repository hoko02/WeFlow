"""Bounded QQ sandbox WebSocket session for the explicit live acceptance command."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weflow_control_kernel.ledger import IntakeRejected, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQAcknowledgementController,
    QQEventRejected,
    QQSandboxConfig,
    QQSandboxIntakeService,
    QQTransportError,
    SQLiteQQSandboxJournal,
)
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
    RealQQPassiveAcknowledgementTransport,
    RealQQTokenTransport,
    RealQQWebSocketTransport,
)

MAX_RECONNECTS = 3
OPEN_TIMEOUT_SECONDS = 10.0
RECEIVE_TIMEOUT_SECONDS = 60.0
MIN_HEARTBEAT_MILLISECONDS = 1_000
MAX_HEARTBEAT_MILLISECONDS = 120_000


@dataclass(frozen=True)
class QQGatewayRunResult:
    report: dict[str, Any]


class QQGatewayRunner:
    def __init__(
        self,
        *,
        config: QQSandboxConfig,
        token_transport: QQTokenTransport,
        gateway_transport: QQGatewayTransport,
        websocket_transport: QQWebSocketTransport,
        ledger: SQLiteCaseLedger,
        journal: SQLiteQQSandboxJournal,
        passive_transport_factory: Any,
        contract_root: Path,
        evidence_mode: str = "fake",
        monotonic_clock: Callable[[], float] = time.monotonic,
        verify_event_dedup: bool = False,
    ) -> None:
        self._config = config
        self._token_transport = token_transport
        self._gateway_transport = gateway_transport
        self._websocket_transport = websocket_transport
        self._ledger = ledger
        self._journal = journal
        self._passive_transport_factory = passive_transport_factory
        self._contract_root = contract_root
        self._monotonic = monotonic_clock
        self._verify_event_dedup = verify_event_dedup
        if evidence_mode not in {"fake", "live"}:
            raise ValueError("qq_evidence_mode_invalid")
        self._evidence_mode = evidence_mode
        if evidence_mode == "live" and not (
            isinstance(token_transport, RealQQTokenTransport)
            and isinstance(gateway_transport, RealQQGatewayTransport)
            and isinstance(websocket_transport, RealQQWebSocketTransport)
        ):
            raise ValueError("qq_live_evidence_requires_real_adapters")

    @staticmethod
    def _sequence(frame: dict[str, Any]) -> int | None:
        value = frame.get("s")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def _safe_report(
        self,
        *,
        case_id: str,
        intake_disposition: str,
        acknowledgement: Mapping[str, Any],
        rejected_events: int,
        reconnects: int,
        gateway_event_observed_this_run: bool,
        deduplication_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        counts = self._journal.safe_counts(self._config.tenant_id)
        completed = acknowledgement["status"] == "completed"
        deduplication_verified = (
            deduplication_evidence is None
            or deduplication_evidence.get("same_event_deduplication_verified") is True
        )
        live_evidence = self._evidence_mode == "live"
        return {
            "report_type": (
                "weflow-qq-sandbox-live-acceptance.v1"
                if live_evidence
                else "weflow-qq-sandbox-fake-gateway-run.v1"
            ),
            "accepted": completed and deduplication_verified,
            "mode": "qq-sandbox-live" if live_evidence else "offline-fake-transport",
            "fake_transport_verified": not live_evidence,
            "qq_sandbox_live_verified": live_evidence and completed,
            "customer_receipt_verified": False,
            "case_completion": False,
            "issue_resolution": False,
            "production_ready": False,
            "real_external_write": live_evidence,
            "network_required": live_evidence,
            "credentials_required": live_evidence,
            "model_invocation": False,
            "handler_approval": False,
            "final_delivery": False,
            "privacy": {
                "raw_message_persisted": False,
                "transcript_persisted": False,
                "credential_persisted": False,
                "unrestricted_provider_response_persisted": False,
            },
            "external_write_kind": (
                "fixed-qq-passive-acknowledgement"
                if live_evidence
                else "fake-fixed-qq-passive-acknowledgement"
            ),
            "case_id": case_id,
            "intake_disposition": intake_disposition,
            "acknowledgement_status": acknowledgement["status"],
            "gateway_event_observed_this_run": gateway_event_observed_this_run,
            "recovery_attempted": intake_disposition == "recovered_pending_intent",
            "rejected_event_count": rejected_events,
            "reconnect_count": reconnects,
            **counts,
            **({} if deduplication_evidence is None else dict(deduplication_evidence)),
        }

    async def _authenticate(
        self,
        connection: QQWebSocketConnection,
        *,
        access_token: str,
        session_id: str | None,
        sequence: int | None,
    ) -> int:
        hello = dict(await asyncio.wait_for(connection.receive(), RECEIVE_TIMEOUT_SECONDS))
        data = hello.get("d")
        interval = data.get("heartbeat_interval") if isinstance(data, dict) else None
        if hello.get("op") != 10 or not isinstance(interval, int):
            raise QQTransportError("qq_gateway_hello_invalid")
        if interval < MIN_HEARTBEAT_MILLISECONDS or interval > MAX_HEARTBEAT_MILLISECONDS:
            raise QQTransportError("qq_gateway_heartbeat_invalid")
        token = f"QQBot {access_token}"
        if session_id is not None and sequence is not None:
            await connection.send(
                {
                    "op": 6,
                    "d": {"token": token, "session_id": session_id, "seq": sequence},
                }
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
                            "$browser": "weflow",
                            "$device": "weflow",
                        },
                    },
                }
            )
        return interval

    async def run_one(self) -> QQGatewayRunResult:
        def load_transport_context():
            current_token = self._token_transport.fetch(
                app_id=self._config.app_id,
                client_secret=self._config.client_secret,
            )
            current_gateway = self._gateway_transport.fetch(access_token=current_token.value)
            current_passive = self._passive_transport_factory(current_token.value)
            if self._evidence_mode == "live" and not isinstance(
                current_passive, RealQQPassiveAcknowledgementTransport
            ):
                raise ValueError("qq_live_evidence_requires_real_adapters")
            current_controller = QQAcknowledgementController(
                self._journal, current_passive, self._config
            )
            refresh_at = self._monotonic() + max(1, current_token.expires_in_seconds - 60)
            return current_token, current_gateway, current_controller, refresh_at

        token, gateway, controller, token_refresh_at = load_transport_context()
        service = QQSandboxIntakeService(
            self._ledger,
            self._journal,
            self._config,
            contract_root=self._contract_root,
        )
        baseline_ledger_counts = self._ledger.source_counts(self._config.tenant_id)
        baseline_journal_counts = self._journal.safe_counts(self._config.tenant_id)
        recoverable = self._journal.recoverable_intent_ids(self._config.tenant_id)
        if recoverable and self._verify_event_dedup:
            raise QQTransportError("qq_live_event_dedup_requires_new_event")
        if recoverable:
            recovered_intent = self._journal.get_intent(self._config.tenant_id, recoverable[0])
            recovered_acknowledgement = controller.process(recoverable[0])
            return QQGatewayRunResult(
                self._safe_report(
                    case_id=str(recovered_intent["case_id"]),
                    intake_disposition="recovered_pending_intent",
                    acknowledgement=recovered_acknowledgement,
                    rejected_events=0,
                    reconnects=0,
                    gateway_event_observed_this_run=False,
                )
            )
        session_id: str | None = None
        latest_sequence: int | None = None
        rejected_events = 0
        reconnects = 0
        while reconnects <= MAX_RECONNECTS:
            if self._monotonic() >= token_refresh_at:
                token, gateway, controller, token_refresh_at = load_transport_context()
            connection = await self._websocket_transport.connect(
                endpoint=gateway.url,
                open_timeout_seconds=OPEN_TIMEOUT_SECONDS,
            )
            try:
                heartbeat_ms = await self._authenticate(
                    connection,
                    access_token=token.value,
                    session_id=session_id,
                    sequence=latest_sequence,
                )
                loop = asyncio.get_running_loop()
                next_heartbeat = loop.time() + heartbeat_ms / 1000
                while True:
                    timeout = max(0.01, min(RECEIVE_TIMEOUT_SECONDS, next_heartbeat - loop.time()))
                    try:
                        frame = dict(await asyncio.wait_for(connection.receive(), timeout))
                    except TimeoutError:
                        await connection.send({"op": 1, "d": latest_sequence})
                        next_heartbeat = loop.time() + heartbeat_ms / 1000
                        continue
                    if loop.time() >= next_heartbeat:
                        await connection.send({"op": 1, "d": latest_sequence})
                        next_heartbeat = loop.time() + heartbeat_ms / 1000
                    opcode = frame.get("op")
                    sequence = self._sequence(frame)
                    if sequence is not None:
                        latest_sequence = sequence
                    if opcode == 7:
                        raise QQTransportError("qq_gateway_reconnect_requested")
                    if opcode == 9:
                        session_id = None
                        latest_sequence = None
                        raise QQTransportError("qq_gateway_session_invalid")
                    if opcode != 0:
                        continue
                    event_type = frame.get("t")
                    data = frame.get("d")
                    if event_type == "READY":
                        ready_session = data.get("session_id") if isinstance(data, dict) else None
                        if not isinstance(ready_session, str) or not ready_session:
                            raise QQTransportError("qq_gateway_ready_invalid")
                        session_id = ready_session
                        if sequence is not None:
                            self._journal.record_cursor(
                                self._config,
                                sequence=sequence,
                                status="identified",
                                session_id=session_id,
                            )
                        continue
                    if event_type == "RESUMED":
                        if sequence is not None:
                            self._journal.record_cursor(
                                self._config,
                                sequence=sequence,
                                status="resuming",
                                session_id=session_id,
                            )
                        continue
                    if event_type != "GROUP_AT_MESSAGE_CREATE":
                        rejected_events += 1
                        if sequence is not None:
                            self._journal.record_cursor(
                                self._config,
                                sequence=sequence,
                                status="identified",
                                session_id=session_id,
                            )
                        continue
                    try:
                        accepted = service.accept(frame, session_id=session_id)
                    except (QQEventRejected, IntakeRejected) as error:
                        if str(error) in {
                            "qq_gateway_sequence_gap",
                            "qq_gateway_sequence_out_of_order",
                            "inbound_out_of_order",
                        }:
                            raise QQTransportError("qq_gateway_reconciliation_required") from error
                        rejected_events += 1
                        if sequence is not None:
                            self._journal.record_cursor(
                                self._config,
                                sequence=sequence,
                                status="identified",
                                session_id=session_id,
                            )
                        continue
                    if self._monotonic() >= token_refresh_at:
                        token, gateway, controller, token_refresh_at = load_transport_context()
                    acknowledgement = controller.process(str(accepted.intent["intent_id"]))
                    deduplication_evidence: dict[str, Any] | None = None
                    if self._verify_event_dedup:
                        counts_before_replay = self._ledger.source_counts(self._config.tenant_id)
                        journal_before_replay = self._journal.safe_counts(self._config.tenant_id)
                        replayed = service.accept(frame, session_id=session_id)
                        replayed_acknowledgement = controller.process(
                            str(replayed.intent["intent_id"])
                        )
                        counts_after_replay = self._ledger.source_counts(self._config.tenant_id)
                        journal_after_replay = self._journal.safe_counts(self._config.tenant_id)
                        same_case = replayed.intake.case_id == accepted.intake.case_id
                        same_intent = replayed.intent["intent_id"] == accepted.intent["intent_id"]
                        counts_unchanged = (
                            counts_after_replay == counts_before_replay
                            and journal_after_replay == journal_before_replay
                        )
                        verified = (
                            replayed.intake.disposition == "deduplicated"
                            and same_case
                            and same_intent
                            and replayed_acknowledgement["status"] == "completed"
                            and counts_unchanged
                        )
                        deduplication_evidence = {
                            "deduplication_probe_mode": "same-observed-event-in-memory",
                            "same_event_deduplication_verified": verified,
                            "duplicate_event_count": (
                                1 if replayed.intake.disposition == "deduplicated" else 0
                            ),
                            "same_case_reused": same_case,
                            "same_acknowledgement_intent_reused": same_intent,
                            "second_qq_write_attempted": False,
                            "second_logical_acknowledgement": not counts_unchanged,
                            "case_count_delta": (
                                counts_before_replay["cases"] - baseline_ledger_counts["cases"]
                            ),
                            "acknowledgement_intent_count_delta": (
                                journal_before_replay["acknowledgement_intent_count"]
                                - baseline_journal_counts["acknowledgement_intent_count"]
                            ),
                            "acknowledgement_observation_count_delta": (
                                journal_before_replay["acknowledgement_observation_count"]
                                - baseline_journal_counts["acknowledgement_observation_count"]
                            ),
                            "acknowledgement_completion_count_delta": (
                                journal_before_replay["acknowledgement_completion_count"]
                                - baseline_journal_counts["acknowledgement_completion_count"]
                            ),
                        }
                    return QQGatewayRunResult(
                        self._safe_report(
                            case_id=accepted.intake.case_id,
                            intake_disposition=accepted.intake.disposition,
                            acknowledgement=acknowledgement,
                            rejected_events=rejected_events,
                            reconnects=reconnects,
                            gateway_event_observed_this_run=True,
                            deduplication_evidence=deduplication_evidence,
                        )
                    )
            except QQTransportError:
                reconnects += 1
                cursor = self._journal.get_cursor(self._config)
                if cursor is not None:
                    self._journal.record_cursor(
                        self._config,
                        sequence=int(cursor["last_contiguous_sequence"]),
                        status="disconnected",
                        session_id=session_id,
                    )
                if reconnects > MAX_RECONNECTS:
                    raise QQTransportError("qq_gateway_reconnect_exhausted")
            finally:
                await connection.close()
        raise QQTransportError("qq_gateway_reconnect_exhausted")


def build_real_qq_gateway_runner(
    *,
    config: QQSandboxConfig,
    store_path: Path,
    contract_root: Path,
    verify_event_dedup: bool = False,
) -> QQGatewayRunner:
    client = BoundedQQHTTPClient()
    ledger = SQLiteCaseLedger(store_path, contract_root=contract_root)
    journal = SQLiteQQSandboxJournal(store_path, contract_root=contract_root)
    journal.purge_expired_locators()
    return QQGatewayRunner(
        config=config,
        token_transport=RealQQTokenTransport(client),
        gateway_transport=RealQQGatewayTransport(client),
        websocket_transport=RealQQWebSocketTransport(),
        ledger=ledger,
        journal=journal,
        passive_transport_factory=lambda access_token: RealQQPassiveAcknowledgementTransport(
            client, config, access_token
        ),
        contract_root=contract_root,
        evidence_mode="live",
        verify_event_dedup=verify_event_dedup,
    )
