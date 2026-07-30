"""A deterministic provider that cannot call a model or external tool."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class ReplayConfiguration(Protocol):
    provider_mode: str
    provider_allow_live: bool


class ProviderSelectionDenied(ValueError):
    pass


class ExternalWriteExecutorUnavailable(RuntimeError):
    """Raised whenever Change 0 replay data proposes an external side effect."""


_NAMED_FAULT_PROFILES = frozenset(
    {
        "invalid-configuration",
        "dependency-unavailable",
        "restart",
        "duplicate-delivery",
        "out-of-order-delivery",
    }
)


@dataclass(frozen=True)
class ReplayProvider:
    provider_id: str = "deterministic-replay.v1"

    def replay(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Return synthetic metadata only; no model client or tool executor exists here."""

        fixture_identity = str(request.get("fixture_id", "synthetic-replay"))
        correlation_id = (
            "replay-" + hashlib.sha256(fixture_identity.encode("utf-8")).hexdigest()[:16]
        )
        proposed_action = request.get("proposed_action")
        return {
            "provider_id": self.provider_id,
            "mode": "replay",
            "source": "synthetic-fixture",
            "correlation_id": correlation_id,
            "proposed_action_present": proposed_action is not None,
            "external_write_executed": False,
            "case_completion_declared": False,
        }

    def execute_external_write(self, *_: object, **__: object) -> None:
        raise ExternalWriteExecutorUnavailable("Change 0 registers no external-write executor")


def named_fault_metadata(profile: object) -> dict[str, object] | None:
    """Return deterministic local fault metadata, never an arbitrary caller value."""

    if not isinstance(profile, str) or profile not in _NAMED_FAULT_PROFILES:
        return None
    return {
        "fault_profile": profile,
        "deterministic": True,
        "external_side_effects": False,
        "model_invocation": False,
    }


def select_provider(config: ReplayConfiguration) -> ReplayProvider:
    if config.provider_mode != "replay" or config.provider_allow_live:
        raise ProviderSelectionDenied("replay provider is the only enabled Change 0 provider")
    return ReplayProvider()
