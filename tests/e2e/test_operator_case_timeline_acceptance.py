"""End-to-end acceptance for the fixed offline Operator Case timeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from operator_case_timeline_acceptance import (  # noqa: E402
    publish_operator_case_timeline_acceptance,
)


def test_operator_case_timeline_acceptance_is_source_backed_safe_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "operator-case-timeline-acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["accepted"] is True
    assert report["offline"] is True
    assert report["docker_required"] is False
    assert report["network_required"] is False
    assert report["model_credentials_required"] is False
    assert report["operator_case_snapshot"]["counts"] == {
        "timeline_entry_count": 49,
        "case_event_count": 9,
        "case_revision_count": 1,
        "workflow_checkpoint_count": 13,
        "agent_step_count": 4,
        "tool_result_count": 3,
        "local_ticket_effect_count": 2,
        "fixture_delivery_effect_count": 1,
        "evidence_node_count": 48,
        "replay_result_count": 1,
    }
    assert report["determinism"] == {
        "repeated_baseline_equal": True,
        "intentional_nondeterministic_fields": [],
    }
    assert set(report["negative_matrix"]) == {
        "missing",
        "foreign",
        "malformed",
        "duplicate_key",
        "unsafe_path",
        "unsafe_field",
        "detached_hash",
        "detached_predecessor",
        "duplicate_source",
        "out_of_order_source",
        "count_mismatch",
        "stale_approval",
        "policy_denial",
        "restart_timeout_duplicate_completion",
        "unsupported_customer_success",
        "unsupported_authority",
        "arbitrary_selector",
        "unsupported_method",
    }
    assert set(report["negative_matrix"].values()) == {
        "operator_case_not_found",
        "operator_case_not_ready",
        "operator_case_request_invalid",
        "method_not_allowed",
    }
    assert all(value == 0 for value in report["side_effect_counts"].values())
    assert report["capabilities"]["live_provider_enabled"] is False
    assert report["capabilities"]["external_writes_enabled"] is False
    assert report["capabilities"]["customer_resolution_enabled"] is False
    assert report["capabilities"]["business_workflow_complete"] is False
    for forbidden in ("raw_payload", "provider_token", "traceback", "C:/private"):
        assert forbidden not in completed.stdout


def test_invalid_pending_report_preserves_prior_canonical_report(tmp_path: Path) -> None:
    canonical = (
        tmp_path / "reports" / "add-offline-operator-case-timeline-acceptance.json"
    )
    canonical.parent.mkdir(parents=True)
    prior = b'{"prior":"preserved"}\n'
    canonical.write_bytes(prior)

    with pytest.raises(ValueError):
        publish_operator_case_timeline_acceptance(
            tmp_path,
            {"report_type": "invalid", "accepted": False},
        )

    assert canonical.read_bytes() == prior
    assert not list(canonical.parent.glob("*.pending"))
