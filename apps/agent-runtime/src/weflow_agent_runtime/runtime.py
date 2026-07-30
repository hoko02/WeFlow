"""Deterministic replay runtime that cannot authorize or execute an external side effect."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from weflow_control_kernel.config import load_config
from weflow_extension_sdk import named_fault_metadata, select_provider

_FORBIDDEN_ACTION_FIELDS = ("proposed_action", "external_action", "ticket", "reply")
_SELF_APPROVAL_FIELDS = ("purported_approval", "case_completed", "completion", "success")
_AUTHORITY_CLAIM_FIELDS = (
    "capability_grant",
    "policy_decision",
    "approval",
    "approval_decision",
    "verifier_result",
)


def run_replay(
    request: Mapping[str, Any], environment: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Replay synthetic input without granting authority or creating an external effect."""

    config = load_config(environment)
    provider = select_provider(config)
    result = provider.replay(request)
    requested_fault = request.get("fault_profile")
    fault_metadata = named_fault_metadata(requested_fault)
    if requested_fault is not None:
        result["fault_metadata"] = fault_metadata or {
            "fault_profile": "unrecognized",
            "deterministic": True,
            "external_side_effects": False,
            "model_invocation": False,
        }

    has_external_proposal = any(request.get(name) for name in _FORBIDDEN_ACTION_FIELDS)
    has_self_approval = any(request.get(name) for name in _SELF_APPROVAL_FIELDS)
    has_authority_claim = any(request.get(name) for name in _AUTHORITY_CLAIM_FIELDS)
    if has_external_proposal:
        result["authorization"] = "denied"
        result["reason_code"] = "external_write_executor_not_registered"
    elif has_self_approval:
        result["authorization"] = "denied"
        result["reason_code"] = "self_approval_not_authoritative"
    elif has_authority_claim:
        result["authorization"] = "denied"
        result["reason_code"] = "replay_authority_claim_not_authoritative"
    elif requested_fault is not None and fault_metadata is None:
        result["authorization"] = "denied"
        result["reason_code"] = "unknown_fault_profile"
    else:
        result["authorization"] = "not-applicable"
        result["reason_code"] = "replay-data-only"
    return result
