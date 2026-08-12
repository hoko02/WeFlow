from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQ_ACK_TEMPLATE,
    QQAcknowledgementController,
    QQActivationDenied,
    QQEventRejected,
    QQPassiveAcknowledgementTransport,
    QQSandboxConfig,
    QQSandboxIntakeService,
    QQSendOutcome,
    QQTransportError,
    SQLiteQQSandboxJournal,
    normalize_qq_group_at_event,
    reject_qq_configuration_for_ordinary_command,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 10, 0, 0, 1, tzinfo=UTC)


def config() -> QQSandboxConfig:
    return QQSandboxConfig(
        app_id="qq-app-sandbox",
        client_secret="not-a-real-secret",
        group_openid="qq-group-sandbox",
        tenant_id="tenant-alpha",
        identity_salt="process-only-identity-salt",
    )


def raw_event(
    *,
    message_id: str = "qq-message-001",
    sequence: int = 42,
    content: str = "@机器人 广告系统出现了API 503错误",
    group_openid: str = "qq-group-sandbox",
) -> dict[str, object]:
    return {
        "op": 0,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "s": sequence,
        "d": {
            "id": message_id,
            "group_openid": group_openid,
            "author": {"member_openid": "qq-member-customer", "member_role": "2"},
            "content": content,
            "timestamp": "2026-08-10T00:00:00Z",
        },
    }


class FakeQQTransport(QQPassiveAcknowledgementTransport):
    def __init__(
        self,
        *,
        send_status: str = "accepted",
        reconcile_status: str = "absent",
        lose_first_response: bool = False,
    ) -> None:
        self.send_status = send_status
        self.reconcile_status = reconcile_status
        self.lose_first_response = lose_first_response
        self.effects: dict[tuple[str, str, int], str] = {}
        self.send_calls = 0
        self.reconcile_calls = 0
        self.contents: list[str] = []

    def reconcile(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        idempotency_key: str,
    ) -> QQSendOutcome:
        del idempotency_key
        self.reconcile_calls += 1
        key = (group_openid, source_message_id, reply_msg_seq)
        if key in self.effects:
            return QQSendOutcome("present", "provider_present", self.effects[key])
        return QQSendOutcome(self.reconcile_status, f"provider_{self.reconcile_status}")

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
        self.send_calls += 1
        self.contents.append(content)
        key = (group_openid, source_message_id, reply_msg_seq)
        provider_message_id = self.effects.setdefault(key, "qq-provider-message-001")
        if self.lose_first_response:
            self.lose_first_response = False
            raise QQTransportError("qq_provider_outcome_unknown")
        return QQSendOutcome(
            self.send_status,
            f"provider_{self.send_status}",
            provider_message_id
            if self.send_status in {"accepted", "present", "duplicate"}
            else None,
        )


def make_service(tmp_path: Path):
    path = tmp_path / "qq.sqlite3"
    clock = FixedClock(NOW)
    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=ROOT)
    service = QQSandboxIntakeService(
        ledger,
        journal,
        config(),
        clock=clock,
        contract_root=ROOT,
    )
    return path, ledger, journal, service


def test_qq_activation_is_explicit_exact_and_redacted() -> None:
    environment = {
        "WEFLOW_QQ_APP_ID": "qq-app-sandbox",
        "WEFLOW_QQ_CLIENT_SECRET": "not-a-real-secret",
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID": "qq-group-sandbox",
        "WEFLOW_QQ_TENANT_ID": "tenant-alpha",
        "WEFLOW_QQ_IDENTITY_SALT": "process-only-identity-salt",
    }
    with pytest.raises(QQActivationDenied, match="explicit_confirmation_required"):
        QQSandboxConfig.from_environment(confirm_live=False, environ=environment)
    with pytest.raises(QQActivationDenied, match="qq_configuration_missing"):
        QQSandboxConfig.from_environment(confirm_live=True, environ={})
    with pytest.raises(QQActivationDenied, match="qq_capability_scope_denied"):
        QQSandboxConfig.from_environment(
            confirm_live=True,
            environ={**environment, "WEFLOW_QQ_CAPABILITIES": "qq.group_at.read,admin"},
        )
    with pytest.raises(QQActivationDenied, match="qq_configuration_forbidden_for_command"):
        reject_qq_configuration_for_ordinary_command(environment)

    loaded = QQSandboxConfig.from_environment(confirm_live=True, environ=environment)
    readiness = loaded.safe_readiness()
    assert readiness["ready"] is True
    assert readiness["model_enabled"] is False
    assert "process-only" not in str(readiness)
    assert "qq-group-sandbox" not in str(readiness)


def test_qq_normalization_discards_text_and_rejects_unsupported_authority() -> None:
    normalized = normalize_qq_group_at_event(
        raw_event(), config(), received_at=NOW, contract_root=ROOT
    )

    assert normalized["provider"] == "qq-sandbox"
    assert normalized["gateway_sequence"] == 42
    assert normalized["tenant_id"] == "tenant-alpha"
    assert "广告系统" not in str(normalized)
    assert "qq-member-customer" not in str(normalized)
    assert normalized["customer_id"].startswith("qq-customer:")

    with pytest.raises(QQEventRejected, match="qq_group_not_allowlisted"):
        normalize_qq_group_at_event(
            raw_event(group_openid="qq-group-foreign"),
            config(),
            received_at=NOW,
            contract_root=ROOT,
        )
    attachment = raw_event()
    attachment["d"]["attachments"] = [{"url": "blocked"}]  # type: ignore[index]
    with pytest.raises(QQEventRejected, match="qq_attachment_unsupported"):
        normalize_qq_group_at_event(attachment, config(), received_at=NOW, contract_root=ROOT)
    forged = raw_event()
    forged["tenant_id"] = "tenant-foreign"
    with pytest.raises(QQEventRejected, match="qq_event_authority_field_forbidden"):
        normalize_qq_group_at_event(forged, config(), received_at=NOW, contract_root=ROOT)


def test_qq_intake_reuses_atomic_ledger_and_deduplicates_after_restart(tmp_path: Path) -> None:
    path, ledger, journal, service = make_service(tmp_path)

    first = service.accept(raw_event(), session_id="session-001")
    duplicate = service.accept(raw_event(), session_id="session-001")

    assert first.intake.disposition == "accepted"
    assert duplicate.intake.disposition == "deduplicated"
    assert first.intake.case_id == duplicate.intake.case_id
    assert first.intent["intent_id"] == duplicate.intent["intent_id"]
    assert ledger.source_counts("tenant-alpha") == {
        "inbound_receipts": 1,
        "cases": 1,
        "case_revisions": 1,
        "business_events": 3,
        "case_projection": 1,
    }
    assert journal.safe_counts("tenant-alpha") == {
        "gateway_cursor_count": 1,
        "acknowledgement_intent_count": 1,
        "acknowledgement_observation_count": 0,
        "acknowledgement_completion_count": 0,
    }
    projection = ledger.get_case_projection("tenant-alpha", first.intake.case_id)
    assert projection is not None and projection["state"] == "RECEIVED"
    assert [
        event["event_type"]
        for event in ledger.list_case_events("tenant-alpha", first.intake.case_id)
    ] == [
        "inbound.received.v1",
        "case.revision-created.v1",
        "case.state-transitioned.v1",
    ]

    restarted_ledger = SQLiteCaseLedger(path, clock=FixedClock(NOW), contract_root=ROOT)
    restarted_journal = SQLiteQQSandboxJournal(path, clock=FixedClock(NOW), contract_root=ROOT)
    restarted = QQSandboxIntakeService(
        restarted_ledger,
        restarted_journal,
        config(),
        clock=FixedClock(NOW),
        contract_root=ROOT,
    ).accept(raw_event(), session_id="session-002")
    assert restarted.intake.disposition == "deduplicated"
    assert restarted_journal.safe_counts("tenant-alpha")["acknowledgement_intent_count"] == 1


def test_qq_gateway_gap_fails_before_case_or_intent(tmp_path: Path) -> None:
    _, ledger, journal, service = make_service(tmp_path)
    service.accept(raw_event(), session_id="session-001")

    with pytest.raises(QQEventRejected, match="qq_gateway_sequence_gap"):
        service.accept(
            raw_event(message_id="qq-message-002", sequence=44),
            session_id="session-001",
        )

    assert ledger.source_counts("tenant-alpha")["cases"] == 1
    assert journal.safe_counts("tenant-alpha")["acknowledgement_intent_count"] == 1
    assert journal.get_cursor(config())["status"] == "reconciliation_required"


def test_qq_acknowledgement_completes_once_with_fixed_content(tmp_path: Path) -> None:
    _, _, journal, service = make_service(tmp_path)
    accepted = service.accept(raw_event())
    transport = FakeQQTransport()
    controller = QQAcknowledgementController(journal, transport, config(), clock=FixedClock(NOW))

    first = controller.process(str(accepted.intent["intent_id"]))
    duplicate = controller.process(str(accepted.intent["intent_id"]))

    assert first["status"] == duplicate["status"] == "completed"
    assert transport.send_calls == 1
    assert transport.contents == [QQ_ACK_TEMPLATE.format(case_id=accepted.intake.case_id)]
    assert journal.safe_counts("tenant-alpha")["acknowledgement_completion_count"] == 1
    assert first["customer_receipt_verified"] is False
    assert first["case_completion"] is False


def test_qq_lost_response_reconciles_without_second_send(tmp_path: Path) -> None:
    _, _, journal, service = make_service(tmp_path)
    accepted = service.accept(raw_event())
    transport = FakeQQTransport(lose_first_response=True)
    controller = QQAcknowledgementController(journal, transport, config(), clock=FixedClock(NOW))

    unknown = controller.process(str(accepted.intent["intent_id"]))
    recovered = controller.process(str(accepted.intent["intent_id"]))

    assert unknown["status"] == "NEEDS_RECONCILIATION"
    assert recovered["status"] == "completed"
    assert transport.send_calls == 1
    assert transport.reconcile_calls == 2
    assert journal.safe_counts("tenant-alpha")["acknowledgement_observation_count"] == 2
    assert journal.safe_counts("tenant-alpha")["acknowledgement_completion_count"] == 1


def test_qq_unknown_expired_and_unauthorized_never_complete(tmp_path: Path) -> None:
    _, _, journal, service = make_service(tmp_path)
    accepted = service.accept(raw_event())
    unknown_transport = FakeQQTransport(reconcile_status="unknown")
    unknown = QQAcknowledgementController(
        journal, unknown_transport, config(), clock=FixedClock(NOW)
    ).process(str(accepted.intent["intent_id"]))
    assert unknown["status"] == "NEEDS_RECONCILIATION"
    assert unknown_transport.send_calls == 0

    second_path = tmp_path / "expired.sqlite3"
    clock = FixedClock(NOW)
    ledger = SQLiteCaseLedger(second_path, clock=clock, contract_root=ROOT)
    expired_journal = SQLiteQQSandboxJournal(second_path, clock=clock, contract_root=ROOT)
    expired_service = QQSandboxIntakeService(
        ledger, expired_journal, config(), clock=clock, contract_root=ROOT
    )
    expired_intake = expired_service.accept(raw_event())
    no_call_transport = FakeQQTransport()
    expired = QQAcknowledgementController(
        expired_journal,
        no_call_transport,
        config(),
        clock=FixedClock(NOW + timedelta(minutes=6)),
    ).process(str(expired_intake.intent["intent_id"]))
    assert expired["status"] == "expired"
    assert no_call_transport.reconcile_calls == no_call_transport.send_calls == 0

    third_path = tmp_path / "unauthorized.sqlite3"
    third_ledger = SQLiteCaseLedger(third_path, clock=clock, contract_root=ROOT)
    third_journal = SQLiteQQSandboxJournal(third_path, clock=clock, contract_root=ROOT)
    third_intake = QQSandboxIntakeService(
        third_ledger, third_journal, config(), clock=clock, contract_root=ROOT
    ).accept(raw_event())
    unauthorized_transport = FakeQQTransport()
    unauthorized = QQAcknowledgementController(
        third_journal, unauthorized_transport, config(), clock=clock
    ).process(str(third_intake.intent["intent_id"]), capability_active=False)
    assert unauthorized["status"] == "NEEDS_RECONCILIATION"
    assert unauthorized_transport.reconcile_calls == unauthorized_transport.send_calls == 0
    assert third_journal.safe_counts("tenant-alpha")["acknowledgement_completion_count"] == 0
