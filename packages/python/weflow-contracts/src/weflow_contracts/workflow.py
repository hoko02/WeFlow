"""Safe contract helpers for the deterministic durable workflow boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .validation import ContractValidationError, validate_payload, validate_tenant_reference

SIDE_EFFECT_COMPLETION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/side-effect-completion.schema.json"
)
SIDE_EFFECT_INTENT_SCHEMA_ID = "https://weflow.local/contracts/v1/side-effect-intent.schema.json"
SIDE_EFFECT_OBSERVATION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/side-effect-observation.schema.json"
)
SYNTHETIC_SLA_POLICY_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/synthetic-sla-policy.schema.json"
)
WORKFLOW_CHECKPOINT_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-checkpoint.schema.json"
WORKFLOW_COMMAND_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-command.schema.json"
WORKFLOW_PROJECTION_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-projection.schema.json"


def _require_schema(
    payload: Mapping[str, Any],
    expected_schema_id: str,
    schema_name: str,
    root: Any = None,
) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != expected_schema_id:
        raise ContractValidationError(schema_name, "unexpected_schema")


def validate_workflow_projection(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, WORKFLOW_PROJECTION_SCHEMA_ID, "workflow-projection", root)


def validate_workflow_checkpoint(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, WORKFLOW_CHECKPOINT_SCHEMA_ID, "workflow-checkpoint", root)


def validate_workflow_command(
    payload: Mapping[str, Any],
    root: Any = None,
    *,
    effective_tenant_id: str | None = None,
) -> None:
    _require_schema(payload, WORKFLOW_COMMAND_SCHEMA_ID, "workflow-command", root)
    if effective_tenant_id is not None and payload.get("tenant_id") != effective_tenant_id:
        raise ContractValidationError("workflow-command", "tenant_identity_mismatch")


def validate_workflow_command_version(
    payload: Mapping[str, Any],
    current_workflow_version: int,
    root: Any = None,
    *,
    effective_tenant_id: str | None = None,
) -> None:
    """Require a command to name the exact durable workflow version it observed."""

    validate_workflow_command(payload, root, effective_tenant_id=effective_tenant_id)
    if (
        current_workflow_version < 0
        or payload.get("expected_workflow_version") != current_workflow_version
    ):
        raise ContractValidationError("workflow-command", "workflow_version_conflict")


def validate_synthetic_sla_policy(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, SYNTHETIC_SLA_POLICY_SCHEMA_ID, "synthetic-sla-policy", root)


def validate_side_effect_intent(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, SIDE_EFFECT_INTENT_SCHEMA_ID, "side-effect-intent", root)


def validate_side_effect_observation(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, SIDE_EFFECT_OBSERVATION_SCHEMA_ID, "side-effect-observation", root)


def validate_side_effect_completion(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, SIDE_EFFECT_COMPLETION_SCHEMA_ID, "side-effect-completion", root)


def validate_checkpoint_sequence(
    checkpoints: Sequence[Mapping[str, Any]], root: Any = None
) -> None:
    """Require one immutable, linked checkpoint chain for one workflow identity."""

    if not checkpoints:
        raise ContractValidationError("workflow-checkpoint", "checkpoint_chain_empty")
    expected_sequence = 1
    previous_id: str | None = None
    identity: tuple[object, object, object, object] | None = None
    previous_version: int | None = None
    completed_ids: set[str] = set()
    checkpoint_ids: set[str] = set()
    for checkpoint in checkpoints:
        validate_workflow_checkpoint(checkpoint, root)
        current_identity = (
            checkpoint["tenant_id"],
            checkpoint["case_id"],
            checkpoint["case_revision_id"],
            checkpoint["workflow_id"],
        )
        if identity is None:
            identity = current_identity
        elif identity != current_identity:
            raise ContractValidationError("workflow-checkpoint", "workflow_identity_mismatch")
        if checkpoint["checkpoint_sequence"] != expected_sequence:
            raise ContractValidationError("workflow-checkpoint", "checkpoint_not_monotonic")
        if checkpoint.get("previous_checkpoint_id") != previous_id:
            raise ContractValidationError("workflow-checkpoint", "checkpoint_predecessor_mismatch")
        checkpoint_id = str(checkpoint["checkpoint_id"])
        if checkpoint_id in checkpoint_ids:
            raise ContractValidationError("workflow-checkpoint", "checkpoint_id_duplicate")
        checkpoint_ids.add(checkpoint_id)
        pending = set(checkpoint["pending_intent_ids"])
        completed = set(checkpoint["completed_intent_ids"])
        if pending & completed:
            raise ContractValidationError("workflow-checkpoint", "checkpoint_effect_overlap")
        if not completed_ids <= completed:
            raise ContractValidationError("workflow-checkpoint", "completed_effect_regressed")
        version = int(checkpoint["workflow_version"])
        if previous_version is not None and version <= previous_version:
            raise ContractValidationError("workflow-checkpoint", "workflow_version_not_monotonic")
        previous_id = str(checkpoint["checkpoint_id"])
        previous_version = version
        completed_ids = completed
        expected_sequence += 1


def validate_side_effect_intents(intents: Sequence[Mapping[str, Any]], root: Any = None) -> None:
    """Reject duplicate logical intents before an executor receives work."""

    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    identity: tuple[object, object, object, object] | None = None
    for intent in intents:
        validate_side_effect_intent(intent, root)
        current_identity = (
            intent["tenant_id"],
            intent["case_id"],
            intent["case_revision_id"],
            intent["workflow_id"],
        )
        if identity is None:
            identity = current_identity
        elif identity != current_identity:
            raise ContractValidationError("side-effect-intent", "workflow_identity_mismatch")
        intent_id = str(intent["intent_id"])
        key = str(intent["idempotency_key"])
        if intent_id in seen_ids or key in seen_keys:
            raise ContractValidationError("side-effect-intent", "duplicate_intent")
        seen_ids.add(intent_id)
        seen_keys.add(key)


def validate_side_effect_chain(
    intent: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    completions: Sequence[Mapping[str, Any]],
    root: Any = None,
) -> None:
    """Reject a detached, cross-tenant, or multiply completed local effect chain."""

    validate_side_effect_intent(intent, root)
    if len(completions) > 1:
        raise ContractValidationError("side-effect-completion", "multiple_completions")
    observation_ids: set[str] = set()
    for observation in observations:
        validate_side_effect_observation(observation, root)
        observation_id = str(observation["observation_id"])
        if observation_id in observation_ids:
            raise ContractValidationError("side-effect-observation", "duplicate_observation")
        observation_ids.add(observation_id)
        validate_tenant_reference(intent, observation)
        for field in ("case_id", "case_revision_id", "workflow_id", "checkpoint_id"):
            if intent.get(field) != observation.get(field):
                raise ContractValidationError(
                    "side-effect-observation", "intent_reference_mismatch"
                )
        if observation.get("intent_id") != intent.get("intent_id"):
            raise ContractValidationError("side-effect-observation", "intent_reference_mismatch")
    for completion in completions:
        validate_side_effect_completion(completion, root)
        validate_tenant_reference(intent, completion)
        for field in ("case_id", "case_revision_id", "workflow_id", "checkpoint_id"):
            if intent.get(field) != completion.get(field):
                raise ContractValidationError("side-effect-completion", "intent_reference_mismatch")
        if completion.get("intent_id") != intent.get("intent_id"):
            raise ContractValidationError("side-effect-completion", "intent_reference_mismatch")
        matching_observation = next(
            (
                observation
                for observation in observations
                if observation.get("observation_id") == completion.get("observation_id")
                and observation.get("status") == "present"
            ),
            None,
        )
        if matching_observation is None:
            raise ContractValidationError(
                "side-effect-completion", "completion_observation_missing"
            )
        if (
            completion.get("observed_ticket_id") != matching_observation.get("observed_ticket_id")
            or completion.get("observed_version") != matching_observation.get("observed_version")
            or completion.get("result_sha256") != matching_observation.get("outcome_sha256")
        ):
            raise ContractValidationError(
                "side-effect-completion", "completion_observation_mismatch"
            )
