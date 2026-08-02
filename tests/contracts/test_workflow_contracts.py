import json
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    validate_checkpoint_sequence,
    validate_side_effect_chain,
    validate_side_effect_completion,
    validate_side_effect_intent,
    validate_side_effect_intents,
    validate_side_effect_observation,
    validate_synthetic_sla_policy,
    validate_workflow_checkpoint,
    validate_workflow_command,
    validate_workflow_command_version,
    validate_workflow_projection,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def load_fixture(relative_path: str):
    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_workflow_contracts_accept_safe_boundary_payloads() -> None:
    payloads = load_fixture("valid-payloads.json")

    validate_workflow_projection(payloads["workflow-projection"], ROOT)
    validate_workflow_checkpoint(payloads["workflow-checkpoint"], ROOT)
    validate_workflow_command(payloads["workflow-command"], ROOT)
    validate_synthetic_sla_policy(payloads["synthetic-sla-policy"], ROOT)
    validate_side_effect_intent(payloads["side-effect-intent"], ROOT)
    validate_side_effect_observation(payloads["side-effect-observation"], ROOT)
    validate_side_effect_completion(payloads["side-effect-completion"], ROOT)


@pytest.mark.parametrize(
    "payload",
    load_fixture("invalid/workflow-invalid-payloads.json").values(),
)
def test_workflow_contracts_reject_raw_or_unauthorized_shape(payload: dict[str, object]) -> None:
    validators = {
        "workflow-command.schema.json": validate_workflow_command,
        "side-effect-intent.schema.json": validate_side_effect_intent,
        "side-effect-observation.schema.json": validate_side_effect_observation,
        "workflow-checkpoint.schema.json": validate_workflow_checkpoint,
    }
    schema_name = str(payload["schema_id"]).rsplit("/", 1)[-1]
    with pytest.raises(ContractValidationError):
        validators[schema_name](payload, ROOT)


def test_checkpoint_and_side_effect_recovery_chains_are_tenant_bound() -> None:
    fixture = load_fixture("semantic/workflow-recovery.json")

    validate_checkpoint_sequence(fixture["checkpoints"], ROOT)
    validate_side_effect_chain(
        fixture["intent"], fixture["observations"], fixture["completions"], ROOT
    )


def test_side_effect_completion_requires_a_matching_present_observation() -> None:
    fixture = load_fixture("semantic/workflow-recovery.json")
    completion = dict(fixture["completions"][0])
    completion["observation_id"] = "missing-observation"

    with pytest.raises(ContractValidationError, match="completion_observation_missing"):
        validate_side_effect_chain(fixture["intent"], fixture["observations"], [completion], ROOT)


def test_workflow_contract_semantics_reject_foreign_stale_and_duplicate_authority() -> None:
    fixture = load_fixture("semantic/workflow-negative-cases.json")

    with pytest.raises(ContractValidationError, match="tenant_identity_mismatch"):
        validate_workflow_command(
            fixture["foreign_command"], ROOT, effective_tenant_id="tenant-demo"
        )
    with pytest.raises(ContractValidationError, match="workflow_version_conflict"):
        validate_workflow_command_version(
            fixture["stale_command"], fixture["current_workflow_version"], ROOT
        )
    with pytest.raises(ContractValidationError, match="duplicate_intent"):
        validate_side_effect_intents(fixture["duplicate_intents"], ROOT)

    validate_side_effect_observation(fixture["conflicting_observation"], ROOT)
