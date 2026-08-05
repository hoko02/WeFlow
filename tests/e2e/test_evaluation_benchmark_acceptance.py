"""End-to-end acceptance for the 12-task deterministic evaluation benchmark core."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def test_evaluation_benchmark_acceptance_is_offline_deterministic_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "evaluation-benchmark-acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["accepted"] is True
    assert report["offline"] is True
    assert report["docker_required"] is False
    assert report["network_required"] is False
    assert report["model_credentials_required"] is False
    assert report["determinism"] == {
        "repeated_baseline_equal": True,
        "intentional_nondeterministic_fields": [],
    }
    suite = report["suite_report"]
    assert suite["profile"] == "benchmark-core.v1"
    assert suite["task_count"] == 12
    assert suite["passed_task_count"] == 12
    assert suite["failed_task_count"] == 0
    assert suite["unscored_task_count"] == 0
    assert suite["capability_flags"] == {
        "offline": True,
        "replay": True,
        "network": False,
        "model": False,
        "external_write": False,
    }
    assert len(report["task_diagnostics"]) == 12
    assert all(item["grader_result"]["hard_gate_passed"] for item in report["task_diagnostics"])
    assert all(item["grader_result"]["quality_score"] == 100 for item in report["task_diagnostics"])
    result_ids = [
        item["evaluation_result"]["evaluation_result_id"]
        for item in report["task_diagnostics"]
    ]
    case_ids = [
        item["evaluation_case"]["evaluation_case_id"]
        for item in report["task_diagnostics"]
    ]
    assert suite["task_result_ids"] == result_ids
    assert len(set(result_ids)) == 12
    assert len(set(case_ids)) == 12
    assert all(
        item["evaluation_case"]["input_hash"] == item["fixture_sha256"]
        for item in report["task_diagnostics"]
    )
    assert all(
        item["fixture_source_path"].startswith("fixtures/")
        and item["policy_source_path"] == "evals/sources/offline-policy.v1.json"
        for item in report["task_diagnostics"]
    )
    diagnostics = {
        item["evaluation_task_id"]: item for item in report["task_diagnostics"]
    }
    stale = diagnostics["policy-stale-approval"]["observation"]
    assert stale["state"] == "APPROVAL_INVALIDATED"
    assert stale["outcome"] == "authorization_denied"
    assert stale["approval_valid"] is True
    recovery = diagnostics["policy-delivery-recovery"]["observation"]
    assert recovery["state"] == "DELIVERY_RECORDED"
    assert recovery["outcome"] == "recovered_after_interruption"
    assert recovery["local_effect_count"] == 1
    tampered = diagnostics["evidence-tampered-lineage"]["observation"]
    assert tampered["state"] == "TRAJECTORY_REPLAY_REJECTED"
    assert tampered["outcome"] == "lineage_invalid"
    assert tampered["evidence_valid"] is True
    for forbidden in ("customer-api-503-alpha", "provider_token", "private prompt", "raw_message"):
        assert forbidden not in completed.stdout
