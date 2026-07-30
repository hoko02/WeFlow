import json
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    validate_case_projection,
    validate_generated_ledger_event,
    validate_inbound_message_event,
    validate_inbound_tenant_claim,
    validate_payload,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def load_fixture(relative_path: str):
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_inbound_and_projection_contracts_accept_safe_normalized_payloads() -> None:
    payloads = load_fixture("valid-payloads.json")

    validate_inbound_message_event(payloads["inbound-message-event"], ROOT)
    validate_case_projection(payloads["case-projection"], ROOT)


@pytest.mark.parametrize("payload", load_fixture("invalid/intake-invalid-payloads.json").values())
def test_raw_or_invalid_intake_contracts_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ContractValidationError):
        validate_payload(payload, ROOT)


def test_generated_ledger_events_need_order_and_payload_digest() -> None:
    payload = load_fixture("semantic/missing-generated-ledger-metadata.json")

    validate_payload(payload, ROOT)
    with pytest.raises(ContractValidationError, match="case_event_index_required"):
        validate_generated_ledger_event(payload, ROOT)


def test_inbound_tenant_claim_must_match_server_derived_tenant() -> None:
    fixture = load_fixture("semantic/inbound-tenant-mismatch.json")

    with pytest.raises(ContractValidationError, match="tenant_identity_mismatch"):
        validate_inbound_tenant_claim(
            fixture["inbound_message"],
            effective_tenant_id=fixture["effective_tenant_id"],
            root=ROOT,
        )
