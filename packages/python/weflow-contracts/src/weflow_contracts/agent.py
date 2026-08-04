"""Contract helpers for the replay-only investigation Agent boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .validation import ContractValidationError, validate_payload

CONTEXT_MANIFEST_SCHEMA_ID = "https://weflow.local/contracts/v1/context-manifest.schema.json"
AGENT_ACTION_SCHEMA_ID = "https://weflow.local/contracts/v1/agent-action.schema.json"
TOOL_REQUEST_SCHEMA_ID = "https://weflow.local/contracts/v1/tool-request.schema.json"
TOOL_RESULT_SCHEMA_ID = "https://weflow.local/contracts/v1/tool-result.schema.json"
RESPONSE_CANDIDATE_SCHEMA_ID = "https://weflow.local/contracts/v1/response-candidate.schema.json"
VERIFIER_OUTCOME_SCHEMA_ID = "https://weflow.local/contracts/v1/verifier-outcome.schema.json"

_IDENTITY_FIELDS = (
    "tenant_id",
    "case_id",
    "case_revision_id",
    "workflow_id",
    "checkpoint_id",
    "context_manifest_id",
)


def _validate(payload: Mapping[str, Any], schema_id: str, name: str, root: Any = None) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != schema_id:
        raise ContractValidationError(name, "unexpected_schema")


def _require_link(
    payload: Mapping[str, Any],
    reference: Mapping[str, Any],
    *,
    name: str,
    fields: Sequence[str] = _IDENTITY_FIELDS,
) -> None:
    for field in fields:
        if payload.get(field) != reference.get(field):
            reason = "tenant_identity_mismatch" if field == "tenant_id" else "causation_mismatch"
            raise ContractValidationError(name, reason)


def validate_context_manifest(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, CONTEXT_MANIFEST_SCHEMA_ID, "context-manifest", root)


def validate_agent_action(
    payload: Mapping[str, Any],
    root: Any = None,
    *,
    context_manifest: Mapping[str, Any] | None = None,
) -> None:
    _validate(payload, AGENT_ACTION_SCHEMA_ID, "agent-action", root)
    if context_manifest is not None:
        validate_context_manifest(context_manifest, root)
        _require_link(payload, context_manifest, name="agent-action")


def validate_tool_request(
    payload: Mapping[str, Any],
    root: Any = None,
    *,
    context_manifest: Mapping[str, Any] | None = None,
) -> None:
    _validate(payload, TOOL_REQUEST_SCHEMA_ID, "tool-request", root)
    if context_manifest is not None:
        validate_context_manifest(context_manifest, root)
        _require_link(payload, context_manifest, name="tool-request")


def validate_tool_result(
    payload: Mapping[str, Any],
    root: Any = None,
    *,
    tool_request: Mapping[str, Any] | None = None,
) -> None:
    _validate(payload, TOOL_RESULT_SCHEMA_ID, "tool-result", root)
    if tool_request is not None:
        validate_tool_request(tool_request, root)
        _require_link(payload, tool_request, name="tool-result")
        if payload.get("tool_request_id") != tool_request.get("tool_request_id"):
            raise ContractValidationError("tool-result", "tool_request_mismatch")
        if payload.get("tool_name") != tool_request.get("tool_name"):
            raise ContractValidationError("tool-result", "tool_name_mismatch")


def validate_response_candidate(
    payload: Mapping[str, Any],
    root: Any = None,
    *,
    context_manifest: Mapping[str, Any] | None = None,
    evidence_hashes: Sequence[str] | None = None,
) -> None:
    _validate(payload, RESPONSE_CANDIDATE_SCHEMA_ID, "response-candidate", root)
    if context_manifest is not None:
        validate_context_manifest(context_manifest, root)
        _require_link(payload, context_manifest, name="response-candidate")
        if payload.get("context_sha256") != context_manifest.get("context_sha256"):
            raise ContractValidationError("response-candidate", "context_hash_mismatch")
    if evidence_hashes is not None and not set(payload["evidence_hashes"]).issubset(
        evidence_hashes
    ):
        raise ContractValidationError("response-candidate", "evidence_reference_mismatch")


def validate_verifier_outcome(
    payload: Mapping[str, Any],
    root: Any = None,
    *,
    candidate: Mapping[str, Any] | None = None,
) -> None:
    _validate(payload, VERIFIER_OUTCOME_SCHEMA_ID, "verifier-outcome", root)
    if candidate is not None:
        validate_response_candidate(candidate, root)
        _require_link(payload, candidate, name="verifier-outcome")
        for field in ("candidate_id", "candidate_sha256"):
            if payload.get(field) != candidate.get(field):
                raise ContractValidationError("verifier-outcome", "candidate_reference_mismatch")
