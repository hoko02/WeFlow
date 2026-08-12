"""Payload-safe QQ sandbox boundary contracts and recovery-chain validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .validation import ContractValidationError, validate_payload, validate_tenant_reference

QQ_SANDBOX_INBOUND_EVENT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-sandbox-inbound-event.schema.json"
)
QQ_GATEWAY_CURSOR_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-gateway-cursor.schema.json"
)
QQ_ACKNOWLEDGEMENT_INTENT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-acknowledgement-intent.schema.json"
)
QQ_ACKNOWLEDGEMENT_OBSERVATION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-acknowledgement-observation.schema.json"
)
QQ_ACKNOWLEDGEMENT_COMPLETION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-acknowledgement-completion.schema.json"
)

_COMPLETABLE_STATUSES = frozenset({"accepted", "present", "duplicate"})


def canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_schema(
    payload: Mapping[str, Any],
    expected_schema_id: str,
    schema_name: str,
    root: Any = None,
) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != expected_schema_id:
        raise ContractValidationError(schema_name, "unexpected_schema")


def validate_qq_sandbox_inbound_event(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _require_schema(
        payload,
        QQ_SANDBOX_INBOUND_EVENT_SCHEMA_ID,
        "qq-sandbox-inbound-event",
        root,
    )
    source_message_id = str(payload["source_message_id"])
    expected_source_hash = hashlib.sha256(source_message_id.encode("utf-8")).hexdigest()
    if payload["source_message_id_hash"] != expected_source_hash:
        raise ContractValidationError(
            "qq-sandbox-inbound-event", "source_message_id_hash_mismatch"
        )
    expected_natural_key = canonical_sha256(
        {
            "app_id_hash": payload["app_id_hash"],
            "group_openid_hash": payload["group_openid_hash"],
            "provider": "qq-sandbox",
            "source_message_id": source_message_id,
            "tenant_id": payload["tenant_id"],
        }
    )
    if payload["inbound_natural_key"] != expected_natural_key:
        raise ContractValidationError(
            "qq-sandbox-inbound-event", "inbound_natural_key_mismatch"
        )


def qq_gateway_cursor_sha256(payload: Mapping[str, Any]) -> str:
    material = dict(payload)
    material.pop("cursor_sha256", None)
    return canonical_sha256(material)


def validate_qq_gateway_cursor(payload: Mapping[str, Any], root: Any = None) -> None:
    _require_schema(payload, QQ_GATEWAY_CURSOR_SCHEMA_ID, "qq-gateway-cursor", root)
    if payload["cursor_sha256"] != qq_gateway_cursor_sha256(payload):
        raise ContractValidationError("qq-gateway-cursor", "cursor_sha256_mismatch")


def validate_qq_acknowledgement_intent(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _require_schema(
        payload,
        QQ_ACKNOWLEDGEMENT_INTENT_SCHEMA_ID,
        "qq-acknowledgement-intent",
        root,
    )
    expected_source_hash = hashlib.sha256(
        str(payload["source_message_id"]).encode("utf-8")
    ).hexdigest()
    if payload["source_message_id_hash"] != expected_source_hash:
        raise ContractValidationError(
            "qq-acknowledgement-intent", "source_message_id_hash_mismatch"
        )


def validate_qq_acknowledgement_observation(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _require_schema(
        payload,
        QQ_ACKNOWLEDGEMENT_OBSERVATION_SCHEMA_ID,
        "qq-acknowledgement-observation",
        root,
    )


def validate_qq_acknowledgement_completion(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _require_schema(
        payload,
        QQ_ACKNOWLEDGEMENT_COMPLETION_SCHEMA_ID,
        "qq-acknowledgement-completion",
        root,
    )


def validate_qq_acknowledgement_chain(
    intent: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    completions: Sequence[Mapping[str, Any]],
    root: Any = None,
) -> None:
    validate_qq_acknowledgement_intent(intent, root)
    seen_observation_ids: set[str] = set()
    observations_by_id: dict[str, Mapping[str, Any]] = {}
    for observation in observations:
        validate_qq_acknowledgement_observation(observation, root)
        validate_tenant_reference(intent, observation)
        if (
            observation["case_id"] != intent["case_id"]
            or observation["case_revision_id"] != intent["case_revision_id"]
            or observation["intent_id"] != intent["intent_id"]
        ):
            raise ContractValidationError("qq-acknowledgement", "observation_link_mismatch")
        observation_id = str(observation["observation_id"])
        if observation_id in seen_observation_ids:
            raise ContractValidationError("qq-acknowledgement", "duplicate_observation")
        seen_observation_ids.add(observation_id)
        observations_by_id[observation_id] = observation

    seen_completion_ids: set[str] = set()
    for completion in completions:
        validate_qq_acknowledgement_completion(completion, root)
        validate_tenant_reference(intent, completion)
        if (
            completion["case_id"] != intent["case_id"]
            or completion["case_revision_id"] != intent["case_revision_id"]
            or completion["intent_id"] != intent["intent_id"]
        ):
            raise ContractValidationError("qq-acknowledgement", "completion_link_mismatch")
        completion_id = str(completion["completion_id"])
        if completion_id in seen_completion_ids:
            raise ContractValidationError("qq-acknowledgement", "duplicate_completion")
        seen_completion_ids.add(completion_id)
        observation = observations_by_id.get(str(completion["observation_id"]))
        if observation is None:
            raise ContractValidationError(
                "qq-acknowledgement", "completion_observation_missing"
            )
        if observation["status"] not in _COMPLETABLE_STATUSES:
            raise ContractValidationError(
                "qq-acknowledgement", "completion_observation_not_present"
            )
        if (
            completion["provider_message_id_hash"]
            != observation["provider_message_id_hash"]
            or completion["outcome_sha256"] != observation["outcome_sha256"]
        ):
            raise ContractValidationError(
                "qq-acknowledgement", "completion_observation_mismatch"
            )

    if len(completions) > 1:
        raise ContractValidationError("qq-acknowledgement", "duplicate_completion")
