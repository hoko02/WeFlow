import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    approval_is_authorized,
    validate_approval_decision,
    validate_approval_request,
    validate_authorization_binding,
    validate_capability_grant,
    validate_change4_authorization_profile,
    validate_hash_bound_approval,
    validate_outbound_delivery_chain,
    validate_outbound_delivery_intent,
    validate_policy_decision,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"
NOW = datetime(2026, 7, 29, 0, 0, 3, tzinfo=UTC)


def load_fixture(relative_path: str):
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def _profile(fixture: dict[str, object]) -> None:
    validate_change4_authorization_profile(
        fixture["authorization_binding"],
        fixture["grant"],
        fixture["policy_decision"],
        action="outbound_delivery.execute",
        current_case_revision_id="revision-api-503",
        current_checkpoint_id="checkpoint-api-503",
        current_workflow_version=7,
        current_candidate_hash="d" * 64,
        current_evidence_hashes=["a" * 64, "b" * 64, "c" * 64],
        resource_id="fixture-local-im:api-503",
        data_classification="synthetic",
        effective_tenant_id="tenant-alpha",
        now=NOW,
    )


def test_change4_contracts_are_hash_bound_and_cross_record_valid() -> None:
    fixture = load_fixture("semantic/authorization-delivery.json")

    validate_capability_grant(fixture["grant"], ROOT)
    validate_policy_decision(fixture["policy_decision"], ROOT)
    validate_authorization_binding(fixture["authorization_binding"], ROOT)
    validate_approval_request(fixture["approval_request"], ROOT)
    validate_approval_decision(fixture["approval_decision"], ROOT)
    validate_outbound_delivery_intent(fixture["outbound_delivery_intent"], ROOT)
    _profile(fixture)
    validate_hash_bound_approval(
        fixture["approval_request"],
        fixture["approval_decision"],
        fixture["authorization_binding"],
        current_case_revision_id="revision-api-503",
        current_checkpoint_id="checkpoint-api-503",
        current_workflow_version=7,
        current_candidate_hash="d" * 64,
        current_evidence_hashes=["a" * 64, "b" * 64, "c" * 64],
        effective_tenant_id="tenant-alpha",
        effective_approver_id="fixture-approver-alpha",
        effective_approver_role="fixture-approver",
        now=NOW,
    )
    validate_outbound_delivery_chain(
        fixture["outbound_delivery_intent"],
        [fixture["outbound_delivery_observation"]],
        [fixture["outbound_delivery_completion"]],
        fixture["authorization_binding"],
        ROOT,
    )
    assert approval_is_authorized(
        fixture["approval_request"],
        fixture["approval_decision"],
        current_case_revision_id="revision-api-503",
        current_evidence_hashes=["a" * 64, "b" * 64, "c" * 64],
        now=NOW,
        authorization_binding=fixture["authorization_binding"],
        capability_grant=fixture["grant"],
        policy_decision=fixture["policy_decision"],
        current_checkpoint_id="checkpoint-api-503",
        current_workflow_version=7,
        current_candidate_hash="d" * 64,
        effective_tenant_id="tenant-alpha",
        effective_approver_id="fixture-approver-alpha",
        effective_approver_role="fixture-approver",
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "foreign_tenant",
        "expired_grant",
        "revoked_grant",
        "unsafe_classification",
        "stale_binding",
    ],
)
def test_change4_profile_denies_all_invalid_authorization_fixtures(scenario: str) -> None:
    valid = load_fixture("semantic/authorization-delivery.json")
    invalid = load_fixture("invalid/authorization-delivery-invalid-payloads.json")[scenario]
    with pytest.raises(ContractValidationError):
        validate_change4_authorization_profile(
            invalid["binding"],
            invalid["grant"],
            invalid["policy_decision"],
            action="outbound_delivery.execute",
            current_case_revision_id="revision-api-503",
            current_checkpoint_id="checkpoint-api-503",
            current_workflow_version=7,
            current_candidate_hash="d" * 64,
            current_evidence_hashes=valid["authorization_binding"]["evidence_hashes"],
            resource_id="fixture-local-im:api-503",
            data_classification="synthetic",
            effective_tenant_id="tenant-alpha",
            now=NOW,
        )


def test_change4_role_and_raw_content_are_never_authorized() -> None:
    valid = load_fixture("semantic/authorization-delivery.json")
    invalid = load_fixture("invalid/authorization-delivery-invalid-payloads.json")
    with pytest.raises(ContractValidationError):
        validate_hash_bound_approval(
            invalid["wrong_role"]["request"],
            invalid["wrong_role"]["decision"],
            invalid["wrong_role"]["binding"],
            current_case_revision_id="revision-api-503",
            current_checkpoint_id="checkpoint-api-503",
            current_workflow_version=7,
            current_candidate_hash="d" * 64,
            current_evidence_hashes=valid["authorization_binding"]["evidence_hashes"],
            effective_tenant_id="tenant-alpha",
            effective_approver_id="fixture-approver-alpha",
            effective_approver_role="fixture-approver",
            now=NOW,
        )
    with pytest.raises(ContractValidationError):
        validate_outbound_delivery_intent(invalid["raw_content"]["intent"], ROOT)
    with pytest.raises(ContractValidationError):
        validate_authorization_binding(invalid["schema_invalid"]["binding"], ROOT)
