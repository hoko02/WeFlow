from __future__ import annotations

from pathlib import Path

import pytest
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
