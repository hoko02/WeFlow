import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def test_policy_approval_acceptance_is_offline_deterministic_idempotent_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "policy-approval-acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    baseline = report["fixture_outcomes"]["api_503_policy_approval_delivery"]
    denial = report["fixture_outcomes"]["authorization_denial"]
    faults = report["fixture_outcomes"]["fault_recovery"]

    assert report["accepted"] is True
    assert report["offline"] is True
    assert report["network_required"] is False
    assert report["docker_required"] is False
    assert report["model_credentials_required"] is False
    assert baseline["state"] == "DELIVERY_RECORDED"
    assert baseline["fixture_local"] is True
    assert baseline["real_external_write"] is False
    assert baseline["customer_resolution"] is False
    assert baseline["source_counts"]["fixture_delivery_records"] == 1
    assert baseline["source_counts"]["fixture_delivery_operations"] == 1
    assert denial == {
        "state": "WAITING_FOR_OPERATOR",
        "reason_code": "authorization_denied_grant_revoked",
        "approval_decision_count": 1,
        "delivery_intent_count": 0,
        "delivery_record_count": 0,
        "real_external_write": False,
        "customer_resolution": False,
    }
    assert [item["fault_point"] for item in faults] == [
        "policy",
        "approval-request",
        "approval-decision",
        "delivery-intent",
        "delivery-execute",
        "delivery-lost-response",
        "delivery-observation",
        "delivery-completion",
        "delivery-transition",
        "reconciliation-timeout",
    ]
    assert all(
        item["state"] == "DELIVERY_RECORDED"
        and item["delivery_record_count"] == 1
        and item["delivery_operation_count"] == 1
        and item["delivery_intent_count"] == 1
        and item["delivery_completion_count"] == 1
        and item["duplicate_delivery"] is False
        and isinstance(item["reconciliation_timeout"], bool)
        for item in faults
    )
    assert report["determinism"] == {
        "repeated_baseline_equal": True,
        "intentional_nondeterministic_fields": [],
    }
    assert report["capabilities"] == {
        "fixture_policy_approval_delivery_implemented": True,
        "fixture_approval_enabled": True,
        "fixture_outbound_delivery_enabled": True,
        "live_approval_enabled": False,
        "live_outbound_delivery_enabled": False,
        "business_workflow_implemented": False,
        "real_provider_enabled": False,
        "external_writes_enabled": False,
        "customer_resolution_enabled": False,
        "model_invocation": False,
    }
    assert report["environment_limits"]["docker_required"] is False
    assert report["environment_limits"]["node_required_for_core_acceptance"] is False
    assert report["environment_limits"]["node_required_for_typescript_and_console_checks"] is True
    for forbidden in (
        "customer-api-503-alpha",
        "provider_token",
        "private prompt",
        "raw_message",
        "fixture-controller-alpha",
    ):
        assert forbidden not in completed.stdout
