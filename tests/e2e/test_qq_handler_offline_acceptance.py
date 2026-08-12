from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from qq_handler_acceptance import run_qq_handler_offline_acceptance  # noqa: E402


def test_qq_handler_offline_acceptance_is_deterministic_and_privacy_safe() -> None:
    first = run_qq_handler_offline_acceptance(ROOT)
    second = run_qq_handler_offline_acceptance(ROOT)

    assert first == second
    assert first["dual_surface_binding_verified"] is True
    assert first["notification_status"] == "accepted"
    assert first["notification_attempt_count"] == 1
    assert first["private_workflow_verified"] is True
    assert first["group_approval_verified"] is True
    assert first["final_provider_accepted"] is True
    assert first["artifact_deletion_verified"] is True
    assert first["duplicate_event_count"] == 1
    assert first["rejected_event_count"] == 1
    assert first["network_contacted"] is False
    assert first["external_write_attempted"] is False
    assert first["model_invocation"] is False
    assert first["customer_receipt_verified"] is False
    assert first["issue_resolution"] is False
    assert first["case_completion"] is False
    assert first["production_ready"] is False
