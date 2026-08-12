"""Narrow QQ transport contracts and deterministic offline fakes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .qq_sandbox import QQSendOutcome, QQTransportError


@dataclass(frozen=True)
class QQAccessToken:
    """Process-memory token value; callers must never serialize this object."""

    value: str
    expires_in_seconds: int


@dataclass(frozen=True)
class QQGatewayEndpoint:
    """One bounded WebSocket gateway result."""

    url: str


class QQTokenTransport(Protocol):
    def fetch(self, *, app_id: str, client_secret: str) -> QQAccessToken: ...


class QQGatewayTransport(Protocol):
    def fetch(self, *, access_token: str) -> QQGatewayEndpoint: ...


class QQWebSocketConnection(Protocol):
    async def receive(self) -> Mapping[str, Any]: ...

    async def send(self, payload: Mapping[str, Any]) -> None: ...

    async def close(self) -> None: ...


class QQWebSocketTransport(Protocol):
    async def connect(
        self, *, endpoint: str, open_timeout_seconds: float
    ) -> QQWebSocketConnection: ...


@dataclass
class FakeQQTokenTransport:
    token: str = "fake-qq-access-token"
    expires_in_seconds: int = 7200
    calls: int = 0

    def fetch(self, *, app_id: str, client_secret: str) -> QQAccessToken:
        if not app_id or not client_secret:
            raise QQTransportError("qq_fake_token_configuration_missing")
        self.calls += 1
        return QQAccessToken(self.token, self.expires_in_seconds)


@dataclass
class FakeQQGatewayTransport:
    endpoint: str = "wss://qq.invalid/offline-fake"
    calls: int = 0

    def fetch(self, *, access_token: str) -> QQGatewayEndpoint:
        if not access_token:
            raise QQTransportError("qq_fake_gateway_token_missing")
        self.calls += 1
        return QQGatewayEndpoint(self.endpoint)


@dataclass
class FakeQQWebSocketConnection:
    inbound: list[Mapping[str, Any]]
    sent: list[Mapping[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def receive(self) -> Mapping[str, Any]:
        if self.closed or not self.inbound:
            raise QQTransportError("qq_fake_websocket_exhausted")
        return self.inbound.pop(0)

    async def send(self, payload: Mapping[str, Any]) -> None:
        if self.closed:
            raise QQTransportError("qq_fake_websocket_closed")
        self.sent.append(dict(payload))

    async def close(self) -> None:
        self.closed = True


@dataclass
class FakeQQWebSocketTransport:
    frames: Sequence[Mapping[str, Any]]
    connections: list[FakeQQWebSocketConnection] = field(default_factory=list)

    async def connect(
        self, *, endpoint: str, open_timeout_seconds: float
    ) -> FakeQQWebSocketConnection:
        if not endpoint or open_timeout_seconds <= 0:
            raise QQTransportError("qq_fake_websocket_configuration_invalid")
        connection = FakeQQWebSocketConnection([dict(frame) for frame in self.frames])
        self.connections.append(connection)
        return connection


@dataclass
class FakeQQPassiveAcknowledgementTransport:
    """Provider-state fake keyed by QQ's source-msg-id plus deterministic msg-seq."""

    configured_group_openid: str
    send_status: str = "accepted"
    reconcile_status: str = "absent"
    lose_first_response: bool = False
    effects: dict[tuple[str, str, int], str] = field(default_factory=dict)
    send_calls: int = 0
    reconcile_calls: int = 0
    contents: list[str] = field(default_factory=list)

    def _validate(self, group_openid: str, reply_msg_seq: int) -> None:
        if group_openid != self.configured_group_openid:
            raise QQTransportError("qq_passive_destination_denied")
        if reply_msg_seq != 1:
            raise QQTransportError("qq_passive_sequence_denied")

    def reconcile(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        idempotency_key: str,
    ) -> QQSendOutcome:
        del idempotency_key
        self._validate(group_openid, reply_msg_seq)
        self.reconcile_calls += 1
        key = (group_openid, source_message_id, reply_msg_seq)
        if key in self.effects:
            return QQSendOutcome("present", "qq_fake_provider_present", self.effects[key])
        return QQSendOutcome(self.reconcile_status, f"qq_fake_provider_{self.reconcile_status}")

    def send_fixed_acknowledgement(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        idempotency_key: str,
        content: str,
    ) -> QQSendOutcome:
        del idempotency_key
        self._validate(group_openid, reply_msg_seq)
        self.send_calls += 1
        self.contents.append(content)
        key = (group_openid, source_message_id, reply_msg_seq)
        provider_message_id = self.effects.setdefault(key, "fake-qq-provider-message")
        if self.lose_first_response:
            self.lose_first_response = False
            raise QQTransportError("qq_provider_outcome_unknown")
        return QQSendOutcome(
            self.send_status,
            f"qq_fake_provider_{self.send_status}",
            provider_message_id
            if self.send_status in {"accepted", "present", "duplicate"}
            else None,
        )
