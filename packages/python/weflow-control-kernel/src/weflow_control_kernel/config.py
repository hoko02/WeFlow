"""Fail-closed configuration for the Change 0 replay-only foundation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass


class ConfigurationDenied(ValueError):
    """A safe configuration denial that never includes a supplied secret value."""

    def __init__(self, capability: str, reason_code: str) -> None:
        self.capability = capability
        self.reason_code = reason_code
        super().__init__(f"{capability} denied: {reason_code}")

    def as_dict(self) -> dict[str, str]:
        return {
            "capability": self.capability,
            "reason_code": self.reason_code,
            "status": "denied",
        }


@dataclass(frozen=True)
class WeFlowConfig:
    mode: str
    provider_mode: str
    provider_allow_live: bool
    external_write_enabled: bool
    multi_agent_enabled: bool
    log_level: str
    service_boundary_timeout_seconds: float

    def public_dict(self) -> dict[str, object]:
        """Return only values that are safe to expose in readiness diagnostics."""

        return asdict(self)


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_CREDENTIAL_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _read_bool(environment: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environment.get(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigurationDenied("configuration", f"invalid_boolean:{name.lower()}")


def _read_positive_float(environment: Mapping[str, str], name: str, default: float) -> float:
    raw = environment.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationDenied("configuration", f"invalid_number:{name.lower()}") from error
    if value <= 0:
        raise ConfigurationDenied("configuration", f"non_positive_number:{name.lower()}")
    return value


def _reject_credential_settings(environment: Mapping[str, str]) -> None:
    for name, value in environment.items():
        normalized_name = name.upper()
        if not normalized_name.startswith("WEFLOW_") or not value:
            continue
        if any(marker in normalized_name for marker in _CREDENTIAL_MARKERS):
            raise ConfigurationDenied("provider_credentials", "credentials_not_allowed")


def load_config(environment: Mapping[str, str] | None = None) -> WeFlowConfig:
    """Load the only safe Change 0 configuration: deterministic replay."""

    values = os.environ if environment is None else environment
    _reject_credential_settings(values)

    mode = values.get("WEFLOW_MODE", "offline").strip().lower()
    if mode not in {"offline", "service-boundary"}:
        raise ConfigurationDenied("runtime_mode", "unsupported_mode")

    provider_mode = values.get("WEFLOW_PROVIDER_MODE", "replay").strip().lower()
    if provider_mode != "replay":
        raise ConfigurationDenied("live_provider", "replay_only")

    provider_allow_live = _read_bool(values, "WEFLOW_PROVIDER_ALLOW_LIVE", False)
    if provider_allow_live:
        raise ConfigurationDenied("live_provider", "live_access_disabled")

    external_write_enabled = _read_bool(values, "WEFLOW_EXTERNAL_WRITE_ENABLED", False)
    if external_write_enabled:
        raise ConfigurationDenied("external_write", "executor_not_registered")

    multi_agent_enabled = _read_bool(values, "WEFLOW_MULTI_AGENT_ENABLED", False)
    if multi_agent_enabled:
        raise ConfigurationDenied("multi_agent", "single_agent_baseline_only")

    log_level = values.get("WEFLOW_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ConfigurationDenied("configuration", "invalid_log_level")

    return WeFlowConfig(
        mode=mode,
        provider_mode=provider_mode,
        provider_allow_live=provider_allow_live,
        external_write_enabled=external_write_enabled,
        multi_agent_enabled=multi_agent_enabled,
        log_level=log_level,
        service_boundary_timeout_seconds=_read_positive_float(
            values, "WEFLOW_SERVICE_BOUNDARY_TIMEOUT_SECONDS", 3.0
        ),
    )
