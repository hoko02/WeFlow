"""Read-only validation and projection for the canonical offline evaluation report."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from weflow_contracts import ContractValidationError
from weflow_contracts.evaluation import (
    EVALUATION_SUITE_SNAPSHOT_SCHEMA_ID,
    canonical_sha256,
    validate_evaluation_suite_report,
    validate_evaluation_suite_snapshot,
)

from .benchmark_observation import OFFLINE_CAPABILITY_FLAGS
from .evaluation_benchmark import (
    BenchmarkValidationError,
    load_offline_seed_suite,
    validate_retained_benchmark_diagnostic,
)

JsonObject = dict[str, Any]
CANONICAL_EVALUATION_REPORT_PATH: Final = (
    "reports/change-6-evaluation-benchmark-core-acceptance.json"
)
EVALUATION_REPORT_NOT_FOUND: Final = "evaluation_report_not_found"
EVALUATION_REPORT_NOT_READY: Final = "evaluation_report_not_ready"

_ENVELOPE_KEYS = {
    "accepted",
    "capabilities",
    "determinism",
    "docker_required",
    "model_credentials_required",
    "network_required",
    "offline",
    "report_type",
    "suite_report",
    "task_diagnostics",
}
_EXPECTED_CAPABILITIES = {
    "offline_evaluation_benchmark_core_implemented": True,
    "live_model_enabled": False,
    "external_writes_enabled": False,
    "customer_resolution_enabled": False,
    "multi_agent_enabled": False,
    "planned_live_runs": 0,
    "planned_task_count": 60,
}
_FORBIDDEN_KEYS = {
    "adapter_payload",
    "caller_authority",
    "caller_role",
    "credential",
    "customer_receipt",
    "customer_resolved",
    "customer_success",
    "live_provider",
    "private_prompt",
    "provider_acknowledged",
    "provider_token",
    "raw_message",
    "raw_payload",
    "stack",
    "tool_output",
    "traceback",
}


class EvaluationReportError(ValueError):
    """An allowlisted unavailable state that never contains report values or paths."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _safe_report_path(relative_path: object) -> PurePosixPath:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
    pure = PurePosixPath(relative_path)
    if (
        pure.is_absolute()
        or not pure.parts
        or pure.parts[0] != "reports"
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
    return pure


@dataclass(frozen=True)
class RepositoryEvaluationReportSource:
    """A repository-bounded source; overrides are opt-in and intended for tests only."""

    root: Path
    relative_path: str = CANONICAL_EVALUATION_REPORT_PATH
    allow_test_override: bool = False

    def read_text(self) -> str:
        pure = _safe_report_path(self.relative_path)
        if not self.allow_test_override and pure.as_posix() != CANONICAL_EVALUATION_REPORT_PATH:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
        reports_root = (self.root / "reports").resolve()
        path = (self.root / Path(*pure.parts)).resolve()
        try:
            path.relative_to(reports_root)
        except ValueError as error:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY) from error
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_FOUND) from error
        except (OSError, UnicodeError) as error:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY) from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    loaded: JsonObject = {}
    for key, value in pairs:
        if key in loaded:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
        loaded[key] = value
    return loaded


def _parse_report(text: str) -> JsonObject:
    try:
        loaded = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except EvaluationReportError:
        raise
    except (json.JSONDecodeError, TypeError, UnicodeError) as error:
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY) from error
    if not isinstance(loaded, dict):
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
    return loaded


def _contains_unsafe_field(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized.startswith("raw_") or normalized in _FORBIDDEN_KEYS:
                return True
            if _contains_unsafe_field(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_unsafe_field(item) for item in value)
    return False


def _validate_acceptance_envelope(report: JsonObject) -> tuple[JsonObject, list[JsonObject]]:
    if set(report) != _ENVELOPE_KEYS or _contains_unsafe_field(report):
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
    if (
        report.get("report_type") != "weflow-change-6-evaluation-benchmark-core-acceptance.v1"
        or report.get("accepted") is not True
        or report.get("offline") is not True
        or report.get("docker_required") is not False
        or report.get("network_required") is not False
        or report.get("model_credentials_required") is not False
        or report.get("capabilities") != _EXPECTED_CAPABILITIES
        or report.get("determinism")
        != {
            "repeated_baseline_equal": True,
            "intentional_nondeterministic_fields": [],
        }
    ):
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
    suite_report = report.get("suite_report")
    diagnostics = report.get("task_diagnostics")
    if not isinstance(suite_report, dict) or not isinstance(diagnostics, list):
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
    if not all(isinstance(item, dict) for item in diagnostics):
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
    return suite_report, diagnostics


def _project_task(record: JsonObject, diagnostic: JsonObject) -> JsonObject:
    task = record["task"]
    oracle = record["oracle"]
    evaluation_case = diagnostic["evaluation_case"]
    grader = diagnostic["grader_result"]
    metrics = diagnostic["metrics"]
    evaluation_result = diagnostic["evaluation_result"]
    observation = diagnostic["observation"]
    return {
        "tenant_id": task["tenant_id"],
        "evaluation_task_id": task["evaluation_task_id"],
        "fixture_id": task["fixture_id"],
        "fixture_source_id": task["fixture_source_id"],
        "fixture_source_path": record["fixture_source_path"],
        "fixture_sha256": task["fixture_sha256"],
        "policy_source_id": task["policy_source_id"],
        "policy_source_path": record["policy_source_path"],
        "policy_sha256": task["policy_sha256"],
        "task_sha256": diagnostic["task_sha256"],
        "oracle_id": oracle["oracle_id"],
        "oracle_sha256": diagnostic["oracle_sha256"],
        "evaluation_case_id": evaluation_case["evaluation_case_id"],
        "grader_result_id": grader["grader_result_id"],
        "run_metrics_id": metrics["run_metrics_id"],
        "evaluation_result_id": evaluation_result["evaluation_result_id"],
        "result": evaluation_result["result"],
        "failure_classification": evaluation_result["failure_classification"],
        "hard_gate_passed": grader["hard_gate_passed"],
        "hard_gates": [dict(item) for item in grader["hard_gates"]],
        "dimensions": [dict(item) for item in grader["dimensions"]],
        "quality_score": grader["quality_score"],
        "metrics": {
            key: metrics[key]
            for key in (
                "tool_call_count",
                "local_effect_count",
                "network_request_count",
                "model_invocation_count",
                "external_write_attempt_count",
            )
        },
        "observation": {
            key: observation[key]
            for key in (
                "state",
                "outcome",
                "evidence_valid",
                "approval_valid",
                "tool_call_count",
                "local_effect_count",
                "offline",
                "replay",
                "network",
                "model",
                "external_write",
            )
        },
    }


def read_evaluation_suite_snapshot(
    root: Path,
    *,
    report_source: RepositoryEvaluationReportSource | None = None,
) -> JsonObject:
    """Return a validated snapshot or one allowlisted unavailable reason."""

    source = report_source or RepositoryEvaluationReportSource(root)
    try:
        acceptance = _parse_report(source.read_text())
        suite_report, diagnostics = _validate_acceptance_envelope(acceptance)
        validate_evaluation_suite_report(suite_report, root)
        suite, records = load_offline_seed_suite(root)
        if (
            suite_report.get("suite_id") != "offline-seed.v1"
            or suite_report.get("profile") != "benchmark-core.v1"
            or suite_report.get("suite_sha256") != canonical_sha256(suite)
            or suite_report.get("task_count") != 12
            or suite_report.get("passed_task_count") != 12
            or suite_report.get("failed_task_count") != 0
            or suite_report.get("unscored_task_count") != 0
            or len(diagnostics) != len(records)
        ):
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)

        expected_task_ids = [record["task"]["evaluation_task_id"] for record in records]
        diagnostic_task_ids = [item.get("evaluation_task_id") for item in diagnostics]
        if diagnostic_task_ids != expected_task_ids:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)

        projected_tasks: list[JsonObject] = []
        for record, diagnostic in zip(records, diagnostics, strict=True):
            validate_retained_benchmark_diagnostic(root, record, diagnostic, suite_report)
            projected_tasks.append(_project_task(record, diagnostic))
        projected_result_ids = [item["evaluation_result_id"] for item in projected_tasks]
        if suite_report.get("task_result_ids") != projected_result_ids:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)

        tenant_ids = {item["tenant_id"] for item in projected_tasks}
        if len(tenant_ids) != 1:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY)
        report_sha256 = suite_report["report_sha256"]
        snapshot: JsonObject = {
            "schema_id": EVALUATION_SUITE_SNAPSHOT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": tenant_ids.pop(),
            "evaluation_suite_snapshot_id": f"evaluation-suite-snapshot:{report_sha256}",
            "suite_id": suite_report["suite_id"],
            "profile": suite_report["profile"],
            "suite_report_id": suite_report["suite_report_id"],
            "suite_sha256": suite_report["suite_sha256"],
            "report_sha256": report_sha256,
            "accepted": True,
            "repeated_baseline_equal": True,
            "task_count": suite_report["task_count"],
            "passed_task_count": suite_report["passed_task_count"],
            "failed_task_count": suite_report["failed_task_count"],
            "unscored_task_count": suite_report["unscored_task_count"],
            "task_result_ids": list(suite_report["task_result_ids"]),
            "capability_flags": dict(OFFLINE_CAPABILITY_FLAGS),
            "tasks": projected_tasks,
        }
        snapshot["snapshot_sha256"] = canonical_sha256(snapshot)
        validate_evaluation_suite_snapshot(snapshot, root)
        return snapshot
    except EvaluationReportError:
        raise
    except (
        BenchmarkValidationError,
        ContractValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise EvaluationReportError(EVALUATION_REPORT_NOT_READY) from error
