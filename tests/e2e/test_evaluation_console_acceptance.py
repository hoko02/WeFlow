"""End-to-end acceptance for the read-only offline evaluation report console."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def test_evaluation_console_acceptance_is_deterministic_safe_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "evaluation-console-acceptance", "--output", ""],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["accepted"] is True
    assert report["offline"] is True
    assert report["docker_required"] is False
    assert report["network_required"] is False
    assert report["model_credentials_required"] is False
    assert report["suite"]["task_count"] == 12
    assert report["suite"]["passed_task_count"] == 12
    assert report["suite"]["failed_task_count"] == 0
    assert report["suite"]["unscored_task_count"] == 0
    assert len(report["suite"]["task_result_ids"]) == 12
    assert report["determinism"] == {
        "snapshot_reads_equal": True,
        "intentional_nondeterministic_fields": [],
    }
    assert report["api"] == {
        "authorized_status": 200,
        "foreign_and_missing_status": 404,
        "selector_status": 422,
        "unsupported_method_status": 405,
        "identity_denied_status": 403,
        "tenant_identity_derived": True,
    }
    assert set(report["integrity_matrix"]) == {
        "arbitrary_selector",
        "detached",
        "duplicate_key",
        "foreign",
        "malformed",
        "missing",
        "stale",
        "tampered",
        "unsafe",
        "unsafe_path",
        "unsupported_claim",
    }
    assert report["console"]["task_summaries_rendered"] == 12
    assert report["console"]["production_vite_build"] is True
    assert report["console"]["unrestricted_json_rendered"] is False
    assert report["side_effects"] == {
        "source_report_mutation_count": 0,
        "retained_store_mutation_count": 0,
        "case_workflow_approval_delivery_mutation_count": 0,
        "network_request_count": 0,
        "model_invocation_count": 0,
        "external_write_attempt_count": 0,
    }
    for forbidden in (
        "raw_payload",
        "provider_token",
        "customer-api-503-alpha",
        "C:/private",
        "traceback",
    ):
        assert forbidden not in completed.stdout
