"""Named local-only fault profiles; none can contact a provider."""

from __future__ import annotations

from enum import StrEnum


class FaultProfile(StrEnum):
    INVALID_CONFIGURATION = "invalid-configuration"
    DEPENDENCY_UNAVAILABLE = "dependency-unavailable"
    RESTART = "restart"
    DUPLICATE_DELIVERY = "duplicate-delivery"
    OUT_OF_ORDER_DELIVERY = "out-of-order-delivery"


class WorkflowFaultPoint(StrEnum):
    """Change 2 durable boundaries that can be interrupted in local fixtures."""

    ACTIVATION = "activation"
    CHECKPOINT = "checkpoint"
    INTENT = "intent"
    RECONCILE = "reconcile"
    EXECUTE = "execute"
    LOST_RESPONSE = "lost-response"
    OBSERVATION = "observation"
    COMPLETION = "completion"
    RECONCILIATION_TIMEOUT = "reconciliation-timeout"


def fault_report(profile: FaultProfile) -> dict[str, object]:
    return {
        "fault_profile": profile.value,
        "deterministic": True,
        "external_side_effects": False,
        "model_invocation": False,
    }


def workflow_fault_report(point: WorkflowFaultPoint) -> dict[str, object]:
    """Describe a synthetic workflow fault without exposing payload or runtime state."""

    return {
        "fault_profile": point.value,
        "deterministic": True,
        "external_side_effects": False,
        "model_invocation": False,
        "customer_resolution": False,
    }
