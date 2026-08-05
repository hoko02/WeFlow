from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import weflow_testkit.evaluation_benchmark as benchmark
from weflow_testkit.benchmark_observation import make_benchmark_observation
from weflow_testkit.evaluation_benchmark import (
    BenchmarkValidationError,
    load_offline_seed_suite,
    run_offline_seed_suite,
)

ROOT = Path(__file__).resolve().parents[2]


def test_offline_seed_suite_has_exactly_twelve_ordered_safe_tasks() -> None:
    suite, records = load_offline_seed_suite(ROOT)

    assert suite["suite_id"] == "offline-seed.v1"
    assert len(records) == 12
    assert [record["task"]["evaluation_task_id"] for record in records] == [
        item["evaluation_task_id"] for item in suite["tasks"]
    ]
    assert {record["task"]["tenant_id"] for record in records} == {"tenant-alpha"}


@pytest.mark.parametrize(
    "configuration",
    (
        {"mode": "service-boundary"},
        {"provider": "live"},
        {"external_write": True},
        {"multi_agent": True},
    ),
)
def test_runner_denies_non_offline_configuration_before_task_execution(
    configuration: dict[str, object],
) -> None:
    with pytest.raises(BenchmarkValidationError, match="offline_benchmark_configuration_denied"):
        run_offline_seed_suite(ROOT, configuration=configuration)


def test_unexpected_observation_state_fails_expected_outcome_gate() -> None:
    _suite, records = load_offline_seed_suite(ROOT)
    record = records[0]
    observation = make_benchmark_observation(
        tenant_id="tenant-alpha",
        state="UNEXPECTED_STATE",
        outcome="unexpected_state",
        evidence_valid=True,
        approval_valid=False,
        local_effect_count=0,
        tool_call_count=0,
    )

    grader, _metrics = benchmark._grade(
        record["task"], record["oracle"], observation, "unexpected-state"
    )

    expected_gate = next(
        gate for gate in grader["hard_gates"] if gate["name"] == "expected_outcome"
    )
    assert expected_gate["passed"] is False
    assert grader["hard_gate_passed"] is False
    assert grader["quality_score"] == "not_scored"


def test_runner_allocates_one_fresh_store_per_task_without_cross_task_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_paths: set[Path] = set()

    def observe(
        _root: Path, record: dict[str, object], store_path: Path
    ) -> dict[str, object]:
        resolved = store_path.resolve()
        assert resolved not in observed_paths
        observed_paths.add(resolved)
        connection = sqlite3.connect(store_path)
        try:
            tables = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = 'task_marker'"
            ).fetchone()
            assert tables == (0,)
            connection.execute(
                "CREATE TABLE task_marker (evaluation_task_id TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO task_marker (evaluation_task_id) VALUES (?)",
                (record["task"]["evaluation_task_id"],),
            )
            connection.commit()
        finally:
            connection.close()
        oracle = record["oracle"]
        return make_benchmark_observation(
            tenant_id=str(record["task"]["tenant_id"]),
            state="FAKE_SAFE_STATE",
            outcome=str(oracle["expected_outcome"]),
            evidence_valid=True,
            approval_valid="approval_binding" in oracle["required_hard_gates"],
            local_effect_count=int(oracle["expected_local_effect_count"]),
            tool_call_count=0,
        )

    monkeypatch.setattr(benchmark, "_observe_task", observe)
    result = run_offline_seed_suite(ROOT, run_id="isolated-stores")

    assert len(observed_paths) == 12
    assert result["suite_report"]["passed_task_count"] == 12
