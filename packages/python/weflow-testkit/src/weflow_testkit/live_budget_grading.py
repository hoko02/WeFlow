"""Independent integrity checks for append-only live budget evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_budget_integrity(
    profile: Mapping[str, Any],
    result: Mapping[str, Any],
    store_snapshot: Mapping[str, Any],
) -> bool:
    events = store_snapshot["budget_events"]
    reservations: dict[str, Mapping[str, Any]] = {}
    settlements: dict[str, Mapping[str, Any]] = {}
    for event in events:
        invocation_id = event["invocation_id"]
        if event["event_kind"] == "provider_reserved" and invocation_id:
            reservations[str(invocation_id)] = event["payload"]
        elif event["event_kind"] == "provider_settled" and invocation_id:
            settlements[str(invocation_id)] = event["payload"]
    settlement_integrity = all(
        invocation_id in reservations
        and int(settlement["input_tokens"]) <= int(reservations[invocation_id]["input_tokens"])
        and int(settlement["output_tokens"]) <= int(reservations[invocation_id]["output_tokens"])
        and int(settlement["total_tokens"]) <= int(reservations[invocation_id]["total_tokens"])
        and float(settlement["estimated_cost"])
        <= float(reservations[invocation_id]["estimated_cost"])
        for invocation_id, settlement in settlements.items()
    )
    budget = result["budget"]
    return bool(
        settlement_integrity
        and len(reservations) == int(budget["provider_call_count"])
        and len(reservations) == len(store_snapshot["observations"])
        and int(budget["provider_call_count"]) <= int(profile["provider_call_limit"])
        and int(budget["retry_count"]) <= int(profile["retry_limit"])
        and int(budget["input_tokens"]) <= int(profile["input_token_limit"])
        and int(budget["output_tokens"]) <= int(profile["output_token_limit"])
        and int(budget["total_tokens"]) <= int(profile["total_token_limit"])
        and int(budget["action_count"]) <= int(profile["action_limit"])
        and int(budget["tool_count"]) <= int(profile["tool_limit"])
        and int(budget["no_progress_count"]) <= int(profile["no_progress_limit"])
        and float(budget["estimated_cost"]) <= float(profile["estimated_cost_limit"])
        and int(result["end_to_end_latency_ms"]) <= int(profile["wall_time_ms"])
    )


__all__ = ["validate_budget_integrity"]
