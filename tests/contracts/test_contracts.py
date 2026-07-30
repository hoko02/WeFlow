import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    approval_is_authorized,
    classify_event_delivery,
    schema_fingerprints,
    stable_idempotency_key,
    validate_payload,
    validate_revision_chain,
    validate_tenant_reference,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def load_fixture(relative_path: str):
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_valid_payloads_are_accepted_by_canonical_schemas() -> None:
    payloads = load_fixture("valid-payloads.json")

    assert len(payloads) == 16
    for payload in payloads.values():
        validate_payload(payload, ROOT)


def test_missing_schema_identity_is_rejected_without_echoing_payload() -> None:
    with pytest.raises(ContractValidationError) as error:
        validate_payload(load_fixture("invalid/missing-schema-identity.json"), ROOT)

    assert error.value.reason_code == "missing_schema_id"
    assert "case-invalid" not in str(error.value)


def test_revision_chain_is_monotonic_and_immutable() -> None:
    validate_revision_chain(load_fixture("semantic/revision-chain.json")["revisions"])


def test_cross_tenant_evidence_reference_is_rejected() -> None:
    fixture = load_fixture("semantic/cross-tenant-evidence.json")
    validate_payload(fixture["case"], ROOT)
    validate_payload(fixture["evidence"], ROOT)

    with pytest.raises(ContractValidationError, match="tenant_mismatch"):
        validate_tenant_reference(fixture["case"], fixture["evidence"])


def test_duplicate_delivery_uses_a_stable_idempotency_key_without_execution() -> None:
    fixture = load_fixture("semantic/duplicate-delivery.json")
    material = fixture["idempotency_material"]
    key = stable_idempotency_key(**material)

    for intent in fixture["intents"]:
        validate_payload(intent, ROOT)
        assert intent["stage"] == "intent"
        assert intent["idempotency_key"] == key


def test_out_of_order_events_are_preserved_for_fixture_classification() -> None:
    classification = classify_event_delivery(
        load_fixture("semantic/out-of-order-events.json")["events"]
    )

    assert classification == {"duplicate": False, "out_of_order": True}


def test_stale_approval_is_not_authorized() -> None:
    fixture = load_fixture("semantic/stale-approval.json")

    assert not approval_is_authorized(
        fixture["request"],
        fixture["decision"],
        current_case_revision_id=fixture["current_case_revision_id"],
        current_evidence_hashes=fixture["current_evidence_hashes"],
        now=datetime(2026, 7, 29, tzinfo=UTC),
    )


def test_schema_fingerprints_detect_a_changed_v1_semantic_contract() -> None:
    expected = load_fixture("schema-fingerprints.json")

    assert schema_fingerprints(ROOT) == expected
