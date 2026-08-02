import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def test_durable_workflow_acceptance_is_offline_deterministic_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "durable-workflow-acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["accepted"] is True
    assert report["offline"] is True
    assert report["network_required"] is False
    assert report["docker_required"] is False
    assert report["model_credentials_required"] is False
    assert report["fixture_outcomes"]["ticket_handoff"]["state"] == "TICKET_READY"
    assert report["fixture_outcomes"]["ticket_handoff"]["reconciliation"]["operation_count"] == 2
    assert all(
        outcome["state"] == "TICKET_READY"
        and outcome["operation_count"] == 2
        for outcome in report["fixture_outcomes"]["fault_recovery"]
    )
    assert report["fixture_outcomes"]["synthetic_sla"]["state"] == "WAITING_FOR_OPERATOR"
    assert report["determinism"]["repeated_baseline_equal"] is True
    assert report["capabilities"] == {
        "approval": False,
        "business_workflow_implemented": False,
        "customer_resolution": False,
        "durable_support_workflow_implemented": True,
        "external_writes_enabled": False,
        "model_invocation": False,
        "outbound_delivery": False,
    }
    assert "customer-api-503-alpha" not in completed.stdout
    assert "sender-api-503-alpha" not in completed.stdout
    assert "private prompt" not in completed.stdout.lower()
