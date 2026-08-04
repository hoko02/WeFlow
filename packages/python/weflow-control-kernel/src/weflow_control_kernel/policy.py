"""Pure, fixture-owned capability and policy helpers for Change 4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from weflow_contracts import (
    APPROVAL_DECISION_SCHEMA_ID,
    APPROVAL_REQUEST_SCHEMA_ID,
    AUTHORIZATION_BINDING_SCHEMA_ID,
    CAPABILITY_GRANT_SCHEMA_ID,
    POLICY_DECISION_SCHEMA_ID,
    canonical_sha256,
    content_hash,
    validate_approval_decision,
    validate_approval_request,
    validate_authorization_binding,
    validate_capability_grant,
    validate_policy_decision,
)

JsonObject = dict[str, Any]

API_503_POLICY_FIXTURE_ID = "api-503-policy-approval-delivery"
API_503_DELIVERY_RESOURCE_ID = "fixture-local-im:api-503"
API_503_DELIVERY_RESOURCE_SCOPE = API_503_DELIVERY_RESOURCE_ID
API_503_POLICY_VERSION = "fixture-policy.v1"
API_503_DELIVERY_BUDGET = 1
FIXTURE_CONTROLLER_ROLE = "fixture-controller"
FIXTURE_APPROVER_ROLE = "fixture-approver"

_ALLOWLISTED_ACTIONS = frozenset(
    {"approval.request", "approval.decide", "outbound_delivery.execute"}
)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _stable_identifier(prefix: str, material: object) -> str:
    return f"{prefix}_{canonical_sha256({'prefix': prefix, 'material': material})[:32]}"


def api_503_policy_fixture(now: datetime) -> JsonObject:
    """Expose only safe, deterministic configuration metadata for the named fixture."""

    return {
        "fixture_id": API_503_POLICY_FIXTURE_ID,
        "tenant_id": "tenant-alpha",
        "policy_version": API_503_POLICY_VERSION,
        "delivery_resource_id": API_503_DELIVERY_RESOURCE_ID,
        "delivery_resource_scope": API_503_DELIVERY_RESOURCE_SCOPE,
        "data_classification": "synthetic",
        "delivery_budget": API_503_DELIVERY_BUDGET,
        "fixed_at": _timestamp(now),
        "network_required": False,
        "credentials_required": False,
    }


def issue_fixture_grant(
    *,
    tenant_id: str,
    subject_id: str,
    role: str,
    now: datetime,
    status: str = "active",
    expires_at: datetime | None = None,
) -> JsonObject:
    """Create an immutable local grant; only setup/control code calls this helper."""

    expiry = expires_at or (now + timedelta(minutes=30))
    grant_id = _stable_identifier(
        "fixture_grant",
        {
            "fixture_id": API_503_POLICY_FIXTURE_ID,
            "tenant_id": tenant_id,
            "subject_id": subject_id,
            "role": role,
        },
    )
    grant: JsonObject = {
        "schema_id": CAPABILITY_GRANT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": tenant_id,
        "grant_id": grant_id,
        "subject_id": subject_id,
        "capability": "fixture-policy-approval-delivery",
        "scopes": sorted(_ALLOWLISTED_ACTIONS),
        "issued_at": _timestamp(now),
        "expires_at": _timestamp(expiry),
        "status": status,
        "grant_version": "fixture-v1",
        "role": role,
        "resource_scope": API_503_DELIVERY_RESOURCE_SCOPE,
        "data_classifications": ["synthetic"],
    }
    grant["grant_sha256"] = content_hash(grant, without="grant_sha256")
    validate_capability_grant(grant)
    return grant


def evaluate_fixture_policy(
    *,
    tenant_id: str,
    subject_id: str,
    role: str,
    action: str,
    case_id: str,
    case_revision_id: str,
    workflow_id: str,
    checkpoint_id: str,
    workflow_version: int,
    candidate_hash: str,
    evidence_hashes: Sequence[str],
    grant: Mapping[str, Any] | None,
    resource_id: str,
    data_classification: str,
    remaining_budget: int,
    now: datetime,
) -> JsonObject:
    """Evaluate exactly one deterministic, default-deny fixture policy decision."""

    grant_hash = "0" * 64
    grant_id = "grant-unavailable"
    if grant is not None:
        grant_hash = str(grant.get("grant_sha256", grant_hash))
        grant_id = str(grant.get("grant_id", grant_id))
    input_material = {
        "tenant_id": tenant_id,
        "subject_id": subject_id,
        "role": role,
        "action": action,
        "case_id": case_id,
        "case_revision_id": case_revision_id,
        "workflow_id": workflow_id,
        "checkpoint_id": checkpoint_id,
        "workflow_version": workflow_version,
        "candidate_hash": candidate_hash,
        "evidence_hashes": list(evidence_hashes),
        "resource_id": resource_id,
        "data_classification": data_classification,
        "remaining_budget": remaining_budget,
        "policy_version": API_503_POLICY_VERSION,
        "grant_id": grant_id,
        "grant_sha256": grant_hash,
    }
    reason_code = "policy_default_deny"
    allow = False
    if (
        tenant_id != "tenant-alpha"
        or action not in _ALLOWLISTED_ACTIONS
        or not case_id
        or not case_revision_id
        or not workflow_id
        or not checkpoint_id
        or workflow_version < 0
        or len(evidence_hashes) == 0
    ):
        reason_code = "policy_identity_or_causation_denied"
    elif resource_id != API_503_DELIVERY_RESOURCE_ID:
        reason_code = "policy_resource_denied"
    elif data_classification != "synthetic":
        reason_code = "policy_classification_denied"
    elif remaining_budget < 1:
        reason_code = "policy_budget_denied"
    elif grant is None:
        reason_code = "policy_grant_missing"
    elif (
        grant.get("tenant_id") != tenant_id
        or grant.get("subject_id") != subject_id
        or grant.get("role") != role
        or grant.get("status") != "active"
        or action not in grant.get("scopes", [])
        or grant.get("resource_scope") != resource_id
        or data_classification not in grant.get("data_classifications", [])
    ):
        reason_code = "policy_grant_denied"
    else:
        try:
            expiry = datetime.fromisoformat(str(grant["expires_at"]).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError("timezone_required")
        except (KeyError, TypeError, ValueError):
            reason_code = "policy_grant_invalid"
        else:
            expected_role = (
                FIXTURE_APPROVER_ROLE if action == "approval.decide" else FIXTURE_CONTROLLER_ROLE
            )
            if expiry.astimezone(UTC) <= now.astimezone(UTC):
                reason_code = "policy_grant_expired"
            elif role != expected_role:
                reason_code = "policy_role_denied"
            else:
                allow = True
                reason_code = "fixture_policy_allowed"
    policy_input_sha256 = canonical_sha256(input_material)
    decision: JsonObject = {
        "schema_id": POLICY_DECISION_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": tenant_id,
        "policy_decision_id": _stable_identifier(
            "policy_decision", {"policy_input_sha256": policy_input_sha256, "decision": allow}
        ),
        "case_id": case_id,
        "case_revision_id": case_revision_id,
        "decision": "allow" if allow else "deny",
        "reason_code": reason_code,
        "evidence_hashes": list(evidence_hashes),
        "decided_at": _timestamp(now),
        "checkpoint_id": checkpoint_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "candidate_hash": candidate_hash,
        "action": action,
        "policy_version": API_503_POLICY_VERSION,
        "policy_input_sha256": policy_input_sha256,
        "grant_id": grant_id,
        "grant_sha256": grant_hash,
        "subject_id": subject_id,
        "role": role,
        "resource_id": resource_id,
        "data_classification": data_classification,
    }
    decision["policy_decision_sha256"] = content_hash(decision, without="policy_decision_sha256")
    validate_policy_decision(decision)
    return decision


def bind_fixture_authorization(
    *,
    decision: Mapping[str, Any],
    grant: Mapping[str, Any],
    remaining_budget: int,
    expires_at: datetime,
    created_at: datetime,
) -> JsonObject:
    """Create one content-addressed profile after a policy allow decision."""

    binding_id = _stable_identifier(
        "authorization_binding",
        {
            "policy_decision_sha256": decision["policy_decision_sha256"],
            "grant_sha256": grant["grant_sha256"],
            "candidate_hash": decision["candidate_hash"],
            "evidence_hashes": list(decision["evidence_hashes"]),
        },
    )
    binding: JsonObject = {
        "schema_id": AUTHORIZATION_BINDING_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": decision["tenant_id"],
        "authorization_binding_id": binding_id,
        "case_id": decision["case_id"],
        "case_revision_id": decision["case_revision_id"],
        "workflow_id": decision["workflow_id"],
        "checkpoint_id": decision["checkpoint_id"],
        "workflow_version": decision["workflow_version"],
        "candidate_hash": decision["candidate_hash"],
        "evidence_hashes": list(decision["evidence_hashes"]),
        "action": decision["action"],
        "policy_decision_id": decision["policy_decision_id"],
        "policy_version": decision["policy_version"],
        "policy_decision_sha256": decision["policy_decision_sha256"],
        "grant_id": grant["grant_id"],
        "grant_version": grant["grant_version"],
        "grant_sha256": grant["grant_sha256"],
        "subject_id": grant["subject_id"],
        "role": grant["role"],
        "delivery_resource_id": API_503_DELIVERY_RESOURCE_ID,
        "delivery_resource_scope": API_503_DELIVERY_RESOURCE_SCOPE,
        "data_classification": "synthetic",
        "remaining_budget": remaining_budget,
        "expires_at": _timestamp(expires_at),
        "created_at": _timestamp(created_at),
    }
    binding["authorization_binding_sha256"] = content_hash(
        binding, without="authorization_binding_sha256"
    )
    validate_authorization_binding(binding)
    return binding


def build_approval_request(binding: Mapping[str, Any], *, created_at: datetime) -> JsonObject:
    request: JsonObject = {
        "schema_id": APPROVAL_REQUEST_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": binding["tenant_id"],
        "approval_request_id": _stable_identifier(
            "approval_request",
            {"authorization_binding_sha256": binding["authorization_binding_sha256"]},
        ),
        "case_id": binding["case_id"],
        "case_revision_id": binding["case_revision_id"],
        "candidate_hash": binding["candidate_hash"],
        "policy_decision_id": binding["policy_decision_id"],
        "evidence_hashes": list(binding["evidence_hashes"]),
        "created_at": _timestamp(created_at),
        "expires_at": binding["expires_at"],
        "workflow_id": binding["workflow_id"],
        "checkpoint_id": binding["checkpoint_id"],
        "workflow_version": binding["workflow_version"],
        "authorization_binding_sha256": binding["authorization_binding_sha256"],
        "policy_decision_sha256": binding["policy_decision_sha256"],
        "policy_version": binding["policy_version"],
        "grant_sha256": binding["grant_sha256"],
    }
    validate_approval_request(request)
    return request


def build_approval_decision(
    request: Mapping[str, Any],
    *,
    approver_id: str,
    approver_role: str,
    decision: str,
    decided_at: datetime,
) -> JsonObject:
    result: JsonObject = {
        "schema_id": APPROVAL_DECISION_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": request["tenant_id"],
        "approval_decision_id": _stable_identifier(
            "approval_decision",
            {
                "approval_request_id": request["approval_request_id"],
                "decision": decision,
                "approver_id": approver_id,
            },
        ),
        "approval_request_id": request["approval_request_id"],
        "case_id": request["case_id"],
        "case_revision_id": request["case_revision_id"],
        "candidate_hash": request["candidate_hash"],
        "evidence_hashes": list(request["evidence_hashes"]),
        "decision": decision,
        "decided_at": _timestamp(decided_at),
        "expires_at": request["expires_at"],
        "workflow_id": request["workflow_id"],
        "checkpoint_id": request["checkpoint_id"],
        "workflow_version": request["workflow_version"],
        "authorization_binding_sha256": request["authorization_binding_sha256"],
        "approver_id": approver_id,
        "approver_role": approver_role,
    }
    result["decision_sha256"] = content_hash(result, without="decision_sha256")
    validate_approval_decision(result)
    return result
