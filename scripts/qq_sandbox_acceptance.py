"""Deterministic offline acceptance and strict safe-report verifier for QQ stage one."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQAcknowledgementController,
    QQEventRejected,
    QQSandboxConfig,
    QQSandboxIntakeService,
    SQLiteQQSandboxJournal,
)
from weflow_control_kernel.qq_transport import FakeQQPassiveAcknowledgementTransport

JsonObject = dict[str, Any]
NOW = datetime(2026, 8, 10, 0, 0, 1, tzinfo=UTC)
EXPECTED_SCENARIOS = frozenset(
    {
        "duplicate_delivery",
        "gap_and_out_of_order",
        "reconnect_resume_replay",
        "restart_after_receipt",
        "concurrent_intake",
        "stop_after_intent",
        "provider_acceptance_lost_response",
        "pre_acceptance_timeout",
        "disconnect_unknown",
        "provider_duplicate_response",
        "conflicting_identity",
        "unreadable_response",
        "expired_deadline",
        "unauthorized_capability",
    }
)
FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "raw_message",
        "raw_content",
        "transcript",
        "group_openid",
        "member_openid",
        "client_secret",
        "access_token",
        "authorization",
        "provider_response",
    }
)


def _require(condition: bool, reason_code: str) -> None:
    if not condition:
        raise RuntimeError(reason_code)


def _config() -> QQSandboxConfig:
    return QQSandboxConfig(
        app_id="offline-fake-app",
        client_secret="not-a-real-secret",
        group_openid="offline-fake-group",
        tenant_id="tenant-qq-offline",
        identity_salt="offline-fake-salt",
    )


def _event(*, message_id: str = "qq-message-001", sequence: int = 42) -> JsonObject:
    return {
        "op": 0,
        "s": sequence,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": message_id,
            "group_openid": "offline-fake-group",
            "author": {"member_openid": "offline-fake-member"},
            "content": "广告系统出现了API 503错误",
            "timestamp": "2026-08-10T00:00:00Z",
        },
    }


def _stack(root: Path, path: Path):
    clock = FixedClock(NOW)
    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=root)
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=root)
    service = QQSandboxIntakeService(
        ledger,
        journal,
        _config(),
        clock=clock,
        contract_root=root,
    )
    return ledger, journal, service


class OutcomeTransport(FakeQQPassiveAcknowledgementTransport):
    def __init__(self, *, reconcile: str, send: str = "accepted") -> None:
        super().__init__("offline-fake-group", send_status=send, reconcile_status=reconcile)


def _one_case_and_intent(ledger: SQLiteCaseLedger, journal: SQLiteQQSandboxJournal) -> bool:
    return (
        ledger.source_counts("tenant-qq-offline")
        == {
            "inbound_receipts": 1,
            "cases": 1,
            "case_revisions": 1,
            "business_events": 3,
            "case_projection": 1,
        }
        and journal.safe_counts("tenant-qq-offline")["acknowledgement_intent_count"] == 1
    )


def run_qq_sandbox_offline_acceptance(root: Path) -> JsonObject:
    """Exercise the QQ slice without importing or constructing a real adapter."""

    with TemporaryDirectory(prefix="weflow-qq-offline-") as temporary:
        workspace = Path(temporary)
        scenarios: JsonObject = {}

        path = workspace / "dedup.sqlite3"
        ledger, journal, service = _stack(root, path)
        first = service.accept(_event(), session_id="memory-session-a")
        duplicate = service.accept(_event(), session_id="memory-session-b")
        _require(first.intake.case_id == duplicate.intake.case_id, "qq_duplicate_case_mismatch")
        _require(_one_case_and_intent(ledger, journal), "qq_duplicate_counts_invalid")
        scenarios["duplicate_delivery"] = {"passed": True, "case_count": 1, "intent_count": 1}

        try:
            service.accept(_event(message_id="qq-message-gap", sequence=44))
            raise RuntimeError("qq_gap_not_rejected")
        except QQEventRejected as error:
            _require(error.reason_code == "qq_gateway_sequence_gap", "qq_gap_reason_invalid")
        try:
            service.accept(_event(message_id="qq-message-old", sequence=41))
            raise RuntimeError("qq_out_of_order_not_rejected")
        except QQEventRejected as error:
            _require(
                error.reason_code == "qq_gateway_sequence_out_of_order",
                "qq_out_of_order_reason_invalid",
            )
        _require(_one_case_and_intent(ledger, journal), "qq_sequence_rejection_mutated")
        scenarios["gap_and_out_of_order"] = {"passed": True, "case_count": 1}

        restarted_ledger, restarted_journal, restarted_service = _stack(root, path)
        replay = restarted_service.accept(_event(), session_id="memory-session-resumed")
        _require(replay.intake.disposition == "deduplicated", "qq_resume_not_deduplicated")
        _require(
            _one_case_and_intent(restarted_ledger, restarted_journal),
            "qq_resume_counts_invalid",
        )
        scenarios["reconnect_resume_replay"] = {"passed": True, "case_count": 1}
        scenarios["restart_after_receipt"] = {"passed": True, "intent_count": 1}

        concurrent_path = workspace / "concurrent.sqlite3"
        concurrent_ledger, concurrent_journal, concurrent_service = _stack(root, concurrent_path)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: concurrent_service.accept(_event()), range(2)))
        _require(
            {result.intake.disposition for result in results} == {"accepted", "deduplicated"},
            "qq_concurrent_disposition_invalid",
        )
        _require(
            _one_case_and_intent(concurrent_ledger, concurrent_journal),
            "qq_concurrent_counts_invalid",
        )
        scenarios["concurrent_intake"] = {"passed": True, "case_count": 1}

        recovery_path = workspace / "recovery.sqlite3"
        _, recovery_journal, recovery_service = _stack(root, recovery_path)
        pending = recovery_service.accept(_event())
        _require(
            recovery_journal.safe_counts("tenant-qq-offline")["acknowledgement_completion_count"]
            == 0,
            "qq_stop_after_intent_completed",
        )
        scenarios["stop_after_intent"] = {"passed": True, "completion_count": 0}

        lost = FakeQQPassiveAcknowledgementTransport("offline-fake-group", lose_first_response=True)
        controller = QQAcknowledgementController(
            recovery_journal, lost, _config(), clock=FixedClock(NOW)
        )
        unknown = controller.process(str(pending.intent["intent_id"]))
        recovered = controller.process(str(pending.intent["intent_id"]))
        _require(unknown["status"] == "NEEDS_RECONCILIATION", "qq_lost_response_claimed")
        _require(recovered["status"] == "completed", "qq_lost_response_not_recovered")
        _require(lost.send_calls == 1, "qq_lost_response_second_send")
        scenarios["provider_acceptance_lost_response"] = {
            "passed": True,
            "logical_acknowledgement_count": 1,
            "send_call_count": 1,
        }

        for name, reconcile_status in (
            ("pre_acceptance_timeout", "unknown"),
            ("disconnect_unknown", "unknown"),
            ("conflicting_identity", "conflict"),
            ("unreadable_response", "unknown"),
        ):
            scenario_path = workspace / f"{name}.sqlite3"
            _, scenario_journal, scenario_service = _stack(root, scenario_path)
            intake = scenario_service.accept(_event())
            transport = OutcomeTransport(reconcile=reconcile_status)
            outcome = QQAcknowledgementController(
                scenario_journal, transport, _config(), clock=FixedClock(NOW)
            ).process(str(intake.intent["intent_id"]))
            _require(outcome["status"] == "NEEDS_RECONCILIATION", f"qq_{name}_claimed")
            _require(transport.send_calls == 0, f"qq_{name}_sent")
            scenarios[name] = {"passed": True, "completion_count": 0}

        duplicate_path = workspace / "provider-duplicate.sqlite3"
        _, duplicate_journal, duplicate_service = _stack(root, duplicate_path)
        duplicate_intake = duplicate_service.accept(_event())
        duplicate_transport = OutcomeTransport(reconcile="absent", send="duplicate")
        duplicate_result = QQAcknowledgementController(
            duplicate_journal, duplicate_transport, _config(), clock=FixedClock(NOW)
        ).process(str(duplicate_intake.intent["intent_id"]))
        _require(duplicate_result["status"] == "completed", "qq_duplicate_not_completed")
        scenarios["provider_duplicate_response"] = {
            "passed": True,
            "logical_acknowledgement_count": 1,
        }

        expired_path = workspace / "expired.sqlite3"
        _, expired_journal, expired_service = _stack(root, expired_path)
        expired_intake = expired_service.accept(_event())
        expired_transport = OutcomeTransport(reconcile="absent")
        expired = QQAcknowledgementController(
            expired_journal,
            expired_transport,
            _config(),
            clock=FixedClock(NOW + timedelta(minutes=6)),
        ).process(str(expired_intake.intent["intent_id"]))
        _require(expired["status"] == "expired", "qq_expired_status_invalid")
        _require(expired_transport.reconcile_calls == 0, "qq_expired_contacted_provider")
        scenarios["expired_deadline"] = {"passed": True, "completion_count": 0}

        unauthorized_path = workspace / "unauthorized.sqlite3"
        _, unauthorized_journal, unauthorized_service = _stack(root, unauthorized_path)
        unauthorized_intake = unauthorized_service.accept(_event())
        unauthorized_transport = OutcomeTransport(reconcile="absent")
        unauthorized = QQAcknowledgementController(
            unauthorized_journal,
            unauthorized_transport,
            _config(),
            clock=FixedClock(NOW),
        ).process(str(unauthorized_intake.intent["intent_id"]), capability_active=False)
        _require(unauthorized["status"] == "NEEDS_RECONCILIATION", "qq_unauthorized_claimed")
        _require(unauthorized_transport.reconcile_calls == 0, "qq_unauthorized_contacted")
        scenarios["unauthorized_capability"] = {"passed": True, "completion_count": 0}

        report = {
            "report_type": "weflow-qq-sandbox-offline-acceptance.v1",
            "accepted": True,
            "mode": "offline-fake-transport",
            "fake_transport_verified": True,
            "qq_sandbox_live_verified": False,
            "customer_receipt_verified": False,
            "case_completion": False,
            "issue_resolution": False,
            "handler_approval": False,
            "final_delivery": False,
            "model_invocation": False,
            "real_external_write": False,
            "network_required": False,
            "credentials_required": False,
            "production_ready": False,
            "scenario_count": len(scenarios),
            "scenarios": scenarios,
            "privacy": {
                "raw_message_persisted": False,
                "transcript_persisted": False,
                "credential_persisted": False,
                "unrestricted_provider_response_persisted": False,
            },
        }
        validate_qq_acceptance_report(report, expected_mode="offline")
        return report


def _walk_safe(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_REPORT_KEYS:
                raise RuntimeError("qq_acceptance_report_unsafe_key")
            _walk_safe(item)
    elif isinstance(value, list):
        for item in value:
            _walk_safe(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(
            marker in lowered
            for marker in (
                "广告系统出现了api 503错误",
                "client_secret",
                "access_token",
                "authorization: qqbot",
            )
        ):
            raise RuntimeError("qq_acceptance_report_unsafe_value")


def validate_qq_acceptance_report(report: dict[str, Any], *, expected_mode: str) -> None:
    """Reject unsafe or overstated fake/live QQ evidence."""

    _walk_safe(report)
    _require(report.get("accepted") is True, "qq_acceptance_not_accepted")
    _require(report.get("customer_receipt_verified") is False, "qq_customer_receipt_overclaim")
    _require(report.get("case_completion") is False, "qq_case_completion_overclaim")
    _require(report.get("issue_resolution") is False, "qq_resolution_overclaim")
    _require(report.get("handler_approval") is False, "qq_handler_approval_overclaim")
    _require(report.get("final_delivery") is False, "qq_final_delivery_overclaim")
    _require(report.get("model_invocation") is False, "qq_model_use_overclaim")
    _require(report.get("production_ready") is False, "qq_production_readiness_overclaim")
    privacy = report.get("privacy")
    _require(isinstance(privacy, dict), "qq_privacy_evidence_missing")
    _require(
        all(
            privacy.get(field) is False
            for field in (
                "raw_message_persisted",
                "transcript_persisted",
                "credential_persisted",
                "unrestricted_provider_response_persisted",
            )
        ),
        "qq_privacy_evidence_invalid",
    )
    if expected_mode == "offline":
        _require(
            report.get("report_type") == "weflow-qq-sandbox-offline-acceptance.v1",
            "qq_offline_report_type_invalid",
        )
        _require(report.get("mode") == "offline-fake-transport", "qq_offline_mode_invalid")
        _require(report.get("fake_transport_verified") is True, "qq_fake_verification_missing")
        _require(report.get("qq_sandbox_live_verified") is False, "qq_live_verification_overclaim")
        _require(report.get("real_external_write") is False, "qq_real_write_overclaim")
        _require(report.get("network_required") is False, "qq_offline_network_overclaim")
        scenarios = report.get("scenarios")
        _require(isinstance(scenarios, dict), "qq_scenarios_missing")
        _require(set(scenarios) == EXPECTED_SCENARIOS, "qq_scenario_set_invalid")
        _require(report.get("scenario_count") == len(scenarios), "qq_scenario_count_invalid")
        _require(
            all(
                isinstance(value, dict) and value.get("passed") is True
                for value in scenarios.values()
            ),
            "qq_scenario_failed",
        )
    elif expected_mode in {"live", "live-dedup"}:
        _require(
            report.get("report_type") == "weflow-qq-sandbox-live-acceptance.v1",
            "qq_live_report_type_invalid",
        )
        _require(report.get("mode") == "qq-sandbox-live", "qq_live_mode_invalid")
        _require(report.get("fake_transport_verified") is False, "qq_live_report_fake_claim")
        _require(report.get("qq_sandbox_live_verified") is True, "qq_live_verification_missing")
        _require(report.get("real_external_write") is True, "qq_live_write_evidence_missing")
        _require(report.get("network_required") is True, "qq_live_network_evidence_missing")
        _require(report.get("credentials_required") is True, "qq_live_credentials_evidence_missing")
        _require(
            report.get("acknowledgement_status") == "completed",
            "qq_live_acknowledgement_incomplete",
        )
        _require(
            isinstance(report.get("acknowledgement_completion_count"), int)
            and report["acknowledgement_completion_count"] >= 1,
            "qq_live_completion_evidence_missing",
        )
        if expected_mode == "live-dedup":
            _require(
                report.get("deduplication_probe_mode") == "same-observed-event-in-memory",
                "qq_live_dedup_probe_mode_invalid",
            )
            _require(
                report.get("same_event_deduplication_verified") is True,
                "qq_live_event_deduplication_missing",
            )
            _require(report.get("duplicate_event_count") == 1, "qq_duplicate_count_invalid")
            _require(report.get("same_case_reused") is True, "qq_live_case_reuse_missing")
            _require(
                report.get("same_acknowledgement_intent_reused") is True,
                "qq_live_acknowledgement_reuse_missing",
            )
            _require(
                report.get("second_qq_write_attempted") is False,
                "qq_second_write_attempted",
            )
            _require(
                report.get("second_logical_acknowledgement") is False,
                "qq_second_logical_acknowledgement",
            )
            for field in (
                "case_count_delta",
                "acknowledgement_intent_count_delta",
                "acknowledgement_observation_count_delta",
                "acknowledgement_completion_count_delta",
            ):
                _require(report.get(field) == 1, f"qq_live_dedup_{field}_invalid")
    else:
        raise RuntimeError("qq_acceptance_mode_invalid")


__all__ = ["run_qq_sandbox_offline_acceptance", "validate_qq_acceptance_report"]
