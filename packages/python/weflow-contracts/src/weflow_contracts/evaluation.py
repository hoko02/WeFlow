"""Payload-safe contracts and semantic checks for offline benchmark results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .validation import ContractValidationError, validate_payload, validate_tenant_reference

EVALUATION_TASK_SCHEMA_ID = "https://weflow.local/contracts/v1/evaluation-task.schema.json"
EVALUATION_ORACLE_SCHEMA_ID = "https://weflow.local/contracts/v1/evaluation-oracle.schema.json"
GRADER_RESULT_SCHEMA_ID = "https://weflow.local/contracts/v1/grader-result.schema.json"
RUN_METRICS_SCHEMA_ID = "https://weflow.local/contracts/v1/run-metrics.schema.json"
EVALUATION_SUITE_REPORT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/evaluation-suite-report.schema.json"
)


def canonical_sha256(value: Mapping[str, Any], *, without: str | None = None) -> str:
    """Return a stable hash without ever serializing values into an error message."""

    material = {key: item for key, item in value.items() if key != without}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_evaluation_task(task: Mapping[str, Any], root: Any = None) -> None:
    validate_payload(task, root)
    if task.get("schema_id") != EVALUATION_TASK_SCHEMA_ID:
        raise ContractValidationError("evaluation-task", "schema_identity_invalid")


def validate_evaluation_oracle(oracle: Mapping[str, Any], root: Any = None) -> None:
    validate_payload(oracle, root)
    if oracle.get("schema_id") != EVALUATION_ORACLE_SCHEMA_ID:
        raise ContractValidationError("evaluation-oracle", "schema_identity_invalid")
    weights = oracle.get("quality_weights")
    if not isinstance(weights, Mapping) or sum(weights.values()) != 100:
        raise ContractValidationError("evaluation-oracle", "quality_weights_invalid")


def validate_grader_result(result: Mapping[str, Any], root: Any = None) -> None:
    validate_payload(result, root)
    if result.get("schema_id") != GRADER_RESULT_SCHEMA_ID:
        raise ContractValidationError("grader-result", "schema_identity_invalid")
    gates = result.get("hard_gates")
    if not isinstance(gates, Sequence) or isinstance(gates, (str, bytes)):
        raise ContractValidationError("grader-result", "hard_gates_invalid")
    applicable = [gate for gate in gates if isinstance(gate, Mapping) and gate.get("applicable")]
    passed = bool(applicable) and all(gate.get("passed") is True for gate in applicable)
    if result.get("hard_gate_passed") is not passed:
        raise ContractValidationError("grader-result", "hard_gate_summary_invalid")
    quality_score = result.get("quality_score")
    if passed:
        if not isinstance(quality_score, (int, float)) or isinstance(quality_score, bool):
            raise ContractValidationError("grader-result", "quality_score_missing")
    elif quality_score != "not_scored":
        raise ContractValidationError("grader-result", "quality_score_not_scored")


def validate_run_metrics(metrics: Mapping[str, Any], root: Any = None) -> None:
    validate_payload(metrics, root)
    if metrics.get("schema_id") != RUN_METRICS_SCHEMA_ID:
        raise ContractValidationError("run-metrics", "schema_identity_invalid")


def validate_evaluation_suite_report(report: Mapping[str, Any], root: Any = None) -> None:
    validate_payload(report, root)
    if report.get("schema_id") != EVALUATION_SUITE_REPORT_SCHEMA_ID:
        raise ContractValidationError("evaluation-suite-report", "schema_identity_invalid")
    if report.get("report_sha256") != canonical_sha256(report, without="report_sha256"):
        raise ContractValidationError("evaluation-suite-report", "report_sha256_mismatch")
    task_count = report.get("task_count")
    result_ids = report.get("task_result_ids")
    if (
        not isinstance(task_count, int)
        or not isinstance(result_ids, list)
        or task_count != len(result_ids)
    ):
        raise ContractValidationError("evaluation-suite-report", "task_count_invalid")
    counts = (
        report.get("passed_task_count"),
        report.get("failed_task_count"),
        report.get("unscored_task_count"),
    )
    if not all(isinstance(count, int) for count in counts) or sum(counts) != task_count:
        raise ContractValidationError("evaluation-suite-report", "result_counts_invalid")


def validate_benchmark_result(
    evaluation_case: Mapping[str, Any],
    evaluation_result: Mapping[str, Any],
    task: Mapping[str, Any],
    oracle: Mapping[str, Any],
    grader_result: Mapping[str, Any],
    metrics: Mapping[str, Any],
    suite_report: Mapping[str, Any],
    root: Any = None,
) -> None:
    """Validate the hash-bound benchmark-core profile across all safe records."""

    for record in (evaluation_case, evaluation_result):
        validate_payload(record, root)
    validate_evaluation_task(task, root)
    validate_evaluation_oracle(oracle, root)
    validate_grader_result(grader_result, root)
    validate_run_metrics(metrics, root)
    validate_evaluation_suite_report(suite_report, root)

    records = (evaluation_case, evaluation_result, task, oracle, grader_result, metrics)
    validate_tenant_reference(*records)
    task_id = task["evaluation_task_id"]
    task_sha256 = canonical_sha256(task)
    oracle_sha256 = canonical_sha256(oracle)
    if oracle.get("evaluation_task_id") != task_id:
        raise ContractValidationError("evaluation-benchmark", "oracle_task_mismatch")
    expected = {
        "benchmark_profile": "benchmark-core.v1",
        "suite_id": task["suite_id"],
        "evaluation_task_id": task_id,
        "task_sha256": task_sha256,
        "oracle_sha256": oracle_sha256,
    }
    for record in (evaluation_case, evaluation_result):
        for key, value in expected.items():
            if record.get(key) != value:
                raise ContractValidationError("evaluation-benchmark", f"{key}_mismatch")
    for key in ("suite_id", "evaluation_task_id", "task_sha256", "oracle_sha256"):
        if grader_result.get(key) != expected[key]:
            raise ContractValidationError("evaluation-benchmark", f"grader_{key}_mismatch")
    if metrics.get("suite_id") != task["suite_id"] or metrics.get("evaluation_task_id") != task_id:
        raise ContractValidationError("evaluation-benchmark", "metrics_link_mismatch")
    if grader_result.get("run_id") != metrics.get("run_id"):
        raise ContractValidationError("evaluation-benchmark", "run_identity_mismatch")
    if evaluation_result.get("grader_result_id") != grader_result.get("grader_result_id"):
        raise ContractValidationError("evaluation-benchmark", "grader_link_mismatch")
    if evaluation_result.get("run_metrics_id") != metrics.get("run_metrics_id"):
        raise ContractValidationError("evaluation-benchmark", "metrics_link_mismatch")
    if evaluation_result.get("suite_report_id") != suite_report.get("suite_report_id"):
        raise ContractValidationError("evaluation-benchmark", "report_link_mismatch")
    if evaluation_result.get("report_sha256") != suite_report.get("report_sha256"):
        raise ContractValidationError("evaluation-benchmark", "report_hash_mismatch")
    if evaluation_result.get("evaluation_case_id") != evaluation_case.get("evaluation_case_id"):
        raise ContractValidationError("evaluation-benchmark", "evaluation_case_mismatch")
    if evaluation_result.get("hard_gate_passed") is not grader_result.get("hard_gate_passed"):
        raise ContractValidationError("evaluation-benchmark", "hard_gate_result_mismatch")
    if evaluation_result.get("quality_score") != grader_result.get("quality_score"):
        raise ContractValidationError("evaluation-benchmark", "quality_score_mismatch")
    if evaluation_result.get("capability_flags") != grader_result.get("capability_flags"):
        raise ContractValidationError("evaluation-benchmark", "capability_flags_mismatch")
    if evaluation_result.get("evaluation_result_id") not in suite_report.get("task_result_ids", []):
        raise ContractValidationError("evaluation-benchmark", "suite_result_missing")
