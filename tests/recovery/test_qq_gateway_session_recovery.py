from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weflow_control_kernel.ledger import SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import QQSandboxConfig, SQLiteQQSandboxJournal
from weflow_control_kernel.qq_transport import (
    FakeQQGatewayTransport,
    FakeQQPassiveAcknowledgementTransport,
    FakeQQTokenTransport,
    FakeQQWebSocketConnection,
)
from weflow_control_worker.qq_runner import QQGatewayRunner

ROOT = Path(__file__).resolve().parents[2]


def config() -> QQSandboxConfig:
    return QQSandboxConfig(
        app_id="offline-app",
        client_secret="not-a-real-secret",
        group_openid="offline-group",
        tenant_id="offline-tenant",
        identity_salt="offline-salt",
    )


def event(sequence: int) -> dict[str, Any]:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "op": 0,
        "s": sequence,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "offline-source-message",
            "group_openid": "offline-group",
            "author": {"member_openid": "offline-member"},
            "content": "广告系统出现了API 503错误",
            "timestamp": timestamp,
        },
    }


class ScriptedWebSocketTransport:
    def __init__(self, scripts: list[list[dict[str, Any]]]) -> None:
        self.scripts = scripts
        self.connections: list[FakeQQWebSocketConnection] = []

    async def connect(
        self, *, endpoint: str, open_timeout_seconds: float
    ) -> FakeQQWebSocketConnection:
        assert endpoint and open_timeout_seconds > 0
        connection = FakeQQWebSocketConnection(self.scripts.pop(0))
        self.connections.append(connection)
        return connection


def test_gateway_reconnect_uses_resume_cursor_and_replays_one_case(tmp_path: Path) -> None:
    websocket = ScriptedWebSocketTransport(
        [
            [
                {"op": 10, "d": {"heartbeat_interval": 45_000}},
                {"op": 0, "s": 1, "t": "READY", "d": {"session_id": "memory-session"}},
                {"op": 7},
            ],
            [
                {"op": 10, "d": {"heartbeat_interval": 45_000}},
                {"op": 0, "s": 2, "t": "RESUMED", "d": ""},
                event(3),
            ],
        ]
    )
    path = tmp_path / "qq.sqlite3"
    ledger = SQLiteCaseLedger(path, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, contract_root=ROOT)
    passive = FakeQQPassiveAcknowledgementTransport("offline-group")
    runner = QQGatewayRunner(
        config=config(),
        token_transport=FakeQQTokenTransport(),
        gateway_transport=FakeQQGatewayTransport(),
        websocket_transport=websocket,
        ledger=ledger,
        journal=journal,
        passive_transport_factory=lambda _: passive,
        contract_root=ROOT,
    )

    report = asyncio.run(runner.run_one()).report

    assert report["accepted"] is True
    assert report["reconnect_count"] == 1
    assert websocket.connections[0].sent[0]["op"] == 2
    assert websocket.connections[1].sent[0] == {
        "op": 6,
        "d": {
            "token": "QQBot fake-qq-access-token",
            "session_id": "memory-session",
            "seq": 1,
        },
    }
    assert ledger.source_counts("offline-tenant")["cases"] == 1
    assert journal.safe_counts("offline-tenant")["acknowledgement_intent_count"] == 1


class HeartbeatConnection(FakeQQWebSocketConnection):
    def __init__(self) -> None:
        super().__init__(
            [
                {"op": 10, "d": {"heartbeat_interval": 1_000}},
                {"op": 0, "s": 1, "t": "READY", "d": {"session_id": "heartbeat-session"}},
            ]
        )
        self.receive_calls = 0

    async def receive(self):
        self.receive_calls += 1
        if self.receive_calls == 3:
            await asyncio.sleep(2)
        if self.receive_calls == 4:
            return event(2)
        return await super().receive()


class HeartbeatTransport:
    def __init__(self) -> None:
        self.connection = HeartbeatConnection()

    async def connect(self, *, endpoint: str, open_timeout_seconds: float):
        assert endpoint and open_timeout_seconds > 0
        return self.connection


def test_gateway_emits_qq_heartbeat_with_latest_sequence(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.sqlite3"
    transport = HeartbeatTransport()
    passive = FakeQQPassiveAcknowledgementTransport("offline-group")
    runner = QQGatewayRunner(
        config=config(),
        token_transport=FakeQQTokenTransport(),
        gateway_transport=FakeQQGatewayTransport(),
        websocket_transport=transport,
        ledger=SQLiteCaseLedger(path, contract_root=ROOT),
        journal=SQLiteQQSandboxJournal(path, contract_root=ROOT),
        passive_transport_factory=lambda _: passive,
        contract_root=ROOT,
    )

    report = asyncio.run(runner.run_one()).report

    assert report["accepted"] is True
    assert {"op": 1, "d": 1} in transport.connection.sent
