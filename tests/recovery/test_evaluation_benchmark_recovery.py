from __future__ import annotations

from pathlib import Path

from weflow_testkit.evaluation_benchmark import load_offline_seed_suite

ROOT = Path(__file__).resolve().parents[2]


def test_seed_suite_contains_named_recovery_and_safe_denial_oracles() -> None:
    _suite, records = load_offline_seed_suite(ROOT)
    outcomes = {
        record["task"]["evaluation_task_id"]: record["oracle"]["expected_outcome"]
        for record in records
    }

    assert outcomes["investigation-candidate-recovery"] == "response_ready"
    assert outcomes["policy-delivery-recovery"] == "recovered_after_interruption"
    assert outcomes["policy-revoked-grant"] == "authorization_denied"
    assert outcomes["policy-stale-approval"] == "authorization_denied"
    assert outcomes["evidence-tampered-lineage"] == "lineage_invalid"
