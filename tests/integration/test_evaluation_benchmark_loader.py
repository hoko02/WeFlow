from __future__ import annotations

from pathlib import Path

from weflow_testkit.evaluation_benchmark import load_offline_seed_suite

ROOT = Path(__file__).resolve().parents[2]


def test_seed_tasks_bind_safe_fixture_and_policy_references() -> None:
    suite, records = load_offline_seed_suite(ROOT)

    assert suite["profile"] == "benchmark-core.v1"
    for record in records:
        task = record["task"]
        assert record["fixture"]["fixture_id"] == task["fixture_id"]
        assert record["fixture"]["fixture_sha256"] == task["fixture_sha256"]
        assert record["policy"]["policy_id"] == "offline-policy.v1"
        assert record["policy"]["policy_sha256"] == task["policy_sha256"]
