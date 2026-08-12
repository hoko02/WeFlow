"""Payload-safe contracts for secure first QQ sandbox group pairing."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from .qq import canonical_sha256
from .validation import ContractValidationError, validate_payload

QQ_GROUP_PAIRING_CHALLENGE_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-group-pairing-challenge.schema.json"
)
QQ_GROUP_PAIRING_COMPLETION_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-group-pairing-completion.schema.json"
)
QQ_GROUP_PAIRING_ACCEPTANCE_REPORT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/qq-group-pairing-acceptance-report.schema.json"
)


def _schema(payload: Mapping[str, Any], expected: str, name: str, root: Any = None) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != expected:
        raise ContractValidationError(name, "unexpected_schema")


def validate_qq_group_pairing_challenge(payload: Mapping[str, Any], root: Any = None) -> None:
    _schema(payload, QQ_GROUP_PAIRING_CHALLENGE_SCHEMA_ID, "qq-group-pairing-challenge", root)
    expected = hashlib.sha256(str(payload["tenant_id"]).encode()).hexdigest()
    if payload["tenant_id_hash"] != expected:
        raise ContractValidationError("qq-group-pairing-challenge", "tenant_hash_mismatch")
    if str(payload["deadline_at"]) <= str(payload["created_at"]):
        raise ContractValidationError("qq-group-pairing-challenge", "deadline_invalid")


def validate_qq_group_pairing_completion(payload: Mapping[str, Any], root: Any = None) -> None:
    _schema(payload, QQ_GROUP_PAIRING_COMPLETION_SCHEMA_ID, "qq-group-pairing-completion", root)
    expected = hashlib.sha256(str(payload["tenant_id"]).encode()).hexdigest()
    if payload["tenant_id_hash"] != expected:
        raise ContractValidationError("qq-group-pairing-completion", "tenant_hash_mismatch")
    if str(payload["expires_at"]) <= str(payload["completed_at"]):
        raise ContractValidationError("qq-group-pairing-completion", "expiry_invalid")


def validate_qq_group_pairing_chain(
    challenge: Mapping[str, Any], completions: Sequence[Mapping[str, Any]], root: Any = None
) -> None:
    validate_qq_group_pairing_challenge(challenge, root)
    seen: set[str] = set()
    for completion in completions:
        validate_qq_group_pairing_completion(completion, root)
        completion_id = str(completion["completion_id"])
        if completion_id in seen:
            raise ContractValidationError("qq-group-pairing", "duplicate_completion")
        seen.add(completion_id)
        if any(
            completion[field] != challenge[field]
            for field in ("challenge_id", "tenant_id", "tenant_id_hash", "app_id_hash")
        ):
            raise ContractValidationError("qq-group-pairing", "completion_link_mismatch")
    if len(completions) > 1:
        raise ContractValidationError("qq-group-pairing", "duplicate_completion")


def qq_group_pairing_report_sha256(payload: Mapping[str, Any]) -> str:
    material = dict(payload)
    material.pop("report_sha256", None)
    return canonical_sha256(material)


def validate_qq_group_pairing_acceptance_report(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _schema(
        payload,
        QQ_GROUP_PAIRING_ACCEPTANCE_REPORT_SCHEMA_ID,
        "qq-group-pairing-acceptance-report",
        root,
    )
    if payload["report_sha256"] != qq_group_pairing_report_sha256(payload):
        raise ContractValidationError("qq-group-pairing-acceptance-report", "report_hash_mismatch")
    completed = payload["completion_status"] == "COMPLETED"
    safe_links = all(
        isinstance(payload.get(field), str)
        for field in ("pairing_id", "app_id_hash", "group_openid_hash", "tenant_id_hash")
    )
    if payload["accepted"] is not (completed and safe_links):
        raise ContractValidationError("qq-group-pairing-acceptance-report", "acceptance_mismatch")
    if payload["mode"] == "offline-fake":
        if (
            payload["fake_pairing_verified"],
            payload["qq_group_pairing_live_verified"],
            payload["network_required"],
            payload["credentials_required"],
        ) != (True, False, False, False):
            raise ContractValidationError(
                "qq-group-pairing-acceptance-report", "fake_mode_overclaim"
            )
    elif (
        payload["fake_pairing_verified"],
        payload["qq_group_pairing_live_verified"],
        payload["network_required"],
        payload["credentials_required"],
    ) != (False, completed, True, True):
        raise ContractValidationError("qq-group-pairing-acceptance-report", "live_mode_invalid")


__all__ = [
    name
    for name in globals()
    if name.startswith("QQ_GROUP_")
    or name.startswith("validate_qq_group_")
    or name == "qq_group_pairing_report_sha256"
]
