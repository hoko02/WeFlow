"""Typed, redacted facts returned by public offline benchmark adapters."""

from __future__ import annotations

from typing import Literal, TypedDict


class BenchmarkObservation(TypedDict):
    tenant_id: str
    state: str
    outcome: str
    evidence_valid: bool
    approval_valid: bool
    local_effect_count: int
    tool_call_count: int
    offline: Literal[True]
    replay: Literal[True]
    network: Literal[False]
    model: Literal[False]
    external_write: Literal[False]


OFFLINE_CAPABILITY_FLAGS = {
    "offline": True,
    "replay": True,
    "network": False,
    "model": False,
    "external_write": False,
}


def make_benchmark_observation(
    *,
    tenant_id: str,
    state: str,
    outcome: str,
    evidence_valid: bool,
    approval_valid: bool,
    local_effect_count: int,
    tool_call_count: int,
) -> BenchmarkObservation:
    """Construct only the closed, safe observation shape used by hard gates."""

    observation: BenchmarkObservation = {
        "tenant_id": tenant_id,
        "state": state,
        "outcome": outcome,
        "evidence_valid": evidence_valid,
        "approval_valid": approval_valid,
        "local_effect_count": local_effect_count,
        "tool_call_count": tool_call_count,
        "offline": True,
        "replay": True,
        "network": False,
        "model": False,
        "external_write": False,
    }
    validate_benchmark_observation(observation)
    return observation


def validate_benchmark_observation(observation: object) -> None:
    if not isinstance(observation, dict) or set(observation) != {
        "tenant_id",
        "state",
        "outcome",
        "evidence_valid",
        "approval_valid",
        "local_effect_count",
        "tool_call_count",
        *OFFLINE_CAPABILITY_FLAGS,
    }:
        raise ValueError("benchmark_observation_invalid")
    if not all(
        isinstance(observation.get(key), str) and observation[key]
        for key in ("tenant_id", "state", "outcome")
    ):
        raise ValueError("benchmark_observation_invalid")
