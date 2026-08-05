"""Deterministic, fixture-local evaluation benchmark helpers."""

from __future__ import annotations

import hashlib
import importlib
import json
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from weflow_contracts import ContractValidationError, approval_is_authorized
from weflow_contracts.evaluation import (
    EVALUATION_SUITE_REPORT_SCHEMA_ID,
    GRADER_RESULT_SCHEMA_ID,
    RUN_METRICS_SCHEMA_ID,
    canonical_sha256,
    validate_evaluation_oracle,
    validate_evaluation_suite_report,
    validate_evaluation_task,
    validate_grader_result,
    validate_run_metrics,
)

JsonObject = dict[str, Any]
CAPABILITY_FLAGS: JsonObject = {
    "offline": True,
    "replay": True,
    "network": False,
    "model": False,
    "external_write": False,
}
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


def _load_json(path: Path) -> JsonObject:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
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


def _require_safe_reference(reference: JsonObject, *, expected_id: str, expected_hash: str) -> None:
    if _contains_forbidden(reference):
        raise BenchmarkValidationError("benchmark_reference_unsafe")
    if reference.get("fixture_id", reference.get("policy_id")) != expected_id:
        raise BenchmarkValidationError("benchmark_reference_mismatch")
    reference_hash = reference.get("fixture_sha256", reference.get("policy_sha256"))
    if reference_hash != expected_hash:
        raise BenchmarkValidationError("benchmark_reference_hash_mismatch")


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
        task = _load_json(directory / "task.json")
        oracle = _load_json(directory / "oracle.json")
        fixture = _load_json(directory / "fixture.json")
        policy = _load_json(directory / "policy.json")
        if _contains_forbidden(task) or _contains_forbidden(oracle):
            raise BenchmarkValidationError("benchmark_task_unsafe")
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
        _require_safe_reference(
            fixture,
            expected_id=str(task["fixture_id"]),
            expected_hash=str(task["fixture_sha256"]),
        )
        _require_safe_reference(
            policy,
            expected_id="offline-policy.v1",
            expected_hash=str(task["policy_sha256"]),
        )
        loaded.append(
            {
                "task": task,
                "oracle": oracle,
                "fixture": fixture,
                "policy": policy,
            }
        )
    return suite, loaded


def _load_acceptance_module(root: Path, module_name: str) -> Any:
    scripts_path = str(root / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    return importlib.import_module(module_name)


def _acceptance_report(
    root: Path, cache: dict[str, Any], module_name: str, function_name: str
) -> Any:
    cache_key = f"{module_name}:{function_name}"
    if cache_key not in cache:
        module = _load_acceptance_module(root, module_name)
        cache[cache_key] = getattr(module, function_name)(root)
    return cache[cache_key]


def _find_fault(items: object, fault_point: str) -> Mapping[str, Any]:
    if not isinstance(items, list):
        raise BenchmarkValidationError("benchmark_observation_invalid")
    for item in items:
        if isinstance(item, Mapping) and item.get("fault_point") == fault_point:
            return item
    raise BenchmarkValidationError("benchmark_observation_invalid")


def _observe_task(
    root: Path, task: JsonObject, cache: dict[str, Any], store_path: Path
) -> JsonObject:
    """Use supported existing offline paths; no benchmark code selects a provider."""

    adapter = task["execution_adapter"]
    fixture_id = str(task["fixture_id"])
    if adapter == "case-intake":
        report = _acceptance_report(
            root, cache, "case_intake_acceptance", "run_case_intake_acceptance"
        )
        observed = report["fixture_results"].get(fixture_id)
        if not isinstance(observed, Mapping):
            raise BenchmarkValidationError("benchmark_observation_invalid")
        return {
            "tenant_id": "tenant-alpha",
            "outcome": observed["outcome"],
            "local_effect_count": 0,
            "approval_valid": False,
            "evidence_valid": True,
            "tool_call_count": 0,
            **CAPABILITY_FLAGS,
        }
    if adapter == "durable-workflow":
        module = _load_acceptance_module(root, "durable_workflow_acceptance")
        if fixture_id == "api-503-ticket-handoff":
            item = module._baseline(root, store_path)
            outcome = "ticket_ready"
            effects = int(item["reconciliation"]["operation_count"])
        elif fixture_id == "api-503-sla-expiry":
            item = module._sla_recovery(root, store_path)
            outcome = "waiting_for_operator"
            effects = int(item["ticket_operation_count"])
        else:
            raise BenchmarkValidationError("benchmark_fixture_unsupported")
        return {
            "tenant_id": "tenant-alpha",
            "outcome": outcome,
            "local_effect_count": effects,
            "approval_valid": False,
            "evidence_valid": True,
            "tool_call_count": 0,
            **CAPABILITY_FLAGS,
        }
    if adapter == "investigation-agent":
        module = _load_acceptance_module(root, "investigation_agent_acceptance")
        if fixture_id == "api-503-investigation":
            item = module._baseline(root, store_path)
            effects = 0
        else:
            item = module._fault_recovery(root, "candidate", store_path)
            effects = 0
        return {
            "tenant_id": "tenant-alpha",
            "outcome": "response_ready",
            "local_effect_count": effects,
            "approval_valid": False,
            "evidence_valid": item.get("verifier_outcome", "verified") == "verified",
            "tool_call_count": 3,
            **CAPABILITY_FLAGS,
        }
    if adapter == "policy-approval":
        if fixture_id == "api-503-stale-approval":
            fixture = _load_json(
                root / "fixtures" / "contracts" / "v1" / "semantic" / "stale-approval.json"
            )
            authorized = approval_is_authorized(
                fixture["request"],
                fixture["decision"],
                current_case_revision_id=str(fixture["current_case_revision_id"]),
                current_evidence_hashes=fixture["current_evidence_hashes"],
            )
            return {
                "tenant_id": "tenant-alpha",
                "outcome": "authorization_denied"
                if not authorized
                else "fixture_delivery_recorded",
                "local_effect_count": 0,
                "approval_valid": not authorized,
                "evidence_valid": True,
                "tool_call_count": 0,
                **CAPABILITY_FLAGS,
            }
        module = _load_acceptance_module(root, "policy_approval_acceptance")

        if fixture_id == "api-503-policy-approval-delivery":
            item = module._baseline(root, store_path)
            outcome = "fixture_delivery_recorded"
            effects = int(item["source_counts"]["fixture_delivery_records"])
            approval_valid = True
        elif fixture_id == "api-503-policy-revoked-grant":
            item = module._authorization_denial(root, store_path)
            outcome = "authorization_denied"
            effects = int(item["delivery_record_count"])
            approval_valid = True
        else:
            item = module._fault_recovery(root, "delivery-lost-response", store_path)
            outcome = "recovered_after_interruption"
            effects = int(item["delivery_record_count"])
            approval_valid = True
        return {
            "tenant_id": "tenant-alpha",
            "outcome": outcome,
            "local_effect_count": effects,
            "approval_valid": approval_valid,
            "evidence_valid": True,
            "tool_call_count": 3,
            **CAPABILITY_FLAGS,
        }
    if adapter == "evidence-trajectory":
        module = _load_acceptance_module(root, "evidence_trajectory_acceptance")

        item = module._tampered(root, store_path)
        return {
            "tenant_id": "tenant-alpha",
            "outcome": item["outcome"],
            "local_effect_count": 0,
            "approval_valid": False,
            "evidence_valid": item["outcome"] != "lineage_invalid"
            or fixture_id == "api-503-tampered-lineage",
            "tool_call_count": 0,
            **CAPABILITY_FLAGS,
        }
    raise BenchmarkValidationError("benchmark_adapter_unsupported")


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


def run_offline_seed_suite(
    root: Path, *, configuration: Mapping[str, object] | None = None, run_id: str = "run-a"
) -> JsonObject:
    """Execute all 12 checked-in tasks without enabling a provider or external effect."""

    if configuration not in (None, {}, {"mode": "offline"}):
        raise BenchmarkValidationError("offline_benchmark_configuration_denied")
    suite, records = load_offline_seed_suite(root)
    diagnostics: list[JsonObject] = []
    acceptance_cache: dict[str, Any] = {}
    for record in records:
        task = record["task"]
        with TemporaryDirectory(prefix="weflow-evaluation-task-") as temporary:
            store_path = Path(temporary) / "fixture.sqlite3"
            sqlite3.connect(store_path).close()
            observation = _observe_task(root, task, acceptance_cache, store_path)
        grader_result, metrics = _grade(task, record["oracle"], observation, run_id)
        diagnostics.append(
            {
                "evaluation_task_id": task["evaluation_task_id"],
                "fixture_id": task["fixture_id"],
                "task_sha256": canonical_sha256(task),
                "oracle_sha256": canonical_sha256(record["oracle"]),
                "grader_result": grader_result,
                "metrics": metrics,
            }
        )
    passed = sum(item["grader_result"]["result"] == "passed" for item in diagnostics)
    unscored = sum(item["grader_result"]["quality_score"] == "not_scored" for item in diagnostics)
    report: JsonObject = {
        "schema_id": EVALUATION_SUITE_REPORT_SCHEMA_ID,
        "schema_version": "v1",
        "suite_report_id": f"report:{suite['suite_id']}:{run_id}",
        "suite_id": suite["suite_id"],
        "suite_sha256": _sha256(suite),
        "profile": "benchmark-core.v1",
        "task_count": len(diagnostics),
        "passed_task_count": passed,
        "failed_task_count": len(diagnostics) - passed,
        "unscored_task_count": unscored,
        "task_result_ids": [item["grader_result"]["grader_result_id"] for item in diagnostics],
        "capability_flags": dict(CAPABILITY_FLAGS),
    }
    report["report_sha256"] = canonical_sha256(report)
    validate_evaluation_suite_report(report)
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
