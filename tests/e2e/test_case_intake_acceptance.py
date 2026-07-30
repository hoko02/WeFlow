import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def test_case_intake_acceptance_is_offline_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "case-intake-acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["accepted"] is True
    assert report["mode"] == "offline"
    assert report["network_required"] is False
    assert report["model_credentials_required"] is False
    assert report["docker_required"] is False
    assert report["fixture_results"]["api-503-first-delivery"]["outcome"] == "accepted"
    assert report["fixture_results"]["api-503-duplicate-delivery"]["outcome"] == "deduplicated"
    assert report["fixture_results"]["api-503-out-of-order"]["outcome"] == "inbound_out_of_order"
    assert report["source_counts"]["business_events"] == 3
    assert report["snapshot"]["restored"] is True
    assert report["model_invoked"] is False
    assert report["workflow_started"] is False
    assert report["approval_started"] is False
    assert report["customer_resolution_declared"] is False
    assert "customer-api-503-alpha" not in completed.stdout
    assert "sender-api-503-alpha" not in completed.stdout
