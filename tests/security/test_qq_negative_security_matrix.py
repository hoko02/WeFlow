from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQAcknowledgementController,
    QQEventRejected,
    QQJournalError,
    QQSandboxConfig,
    QQSandboxIntakeService,
    QQTransportError,
    SQLiteQQSandboxJournal,
    normalize_qq_group_at_event,
)
from weflow_control_kernel.qq_transport import FakeQQPassiveAcknowledgementTransport
from weflow_control_worker.qq_adapter import (
    RealQQPassiveAcknowledgementTransport,
    _HTTPResult,
)

ROOT = Path(__file__).resolve().parents[2]
DEV_PATH = ROOT / "scripts" / "dev.py"
NOW = datetime(2026, 8, 10, 0, 0, 1, tzinfo=UTC)


def config() -> QQSandboxConfig:
    return QQSandboxConfig(
        app_id="qq-app-sandbox",
        client_secret="not-a-real-secret",
        group_openid="qq-group-sandbox",
        tenant_id="tenant-alpha",
        identity_salt="process-only-salt",
    )


def event() -> dict[str, object]:
    return {
        "op": 0,
        "s": 1,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "qq-source-message",
            "group_openid": "qq-group-sandbox",
            "author": {"member_openid": "qq-private-member"},
            "content": "广告系统出现了API 503错误",
            "timestamp": "2026-08-10T00:00:00Z",
        },
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("tenant_id", "tenant-forged"),
        ("role", "administrator"),
        ("destination", "foreign-group"),
        ("message_body", "arbitrary final reply"),
        ("client_secret", "credential-in-payload"),
        ("access_token", "access-token-in-payload"),
    ),
)
def test_forged_authority_content_and_credentials_are_rejected_without_echo(
    field: str, value: str
) -> None:
    raw = event()
    raw[field] = value
    with pytest.raises(QQEventRejected, match="qq_event_authority_field_forbidden") as caught:
        normalize_qq_group_at_event(raw, config(), received_at=NOW, contract_root=ROOT)
    assert value not in str(caught.value)


class NoCallHTTPClient:
    def __init__(self) -> None:
        self.calls = 0

    def request(self, *_: object, **__: object) -> _HTTPResult:
        self.calls += 1
        return _HTTPResult(200, {"id": "should-not-be-used"})


@pytest.mark.parametrize(
    "override",
    (
        {"group_openid": "foreign-group"},
        {"reply_msg_seq": 99},
        {"content": "任意 Markdown、附件或最终答复"},
        {"source_message_id": "bad/source/id"},
    ),
)
def test_real_executor_rejects_arbitrary_write_before_http(override: dict[str, object]) -> None:
    client = NoCallHTTPClient()
    transport = RealQQPassiveAcknowledgementTransport(client, config(), "access-token")
    request = {
        "group_openid": "qq-group-sandbox",
        "source_message_id": "qq-source-message",
        "reply_msg_seq": 1,
        "idempotency_key": "server-owned",
        "content": "已受理，工单编号：case-safe。当前仅确认已进入处理流程，不代表问题已解决。",
        **override,
    }
    with pytest.raises(QQTransportError):
        transport.send_fixed_acknowledgement(**request)
    assert client.calls == 0


def test_foreign_tenant_and_revoked_capability_cannot_contact_transport(tmp_path: Path) -> None:
    path = tmp_path / "qq.sqlite3"
    clock = FixedClock(NOW)
    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=ROOT)
    accepted = QQSandboxIntakeService(
        ledger, journal, config(), clock=clock, contract_root=ROOT
    ).accept(event())
    transport = FakeQQPassiveAcknowledgementTransport("qq-group-sandbox")

    revoked = QQAcknowledgementController(journal, transport, config(), clock=clock).process(
        str(accepted.intent["intent_id"]), capability_active=False
    )
    assert revoked["status"] == "NEEDS_RECONCILIATION"
    assert transport.reconcile_calls == transport.send_calls == 0

    foreign = QQSandboxConfig(
        app_id="qq-app-sandbox",
        client_secret="not-a-real-secret",
        group_openid="qq-group-sandbox",
        tenant_id="tenant-foreign",
        identity_salt="process-only-salt",
    )
    with pytest.raises(QQJournalError, match="qq_acknowledgement_intent_not_found"):
        QQAcknowledgementController(journal, transport, foreign, clock=clock).process(
            str(accepted.intent["intent_id"])
        )
    assert transport.reconcile_calls == transport.send_calls == 0


def _load_dev_module():
    spec = importlib.util.spec_from_file_location("weflow_dev_qq_matrix", DEV_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dedicated_command_denies_every_other_external_write_executor(monkeypatch, capsys) -> None:
    dev = _load_dev_module()
    environment = {
        "WEFLOW_QQ_APP_ID": "qq-app-sandbox",
        "WEFLOW_QQ_CLIENT_SECRET": "not-a-real-secret",
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID": "qq-group-sandbox",
        "WEFLOW_QQ_TENANT_ID": "tenant-alpha",
        "WEFLOW_QQ_IDENTITY_SALT": "process-only-salt",
        "WEFLOW_EXTERNAL_WRITE_ENABLED": "true",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert dev.main(["qq-sandbox-intake-ack", "--confirm-live-qq"]) == 2
    output = capsys.readouterr().out
    assert "qq_capability_scope_denied" in output
    assert '"network_contacted": false' in output.lower()
    assert "not-a-real-secret" not in output
