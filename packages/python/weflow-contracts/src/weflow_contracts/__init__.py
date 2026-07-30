"""Cross-language contract validation helpers backed by canonical JSON Schema."""

from .intake import (
    BUSINESS_EVENT_SCHEMA_ID,
    CASE_PROJECTION_SCHEMA_ID,
    INBOUND_MESSAGE_EVENT_SCHEMA_ID,
    validate_case_projection,
    validate_generated_ledger_event,
    validate_inbound_message_event,
    validate_inbound_tenant_claim,
)
from .schemas import contract_schema_paths, load_contract_schemas, schema_fingerprints
from .validation import (
    ContractValidationError,
    approval_is_authorized,
    classify_event_delivery,
    stable_idempotency_key,
    validate_payload,
    validate_revision_chain,
    validate_tenant_reference,
)

__all__ = [
    "BUSINESS_EVENT_SCHEMA_ID",
    "CASE_PROJECTION_SCHEMA_ID",
    "ContractValidationError",
    "INBOUND_MESSAGE_EVENT_SCHEMA_ID",
    "approval_is_authorized",
    "classify_event_delivery",
    "contract_schema_paths",
    "load_contract_schemas",
    "schema_fingerprints",
    "stable_idempotency_key",
    "validate_case_projection",
    "validate_generated_ledger_event",
    "validate_inbound_message_event",
    "validate_inbound_tenant_claim",
    "validate_payload",
    "validate_revision_chain",
    "validate_tenant_reference",
]
