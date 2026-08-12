from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qq_sandbox_acceptance import (  # noqa: E402
    EXPECTED_SCENARIOS,
    run_qq_sandbox_offline_acceptance,
    validate_qq_acceptance_report,
)


def test_qq_offline_acceptance_covers_declared_fault_and_recovery_matrix() -> None:
    report = run_qq_sandbox_offline_acceptance(ROOT)

    validate_qq_acceptance_report(report, expected_mode="offline")
    assert report["accepted"] is True
    assert report["scenario_count"] == 14
    assert set(report["scenarios"]) == EXPECTED_SCENARIOS
    assert report["fake_transport_verified"] is True
    assert report["qq_sandbox_live_verified"] is False
    assert report["customer_receipt_verified"] is False
    assert report["case_completion"] is False
    assert report["model_invocation"] is False
