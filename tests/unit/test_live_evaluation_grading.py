from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_contracts.evaluation import canonical_sha256
from weflow_contracts.live import (
    LIVE_EVALUATION_ATTEMPT_SCHEMA_ID,
    LIVE_RUN_METRICS_SCHEMA_ID,
    validate_live_evaluation_attempt,
    validate_live_run_metrics,
)
from weflow_testkit.live_evaluation import load_live_pilot_suite
from weflow_testkit.live_grading import (
    CAPABILITY_FLAGS,
    LiveEvaluationGradingError,
    build_accepted_live_report,
    grade_hard_gates,
    materialize_live_attempt,
    publish_json_atomic,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 6, tzinfo=UTC)


def _suite():
    return load_live_pilot_suite(ROOT, now=NOW)


def test_deterministic_hard_gates_and_attempt_materialization() -> None:
    suite = _suite()
    record = next(
        item for item in suite.records if item["task"]["task_id"] == "grounded-response-ready"
    )
    expected_hashes = {
        name: reference["sha256"] for name, reference in record["task"]["tool_sources"].items()
    }
    evidence = [
        {"tool_name": name, "content_sha256": expected_hashes[name]}
        for name in ("crm", "monitoring", "knowledge")
    ]
    binding_hash = "9" * 64
    store_snapshot = {
        "intents": [
            {
                "tenant_id": "tenant-alpha",
                "provider_profile_sha256": "a" * 64,
                "model_id_sha256": "b" * 64,
                "price_profile_sha256": suite.price_profile["profile_sha256"],
            }
        ],
        "observations": [
            {
                "tenant_id": "tenant-alpha",
                "observation_id": "observation-1",
                "status": "completed",
                "provider_latency_ms": 10,
            }
        ],
        "turns": [{"normalized_action_sha256": "c" * 64}],
        "draft_artifacts": [{"artifact_id": "artifact-1"}],
        "candidate_bindings": [
            {
                "binding_sha256": binding_hash,
                "draft_artifact_id": "artifact-1",
                "evidence_hashes": list(expected_hashes.values()),
            }
        ],
        "budget_events": [
            {
                "event_kind": "provider_reserved",
                "invocation_id": "invocation-1",
                "payload": {
                    "input_tokens": 30,
                    "output_tokens": 20,
                    "total_tokens": 50,
                    "estimated_cost": 0.00001,
                },
            },
            {
                "event_kind": "provider_settled",
                "invocation_id": "invocation-1",
                "payload": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "total_tokens": 30,
                    "estimated_cost": 0.0000056,
                },
            },
        ],
    }
    workflow_facts = {
        "agent_steps": [{"action_type": "response_candidate"}],
        "tool_evidence": evidence,
        "verifier_outcome": {"outcome": "verified"},
        "approval": False,
        "outbound_delivery": False,
        "external_write": False,
    }
    result = {
        "attempt_id": "attempt-1",
        "terminal_outcome": "response_ready",
        "invocation_observation_ids": ["observation-1"],
        "candidate_binding_id": binding_hash,
        "verifier_outcome_id": "verifier-1",
        "state": "RESPONSE_READY",
        "approval_count": 0,
        "delivery_count": 0,
        "external_business_write_count": 0,
        "end_to_end_latency_ms": 20,
        "budget": {
            "provider_call_count": 1,
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
            "estimated_cost": 0.0000056,
            "action_count": 4,
            "tool_count": 3,
            "no_progress_count": 0,
            "retry_count": 0,
        },
    }
    provider_binding = {
        "provider_profile_sha256": "a" * 64,
        "model_id_sha256": "b" * 64,
        "price_profile_sha256": suite.price_profile["profile_sha256"],
    }
    gates = grade_hard_gates(
        task_record=record,
        prompt_template=suite.prompt_template,
        budget_profile=suite.budget_profile,
        provider_binding=provider_binding,
        result=result,
        store_snapshot=store_snapshot,
        workflow_facts=workflow_facts,
        explicitly_authorized=True,
    )
    assert len(gates) == 11
    assert all(item["passed"] for item in gates)

    task_hash = next(
        item["sha256"]
        for item in suite.suite["tasks"]
        if item["task_id"] == "grounded-response-ready"
    )
    metrics, attempt = materialize_live_attempt(
        task_record=record,
        task_sha256=task_hash,
        attempt_index=1,
        evaluation_session_id="session-1",
        model_id_sha256="b" * 64,
        price_profile=suite.price_profile,
        result=result,
        store_snapshot=store_snapshot,
        workflow_facts=workflow_facts,
        hard_gates=gates,
    )
    assert metrics["total_tokens"] == 30
    assert attempt["quality_score"] == 100
    assert attempt["hard_gate_passed"] is True


def _pair(task_id: str, index: int, outcome: str) -> tuple[dict, dict]:
    attempt_id = f"attempt:{task_id}:{index}"
    metrics = {
        "schema_id": LIVE_RUN_METRICS_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": "tenant-alpha",
        "live_run_metrics_id": f"metrics:{attempt_id}",
        "suite_id": "live-pilot.v1",
        "evaluation_task_id": task_id,
        "attempt_id": attempt_id,
        "price_profile_id": "deepseek-v4-flash-2026-08-06",
        "price_profile_sha256": "d" * 64,
        "model_id_sha256": "e" * 64,
        "invocation_count": 1,
        "successful_invocation_count": 1,
        "failed_invocation_count": 0,
        "valid_proposal_count": 1,
        "action_count": 1,
        "tool_call_count": 0,
        "input_tokens": 20 + index,
        "output_tokens": 10,
        "total_tokens": 30 + index,
        "estimated_cost": 0.00001 * index,
        "currency": "USD",
        "provider_latency_ms": 10 + index,
        "end_to_end_latency_ms": 20 + index,
        "wall_time_ms": 20 + index,
        "retry_count": 0,
        "no_progress_count": 0,
        "terminal_outcome": outcome,
        "failure_attribution": None,
        "external_business_write_count": 0,
        "capability_flags": dict(CAPABILITY_FLAGS),
        "metrics_sha256": "",
    }
    metrics["metrics_sha256"] = canonical_sha256(metrics, without="metrics_sha256")
    validate_live_run_metrics(metrics)
    response_ready = outcome == "response_ready"
    attempt = {
        "schema_id": LIVE_EVALUATION_ATTEMPT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": "tenant-alpha",
        "evaluation_session_id": "session-1",
        "suite_id": "live-pilot.v1",
        "evaluation_task_id": task_id,
        "task_sha256": "a" * 64,
        "oracle_sha256": "b" * 64,
        "attempt_id": attempt_id,
        "attempt_index": index,
        "live_run_metrics_id": metrics["live_run_metrics_id"],
        "metrics_sha256": metrics["metrics_sha256"],
        "invocation_observation_ids": [f"observation:{attempt_id}"],
        "candidate_binding_id": f"binding:{attempt_id}" if response_ready else None,
        "verifier_outcome_id": f"verifier:{attempt_id}" if response_ready else None,
        "terminal_outcome": outcome,
        "hard_gates": [{"name": "all", "passed": True, "reason_code": "passed"}],
        "hard_gate_passed": True,
        "quality_dimensions": [
            {"name": "expected_outcome", "score": 100},
            {"name": "action_validity", "score": 100},
            {"name": "tool_efficiency", "score": 100},
            {"name": "evidence_grounding", "score": 100},
            {"name": "response_structure", "score": 100},
        ],
        "quality_score": 100,
        "failure_attribution": None,
        "complete": True,
        "approval_count": 0,
        "delivery_count": 0,
        "external_business_write_count": 0,
        "attempt_sha256": "",
    }
    attempt["attempt_sha256"] = canonical_sha256(attempt, without="attempt_sha256")
    validate_live_evaluation_attempt(attempt)
    return metrics, attempt


def test_accepted_report_aggregates_30_attempts_and_fake_transport_cannot_publish(
    tmp_path: Path,
) -> None:
    suite = _suite()
    outcomes = {
        "grounded-response-ready": "response_ready",
        "missing-information": "needs_information",
        "conflicting-evidence": "needs_operator",
        "prompt-injection": "needs_operator",
        "tool-timeout": "tool_timeout",
        "budget-exhaustion": "budget_exhausted",
    }
    pairs = [
        _pair(task_id, index, outcomes[task_id]) for task_id in outcomes for index in range(1, 6)
    ]
    metrics = [pair[0] for pair in pairs]
    attempts = [pair[1] for pair in pairs]
    expected = {
        record["task"]["task_id"]: record["oracle"]["expected_outcomes"] for record in suite.records
    }

    with pytest.raises(LiveEvaluationGradingError, match="fake_transport"):
        build_accepted_live_report(
            evaluation_session_id="session-1",
            suite=suite.suite,
            suite_sha256=suite.suite_sha256,
            provider_profile_sha256="c" * 64,
            model_id_sha256="e" * 64,
            prompt_template_sha256=suite.suite["prompt_template"]["sha256"],
            price_profile={**suite.price_profile, "profile_sha256": "d" * 64},
            attempts=attempts,
            metrics=metrics,
            expected_outcomes=expected,
            live_verification_eligible=False,
        )

    report = build_accepted_live_report(
        evaluation_session_id="session-1",
        suite=suite.suite,
        suite_sha256=suite.suite_sha256,
        provider_profile_sha256="c" * 64,
        model_id_sha256="e" * 64,
        prompt_template_sha256=suite.suite["prompt_template"]["sha256"],
        price_profile={**suite.price_profile, "profile_sha256": "d" * 64},
        attempts=attempts,
        metrics=metrics,
        expected_outcomes=expected,
        live_verification_eligible=True,
    )
    assert report["accepted"] is True
    assert report["grounded_happy_path_success_count"] == 5
    assert len(report["task_aggregates"]) == 6
    output = tmp_path / "accepted.json"
    publish_json_atomic(output, report)
    assert output.read_text(encoding="utf-8").endswith("\n")
