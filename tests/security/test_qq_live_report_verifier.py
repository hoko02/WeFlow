from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qq_sandbox_acceptance import validate_qq_acceptance_report  # noqa: E402


def live_report() -> dict[str, object]:
    return {
        "report_type": "weflow-qq-sandbox-live-acceptance.v1",
        "mode": "qq-sandbox-live",
        "accepted": True,
        "fake_transport_verified": False,
        "qq_sandbox_live_verified": True,
        "customer_receipt_verified": False,
        "case_completion": False,
        "issue_resolution": False,
        "handler_approval": False,
        "final_delivery": False,
        "model_invocation": False,
        "production_ready": False,
        "real_external_write": True,
        "network_required": True,
        "credentials_required": True,
        "acknowledgement_status": "completed",
        "acknowledgement_completion_count": 1,
        "privacy": {
            "raw_message_persisted": False,
            "transcript_persisted": False,
            "credential_persisted": False,
            "unrestricted_provider_response_persisted": False,
        },
    }


def test_strict_live_report_shape_passes_without_customer_outcome_claim() -> None:
    validate_qq_acceptance_report(live_report(), expected_mode="live")


def test_strict_live_dedup_report_requires_same_event_and_no_second_write() -> None:
    report = live_report()
    report.update(
        {
            "deduplication_probe_mode": "same-observed-event-in-memory",
            "same_event_deduplication_verified": True,
            "duplicate_event_count": 1,
            "same_case_reused": True,
            "same_acknowledgement_intent_reused": True,
            "second_qq_write_attempted": False,
            "second_logical_acknowledgement": False,
            "case_count_delta": 1,
            "acknowledgement_intent_count_delta": 1,
            "acknowledgement_observation_count_delta": 1,
            "acknowledgement_completion_count_delta": 1,
        }
    )
    validate_qq_acceptance_report(report, expected_mode="live-dedup")
    report["second_qq_write_attempted"] = True
    with pytest.raises(RuntimeError, match="qq_second_write_attempted"):
        validate_qq_acceptance_report(report, expected_mode="live-dedup")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("report_type", "weflow-qq-sandbox-fake-gateway-run.v1"),
        ("mode", "offline-fake-transport"),
        ("fake_transport_verified", True),
        ("qq_sandbox_live_verified", False),
        ("real_external_write", False),
        ("network_required", False),
        ("credentials_required", False),
        ("acknowledgement_status", "NEEDS_RECONCILIATION"),
        ("acknowledgement_completion_count", 0),
        ("customer_receipt_verified", True),
    ),
)
def test_live_verifier_rejects_fake_incomplete_or_customer_claim(field: str, value: object) -> None:
    report = deepcopy(live_report())
    report[field] = value
    with pytest.raises(RuntimeError):
        validate_qq_acceptance_report(report, expected_mode="live")
