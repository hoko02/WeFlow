"""Validation helpers for synthetic intake and generated ledger records."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .validation import ContractValidationError, validate_payload

BUSINESS_EVENT_SCHEMA_ID = "https://weflow.local/contracts/v1/business-event.schema.json"
CASE_PROJECTION_SCHEMA_ID = "https://weflow.local/contracts/v1/case-projection.schema.json"
INBOUND_MESSAGE_EVENT_SCHEMA_ID = "https://weflow.local/contracts/v1/inbound-message-event.schema.json"
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def _require_schema(
    payload: Mapping[str, Any],
    expected_schema_id: str,
    schema_name: str,
    root: Any = None,
) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != expected_schema_id:
        raise ContractValidationError(schema_name, "unexpected_schema")


def validate_inbound_message_event(payload: Mapping[str, Any], root: Any = None) -> None:
    """Validate a safe, normalized synthetic inbound event."""

    _require_schema(
        payload,
        INBOUND_MESSAGE_EVENT_SCHEMA_ID,
        "inbound-message-event",
        root,
    )


def validate_inbound_tenant_claim(
    payload: Mapping[str, Any],
    *,
    effective_tenant_id: str,
    root: Any = None,
) -> None:
    """Require an inbound tenant claim to match server-derived authority."""

    validate_inbound_message_event(payload, root)
    if payload.get("tenant_id") != effective_tenant_id:
        raise ContractValidationError("inbound-message-event", "tenant_identity_mismatch")


def validate_case_projection(payload: Mapping[str, Any], root: Any = None) -> None:
    """Validate a tenant-scoped Case read projection."""

    _require_schema(
        payload,
        CASE_PROJECTION_SCHEMA_ID,
        "case-projection",
        root,
    )


def validate_generated_ledger_event(payload: Mapping[str, Any], root: Any = None) -> None:
    """Reject ledger events that lack immutable ordering evidence."""

    _require_schema(
        payload,
        BUSINESS_EVENT_SCHEMA_ID,
        "business-event",
        root,
    )
    event_index = payload.get("case_event_index")
    payload_digest = payload.get("payload_sha256")
    if not isinstance(event_index, int) or isinstance(event_index, bool) or event_index < 1:
        raise ContractValidationError("business-event", "case_event_index_required")
    if not isinstance(payload_digest, str) or not _SHA256_PATTERN.fullmatch(payload_digest):
        raise ContractValidationError("business-event", "payload_sha256_required")

