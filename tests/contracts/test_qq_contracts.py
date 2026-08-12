import copy
import json
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    validate_payload,
    validate_qq_acknowledgement_chain,
    validate_qq_gateway_cursor,
    validate_qq_sandbox_inbound_event,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def load_fixture(relative_path: str):
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_qq_boundary_contracts_and_links_accept_safe_fixtures() -> None:
    fixture = load_fixture("semantic/qq-boundary.json")

    validate_qq_sandbox_inbound_event(fixture["inbound_event"], ROOT)
    validate_qq_gateway_cursor(fixture["gateway_cursor"], ROOT)
    validate_qq_acknowledgement_chain(
        fixture["acknowledgement_intent"],
        [fixture["acknowledgement_observation"]],
        [fixture["acknowledgement_completion"]],
        ROOT,
    )


@pytest.mark.parametrize(
    "payload",
    load_fixture("invalid/qq-boundary-invalid-payloads.json").values(),
)
def test_qq_contracts_reject_raw_secret_authority_and_success_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ContractValidationError):
        validate_payload(payload, ROOT)


def test_qq_inbound_semantics_reject_detached_hash_and_natural_key() -> None:
    inbound = load_fixture("semantic/qq-boundary.json")["inbound_event"]
    detached_source = {**inbound, "source_message_id_hash": "f" * 64}
    detached_natural_key = {**inbound, "inbound_natural_key": "e" * 64}

    with pytest.raises(ContractValidationError, match="source_message_id_hash_mismatch"):
        validate_qq_sandbox_inbound_event(detached_source, ROOT)
    with pytest.raises(ContractValidationError, match="inbound_natural_key_mismatch"):
        validate_qq_sandbox_inbound_event(detached_natural_key, ROOT)


def test_qq_chain_rejects_foreign_or_non_present_completion() -> None:
    fixture = load_fixture("semantic/qq-boundary.json")
    foreign = copy.deepcopy(fixture["acknowledgement_completion"])
    foreign["tenant_id"] = "tenant-foreign"
    unknown = copy.deepcopy(fixture["acknowledgement_observation"])
    unknown.update(
        {
            "status": "unknown",
            "provider_message_id_hash": None,
            "outcome_sha256": None,
            "reason_code": "provider_outcome_unknown",
        }
    )

    with pytest.raises(ContractValidationError, match="tenant_mismatch"):
        validate_qq_acknowledgement_chain(
            fixture["acknowledgement_intent"],
            [fixture["acknowledgement_observation"]],
            [foreign],
            ROOT,
        )
    with pytest.raises(ContractValidationError, match="completion_observation_not_present"):
        validate_qq_acknowledgement_chain(
            fixture["acknowledgement_intent"],
            [unknown],
            [fixture["acknowledgement_completion"]],
            ROOT,
        )
