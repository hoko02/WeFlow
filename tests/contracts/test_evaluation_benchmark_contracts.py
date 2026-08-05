from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from weflow_contracts import ContractValidationError, validate_payload
from weflow_contracts.evaluation import (
    EVALUATION_SUITE_REPORT_SCHEMA_ID,
    GRADER_RESULT_SCHEMA_ID,
    RUN_METRICS_SCHEMA_ID,
    canonical_sha256,
    validate_benchmark_result,
    validate_grader_result,
)
from weflow_testkit.evaluation_benchmark import CAPABILITY_FLAGS, load_offline_seed_suite

ROOT = Path(__file__).resolve().parents[2]


def _records() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    _, records = load_offline_seed_suite(ROOT)
    first = records[0]
    return first["task"], first["oracle"], first["fixture"]


def _linked_records() -> tuple[dict[str, object], ...]:
    task, oracle, _fixture = _records()
    task_hash = canonical_sha256(task)
    oracle_hash = canonical_sha256(oracle)
    gates = [
        {"name": name, "applicable": True, "passed": True, "reason_code": "passed"}
        for name in oracle["required_hard_gates"]
    ]
    grader = {
        "schema_id": GRADER_RESULT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "grader_result_id": "grader-contract-001",
        "suite_id": task["suite_id"],
        "run_id": "contract-run-001",
        "evaluation_task_id": task["evaluation_task_id"],
        "task_sha256": task_hash,
        "oracle_sha256": oracle_hash,
        "hard_gates": gates,
        "hard_gate_passed": True,
        "dimensions": [{"name": name, "score": 100} for name in oracle["quality_weights"]],
        "quality_score": 100,
        "result": "passed",
        "failure_classification": None,
        "capability_flags": dict(CAPABILITY_FLAGS),
    }
    metrics = {
        "schema_id": RUN_METRICS_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "run_metrics_id": "metrics-contract-001",
        "suite_id": task["suite_id"],
        "run_id": "contract-run-001",
        "evaluation_task_id": task["evaluation_task_id"],
        "tool_call_count": 0,
        "local_effect_count": 0,
        "network_request_count": 0,
        "model_invocation_count": 0,
        "external_write_attempt_count": 0,
    }
    evaluation_result_id = "evaluation-result-contract-001"
    report = {
        "schema_id": EVALUATION_SUITE_REPORT_SCHEMA_ID,
        "schema_version": "v1",
        "suite_report_id": "suite-report-contract-001",
        "suite_id": task["suite_id"],
        "suite_sha256": "e" * 64,
        "profile": "benchmark-core.v1",
        "task_count": 1,
        "passed_task_count": 1,
        "failed_task_count": 0,
        "unscored_task_count": 0,
        "task_result_ids": [evaluation_result_id],
        "capability_flags": dict(CAPABILITY_FLAGS),
    }
    report["report_sha256"] = canonical_sha256(report)
    evaluation_case = {
        "schema_id": "https://weflow.local/contracts/v1/evaluation-case.schema.json",
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "evaluation_case_id": "evaluation-case-contract-001",
        "fixture_id": task["fixture_id"],
        "input_hash": task["fixture_sha256"],
        "created_at": "2026-08-05T00:00:00Z",
        "oracle_id": oracle["oracle_id"],
        "benchmark_profile": "benchmark-core.v1",
        "suite_id": task["suite_id"],
        "evaluation_task_id": task["evaluation_task_id"],
        "task_sha256": task_hash,
        "oracle_sha256": oracle_hash,
    }
    evaluation_result = {
        "schema_id": "https://weflow.local/contracts/v1/evaluation-result.schema.json",
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "evaluation_result_id": evaluation_result_id,
        "evaluation_case_id": evaluation_case["evaluation_case_id"],
        "result": "passed",
        "recorded_at": "2026-08-05T00:00:00Z",
        "failure_classification": None,
        "benchmark_profile": "benchmark-core.v1",
        "suite_id": task["suite_id"],
        "evaluation_task_id": task["evaluation_task_id"],
        "task_sha256": task_hash,
        "oracle_sha256": oracle_hash,
        "hard_gate_passed": True,
        "grader_result_id": grader["grader_result_id"],
        "run_metrics_id": metrics["run_metrics_id"],
        "suite_report_id": report["suite_report_id"],
        "report_sha256": report["report_sha256"],
        "quality_score": 100,
        "capability_flags": dict(CAPABILITY_FLAGS),
    }
    return evaluation_case, evaluation_result, task, oracle, grader, metrics, report


def test_seed_task_and_oracle_contracts_validate() -> None:
    _, records = load_offline_seed_suite(ROOT)

    assert len(records) == 12
    for record in records:
        validate_payload(record["task"], ROOT)
        validate_payload(record["oracle"], ROOT)


def test_benchmark_profile_is_hash_bound_and_cross_record_safe() -> None:
    validate_benchmark_result(*_linked_records(), ROOT)


def test_hard_gate_failure_cannot_keep_a_numeric_quality_score() -> None:
    *_, grader, _metrics, _report = _linked_records()
    invalid = deepcopy(grader)
    invalid["hard_gates"][0]["passed"] = False
    invalid["hard_gate_passed"] = False
    invalid["quality_score"] = 100

    with pytest.raises(ContractValidationError, match="quality_score_not_scored"):
        validate_grader_result(invalid, ROOT)


def test_unsafe_task_field_is_rejected_before_execution() -> None:
    invalid = json.loads(
        (
            ROOT
            / "fixtures"
            / "contracts"
            / "v1"
            / "invalid"
            / "evaluation-benchmark-invalid-payloads.json"
        ).read_text()
    )["raw_task_field"]

    with pytest.raises(ContractValidationError):
        validate_payload(invalid, ROOT)


def test_detached_suite_report_link_is_rejected() -> None:
    records = list(_linked_records())
    records[1] = deepcopy(records[1])
    records[1]["suite_report_id"] = "suite-report-detached"

    with pytest.raises(ContractValidationError, match="report_link_mismatch"):
        validate_benchmark_result(*records, ROOT)


def test_mismatched_evaluation_case_source_is_rejected() -> None:
    records = list(_linked_records())
    records[0] = deepcopy(records[0])
    records[0]["input_hash"] = "f" * 64

    with pytest.raises(ContractValidationError, match="evaluation_case_source_mismatch"):
        validate_benchmark_result(*records, ROOT)


def test_cross_task_metrics_link_is_rejected() -> None:
    records = list(_linked_records())
    records[5] = deepcopy(records[5])
    records[5]["evaluation_task_id"] = "another-task"

    with pytest.raises(ContractValidationError, match="metrics_link_mismatch"):
        validate_benchmark_result(*records, ROOT)


def test_failed_hard_gate_forms_a_complete_unscored_result_chain() -> None:
    evaluation_case, evaluation_result, task, oracle, grader, metrics, report = deepcopy(
        _linked_records()
    )
    grader["hard_gates"][0]["passed"] = False
    grader["hard_gates"][0]["reason_code"] = "tenant_reference_failed"
    grader["hard_gate_passed"] = False
    grader["quality_score"] = "not_scored"
    grader["result"] = "failed"
    grader["failure_classification"] = "hard_gate_failed"
    report["passed_task_count"] = 0
    report["failed_task_count"] = 0
    report["unscored_task_count"] = 1
    report["report_sha256"] = canonical_sha256(report, without="report_sha256")
    evaluation_result["hard_gate_passed"] = False
    evaluation_result["quality_score"] = "not_scored"
    evaluation_result["result"] = "failed"
    evaluation_result["failure_classification"] = "hard_gate_failed"
    evaluation_result["report_sha256"] = report["report_sha256"]

    validate_benchmark_result(
        evaluation_case,
        evaluation_result,
        task,
        oracle,
        grader,
        metrics,
        report,
        ROOT,
    )
