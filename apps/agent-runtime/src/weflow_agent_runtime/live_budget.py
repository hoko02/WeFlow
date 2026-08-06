"""Model-external reservations and exactly-once accounting for live attempts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .live_store import LiveEvaluationStore, LiveStoreError, stable_identifier

JsonObject = dict[str, Any]


class LiveBudgetExceeded(RuntimeError):
    """A hard budget stopped execution before another call or action."""


class LiveBudgetIntegrityError(RuntimeError):
    """Observed provider usage exceeded its immutable reservation."""


@dataclass(frozen=True)
class ProviderReservation:
    invocation_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    wall_time_ms: int
    request_timeout_ms: int

    def as_contract_dict(self) -> JsonObject:
        return {
            "call_count": 1,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "wall_time_ms": self.wall_time_ms,
            "request_timeout_ms": self.request_timeout_ms,
        }


class LiveBudgetLedger:
    def __init__(
        self,
        store: LiveEvaluationStore,
        attempt_id: str,
        budget_profile: Mapping[str, Any],
        price_profile: Mapping[str, Any],
    ) -> None:
        self.store = store
        self.attempt_id = attempt_id
        self.profile = dict(budget_profile)
        self.price = dict(price_profile)

    def snapshot(self) -> JsonObject:
        events = self.store.attempt_snapshot(self.attempt_id)["budget_events"]
        reservations: dict[str, JsonObject] = {}
        settlements: dict[str, JsonObject] = {}
        action_count = tool_count = no_progress_count = retry_count = 0
        for event in events:
            kind = event["event_kind"]
            payload = event["payload"]
            invocation_id = event["invocation_id"]
            if kind == "provider_reserved" and invocation_id:
                reservations[invocation_id] = payload
            elif kind == "provider_settled" and invocation_id:
                settlements[invocation_id] = payload
            elif kind == "action_consumed":
                action_count += int(payload["count"])
            elif kind == "tool_consumed":
                tool_count += int(payload["count"])
            elif kind == "no_progress_consumed":
                no_progress_count += int(payload["count"])
        effective = [settlements.get(key, value) for key, value in reservations.items()]
        retry_count = sum(int(item.get("retry_count", 0)) for item in effective)
        return {
            "provider_call_count": len(reservations),
            "input_tokens": sum(int(item["input_tokens"]) for item in effective),
            "output_tokens": sum(int(item["output_tokens"]) for item in effective),
            "total_tokens": sum(int(item["total_tokens"]) for item in effective),
            "estimated_cost": round(sum(float(item["estimated_cost"]) for item in effective), 12),
            "action_count": action_count,
            "tool_count": tool_count,
            "no_progress_count": no_progress_count,
            "retry_count": retry_count,
        }

    def _estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return round(
            (
                input_tokens * float(self.price["input_per_million_tokens"])
                + output_tokens * float(self.price["output_per_million_tokens"])
            )
            / 1_000_000,
            12,
        )

    def reserve_provider_call(
        self,
        invocation_id: str,
        *,
        input_tokens: int,
        output_tokens: int,
        current_wall_time_ms: int,
        created_at: str,
        retry_count: int = 0,
    ) -> ProviderReservation:
        current = self.snapshot()
        cost = self._estimated_cost(input_tokens, output_tokens)
        total_tokens = input_tokens + output_tokens
        request_timeout = int(self.profile["request_timeout_ms"])
        wall_time = current_wall_time_ms + request_timeout
        checks = (
            current["provider_call_count"] + 1 <= self.profile["provider_call_limit"],
            current["input_tokens"] + input_tokens <= self.profile["input_token_limit"],
            current["output_tokens"] + output_tokens <= self.profile["output_token_limit"],
            current["total_tokens"] + total_tokens <= self.profile["total_token_limit"],
            wall_time <= self.profile["wall_time_ms"],
            current["estimated_cost"] + cost <= self.profile["estimated_cost_limit"],
            current["retry_count"] + retry_count <= self.profile["retry_limit"],
        )
        if not all(checks):
            raise LiveBudgetExceeded("live_budget_exhausted")
        reservation = ProviderReservation(
            invocation_id=invocation_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=cost,
            wall_time_ms=wall_time,
            request_timeout_ms=request_timeout,
        )
        self.store.append_budget_event(
            attempt_id=self.attempt_id,
            invocation_id=invocation_id,
            event_kind="provider_reserved",
            payload={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": cost,
                "wall_time_ms": wall_time,
                "request_timeout_ms": request_timeout,
                "retry_count": retry_count,
            },
            event_id=stable_identifier(
                "budget-provider-reserved", {"invocation_id": invocation_id}
            ),
            created_at=created_at,
        )
        return reservation

    def settle_provider_call(
        self,
        reservation: ProviderReservation,
        *,
        input_tokens: int,
        output_tokens: int,
        provider_latency_ms: int,
        retry_count: int,
        created_at: str,
    ) -> None:
        total_tokens = input_tokens + output_tokens
        cost = self._estimated_cost(input_tokens, output_tokens)
        self.store.append_budget_event(
            attempt_id=self.attempt_id,
            invocation_id=reservation.invocation_id,
            event_kind="provider_settled",
            payload={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": cost,
                "provider_latency_ms": provider_latency_ms,
                "retry_count": retry_count,
            },
            event_id=stable_identifier(
                "budget-provider-settled", {"invocation_id": reservation.invocation_id}
            ),
            created_at=created_at,
        )
        if (
            input_tokens > reservation.input_tokens
            or output_tokens > reservation.output_tokens
            or total_tokens > reservation.total_tokens
            or cost > reservation.estimated_cost
        ):
            raise LiveBudgetIntegrityError("provider_usage_exceeded_reservation")

    def _consume_count(
        self,
        kind: str,
        limit_field: str,
        current_field: str,
        natural_key: str,
        created_at: str,
    ) -> None:
        current = self.snapshot()
        if int(current[current_field]) + 1 > int(self.profile[limit_field]):
            raise LiveBudgetExceeded("live_budget_exhausted")
        try:
            self.store.append_budget_event(
                attempt_id=self.attempt_id,
                event_kind=kind,
                payload={"count": 1},
                event_id=stable_identifier(
                    kind, {"attempt_id": self.attempt_id, "key": natural_key}
                ),
                created_at=created_at,
            )
        except LiveStoreError:
            raise

    def consume_action(self, action_sha256: str, created_at: str) -> None:
        self._consume_count(
            "action_consumed",
            "action_limit",
            "action_count",
            action_sha256,
            created_at,
        )

    def consume_tool(self, tool_request_id: str, created_at: str) -> None:
        self._consume_count(
            "tool_consumed", "tool_limit", "tool_count", tool_request_id, created_at
        )

    def consume_no_progress(self, logical_turn_id: str, created_at: str) -> None:
        self._consume_count(
            "no_progress_consumed",
            "no_progress_limit",
            "no_progress_count",
            logical_turn_id,
            created_at,
        )


__all__ = [
    "LiveBudgetExceeded",
    "LiveBudgetIntegrityError",
    "LiveBudgetLedger",
    "ProviderReservation",
]
