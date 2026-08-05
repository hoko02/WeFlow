"""Machine-readable offline acceptance evidence for the benchmark-core seed suite."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from weflow_testkit.evaluation_benchmark import (
    BenchmarkValidationError,
    run_evaluation_benchmark_acceptance,
)

JsonObject = dict[str, Any]


def run_benchmark_core_acceptance(
    root: Path, *, configuration: Mapping[str, object] | None = None
) -> JsonObject:
    """Run the named 12-task Replay-only benchmark profile."""

    return run_evaluation_benchmark_acceptance(root, configuration=configuration)


__all__ = ["BenchmarkValidationError", "run_benchmark_core_acceptance"]
