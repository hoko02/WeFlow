"""Closed contracts for the bounded QQ plus live-model Stage 3 slice."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .evaluation import canonical_sha256
from .validation import ContractValidationError, validate_payload

BASE = "https://weflow.local/contracts/v1"
QQ_MODEL_WORKFLOW_READINESS_SCHEMA_ID = f"{BASE}/qq-model-workflow-readiness.schema.json"
QQ_MODEL_ASSIST_COMMAND_SCHEMA_ID = f"{BASE}/qq-model-assist-command.schema.json"
QQ_MODEL_ASSIST_REQUEST_SCHEMA_ID = f"{BASE}/qq-model-assist-request.schema.json"
QQ_MODEL_ASSIST_CONTEXT_SCHEMA_ID = f"{BASE}/qq-model-assist-context.schema.json"
QQ_MODEL_CASE_BUDGET_SCHEMA_ID = f"{BASE}/qq-model-case-budget.schema.json"
QQ_MODEL_INVOCATION_EVIDENCE_SCHEMA_ID = f"{BASE}/qq-model-invocation-evidence.schema.json"
QQ_MODEL_CANDIDATE_BINDING_SCHEMA_ID = f"{BASE}/qq-model-candidate-binding.schema.json"
QQ_MODEL_PRIVATE_PREVIEW_SCHEMA_ID = f"{BASE}/qq-model-private-preview.schema.json"
QQ_MODEL_ASSIST_OUTCOME_SCHEMA_ID = f"{BASE}/qq-model-assist-outcome.schema.json"
QQ_MODEL_WORKFLOW_ACCEPTANCE_REPORT_SCHEMA_ID = (
    f"{BASE}/qq-model-workflow-acceptance-report.schema.json"
)
QQ_MODEL_WORKFLOW_VERIFICATION_SCHEMA_ID = f"{BASE}/qq-model-workflow-verification.schema.json"

_FORBIDDEN_KEYS = frozenset(
    {
        "member_openid",
        "user_openid",
        "group_openid",
        "client_secret",
        "access_token",
        "authorization",
        "raw_event",
        "provider_response",
        "provider_request",
        "customer_issue",
        "issue_text",
        "candidate_text",
        "draft",
        "draft_preview",
        "prompt",
        "transcript",
        "tool_output",
    }
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:\bBearer\s+[A-Za-z0-9._-]+|\bsk-[A-Za-z0-9_-]{8,}|"
    r"(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token)\s*[:=])"
)


@dataclass(frozen=True)
class QQModelAssistCommand:
    case_id: str
    expected_version: int


@dataclass(frozen=True)
class QQModelBudgetUsage:
    provider_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_calls: int
    actions: int
    no_progress: int
    wall_time_ms: int
    estimated_cost: float


@dataclass(frozen=True)
class QQModelAssistOutcome:
    terminal_outcome: str
    reason_code: str
    manual_draft_available: bool = True


def _schema(payload: Mapping[str, Any], expected: str, name: str, root: Any = None) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != expected:
        raise ContractValidationError(name, "unexpected_schema")


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ContractValidationError(name, "timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractValidationError(name, "timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise ContractValidationError(name, "timestamp_invalid")
    return parsed


def _claimed_hash(payload: Mapping[str, Any], field: str, name: str) -> None:
    if payload[field] != canonical_sha256(payload, without=field):
        raise ContractValidationError(name, f"{field}_mismatch")


def _same(payloads: tuple[Mapping[str, Any], ...], fields: tuple[str, ...], name: str) -> None:
    first = payloads[0]
    for payload in payloads[1:]:
        if any(payload.get(field) != first.get(field) for field in fields):
            raise ContractValidationError(name, "lineage_mismatch")


def _safe_tree(value: object, name: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                raise ContractValidationError(name, "unsafe_content_key")
            _safe_tree(item, name)
    elif isinstance(value, list):
        for item in value:
            _safe_tree(item, name)
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        raise ContractValidationError(name, "unsafe_content_value")


def validate_qq_model_workflow_readiness(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-workflow-readiness"
    _schema(payload, QQ_MODEL_WORKFLOW_READINESS_SCHEMA_ID, name, root)
    if payload["ready"] is not (payload["selector_resolved"] and payload["profile_current"]):
        raise ContractValidationError(name, "readiness_mismatch")


def validate_qq_model_assist_command(payload: Mapping[str, Any], root: Any = None) -> None:
    _schema(payload, QQ_MODEL_ASSIST_COMMAND_SCHEMA_ID, "qq-model-assist-command", root)


def validate_qq_model_assist_request(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-assist-request"
    _schema(payload, QQ_MODEL_ASSIST_REQUEST_SCHEMA_ID, name, root)
    if _timestamp(payload["expires_at"], name) <= _timestamp(payload["created_at"], name):
        raise ContractValidationError(name, "expiry_invalid")
    _claimed_hash(payload, "request_sha256", name)


def validate_qq_model_assist_context(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-assist-context"
    _schema(payload, QQ_MODEL_ASSIST_CONTEXT_SCHEMA_ID, name, root)
    _claimed_hash(payload, "context_sha256", name)


def validate_qq_model_case_budget(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-case-budget"
    _schema(payload, QQ_MODEL_CASE_BUDGET_SCHEMA_ID, name, root)
    for block in (payload["reserved"], payload["used"]):
        if block["total_tokens"] != block["input_tokens"] + block["output_tokens"]:
            raise ContractValidationError(name, "token_total_mismatch")
    if any(payload["used"][field] > payload["reserved"][field] for field in payload["used"]):
        raise ContractValidationError(name, "budget_exceeded")
    _claimed_hash(payload, "budget_sha256", name)


def validate_qq_model_invocation_evidence(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-invocation-evidence"
    _schema(payload, QQ_MODEL_INVOCATION_EVIDENCE_SCHEMA_ID, name, root)
    for block in (payload["reservation"], payload["usage"]):
        if block["total_tokens"] != block["input_tokens"] + block["output_tokens"]:
            raise ContractValidationError(name, "token_total_mismatch")
    if payload["status"] == "intent_recorded":
        if payload["observation_id"] is not None or payload["observed_at"] is not None:
            raise ContractValidationError(name, "intent_has_observation")
    elif payload["observation_id"] is None or payload["observed_at"] is None:
        raise ContractValidationError(name, "observation_missing")
    if payload["status"] == "provider_outcome_unknown" and not payload["failure_classification"]:
        raise ContractValidationError(name, "unknown_classification_missing")
    _claimed_hash(payload, "evidence_sha256", name)


def validate_qq_model_candidate_binding(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-candidate-binding"
    _schema(payload, QQ_MODEL_CANDIDATE_BINDING_SCHEMA_ID, name, root)
    _claimed_hash(payload, "binding_sha256", name)


def validate_qq_model_private_preview(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-private-preview"
    _schema(payload, QQ_MODEL_PRIVATE_PREVIEW_SCHEMA_ID, name, root)
    if not str(payload["candidate_sha256"]).startswith(str(payload["candidate_hash_prefix"])):
        raise ContractValidationError(name, "candidate_hash_prefix_mismatch")
    _claimed_hash(payload, "preview_sha256", name)


def validate_qq_model_assist_outcome(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-assist-outcome"
    _schema(payload, QQ_MODEL_ASSIST_OUTCOME_SCHEMA_ID, name, root)
    ready = payload["terminal_outcome"] == "response_ready"
    if ready is not bool(payload["candidate_binding_id"] and payload["private_preview_id"]):
        raise ContractValidationError(name, "candidate_outcome_mismatch")
    _claimed_hash(payload, "outcome_sha256", name)


def qq_model_workflow_report_sha256(payload: Mapping[str, Any]) -> str:
    return canonical_sha256(payload, without="report_sha256")


def validate_qq_model_workflow_acceptance_report(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    name = "qq-model-workflow-acceptance-report"
    _schema(payload, QQ_MODEL_WORKFLOW_ACCEPTANCE_REPORT_SCHEMA_ID, name, root)
    if payload["report_sha256"] != qq_model_workflow_report_sha256(payload):
        raise ContractValidationError(name, "report_hash_mismatch")
    _safe_tree(payload, name)
    if any(
        payload[field]
        for field in (
            "customer_receipt_verified",
            "issue_resolution",
            "case_completion",
            "production_ready",
        )
    ):
        raise ContractValidationError(name, "business_outcome_overclaim")
    usage = payload["model_usage"]
    if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        raise ContractValidationError(name, "usage_total_mismatch")
    if payload["mode"] == "offline-fake":
        if payload["live_model_contact_verified"] or usage["available"]:
            raise ContractValidationError(name, "fake_as_live")
    else:
        required = (
            "qq_intake_ack_verified",
            "handler_private_workflow_verified",
            "live_model_contact_verified",
            "candidate_verification_verified",
            "group_approval_verified",
            "final_provider_accepted",
            "artifact_deletion_verified",
        )
        if not all(payload[field] for field in required) or not usage["available"]:
            raise ContractValidationError(name, "live_evidence_incomplete")


def validate_qq_model_workflow_verification(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-model-workflow-verification"
    _schema(payload, QQ_MODEL_WORKFLOW_VERIFICATION_SCHEMA_ID, name, root)
    _claimed_hash(payload, "verification_sha256", name)


def validate_qq_model_lineage(
    *,
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    budget: Mapping[str, Any],
    invocation: Mapping[str, Any],
    binding: Mapping[str, Any],
    preview: Mapping[str, Any],
    outcome: Mapping[str, Any],
    root: Any = None,
) -> None:
    """Validate a complete content-free Stage 3 lineage without network or credentials."""

    validate_qq_model_assist_request(request, root)
    validate_qq_model_assist_context(context, root)
    validate_qq_model_case_budget(budget, root)
    validate_qq_model_invocation_evidence(invocation, root)
    validate_qq_model_candidate_binding(binding, root)
    validate_qq_model_private_preview(preview, root)
    validate_qq_model_assist_outcome(outcome, root)
    records = (request, context, budget, invocation, binding, preview, outcome)
    _same(
        records,
        ("tenant_id", "case_id", "case_revision_id", "handler_binding_id"),
        "qq-model-lineage",
    )
    for record in records[1:]:
        if record.get("assist_request_id") != request["assist_request_id"]:
            raise ContractValidationError("qq-model-lineage", "assist_request_mismatch")
    if (
        invocation["context_id"] != context["context_id"]
        or invocation["context_sha256"] != context["context_sha256"]
        or binding["context_id"] != context["context_id"]
        or binding["context_sha256"] != context["context_sha256"]
        or binding["invocation_id"] != invocation["invocation_id"]
        or binding["invocation_evidence_sha256"] != invocation["evidence_sha256"]
        or binding["budget_sha256"] != budget["budget_sha256"]
        or preview["budget_sha256"] != budget["budget_sha256"]
        or preview["candidate_artifact_id"] != binding["candidate_artifact_id"]
        or preview["candidate_sha256"] != binding["candidate_sha256"]
        or preview["approval_request_id"] != binding["approval_request_id"]
        or outcome["candidate_binding_id"] != binding["binding_id"]
        or outcome["private_preview_id"] != preview["preview_id"]
    ):
        raise ContractValidationError("qq-model-lineage", "lineage_link_mismatch")


__all__ = [
    name
    for name in globals()
    if name.startswith("QQ_MODEL_")
    or name.startswith("validate_qq_model")
    or name.startswith("qq_model_workflow")
]
