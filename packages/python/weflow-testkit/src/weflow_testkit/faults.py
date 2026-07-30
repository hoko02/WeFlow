"""Named local-only fault profiles; none can contact a provider."""

from __future__ import annotations

from enum import StrEnum


class FaultProfile(StrEnum):
    INVALID_CONFIGURATION = "invalid-configuration"
    DEPENDENCY_UNAVAILABLE = "dependency-unavailable"
    RESTART = "restart"
    DUPLICATE_DELIVERY = "duplicate-delivery"
    OUT_OF_ORDER_DELIVERY = "out-of-order-delivery"


def fault_report(profile: FaultProfile) -> dict[str, object]:
    return {
        "fault_profile": profile.value,
        "deterministic": True,
        "external_side_effects": False,
        "model_invocation": False,
    }
