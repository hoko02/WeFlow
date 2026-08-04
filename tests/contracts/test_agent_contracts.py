import json
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    validate_agent_action,
    validate_context_manifest,
    validate_response_candidate,
    validate_tool_request,
    validate_tool_result,
    validate_verifier_outcome,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def load_fixture(relative_path: str):
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_agent_boundary_contracts_are_schema_valid_and_causally_linked() -> None:
    fixture = load_fixture("semantic/agent-boundary.json")

    validate_context_manifest(fixture["context_manifest"], ROOT)
    validate_agent_action(
        fixture["agent_action"], ROOT, context_manifest=fixture["context_manifest"]
    )
    validate_tool_request(
        fixture["tool_request"], ROOT, context_manifest=fixture["context_manifest"]
    )
    validate_tool_result(fixture["tool_result"], ROOT, tool_request=fixture["tool_request"])
    validate_response_candidate(
        fixture["response_candidate"],
        ROOT,
        context_manifest=fixture["context_manifest"],
        evidence_hashes=[fixture["tool_result"]["content_sha256"]],
    )
    validate_verifier_outcome(
        fixture["verifier_outcome"], ROOT, candidate=fixture["response_candidate"]
    )


def test_agent_contracts_reject_raw_and_authority_payload_shapes() -> None:
    invalid = load_fixture("invalid/agent-invalid-payloads.json")

    for payload in invalid.values():
        validator = {
            "agent-action.schema.json": validate_agent_action,
            "tool-request.schema.json": validate_tool_request,
            "tool-result.schema.json": validate_tool_result,
            "response-candidate.schema.json": validate_response_candidate,
            "verifier-outcome.schema.json": validate_verifier_outcome,
        }[str(payload["schema_id"]).rsplit("/", 1)[-1]]
        with pytest.raises(ContractValidationError):
            validator(payload, ROOT)


def test_agent_contracts_reject_cross_tenant_context_linkage() -> None:
    fixture = load_fixture("semantic/agent-boundary.json")

    with pytest.raises(ContractValidationError, match="tenant_identity_mismatch"):
        validate_agent_action(
            fixture["foreign_agent_action"],
            ROOT,
            context_manifest=fixture["context_manifest"],
        )


def test_retained_contract_fixtures_remain_valid() -> None:
    fixture = load_fixture("semantic/agent-boundary.json")
    payloads = load_fixture("valid-payloads.json")

    for name in fixture["retained_fixture_names"]:
        assert name in payloads
