"""Closed, privacy-safe contracts for the QQ handler approval and delivery slice."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from .qq import canonical_sha256
from .validation import ContractValidationError, validate_payload, validate_tenant_reference

BASE = "https://weflow.local/contracts/v1"
QQ_HANDLER_PAIRING_CHALLENGE_SCHEMA_ID = f"{BASE}/qq-handler-pairing-challenge.schema.json"
QQ_HANDLER_BINDING_SCHEMA_ID = f"{BASE}/qq-handler-binding.schema.json"
QQ_HANDLER_PRIVATE_LOCATOR_SCHEMA_ID = f"{BASE}/qq-handler-private-locator.schema.json"
QQ_CUSTOMER_ISSUE_ARTIFACT_SCHEMA_ID = f"{BASE}/qq-customer-issue-artifact.schema.json"
QQ_HANDLER_RESPONSE_ARTIFACT_SCHEMA_ID = f"{BASE}/qq-handler-response-artifact.schema.json"
QQ_HANDLER_COMMAND_SCHEMA_ID = f"{BASE}/qq-handler-command.schema.json"
QQ_HANDLER_NOTIFICATION_INTENT_SCHEMA_ID = f"{BASE}/qq-handler-notification-intent.schema.json"
QQ_HANDLER_NOTIFICATION_RESULT_SCHEMA_ID = f"{BASE}/qq-handler-notification-result.schema.json"
QQ_HANDLER_CANDIDATE_REVISION_SCHEMA_ID = f"{BASE}/qq-handler-candidate-revision.schema.json"
QQ_HANDLER_APPROVAL_REQUEST_SCHEMA_ID = f"{BASE}/qq-handler-approval-request.schema.json"
QQ_HANDLER_APPROVAL_DECISION_SCHEMA_ID = f"{BASE}/qq-handler-approval-decision.schema.json"
QQ_HANDLER_PASSIVE_REPLY_INTENT_SCHEMA_ID = f"{BASE}/qq-handler-passive-reply-intent.schema.json"
QQ_HANDLER_PASSIVE_REPLY_RESULT_SCHEMA_ID = f"{BASE}/qq-handler-passive-reply-result.schema.json"
QQ_HANDLER_ACCEPTANCE_REPORT_SCHEMA_ID = f"{BASE}/qq-handler-acceptance-report.schema.json"

_C2C_COMMANDS = frozenset({"pull", "accept", "draft", "reject"})
_GROUP_COMMANDS = frozenset({"approve"})
_FORBIDDEN_REPORT_KEYS = frozenset(
    {
        "member_openid",
        "user_openid",
        "group_openid",
        "client_secret",
        "access_token",
        "raw_event",
        "provider_response",
        "customer_issue",
        "candidate_text",
        "draft_preview",
        "transcript",
    }
)


def _schema(payload: Mapping[str, Any], expected: str, name: str, root: Any = None) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != expected:
        raise ContractValidationError(name, "unexpected_schema")


def _parse_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ContractValidationError(name, "timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractValidationError(name, "timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise ContractValidationError(name, "timestamp_invalid")
    return parsed


def validate_qq_handler_pairing_challenge(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    name = "qq-handler-pairing-challenge"
    _schema(payload, QQ_HANDLER_PAIRING_CHALLENGE_SCHEMA_ID, name, root)
    if _parse_timestamp(payload["deadline_at"], name) <= _parse_timestamp(
        payload["created_at"], name
    ):
        raise ContractValidationError(name, "deadline_invalid")


def validate_qq_handler_binding(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-handler-binding"
    _schema(payload, QQ_HANDLER_BINDING_SCHEMA_ID, name, root)
    if _parse_timestamp(payload["expires_at"], name) <= _parse_timestamp(
        payload["confirmed_at"], name
    ):
        raise ContractValidationError(name, "expiry_invalid")
    if payload["assurance_level"] == "provider_cross_surface_verified" and not payload.get(
        "cross_surface_identity_hash"
    ):
        raise ContractValidationError(name, "cross_surface_identity_missing")


def validate_qq_handler_private_locator(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    name = "qq-handler-private-locator"
    _schema(payload, QQ_HANDLER_PRIVATE_LOCATOR_SCHEMA_ID, name, root)
    if _parse_timestamp(payload["expires_at"], name) <= _parse_timestamp(
        payload["created_at"], name
    ):
        raise ContractValidationError(name, "expiry_invalid")


def _validate_artifact(
    payload: Mapping[str, Any], expected: str, expected_kind: str, root: Any = None
) -> None:
    name = expected_kind.replace("_", "-")
    _schema(payload, expected, name, root)
    if payload["artifact_kind"] != expected_kind:
        raise ContractValidationError(name, "artifact_kind_mismatch")
    if _parse_timestamp(payload["expires_at"], name) <= _parse_timestamp(
        payload["created_at"], name
    ):
        raise ContractValidationError(name, "expiry_invalid")
    if _parse_timestamp(payload["expires_at"], name) - _parse_timestamp(
        payload["created_at"], name
    ) > timedelta(hours=24):
        raise ContractValidationError(name, "retention_exceeds_24_hours")
    deleted_at = payload.get("deleted_at")
    if (payload["deletion_status"] == "DELETED") is not (deleted_at is not None):
        raise ContractValidationError(name, "deletion_state_invalid")


def validate_qq_customer_issue_artifact(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _validate_artifact(
        payload,
        QQ_CUSTOMER_ISSUE_ARTIFACT_SCHEMA_ID,
        "qq_customer_issue",
        root,
    )


def validate_qq_handler_response_artifact(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _validate_artifact(
        payload,
        QQ_HANDLER_RESPONSE_ARTIFACT_SCHEMA_ID,
        "qq_handler_response",
        root,
    )


def validate_qq_handler_command(payload: Mapping[str, Any], root: Any = None) -> None:
    name = "qq-handler-command"
    _schema(payload, QQ_HANDLER_COMMAND_SCHEMA_ID, name, root)
    command = payload["command"]
    surface = payload["surface"]
    if (surface == "c2c" and command not in _C2C_COMMANDS) or (
        surface == "group" and command not in _GROUP_COMMANDS
    ):
        raise ContractValidationError(name, "command_surface_mismatch")
    if (command == "reject") is not isinstance(payload["rejection_reason_code"], str):
        raise ContractValidationError(name, "rejection_reason_mismatch")
    if command != "reject" and payload["rejection_reason_code"] is not None:
        raise ContractValidationError(name, "rejection_reason_mismatch")
    if command == "draft" and not payload.get("candidate_artifact_id"):
        raise ContractValidationError(name, "candidate_artifact_missing")
    if command == "approve" and not all(
        payload.get(field)
        for field in ("approval_request_id", "candidate_hash_prefix")
    ):
        raise ContractValidationError(name, "approval_metadata_missing")


def validate_qq_handler_notification_chain(
    intent: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    root: Any = None,
) -> None:
    _schema(
        intent,
        QQ_HANDLER_NOTIFICATION_INTENT_SCHEMA_ID,
        "qq-handler-notification-intent",
        root,
    )
    if len(results) > 1:
        raise ContractValidationError("qq-handler-notification", "multiple_attempts_forbidden")
    for result in results:
        _schema(
            result,
            QQ_HANDLER_NOTIFICATION_RESULT_SCHEMA_ID,
            "qq-handler-notification-result",
            root,
        )
        validate_tenant_reference(intent, result)
        if result["intent_id"] != intent["intent_id"]:
            raise ContractValidationError("qq-handler-notification", "result_link_mismatch")
        if result["attempt_count"] != 1:
            raise ContractValidationError("qq-handler-notification", "attempt_count_invalid")
        if result["provider_accepted"] is not (result["status"] == "accepted"):
            raise ContractValidationError("qq-handler-notification", "acceptance_mismatch")


def validate_qq_handler_candidate_revision(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    _schema(
        payload,
        QQ_HANDLER_CANDIDATE_REVISION_SCHEMA_ID,
        "qq-handler-candidate-revision",
        root,
    )


def validate_qq_handler_approval_chain(
    request: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    root: Any = None,
) -> None:
    _schema(
        request,
        QQ_HANDLER_APPROVAL_REQUEST_SCHEMA_ID,
        "qq-handler-approval-request",
        root,
    )
    if not str(request["candidate_sha256"]).startswith(str(request["candidate_hash_prefix"])):
        raise ContractValidationError("qq-handler-approval", "hash_prefix_mismatch")
    if len(decisions) > 1:
        raise ContractValidationError("qq-handler-approval", "duplicate_decision")
    for decision in decisions:
        _schema(
            decision,
            QQ_HANDLER_APPROVAL_DECISION_SCHEMA_ID,
            "qq-handler-approval-decision",
            root,
        )
        validate_tenant_reference(request, decision)
        for field in (
            "approval_request_id",
            "case_id",
            "case_revision_id",
            "handler_binding_id",
            "candidate_revision_id",
            "candidate_sha256",
            "workflow_version",
        ):
            if decision[field] != request[field]:
                raise ContractValidationError("qq-handler-approval", "decision_link_mismatch")


def validate_qq_handler_passive_reply_chain(
    intent: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    root: Any = None,
) -> None:
    _schema(
        intent,
        QQ_HANDLER_PASSIVE_REPLY_INTENT_SCHEMA_ID,
        "qq-handler-passive-reply-intent",
        root,
    )
    expected_shapes = {
        "pull": ("c2c", "qq.c2c.passive_reply.execute", 1),
        "accept": ("c2c", "qq.c2c.passive_reply.execute", 2),
        "draft-preview": ("c2c", "qq.c2c.passive_reply.execute", 3),
        "reject": ("c2c", "qq.c2c.passive_reply.execute", 4),
        "group-nudge": ("group", "qq.final_reply.execute", 2),
        "final": ("group", "qq.final_reply.execute", 5),
    }
    actual_shape = (intent["surface"], intent["operation"], intent["reply_msg_seq"])
    if actual_shape != expected_shapes[intent["response_kind"]]:
        raise ContractValidationError(
            "qq-handler-passive-reply", "response_shape_mismatch"
        )
    if len(results) > 1:
        raise ContractValidationError("qq-handler-passive-reply", "duplicate_result")
    for result in results:
        _schema(
            result,
            QQ_HANDLER_PASSIVE_REPLY_RESULT_SCHEMA_ID,
            "qq-handler-passive-reply-result",
            root,
        )
        validate_tenant_reference(intent, result)
        if result["intent_id"] != intent["intent_id"]:
            raise ContractValidationError("qq-handler-passive-reply", "result_link_mismatch")
        if result["provider_accepted"] is not (
            result["status"] in {"accepted", "duplicate"}
        ):
            raise ContractValidationError("qq-handler-passive-reply", "acceptance_mismatch")


def qq_handler_acceptance_report_sha256(payload: Mapping[str, Any]) -> str:
    material = dict(payload)
    material.pop("report_sha256", None)
    return canonical_sha256(material)


def validate_qq_handler_acceptance_report(
    payload: Mapping[str, Any], root: Any = None
) -> None:
    name = "qq-handler-acceptance-report"
    _schema(payload, QQ_HANDLER_ACCEPTANCE_REPORT_SCHEMA_ID, name, root)
    if payload["report_sha256"] != qq_handler_acceptance_report_sha256(payload):
        raise ContractValidationError(name, "report_hash_mismatch")
    if any(
        payload[field]
        for field in (
            "model_invocation",
            "customer_receipt_verified",
            "issue_resolution",
            "case_completion",
            "production_ready",
        )
    ):
        raise ContractValidationError(name, "acceptance_overclaim")

    def walk(value: object) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).lower() in _FORBIDDEN_REPORT_KEYS:
                    raise ContractValidationError(name, "unsafe_report_key")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)


__all__ = [
    name
    for name in globals()
    if name.startswith("QQ_")
    or name.startswith("validate_qq_handler")
    or name.startswith("validate_qq_customer")
    or name.startswith("qq_handler_acceptance")
]
