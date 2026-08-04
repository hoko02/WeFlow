import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def test_investigation_agent_acceptance_is_offline_deterministic_recoverable_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "investigation-agent-acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    baseline = report["fixture_outcomes"]["api_503_investigation"]
    assert report["accepted"] is True
    assert report["offline"] is True
    assert report["network_required"] is False
    assert report["docker_required"] is False
    assert report["model_credentials_required"] is False
    assert baseline["state"] == "RESPONSE_READY"
    assert baseline["verifier_outcome"] == "verified"
    assert baseline["tool_evidence_count"] == 3
    assert baseline["agent_step_count"] == 4
    assert baseline["source_counts"] == {
        "agent_steps": 4,
        "investigation_tool_requests": 3,
        "investigation_tool_results": 3,
        "investigation_candidates": 1,
        "investigation_verifier_outcomes": 1,
    }
    assert all(
        outcome["state"] == "RESPONSE_READY"
        and outcome["duplicate_tool_result"] is False
        and outcome["duplicate_response_ready_transition"] is False
        for outcome in report["fixture_outcomes"]["fault_recovery"]
    )
    assert report["determinism"]["repeated_baseline_equal"] is True
    assert report["capabilities"] == {
        "replay_investigation_agent_implemented": True,
        "response_candidate_verification_implemented": True,
        "business_workflow_implemented": False,
        "real_provider_enabled": False,
        "multi_agent_enabled": False,
        "external_writes_enabled": False,
        "model_invocation": False,
        "approval": False,
        "outbound_delivery": False,
        "customer_resolution": False,
    }
    assert report["environment_limits"]["docker_required"] is False
    assert report["environment_limits"]["node_required_for_core_acceptance"] is False
    for forbidden in ("customer-api-503-alpha", "provider_token", "private prompt", "raw_message"):
        assert forbidden not in completed.stdout