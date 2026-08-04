"""Hash-bound, fixture-only authorization and outbound delivery contract helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .validation import ContractValidationError, _parse_time, validate_payload

AUTHORIZATION_BINDING_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/authorization-binding.schema.json"
)
CAPABILITY_GRANT_SCHEMA_ID = "https://weflow.local/contracts/v1/capability-grant.schema.json"
POLICY_DECISION_SCHEMA_ID = "https://weflow.local/contracts/v1/policy-decision.schema.json"
APPROVAL_REQUEST_SCHEMA_ID = "https://weflow.local/contracts/v1/approval-request.schema.json"
APPROVAL_DECISION_SCHEMA_ID = "https://weflow.local/contracts/v1/approval-decision.schema.json"
OUTBOUND_DELIVERY_INTENT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/outbound-delivery-intent.schema.json"
)
OUTBOUND_DELIVERY_OBSERVATION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/outbound-delivery-observation.schema.json"
)
OUTBOUND_DELIVERY_COMPLETION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/outbound-delivery-completion.schema.json"
)

CHANGE4_ACTIONS = frozenset({"approval.request", "approval.decide", "outbound_delivery.execute"})
SAFE_DATA_CLASSIFICATIONS = frozenset({"synthetic"})


def canonical_sha256(value: object) -> str:
    """Hash canonical public metadata; callers must never pass raw candidate content."""

    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def content_hash(payload: Mapping[str, Any], *, without: str) -> str:
    """Return the canonical hash claimed by a versioned record."""

    return canonical_sha256({key: value for key, value in payload.items() if key != without})


def _require_schema(
    payload: Mapping[str, Any], expected_schema_id: str, schema_name: str, root: Any = None
) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != expected_schema_id:
        raise ContractValidationError(schema_name, "unexpected_schema")


def _require_fields(payload: Mapping[str, Any], fields: Sequence[str], schema_name: str) -> None:
    for field in fields:
        value = payload.get(field)
        if value is None or value == "" or value == []:
            raise ContractValidationError(schema_name, f"{field}_required")


def _require_hash(payload: Mapping[str, Any], *, hash_field: str, schema_name: str) -> None:
    claimed = payload.get(hash_field)
    if not isinstance(claimed, str) or claimed != content_hash(payload, without=hash_field):
        raise ContractValidationError(schema_name, f"{hash_field}_mismatch")


def _same(
    left: Mapping[str, Any], right: Mapping[str, Any], fields: Sequence[str], schema_name: str
) -> None:
    for field in fields:
        if left.get(field) != right.get(field):
            reason = "tenant_identity_mismatch" if field == "tenant_id" else "binding_mismatch"
            raise ContractValidationError(schema_name, reason)


def validate_capability_grant(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, CAPABILITY_GRANT_SCHEMA_ID, "capability-grant", root)


def validate_policy_decision(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, POLICY_DECISION_SCHEMA_ID, "policy-decision", root)


def validate_approval_request(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, APPROVAL_REQUEST_SCHEMA_ID, "approval-request", root)


def validate_approval_decision(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, APPROVAL_DECISION_SCHEMA_ID, "approval-decision", root)


def validate_authorization_binding(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, AUTHORIZATION_BINDING_SCHEMA_ID, "authorization-binding", root)
    _require_hash(
        payload, hash_field="authorization_binding_sha256", schema_name="authorization-binding"
    )
    evidence = payload.get("evidence_hashes")
    if not isinstance(evidence, list) or len(evidence) != len(set(evidence)):
        raise ContractValidationError("authorization-binding", "evidence_not_ordered_unique")


def validate_outbound_delivery_intent(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, OUTBOUND_DELIVERY_INTENT_SCHEMA_ID, "outbound-delivery-intent", root)


def validate_outbound_delivery_observation(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(
        payload, OUTBOUND_DELIVERY_OBSERVATION_SCHEMA_ID, "outbound-delivery-observation", root
    )


def validate_outbound_delivery_completion(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(
        payload, OUTBOUND_DELIVERY_COMPLETION_SCHEMA_ID, "outbound-delivery-completion", root
    )


def validate_change4_authorization_profile(
    binding: Mapping[str, Any],
    grant: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    action: str,
    current_case_revision_id: str,
    current_checkpoint_id: str,
    current_workflow_version: int,
    current_candidate_hash: str,
    current_evidence_hashes: Sequence[str],
    resource_id: str,
    data_classification: str,
    effective_tenant_id: str | None = None,
    effective_subject_id: str | None = None,
    effective_role: str | None = None,
    now: datetime | None = None,
    require_allow: bool = True,
) -> None:
    """Validate the complete Change 4 profile; omitted/legacy fields never authorize it."""

    if action not in CHANGE4_ACTIONS:
        raise ContractValidationError("authorization-binding", "action_not_allowlisted")
    validate_authorization_binding(binding)
    validate_capability_grant(grant)
    validate_policy_decision(decision)
    _require_fields(
        grant,
        (
            "grant_version",
            "grant_sha256",
            "role",
            "resource_scope",
            "data_classifications",
        ),
        "capability-grant",
    )
    _require_hash(grant, hash_field="grant_sha256", schema_name="capability-grant")
    _require_fields(
        decision,
        (
            "checkpoint_id",
            "workflow_id",
            "workflow_version",
            "candidate_hash",
            "action",
            "policy_version",
            "policy_input_sha256",
            "policy_decision_sha256",
            "grant_id",
            "grant_sha256",
            "subject_id",
            "role",
            "resource_id",
            "data_classification",
        ),
        "policy-decision",
    )
    _require_hash(decision, hash_field="policy_decision_sha256", schema_name="policy-decision")
    if require_allow and decision.get("decision") != "allow":
        raise ContractValidationError("policy-decision", "policy_denied")
    if grant.get("status") != "active":
        raise ContractValidationError("capability-grant", "grant_not_active")
    current_time = now or datetime.now(UTC)
    expiry = _parse_time(grant.get("expires_at"))
    binding_expiry = _parse_time(binding.get("expires_at"))
    if (
        expiry is None
        or binding_expiry is None
        or expiry <= current_time
        or binding_expiry <= current_time
    ):
        raise ContractValidationError("authorization-binding", "authorization_expired")
    if (
        action not in grant.get("scopes", [])
        or resource_id != grant.get("resource_scope")
        or data_classification not in grant.get("data_classifications", [])
        or data_classification not in SAFE_DATA_CLASSIFICATIONS
    ):
        raise ContractValidationError("capability-grant", "grant_scope_denied")
    _same(
        binding,
        grant,
        ("tenant_id", "grant_id", "grant_version", "grant_sha256", "subject_id", "role"),
        "authorization-binding",
    )
    _same(
        binding,
        decision,
        (
            "tenant_id",
            "case_id",
            "case_revision_id",
            "workflow_id",
            "checkpoint_id",
            "workflow_version",
            "candidate_hash",
            "evidence_hashes",
            "policy_decision_id",
            "policy_version",
            "policy_decision_sha256",
            "grant_id",
            "grant_sha256",
            "subject_id",
            "role",
        ),
        "authorization-binding",
    )
    if (
        binding.get("action") != action
        or decision.get("action") != action
        or binding.get("delivery_resource_id") != resource_id
        or binding.get("data_classification") != data_classification
        or decision.get("resource_id") != resource_id
        or decision.get("data_classification") != data_classification
    ):
        raise ContractValidationError("authorization-binding", "binding_mismatch")
    if (
        binding.get("case_revision_id") != current_case_revision_id
        or binding.get("checkpoint_id") != current_checkpoint_id
        or binding.get("workflow_version") != current_workflow_version
        or binding.get("candidate_hash") != current_candidate_hash
        or list(binding.get("evidence_hashes", [])) != list(current_evidence_hashes)
    ):
        raise ContractValidationError("authorization-binding", "stale_authorization_binding")
    if effective_tenant_id is not None and binding.get("tenant_id") != effective_tenant_id:
        raise ContractValidationError("authorization-binding", "tenant_identity_mismatch")
    if effective_subject_id is not None and binding.get("subject_id") != effective_subject_id:
        raise ContractValidationError("authorization-binding", "subject_identity_mismatch")
    if effective_role is not None and binding.get("role") != effective_role:
        raise ContractValidationError("authorization-binding", "role_identity_mismatch")


def validate_hash_bound_approval(
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    current_case_revision_id: str,
    current_checkpoint_id: str,
    current_workflow_version: int,
    current_candidate_hash: str,
    current_evidence_hashes: Sequence[str],
    effective_tenant_id: str,
    effective_approver_id: str,
    effective_approver_role: str,
    now: datetime | None = None,
) -> None:
    """Require a current, approved, server-derived decision for one immutable binding."""

    validate_approval_request(request)
    validate_approval_decision(decision)
    validate_authorization_binding(binding)
    _require_fields(
        request,
        (
            "workflow_id",
            "checkpoint_id",
            "workflow_version",
            "authorization_binding_sha256",
            "policy_decision_sha256",
            "policy_version",
            "grant_sha256",
        ),
        "approval-request",
    )
    _require_fields(
        decision,
        (
            "workflow_id",
            "checkpoint_id",
            "workflow_version",
            "authorization_binding_sha256",
            "approver_id",
            "approver_role",
            "decision_sha256",
        ),
        "approval-decision",
    )
    _require_hash(decision, hash_field="decision_sha256", schema_name="approval-decision")
    if decision.get("decision") != "approved":
        raise ContractValidationError("approval-decision", "approval_not_granted")
    _same(
        request,
        decision,
        (
            "tenant_id",
            "approval_request_id",
            "case_id",
            "case_revision_id",
            "candidate_hash",
            "evidence_hashes",
            "workflow_id",
            "checkpoint_id",
            "workflow_version",
            "authorization_binding_sha256",
        ),
        "approval-decision",
    )
    if (
        request.get("authorization_binding_sha256") != binding.get("authorization_binding_sha256")
        or request.get("policy_decision_sha256") != binding.get("policy_decision_sha256")
        or request.get("policy_version") != binding.get("policy_version")
        or request.get("grant_sha256") != binding.get("grant_sha256")
    ):
        raise ContractValidationError("approval-request", "binding_mismatch")
    if (
        decision.get("tenant_id") != effective_tenant_id
        or decision.get("approver_id") != effective_approver_id
        or decision.get("approver_role") != effective_approver_role
    ):
        raise ContractValidationError("approval-decision", "actor_identity_mismatch")
    if (
        request.get("case_revision_id") != current_case_revision_id
        or request.get("checkpoint_id") != current_checkpoint_id
        or request.get("workflow_version") != current_workflow_version
        or request.get("candidate_hash") != current_candidate_hash
        or list(request.get("evidence_hashes", [])) != list(current_evidence_hashes)
    ):
        raise ContractValidationError("approval-decision", "approval_stale")
    current_time = now or datetime.now(UTC)
    expiry = _parse_time(decision.get("expires_at"))
    if expiry is None or expiry <= current_time:
        raise ContractValidationError("approval-decision", "approval_expired")


def validate_outbound_delivery_chain(
    intent: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    completions: Sequence[Mapping[str, Any]],
    binding: Mapping[str, Any],
    root: Any = None,
) -> None:
    """Validate the separate fixture-only delivery chain without ticket assumptions."""

    validate_outbound_delivery_intent(intent, root)
    validate_authorization_binding(binding, root)
    if intent.get("authorization_binding_sha256") != binding.get("authorization_binding_sha256"):
        raise ContractValidationError("outbound-delivery-intent", "binding_mismatch")
    if list(intent.get("evidence_hashes", [])) != list(binding.get("evidence_hashes", [])):
        raise ContractValidationError("outbound-delivery-intent", "binding_mismatch")
    if intent.get("candidate_hash") != binding.get("candidate_hash"):
        raise ContractValidationError("outbound-delivery-intent", "binding_mismatch")
    if len(completions) > 1:
        raise ContractValidationError("outbound-delivery-completion", "multiple_completions")
    seen_observations: set[str] = set()
    for observation in observations:
        validate_outbound_delivery_observation(observation, root)
        observation_id = str(observation["observation_id"])
        if observation_id in seen_observations:
            raise ContractValidationError("outbound-delivery-observation", "duplicate_observation")
        seen_observations.add(observation_id)
        _same(
            intent,
            observation,
            ("tenant_id", "case_id", "case_revision_id", "workflow_id", "checkpoint_id"),
            "outbound-delivery-observation",
        )
        if observation.get("intent_id") != intent.get("intent_id"):
            raise ContractValidationError(
                "outbound-delivery-observation", "intent_reference_mismatch"
            )
    for completion in completions:
        validate_outbound_delivery_completion(completion, root)
        _same(
            intent,
            completion,
            ("tenant_id", "case_id", "case_revision_id", "workflow_id", "checkpoint_id"),
            "outbound-delivery-completion",
        )
        if completion.get("intent_id") != intent.get("intent_id"):
            raise ContractValidationError(
                "outbound-delivery-completion", "intent_reference_mismatch"
            )
        matching = next(
            (
                observation
                for observation in observations
                if observation.get("observation_id") == completion.get("observation_id")
                and observation.get("status") == "present"
            ),
            None,
        )
        if matching is None:
            raise ContractValidationError(
                "outbound-delivery-completion", "completion_observation_missing"
            )
        if (
            matching.get("observed_delivery_id") != completion.get("observed_delivery_id")
            or matching.get("observed_version") != completion.get("observed_version")
            or matching.get("content_sha256") != completion.get("content_sha256")
        ):
            raise ContractValidationError(
                "outbound-delivery-completion", "completion_observation_mismatch"
            )
