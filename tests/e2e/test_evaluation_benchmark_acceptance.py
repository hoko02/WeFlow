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
    for forbidden in ("customer-api-503-alpha", "provider_token", "private prompt", "raw_message"):
        assert forbidden not in completed.stdout
