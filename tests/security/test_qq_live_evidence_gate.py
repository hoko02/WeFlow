from __future__ import annotations

from pathlib import Path

import pytest
from weflow_control_kernel.ledger import SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import QQSandboxConfig, SQLiteQQSandboxJournal
from weflow_control_kernel.qq_transport import (
    FakeQQGatewayTransport,
    FakeQQPassiveAcknowledgementTransport,
    FakeQQTokenTransport,
    FakeQQWebSocketTransport,
)
from weflow_control_worker.qq_runner import QQGatewayRunner

ROOT = Path(__file__).resolve().parents[2]


def test_fake_transports_cannot_select_live_evidence_mode(tmp_path: Path) -> None:
    config = QQSandboxConfig(
        app_id="fake-app",
        client_secret="fake-secret",
        group_openid="fake-group",
        tenant_id="fake-tenant",
        identity_salt="fake-salt",
    )
    path = tmp_path / "qq.sqlite3"
    with pytest.raises(ValueError, match="qq_live_evidence_requires_real_adapters"):
        QQGatewayRunner(
            config=config,
            token_transport=FakeQQTokenTransport(),
            gateway_transport=FakeQQGatewayTransport(),
            websocket_transport=FakeQQWebSocketTransport([]),
            ledger=SQLiteCaseLedger(path, contract_root=ROOT),
            journal=SQLiteQQSandboxJournal(path, contract_root=ROOT),
            passive_transport_factory=lambda _: FakeQQPassiveAcknowledgementTransport(
                "fake-group"
            ),
            contract_root=ROOT,
            evidence_mode="live",
        )
