from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qq_sandbox_acceptance import (  # noqa: E402
    EXPECTED_SCENARIOS,
    validate_qq_acceptance_report,
)


def safe_report() -> dict[str, object]:
    return {
        "report_type": "weflow-qq-sandbox-offline-acceptance.v1",
        "mode": "offline-fake-transport",
        "accepted": True,
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
        "production_ready": False,
        "scenario_count": len(EXPECTED_SCENARIOS),
        "privacy": {
            "raw_message_persisted": False,
            "transcript_persisted": False,
            "credential_persisted": False,
            "unrestricted_provider_response_persisted": False,
        },
        "scenarios": {name: {"passed": True} for name in EXPECTED_SCENARIOS},
    }


@pytest.mark.parametrize(
    "field",
    (
        "customer_receipt_verified",
        "case_completion",
        "issue_resolution",
        "handler_approval",
        "final_delivery",
        "model_invocation",
        "production_ready",
        "qq_sandbox_live_verified",
        "real_external_write",
        "network_required",
    ),
)
def test_offline_qq_report_rejects_every_overclaim(field: str) -> None:
    report = safe_report()
    report[field] = True
    with pytest.raises(RuntimeError):
        validate_qq_acceptance_report(report, expected_mode="offline")


@pytest.mark.parametrize(
    ("unsafe_key", "unsafe_value"),
    (
        ("raw_content", "incident"),
        ("group_openid", "opaque-but-private"),
        ("access_token", "credential"),
        ("provider_response", {"unrestricted": True}),
        ("note", "广告系统出现了API 503错误"),
    ),
)
def test_qq_report_rejects_raw_or_unrestricted_provider_data(
    unsafe_key: str, unsafe_value: object
) -> None:
    report = deepcopy(safe_report())
    report[unsafe_key] = unsafe_value
    with pytest.raises(RuntimeError, match="qq_acceptance_report_unsafe"):
        validate_qq_acceptance_report(report, expected_mode="offline")


def test_qq_report_rejects_missing_or_failed_scenario() -> None:
    missing = safe_report()
    missing["scenarios"].pop(next(iter(EXPECTED_SCENARIOS)))  # type: ignore[union-attr]
    with pytest.raises(RuntimeError, match="qq_scenario_set_invalid"):
        validate_qq_acceptance_report(missing, expected_mode="offline")

    failed = safe_report()
    failed["scenarios"][next(iter(EXPECTED_SCENARIOS))]["passed"] = False  # type: ignore[index]
    with pytest.raises(RuntimeError, match="qq_scenario_failed"):
        validate_qq_acceptance_report(failed, expected_mode="offline")
