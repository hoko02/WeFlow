from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from weflow_control_kernel.ledger import SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import QQSandboxConfig, SQLiteQQSandboxJournal
from weflow_control_kernel.qq_transport import (
    FakeQQGatewayTransport,
    FakeQQPassiveAcknowledgementTransport,
    FakeQQWebSocketTransport,
    QQAccessToken,
)
from weflow_control_worker.qq_runner import QQGatewayRunner

ROOT = Path(__file__).resolve().parents[2]


class ExpiringTokenTransport:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, *, app_id: str, client_secret: str) -> QQAccessToken:
        assert app_id and client_secret
        self.calls += 1
        return QQAccessToken(f"fake-token-{self.calls}", 61)


def test_runner_refreshes_token_before_passive_send(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    frames = [
        {"op": 10, "d": {"heartbeat_interval": 45_000}},
        {"op": 0, "s": 1, "t": "READY", "d": {"session_id": "memory-session"}},
        {
            "op": 0,
            "s": 2,
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "fake-message",
                "group_openid": "fake-group",
                "author": {"member_openid": "fake-member"},
                "content": "广告系统出现了API 503错误",
                "timestamp": now,
            },
        },
    ]
    monotonic_values = iter((0.0, 0.0, 2.0, 2.0))
    token_transport = ExpiringTokenTransport()
    gateway_transport = FakeQQGatewayTransport()
    used_tokens: list[str] = []
    passive = FakeQQPassiveAcknowledgementTransport("fake-group")

    def passive_factory(value: str):
        used_tokens.append(value)
        return passive

    path = tmp_path / "qq.sqlite3"
    runner = QQGatewayRunner(
        config=QQSandboxConfig(
            "fake-app", "not-a-real-secret", "fake-group", "fake-tenant", "fake-salt"
        ),
        token_transport=token_transport,
        gateway_transport=gateway_transport,
        websocket_transport=FakeQQWebSocketTransport(frames),
        ledger=SQLiteCaseLedger(path, contract_root=ROOT),
        journal=SQLiteQQSandboxJournal(path, contract_root=ROOT),
        passive_transport_factory=passive_factory,
        contract_root=ROOT,
        monotonic_clock=lambda: next(monotonic_values),
    )

    report = asyncio.run(runner.run_one()).report

    assert report["accepted"] is True
    assert token_transport.calls == 2
    assert gateway_transport.calls == 2
    assert used_tokens == ["fake-token-1", "fake-token-2"]
    assert passive.send_calls == 1
