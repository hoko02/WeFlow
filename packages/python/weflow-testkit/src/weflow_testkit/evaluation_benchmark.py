"""Deterministic, fixture-local evaluation benchmark helpers."""

from __future__ import annotations

import hashlib
import importlib
import json
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from weflow_contracts import ContractValidationError
from weflow_contracts.evaluation import (
    EVALUATION_SUITE_REPORT_SCHEMA_ID,
    GRADER_RESULT_SCHEMA_ID,
    RUN_METRICS_SCHEMA_ID,
    canonical_sha256,
    validate_benchmark_result,
    validate_evaluation_oracle,
    validate_evaluation_suite_report,
    validate_evaluation_task,
    validate_grader_result,
    validate_run_metrics,
)

from .benchmark_observation import (
    OFFLINE_CAPABILITY_FLAGS,
    BenchmarkObservation,
    validate_benchmark_observation,
)

JsonObject = dict[str, Any]
CAPABILITY_FLAGS: JsonObject = dict(OFFLINE_CAPABILITY_FLAGS)
FORBIDDEN_INPUT_TOKENS = (
    "raw_message",
    "raw_payload",
    "private prompt",
    "provider_token",
    "caller_role",
    "customer_resolved",
)


class BenchmarkValidationError(ValueError):
    """An evaluation-input failure that never includes source payloads."""


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    loaded: JsonObject = {}
    for key, value in pairs:
        if key in loaded:
            raise BenchmarkValidationError("benchmark_input_invalid")
        loaded[key] = value
    return loaded


def _load_json(path: Path) -> JsonObject:
    try:
        loaded = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, json.JSONDecodeError, UnicodeError) as error:
        raise BenchmarkValidationError("benchmark_input_invalid") from error
    if not isinstance(loaded, dict):
        raise BenchmarkValidationError("benchmark_input_invalid")
    return loaded


def _contains_forbidden(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            token in str(key).lower() or _contains_forbidden(item)
            for key, item in value.items()
            for token in FORBIDDEN_INPUT_TOKENS
        )
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _require_safe_source_path(relative_path: object) -> PurePosixPath:
    if not isinstance(relative_path, str) or "\\" in relative_path:
        raise BenchmarkValidationError("benchmark_source_path_unsafe")
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise BenchmarkValidationError("benchmark_source_path_unsafe")
    return pure


def _resolve_source(
    root: Path,
    relative_path: object,
    *,
    allowed_directory: str,
    expected_id: object,
    expected_hash: object,
    identity_field: str,
) -> tuple[JsonObject, str]:
    pure = _require_safe_source_path(relative_path)
    allowed_root = (root / allowed_directory).resolve()
    source_path = (root / Path(*pure.parts)).resolve()
    try:
        source_path.relative_to(allowed_root)
    except ValueError as error:
        raise BenchmarkValidationError("benchmark_source_path_unsafe") from error
    try:
        source = _load_json(source_path)
    except BenchmarkValidationError as error:
        raise BenchmarkValidationError("benchmark_source_invalid") from error
    if _contains_forbidden(source):
        raise BenchmarkValidationError("benchmark_source_unsafe")
    if not isinstance(expected_id, str) or source.get(identity_field) != expected_id:
        raise BenchmarkValidationError("benchmark_source_identity_mismatch")
    source_hash = _sha256(source)
    if not isinstance(expected_hash, str) or source_hash != expected_hash:
        raise BenchmarkValidationError("benchmark_source_hash_mismatch")
    return source, relative_path


def _validate_policy_source(task: JsonObject, policy: JsonObject) -> None:
    allowed_adapters = policy.get("allowed_adapters")
    if (
        policy.get("tenant_id") != task.get("tenant_id")
        or policy.get("mode") != "offline"
        or not isinstance(allowed_adapters, list)
        or task.get("execution_adapter") not in allowed_adapters
        or policy.get("capability_flags") != CAPABILITY_FLAGS
    ):
        raise BenchmarkValidationError("benchmark_policy_source_mismatch")


def _validate_fixture_source(task: JsonObject, fixture: JsonObject) -> None:
    tenant_id = fixture.get("tenant_id")
    if tenant_id is not None and tenant_id != task.get("tenant_id"):
        raise BenchmarkValidationError("benchmark_source_tenant_mismatch")


def load_offline_seed_suite(
    root: Path, suite_name: str = "offline-seed.v1.json"
) -> tuple[JsonObject, list[JsonObject]]:
    """Load only safe, canonical task directories before any task-store allocation."""

    suite = _load_json(root / "evals" / "suites" / suite_name)
    if _contains_forbidden(suite):
        raise BenchmarkValidationError("benchmark_suite_unsafe")
    tasks = suite.get("tasks")
    if (
        suite.get("suite_id") != "offline-seed.v1"
        or suite.get("profile") != "benchmark-core.v1"
        or not isinstance(tasks, list)
        or len(tasks) != 12
    ):
        raise BenchmarkValidationError("benchmark_suite_invalid")

    loaded: list[JsonObject] = []
    seen: set[str] = set()
    for item in tasks:
        if not isinstance(item, Mapping):
            raise BenchmarkValidationError("benchmark_suite_invalid")
        task_id = item.get("evaluation_task_id")
        if not isinstance(task_id, str) or task_id in seen:
            raise BenchmarkValidationError("benchmark_task_duplicate")
        seen.add(task_id)
        directory = root / "evals" / "tasks" / task_id
        if (directory / "fixture.json").exists() or (directory / "policy.json").exists():
            raise BenchmarkValidationError("benchmark_task_local_mirror_forbidden")
        task = _load_json(directory / "task.json")
        oracle = _load_json(directory / "oracle.json")
        if _contains_forbidden(task) or _contains_forbidden(oracle):
            raise BenchmarkValidationError("benchmark_task_unsafe")
        for source_path_key in ("fixture_source_path", "policy_source_path"):
            _require_safe_source_path(task.get(source_path_key))
        try:
            validate_evaluation_task(task, root)
            validate_evaluation_oracle(oracle, root)
        except ContractValidationError as error:
            raise BenchmarkValidationError("benchmark_contract_invalid") from error
        if task.get("evaluation_task_id") != task_id or task.get("suite_id") != suite["suite_id"]:
            raise BenchmarkValidationError("benchmark_task_identity_mismatch")
        if oracle.get("evaluation_task_id") != task_id or oracle.get("tenant_id") != task.get(
            "tenant_id"
        ):
            raise BenchmarkValidationError("benchmark_oracle_mismatch")
        fixture, fixture_source_path = _resolve_source(
            root,
            task.get("fixture_source_path"),
            allowed_directory="fixtures",
            expected_id=task.get("fixture_source_id"),
            expected_hash=task.get("fixture_sha256"),
            identity_field="fixture_id",
        )
        policy, policy_source_path = _resolve_source(
            root,
            task.get("policy_source_path"),
            allowed_directory="evals/sources",
            expected_id=task.get("policy_source_id"),
            expected_hash=task.get("policy_sha256"),
            identity_field="policy_id",
        )
        _validate_fixture_source(task, fixture)
        _validate_policy_source(task, policy)
        loaded.append(
            {
                "task": task,
                "oracle": oracle,
                "fixture": fixture,
                "policy": policy,
                "fixture_source_path": fixture_source_path,
                "policy_source_path": policy_source_path,
            }
        )
    return suite, loaded


def _load_acceptance_module(root: Path, module_name: str) -> Any:
    scripts_path = str(root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    return importlib.import_module(module_name)


PUBLIC_ADAPTERS: Mapping[str, tuple[str, str]] = {
    "case-intake": (
        "case_intake_acceptance",
        "run_case_intake_benchmark_observation",
    ),
    "durable-workflow": (
        "durable_workflow_acceptance",
        "run_durable_workflow_benchmark_observation",
    ),
    "investigation-agent": (
        "investigation_agent_acceptance",
        "run_investigation_benchmark_observation",
    ),
    "policy-approval": (
        "policy_approval_acceptance",
        "run_policy_approval_benchmark_observation",
    ),
    "evidence-trajectory": (
        "evidence_trajectory_acceptance",
        "run_evidence_trajectory_benchmark_observation",
    ),
}


def _observe_task(root: Path, record: JsonObject, store_path: Path) -> BenchmarkObservation:
    """Invoke one public adapter and accept only its closed, typed safe facts."""

    task = record["task"]
    adapter_spec = PUBLIC_ADAPTERS.get(str(task.get("execution_adapter")))
    if adapter_spec is None:
        raise BenchmarkValidationError("benchmark_adapter_unsupported")
    module_name, function_name = adapter_spec
    if function_name.startswith("_"):
        raise BenchmarkValidationError("benchmark_adapter_not_public")
    module = _load_acceptance_module(root, module_name)
    adapter = getattr(module, function_name, None)
    if not callable(adapter):
        raise BenchmarkValidationError("benchmark_adapter_not_public")
    try:
        observation = adapter(root, task, record["fixture"], store_path)
        validate_benchmark_observation(observation)
    except (KeyError, TypeError, ValueError) as error:
        raise BenchmarkValidationError("benchmark_observation_invalid") from error
    return observation


def _grade(
    task: JsonObject, oracle: JsonObject, observation: JsonObject, run_id: str
) -> tuple[JsonObject, JsonObject]:
    required_gates = set(oracle["required_hard_gates"])
    checks = {
        "tenant_reference": observation["tenant_id"] == task["tenant_id"],
        "offline_replay": all(
            observation[key] == expected for key, expected in CAPABILITY_FLAGS.items()
        ),
        "external_write_absent": observation["external_write"] is False,
        "local_effect_identity": observation["local_effect_count"]
        == oracle["expected_local_effect_count"],
        "approval_binding": observation["approval_valid"] is True,
        "evidence_lineage": observation["evidence_valid"] is True,
        "expected_outcome": observation["outcome"] == oracle["expected_outcome"],
    }
    hard_gates = [
        {
            "name": name,
            "applicable": name in required_gates,
            "passed": checks[name] if name in required_gates else True,
            "reason_code": "passed"
            if checks[name] or name not in required_gates
            else f"{name}_failed",
        }
        for name in (
            "tenant_reference",
            "offline_replay",
            "external_write_absent",
            "local_effect_identity",
            "approval_binding",
            "evidence_lineage",
            "expected_outcome",
        )
    ]
    hard_gate_passed = all(item["passed"] for item in hard_gates if item["applicable"])
    dimensions = []
    for name, weight in oracle["quality_weights"].items():
        dimensions.append({"name": name, "score": 100 if hard_gate_passed else 0, "weight": weight})
    quality_score: int | str = 100 if hard_gate_passed else "not_scored"
    task_hash = canonical_sha256(task)
    oracle_hash = canonical_sha256(oracle)
    grader_result: JsonObject = {
        "schema_id": GRADER_RESULT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "grader_result_id": f"grader:{run_id}:{task['evaluation_task_id']}",
        "suite_id": task["suite_id"],
        "run_id": run_id,
        "evaluation_task_id": task["evaluation_task_id"],
        "task_sha256": task_hash,
        "oracle_sha256": oracle_hash,
        "hard_gates": hard_gates,
        "hard_gate_passed": hard_gate_passed,
        "dimensions": [{"name": item["name"], "score": item["score"]} for item in dimensions],
        "quality_score": quality_score,
        "result": "passed" if hard_gate_passed else "failed",
        "failure_classification": None if hard_gate_passed else "hard_gate_failed",
        "capability_flags": dict(CAPABILITY_FLAGS),
    }
    metrics: JsonObject = {
        "schema_id": RUN_METRICS_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "run_metrics_id": f"metrics:{run_id}:{task['evaluation_task_id']}",
        "suite_id": task["suite_id"],
        "run_id": run_id,
        "evaluation_task_id": task["evaluation_task_id"],
        "tool_call_count": observation["tool_call_count"],
        "local_effect_count": observation["local_effect_count"],
        "network_request_count": 0,
        "model_invocation_count": 0,
        "external_write_attempt_count": 0,
    }
    validate_grader_result(grader_result)
    validate_run_metrics(metrics)
    return grader_result, metrics


def _evaluation_result_id(run_id: str, task: JsonObject) -> str:
    return f"evaluation-result:{run_id}:{task['evaluation_task_id']}"


def _materialize_evaluation_case(task: JsonObject, oracle: JsonObject, run_id: str) -> JsonObject:
    return {
        "schema_id": "https://weflow.local/contracts/v1/evaluation-case.schema.json",
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "evaluation_case_id": f"evaluation-case:{run_id}:{task['evaluation_task_id']}",
        "fixture_id": task["fixture_id"],
        "input_hash": task["fixture_sha256"],
        "created_at": task["created_at"],
        "oracle_id": oracle["oracle_id"],
        "benchmark_profile": "benchmark-core.v1",
        "suite_id": task["suite_id"],
        "evaluation_task_id": task["evaluation_task_id"],
        "task_sha256": canonical_sha256(task),
        "oracle_sha256": canonical_sha256(oracle),
    }


def _materialize_evaluation_result(
    task: JsonObject,
    grader_result: JsonObject,
    metrics: JsonObject,
    evaluation_case: JsonObject,
    suite_report: JsonObject,
    run_id: str,
) -> JsonObject:
    return {
        "schema_id": "https://weflow.local/contracts/v1/evaluation-result.schema.json",
        "schema_version": "v1",
        "tenant_id": task["tenant_id"],
        "evaluation_result_id": _evaluation_result_id(run_id, task),
        "evaluation_case_id": evaluation_case["evaluation_case_id"],
        "result": grader_result["result"],
        "recorded_at": task["created_at"],
        "failure_classification": grader_result["failure_classification"],
        "benchmark_profile": "benchmark-core.v1",
        "suite_id": task["suite_id"],
        "evaluation_task_id": task["evaluation_task_id"],
        "task_sha256": canonical_sha256(task),
        "oracle_sha256": grader_result["oracle_sha256"],
        "hard_gate_passed": grader_result["hard_gate_passed"],
        "grader_result_id": grader_result["grader_result_id"],
        "run_metrics_id": metrics["run_metrics_id"],
        "suite_report_id": suite_report["suite_report_id"],
        "report_sha256": suite_report["report_sha256"],
        "quality_score": grader_result["quality_score"],
        "capability_flags": dict(CAPABILITY_FLAGS),
    }


def validate_retained_benchmark_diagnostic(
    root: Path,
    record: JsonObject,
    diagnostic: Mapping[str, object],
    suite_report: JsonObject,
) -> None:
    """Revalidate one retained diagnostic without executing its adapter."""

    expected_keys = {
        "evaluation_task_id",
        "fixture_id",
        "fixture_source_path",
        "fixture_sha256",
        "policy_source_path",
        "policy_sha256",
        "task_sha256",
        "oracle_sha256",
        "observation",
        "evaluation_case",
        "grader_result",
        "metrics",
        "evaluation_result",
    }
    if set(diagnostic) != expected_keys:
        raise BenchmarkValidationError("benchmark_report_integrity_invalid")

    task = record["task"]
    oracle = record["oracle"]
    expected_metadata = {
        "evaluation_task_id": task["evaluation_task_id"],
        "fixture_id": task["fixture_id"],
        "fixture_source_path": record["fixture_source_path"],
        "fixture_sha256": task["fixture_sha256"],
        "policy_source_path": record["policy_source_path"],
        "policy_sha256": task["policy_sha256"],
        "task_sha256": canonical_sha256(task),
        "oracle_sha256": canonical_sha256(oracle),
    }
    if any(diagnostic.get(key) != value for key, value in expected_metadata.items()):
        raise BenchmarkValidationError("benchmark_report_integrity_invalid")

    observation = diagnostic.get("observation")
    grader_result = diagnostic.get("grader_result")
    metrics = diagnostic.get("metrics")
    evaluation_case = diagnostic.get("evaluation_case")
    evaluation_result = diagnostic.get("evaluation_result")
    if not all(
        isinstance(item, dict)
        for item in (
            observation,
            grader_result,
            metrics,
            evaluation_case,
            evaluation_result,
        )
    ):
        raise BenchmarkValidationError("benchmark_report_integrity_invalid")
    try:
        validate_benchmark_observation(observation)
    except ValueError as error:
        raise BenchmarkValidationError("benchmark_report_integrity_invalid") from error
    if (
        observation.get("tenant_id") != task["tenant_id"]
        or not all(observation.get(key) is value for key, value in CAPABILITY_FLAGS.items())
        or not isinstance(observation.get("tool_call_count"), int)
        or isinstance(observation.get("tool_call_count"), bool)
        or not isinstance(observation.get("local_effect_count"), int)
        or isinstance(observation.get("local_effect_count"), bool)
    ):
        raise BenchmarkValidationError("benchmark_report_integrity_invalid")

    run_id = grader_result.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise BenchmarkValidationError("benchmark_report_integrity_invalid")
    expected_grader, expected_metrics = _grade(task, oracle, observation, run_id)
    expected_case = _materialize_evaluation_case(task, oracle, run_id)
    expected_result = _materialize_evaluation_result(
        task,
        expected_grader,
        expected_metrics,
        expected_case,
        suite_report,
        run_id,
    )
    if (
        grader_result != expected_grader
        or metrics != expected_metrics
        or evaluation_case != expected_case
        or evaluation_result != expected_result
    ):
        raise BenchmarkValidationError("benchmark_report_integrity_invalid")
    try:
        validate_benchmark_result(
            evaluation_case,
            evaluation_result,
            task,
            oracle,
            grader_result,
            metrics,
            suite_report,
            root,
        )
    except ContractValidationError as error:
        raise BenchmarkValidationError("benchmark_report_integrity_invalid") from error


def run_offline_seed_suite(
    root: Path, *, configuration: Mapping[str, object] | None = None, run_id: str = "run-a"
) -> JsonObject:
    """Execute all 12 checked-in tasks without enabling a provider or external effect."""

    if configuration not in (None, {}, {"mode": "offline"}):
        raise BenchmarkValidationError("offline_benchmark_configuration_denied")
    suite, records = load_offline_seed_suite(root)
    executions: list[JsonObject] = []
    for record in records:
        task = record["task"]
        with TemporaryDirectory(prefix="weflow-evaluation-task-") as temporary:
            store_path = Path(temporary) / "fixture.sqlite3"
            sqlite3.connect(store_path).close()
            observation = _observe_task(root, record, store_path)
        grader_result, metrics = _grade(task, record["oracle"], observation, run_id)
        executions.append(
            {
                "record": record,
                "observation": observation,
                "grader_result": grader_result,
                "metrics": metrics,
                "evaluation_case": _materialize_evaluation_case(task, record["oracle"], run_id),
            }
        )
    passed = sum(item["grader_result"]["result"] == "passed" for item in executions)
    unscored = sum(item["grader_result"]["quality_score"] == "not_scored" for item in executions)
    failed = len(executions) - passed - unscored
    report: JsonObject = {
        "schema_id": EVALUATION_SUITE_REPORT_SCHEMA_ID,
        "schema_version": "v1",
        "suite_report_id": f"report:{suite['suite_id']}:{run_id}",
        "suite_id": suite["suite_id"],
        "suite_sha256": _sha256(suite),
        "profile": "benchmark-core.v1",
        "task_count": len(executions),
        "passed_task_count": passed,
        "failed_task_count": failed,
        "unscored_task_count": unscored,
        "task_result_ids": [
            _evaluation_result_id(run_id, item["record"]["task"]) for item in executions
        ],
        "capability_flags": dict(CAPABILITY_FLAGS),
    }
    report["report_sha256"] = canonical_sha256(report)
    validate_evaluation_suite_report(report, root)

    diagnostics: list[JsonObject] = []
    for execution in executions:
        record = execution["record"]
        task = record["task"]
        evaluation_result = _materialize_evaluation_result(
            task,
            execution["grader_result"],
            execution["metrics"],
            execution["evaluation_case"],
            report,
            run_id,
        )
        validate_benchmark_result(
            execution["evaluation_case"],
            evaluation_result,
            task,
            record["oracle"],
            execution["grader_result"],
            execution["metrics"],
            report,
            root,
        )
        diagnostics.append(
            {
                "evaluation_task_id": task["evaluation_task_id"],
                "fixture_id": task["fixture_id"],
                "fixture_source_path": record["fixture_source_path"],
                "fixture_sha256": task["fixture_sha256"],
                "policy_source_path": record["policy_source_path"],
                "policy_sha256": task["policy_sha256"],
                "task_sha256": canonical_sha256(task),
                "oracle_sha256": canonical_sha256(record["oracle"]),
                "observation": execution["observation"],
                "evaluation_case": execution["evaluation_case"],
                "grader_result": execution["grader_result"],
                "metrics": execution["metrics"],
                "evaluation_result": evaluation_result,
            }
        )
    return {"suite_report": report, "task_diagnostics": diagnostics}


def run_evaluation_benchmark_acceptance(
    root: Path, *, configuration: Mapping[str, object] | None = None
) -> JsonObject:
    baseline_a = run_offline_seed_suite(root, configuration=configuration, run_id="baseline")
    baseline_b = run_offline_seed_suite(root, configuration=configuration, run_id="baseline")
    if baseline_a != baseline_b:
        raise BenchmarkValidationError("benchmark_baseline_nondeterministic")
    report: JsonObject = {
        "report_type": "weflow-change-6-evaluation-benchmark-core-acceptance.v1",
        "accepted": baseline_a["suite_report"]["passed_task_count"] == 12,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "suite_report": baseline_a["suite_report"],
        "task_diagnostics": baseline_a["task_diagnostics"],
        "determinism": {"repeated_baseline_equal": True, "intentional_nondeterministic_fields": []},
        "capabilities": {
            "offline_evaluation_benchmark_core_implemented": True,
            "live_model_enabled": False,
            "external_writes_enabled": False,
            "customer_resolution_enabled": False,
            "multi_agent_enabled": False,
            "planned_live_runs": 0,
            "planned_task_count": 60,
        },
    }
    rendered = _canonical(report)
    if any(token in rendered for token in FORBIDDEN_INPUT_TOKENS):
        raise BenchmarkValidationError("benchmark_report_not_redacted")
    if report["accepted"] is not True:
        raise BenchmarkValidationError("benchmark_acceptance_failed")
    return report
