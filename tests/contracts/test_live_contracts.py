from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from weflow_contracts import ContractValidationError, validate_payload
from weflow_contracts.evaluation import canonical_sha256, validate_run_metrics
from weflow_contracts.live import (
    validate_live_contract_chain,
    validate_model_action_proposal,
    validate_model_tool_observation,
    validate_provider_price_profile,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "contracts" / "v1"


def _load(relative_path: str) -> dict[str, object]:
    return json.loads((FIXTURES / relative_path).read_text(encoding="utf-8"))


def _rehash(payload: dict[str, object], field: str) -> None:
    payload[field] = canonical_sha256(payload, without=field)


def _linked_records() -> tuple[dict[str, object], ...]:
    fixture = deepcopy(_load("semantic/live-boundary.json"))
    intent = fixture["model_invocation_intent"]
    observation = fixture["model_invocation_observation"]
    artifact = fixture["response_draft_artifact"]
    binding = fixture["live_candidate_binding"]
    metrics = fixture["live_run_metrics"]
    attempt = fixture["live_evaluation_attempt"]
    report = fixture["live_evaluation_suite_report"]
    for payload, field in (
        (intent, "intent_sha256"),
        (observation, "observation_sha256"),
        (artifact, "artifact_sha256"),
        (binding, "binding_sha256"),
        (metrics, "metrics_sha256"),
    ):
        _rehash(payload, field)
    attempt["metrics_sha256"] = metrics["metrics_sha256"]
    attempt["candidate_binding_id"] = binding["binding_sha256"]
    _rehash(attempt, "attempt_sha256")
    _rehash(report, "report_sha256")
    return intent, observation, artifact, binding, metrics, attempt, report


def test_live_boundary_schema_fixtures_are_closed_and_payload_safe() -> None:
    fixture = _load("semantic/live-boundary.json")
    for payload in fixture.values():
        validate_payload(payload, ROOT)
    validate_model_action_proposal(fixture["model_action_proposal"], ROOT)
    validate_model_tool_observation(fixture["model_tool_observation"], ROOT)


def test_model_boundary_rejects_identity_arguments_authority_raw_body_and_secret_fields() -> None:
    invalid = _load("invalid/live-boundary-invalid-payloads.json")
    for payload in invalid.values():
        with pytest.raises(ContractValidationError):
            validate_payload(payload, ROOT)


def test_live_invocation_to_report_chain_is_hash_linked() -> None:
    validate_live_contract_chain(*_linked_records(), ROOT)


def test_detached_live_candidate_binding_is_rejected() -> None:
    records = list(_linked_records())
    binding = deepcopy(records[3])
    binding["tenant_id"] = "tenant-foreign"
    _rehash(binding, "binding_sha256")
    records[3] = binding

    with pytest.raises(ContractValidationError, match="tenant_identity_mismatch"):
        validate_live_contract_chain(*records, ROOT)


def test_price_profile_is_hash_bound_and_dated() -> None:
    profile = deepcopy(_load("semantic/live-boundary.json")["provider_price_profile"])
    _rehash(profile, "profile_sha256")
    validate_provider_price_profile(profile, ROOT)


def test_live_metrics_cannot_validate_as_retained_offline_run_metrics() -> None:
    live_metrics = _linked_records()[4]
    with pytest.raises(ContractValidationError, match="schema_identity_invalid"):
        validate_run_metrics(live_metrics, ROOT)
