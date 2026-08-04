"""Deterministic validations that complement the JSON Schema boundary contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft202012Validator

from .schemas import load_contract_schemas


class ContractValidationError(ValueError):
    """A validation error intentionally free of payload values and secret material."""

    def __init__(self, schema_name: str, reason_code: str) -> None:
        self.schema_name = schema_name
        self.reason_code = reason_code
        super().__init__(f"invalid_contract:{schema_name}:{reason_code}")


def _schema_name(schema_id: str) -> str:
    return schema_id.rsplit("/", 1)[-1].removesuffix(".schema.json")


def validate_payload(payload: Mapping[str, Any], root: Any = None) -> None:
    declared_schema_id = payload.get("schema_id")
    if not isinstance(declared_schema_id, str) or not declared_schema_id:
        raise ContractValidationError("unknown", "missing_schema_id")
    schemas = load_contract_schemas(root)
    schema = schemas.get(declared_schema_id)
    if schema is None:
        raise ContractValidationError("unknown", "schema_not_found")

    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(dict(payload)), key=lambda error: list(error.absolute_path)
    )
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path) or "root"
        raise ContractValidationError(_schema_name(declared_schema_id), f"{path}:{error.validator}")


def validate_tenant_reference(*records: Mapping[str, Any]) -> None:
    tenant_ids = {record.get("tenant_id") for record in records}
    if None in tenant_ids or "" in tenant_ids:
        raise ContractValidationError("tenant-reference", "tenant_id_missing")
    if len(tenant_ids) != 1:
        raise ContractValidationError("tenant-reference", "tenant_mismatch")


def validate_revision_chain(revisions: Sequence[Mapping[str, Any]]) -> None:
    if not revisions:
        raise ContractValidationError("case-revision", "revision_chain_empty")
    expected_revision = 1
    previous_id: str | None = None
    case_id: str | None = None
    tenant_id: str | None = None
    for revision in revisions:
        validate_payload(revision)
        if revision["revision"] != expected_revision:
            raise ContractValidationError("case-revision", "revision_not_monotonic")
        if revision.get("previous_case_revision_id") != previous_id:
            raise ContractValidationError("case-revision", "predecessor_mismatch")
        if case_id is None:
            case_id = revision["case_id"]
            tenant_id = revision["tenant_id"]
        elif revision["case_id"] != case_id or revision["tenant_id"] != tenant_id:
            raise ContractValidationError("case-revision", "case_or_tenant_mismatch")
        previous_id = revision["case_revision_id"]
        expected_revision += 1


def stable_idempotency_key(
    *, tenant_id: str, provider_id: str, operation: str, natural_key: str, intended_state_hash: str
) -> str:
    material = {
        "tenant_id": tenant_id,
        "provider_id": provider_id,
        "operation": operation,
        "natural_key": natural_key,
        "intended_state_hash": intended_state_hash,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify_event_delivery(events: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    seen_event_ids: set[str] = set()
    duplicate = False
    out_of_order = False
    latest_occurred_at: str | None = None
    for event in events:
        validate_payload(event)
        event_id = str(event["event_id"])
        occurred_at = str(event["occurred_at"])
        if event_id in seen_event_ids:
            duplicate = True
        seen_event_ids.add(event_id)
        if latest_occurred_at is not None and occurred_at < latest_occurred_at:
            out_of_order = True
        latest_occurred_at = max(latest_occurred_at or occurred_at, occurred_at)
    return {"duplicate": duplicate, "out_of_order": out_of_order}


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def approval_is_authorized(
    request: Mapping[str, Any],
    decision: Mapping[str, Any],
    *,
    current_case_revision_id: str,
    current_evidence_hashes: Sequence[str],
    now: datetime | None = None,
    authorization_binding: Mapping[str, Any] | None = None,
    capability_grant: Mapping[str, Any] | None = None,
    policy_decision: Mapping[str, Any] | None = None,
    current_checkpoint_id: str | None = None,
    current_workflow_version: int | None = None,
    current_candidate_hash: str | None = None,
    effective_tenant_id: str | None = None,
    effective_approver_id: str | None = None,
    effective_approver_role: str | None = None,
) -> bool:
    """Return false for stale, expired, mismatched, or non-approved decisions."""

    validate_payload(request)
    validate_payload(decision)
    if decision.get("decision") != "approved":
        return False
    if request.get("tenant_id") != decision.get("tenant_id"):
        return False
    if request.get("approval_request_id") != decision.get("approval_request_id"):
        return False
    if request.get("case_id") != decision.get("case_id"):
        return False
    if request.get("case_revision_id") != decision.get("case_revision_id"):
        return False
    if request.get("case_revision_id") != current_case_revision_id:
        return False
    if request.get("candidate_hash") != decision.get("candidate_hash"):
        return False
    if frozenset(request.get("evidence_hashes", [])) != frozenset(
        decision.get("evidence_hashes", [])
    ):
        return False
    if frozenset(request.get("evidence_hashes", [])) != frozenset(current_evidence_hashes):
        return False
    expiry = _parse_time(decision.get("expires_at"))
    current_time = now or datetime.now(UTC)
    if expiry is None or expiry <= current_time:
        return False

    change4_records = (authorization_binding, capability_grant, policy_decision)
    if not any(record is not None for record in change4_records):
        return True
    if (
        any(record is None for record in change4_records)
        or current_checkpoint_id is None
        or current_workflow_version is None
        or current_candidate_hash is None
        or effective_tenant_id is None
        or effective_approver_id is None
        or effective_approver_role is None
    ):
        return False
    try:
        # Import locally: authorization helpers build on the base schema validator in
        # this module, while this retained helper remains import-compatible.
        from .authorization import (
            validate_change4_authorization_profile,
            validate_hash_bound_approval,
        )

        validate_change4_authorization_profile(
            authorization_binding,
            capability_grant,
            policy_decision,
            action="outbound_delivery.execute",
            current_case_revision_id=current_case_revision_id,
            current_checkpoint_id=current_checkpoint_id,
            current_workflow_version=current_workflow_version,
            current_candidate_hash=current_candidate_hash,
            current_evidence_hashes=current_evidence_hashes,
            resource_id=str(authorization_binding.get("delivery_resource_id", "")),
            data_classification=str(authorization_binding.get("data_classification", "")),
            effective_tenant_id=effective_tenant_id,
            now=current_time,
        )
        validate_hash_bound_approval(
            request,
            decision,
            authorization_binding,
            current_case_revision_id=current_case_revision_id,
            current_checkpoint_id=current_checkpoint_id,
            current_workflow_version=current_workflow_version,
            current_candidate_hash=current_candidate_hash,
            current_evidence_hashes=current_evidence_hashes,
            effective_tenant_id=effective_tenant_id,
            effective_approver_id=effective_approver_id,
            effective_approver_role=effective_approver_role,
            now=current_time,
        )
    except ContractValidationError:
        return False
    return True
