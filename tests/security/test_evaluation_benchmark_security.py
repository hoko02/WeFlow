from __future__ import annotations

from pathlib import Path

import pytest
from weflow_testkit.evaluation_benchmark import (
    BenchmarkValidationError,
    run_evaluation_benchmark_acceptance,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "configuration",
    (
        {"provider": "live"},
        {"network": True},
        {"credential": "blocked"},
        {"external_executor": "blocked"},
        {"multi_agent": True},
    ),
)
def test_benchmark_rejects_forbidden_execution_configuration_before_contact(
    configuration: dict[str, object],
) -> None:
    with pytest.raises(BenchmarkValidationError, match="offline_benchmark_configuration_denied"):
        run_evaluation_benchmark_acceptance(ROOT, configuration=configuration)
