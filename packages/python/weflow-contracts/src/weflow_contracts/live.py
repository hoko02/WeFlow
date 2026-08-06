"""Payload-safe contracts and semantic links for bounded live-model evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .evaluation import canonical_sha256
from .validation import ContractValidationError, validate_payload

MODEL_ACTION_PROPOSAL_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/model-action-proposal.schema.json"
)
MODEL_TOOL_OBSERVATION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/model-tool-observation.schema.json"
)
MODEL_INVOCATION_INTENT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/model-invocation-intent.schema.json"
)
MODEL_INVOCATION_OBSERVATION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/model-invocation-observation.schema.json"
)
RESPONSE_DRAFT_ARTIFACT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/response-draft-artifact.schema.json"
)
LIVE_CANDIDATE_BINDING_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/live-candidate-binding.schema.json"
)
PROVIDER_PRICE_PROFILE_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/provider-price-profile.schema.json"
)
LIVE_RUN_METRICS_SCHEMA_ID = "https://weflow.local/contracts/v1/live-run-metrics.schema.json"
LIVE_EVALUATION_ATTEMPT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/live-evaluation-attempt.schema.json"
)
LIVE_EVALUATION_SUITE_REPORT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/live-evaluation-suite-report.schema.json"
)

_INVOCATION_LINK_FIELDS = (
    "tenant_id",
    "evaluation_session_id",
    "suite_id",
    "evaluation_task_id",
    "attempt_id",
    "logical_turn_id",
    "invocation_id",
)


def _validate(payload: Mapping[str, Any], schema_id: str, name: str, root: Any = None) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != schema_id:
        raise ContractValidationError(name, "unexpected_schema")


def _validate_claimed_hash(payload: Mapping[str, Any], field: str, name: str) -> None:
    if payload.get(field) != canonical_sha256(payload, without=field):
        raise ContractValidationError(name, f"{field}_mismatch")


def _same(
    left: Mapping[str, Any], right: Mapping[str, Any], fields: Sequence[str], name: str
) -> None:
    for field in fields:
        if left.get(field) != right.get(field):
            reason = "tenant_identity_mismatch" if field == "tenant_id" else f"{field}_mismatch"
            raise ContractValidationError(name, reason)


def _parse_datetime(value: object, name: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractValidationError(name, "timestamp_invalid") from error


def validate_model_action_proposal(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, MODEL_ACTION_PROPOSAL_SCHEMA_ID, "model-action-proposal", root)


def validate_model_tool_observation(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, MODEL_TOOL_OBSERVATION_SCHEMA_ID, "model-tool-observation", root)


def validate_model_invocation_intent(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, MODEL_INVOCATION_INTENT_SCHEMA_ID, "model-invocation-intent", root)
    reservation = payload["reservation"]
    if reservation["total_tokens"] != reservation["input_tokens"] + reservation["output_tokens"]:
        raise ContractValidationError("model-invocation-intent", "token_reservation_mismatch")
    if reservation["request_timeout_ms"] > reservation["wall_time_ms"]:
        raise ContractValidationError("model-invocation-intent", "timeout_reservation_mismatch")
    _validate_claimed_hash(payload, "intent_sha256", "model-invocation-intent")


def validate_model_invocation_observation(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(
        payload,
        MODEL_INVOCATION_OBSERVATION_SCHEMA_ID,
        "model-invocation-observation",
        root,
    )
    usage = payload["usage"]
    if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise ContractValidationError("model-invocation-observation", "token_usage_mismatch")
    if payload["status"] == "completed":
        if (
            usage["available"] is not True
            or payload["response_sha256"] is None
            or payload["failure_classification"] is not None
        ):
            raise ContractValidationError(
                "model-invocation-observation", "completed_observation_incomplete"
            )
    elif payload["failure_classification"] is None:
        raise ContractValidationError(
            "model-invocation-observation", "failure_classification_missing"
        )
    _validate_claimed_hash(payload, "observation_sha256", "model-invocation-observation")


def validate_response_draft_artifact(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, RESPONSE_DRAFT_ARTIFACT_SCHEMA_ID, "response-draft-artifact", root)
    if _parse_datetime(payload["expires_at"], "response-draft-artifact") <= _parse_datetime(
        payload["created_at"], "response-draft-artifact"
    ):
        raise ContractValidationError("response-draft-artifact", "expiry_invalid")
    evidence = [item["evidence_sha256"] for item in payload["claim_evidence_summary"]]
    if len(evidence) != len(set(evidence)):
        raise ContractValidationError("response-draft-artifact", "evidence_duplicate")
    _validate_claimed_hash(payload, "artifact_sha256", "response-draft-artifact")


def validate_live_candidate_binding(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, LIVE_CANDIDATE_BINDING_SCHEMA_ID, "live-candidate-binding", root)
    _validate_claimed_hash(payload, "binding_sha256", "live-candidate-binding")


def validate_provider_price_profile(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, PROVIDER_PRICE_PROFILE_SCHEMA_ID, "provider-price-profile", root)
    if _parse_datetime(payload["expires_at"], "provider-price-profile") <= _parse_datetime(
        payload["effective_at"], "provider-price-profile"
    ):
        raise ContractValidationError("provider-price-profile", "expiry_invalid")
    _validate_claimed_hash(payload, "profile_sha256", "provider-price-profile")


def validate_live_run_metrics(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, LIVE_RUN_METRICS_SCHEMA_ID, "live-run-metrics", root)
    if payload["invocation_count"] != (
        payload["successful_invocation_count"] + payload["failed_invocation_count"]
    ):
        raise ContractValidationError("live-run-metrics", "invocation_count_mismatch")
    if payload["total_tokens"] != payload["input_tokens"] + payload["output_tokens"]:
        raise ContractValidationError("live-run-metrics", "token_count_mismatch")
    if payload["valid_proposal_count"] > payload["invocation_count"]:
        raise ContractValidationError("live-run-metrics", "proposal_count_invalid")
    if payload["provider_latency_ms"] > payload["end_to_end_latency_ms"]:
        raise ContractValidationError("live-run-metrics", "latency_order_invalid")
    _validate_claimed_hash(payload, "metrics_sha256", "live-run-metrics")


def validate_live_evaluation_attempt(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, LIVE_EVALUATION_ATTEMPT_SCHEMA_ID, "live-evaluation-attempt", root)
    gates = payload["hard_gates"]
    passed = bool(gates) and all(gate["passed"] is True for gate in gates)
    if payload["hard_gate_passed"] is not passed:
        raise ContractValidationError("live-evaluation-attempt", "hard_gate_summary_invalid")
    if passed and payload["quality_score"] == "not_scored":
        raise ContractValidationError("live-evaluation-attempt", "quality_score_missing")
    if not passed and payload["quality_score"] != "not_scored":
        raise ContractValidationError("live-evaluation-attempt", "quality_score_not_scored")
    response_ready = payload["terminal_outcome"] == "response_ready"
    if response_ready != bool(payload["candidate_binding_id"] and payload["verifier_outcome_id"]):
        raise ContractValidationError("live-evaluation-attempt", "candidate_verifier_link_invalid")
    _validate_claimed_hash(payload, "attempt_sha256", "live-evaluation-attempt")


def validate_live_evaluation_suite_report(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(
        payload,
        LIVE_EVALUATION_SUITE_REPORT_SCHEMA_ID,
        "live-evaluation-suite-report",
        root,
    )
    if len({item["evaluation_task_id"] for item in payload["task_aggregates"]}) != 6:
        raise ContractValidationError("live-evaluation-suite-report", "task_ids_duplicate")
    if payload["attempt_count"] != len(payload["attempt_ids"]):
        raise ContractValidationError("live-evaluation-suite-report", "attempt_count_mismatch")
    _validate_claimed_hash(payload, "report_sha256", "live-evaluation-suite-report")


def validate_model_invocation_chain(
    intent: Mapping[str, Any], observation: Mapping[str, Any], root: Any = None
) -> None:
    validate_model_invocation_intent(intent, root)
    validate_model_invocation_observation(observation, root)
    _same(intent, observation, _INVOCATION_LINK_FIELDS, "model-invocation-chain")


def validate_live_contract_chain(
    intent: Mapping[str, Any],
    observation: Mapping[str, Any],
    artifact: Mapping[str, Any],
    binding: Mapping[str, Any],
    metrics: Mapping[str, Any],
    attempt: Mapping[str, Any],
    report: Mapping[str, Any],
    root: Any = None,
) -> None:
    """Validate the safe invocation-to-report lineage without provider content."""

    validate_model_invocation_chain(intent, observation, root)
    validate_response_draft_artifact(artifact, root)
    validate_live_candidate_binding(binding, root)
    validate_live_run_metrics(metrics, root)
    validate_live_evaluation_attempt(attempt, root)
    validate_live_evaluation_suite_report(report, root)
    _same(observation, artifact, ("tenant_id", "attempt_id"), "live-contract-chain")
    if artifact["producer_invocation_id"] != observation["invocation_id"]:
        raise ContractValidationError("live-contract-chain", "artifact_invocation_mismatch")
    _same(
        binding,
        artifact,
        ("tenant_id", "case_id", "case_revision_id", "attempt_id"),
        "live-contract-chain",
    )
    if (
        binding["invocation_id"] != observation["invocation_id"]
        or binding["observation_id"] != observation["observation_id"]
        or binding["draft_artifact_id"] != artifact["artifact_id"]
        or binding["draft_content_sha256"] != artifact["content_sha256"]
        or set(binding["evidence_hashes"])
        != {item["evidence_sha256"] for item in artifact["claim_evidence_summary"]}
    ):
        raise ContractValidationError("live-contract-chain", "draft_binding_mismatch")
    _same(
        metrics,
        attempt,
        ("tenant_id", "suite_id", "evaluation_task_id", "attempt_id"),
        "live-contract-chain",
    )
    if (
        attempt["live_run_metrics_id"] != metrics["live_run_metrics_id"]
        or attempt["metrics_sha256"] != metrics["metrics_sha256"]
        or observation["observation_id"] not in attempt["invocation_observation_ids"]
        or attempt["candidate_binding_id"] != binding["binding_sha256"]
        or attempt["terminal_outcome"] != metrics["terminal_outcome"]
        or attempt["attempt_id"] not in report["attempt_ids"]
        or report["evaluation_session_id"] != attempt["evaluation_session_id"]
        or report["price_profile_sha256"] != metrics["price_profile_sha256"]
        or report["model_id_sha256"] != metrics["model_id_sha256"]
    ):
        raise ContractValidationError("live-contract-chain", "report_link_mismatch")
