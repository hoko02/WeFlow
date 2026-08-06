from pathlib import Path

import pytest
from weflow_agent_runtime.live_budget import (
    LiveBudgetExceeded,
    LiveBudgetIntegrityError,
    LiveBudgetLedger,
)
from weflow_agent_runtime.live_store import (
    LiveAttemptIdentities,
    LiveEvaluationStore,
    LiveStoreError,
    stable_identifier,
)
from weflow_contracts.evaluation import canonical_sha256
from weflow_contracts.live import (
    MODEL_INVOCATION_INTENT_SCHEMA_ID,
    MODEL_INVOCATION_OBSERVATION_SCHEMA_ID,
)

NOW = "2026-08-06T00:00:00Z"
LATER = "2026-08-06T00:00:01Z"


def _budget() -> dict[str, int | float | str]:
    return {
        "provider_call_limit": 2,
        "retry_limit": 1,
        "input_token_limit": 100,
        "output_token_limit": 40,
        "total_token_limit": 140,
        "wall_time_ms": 10_000,
        "request_timeout_ms": 1_000,
        "action_limit": 2,
        "tool_limit": 1,
        "no_progress_limit": 1,
        "estimated_cost_limit": 1.0,
        "currency": "USD",
    }


def _price() -> dict[str, float]:
    return {"input_per_million_tokens": 1.0, "output_per_million_tokens": 2.0}


def _make_store(tmp_path: Path) -> tuple[LiveEvaluationStore, LiveAttemptIdentities]:
    store = LiveEvaluationStore(tmp_path / "live.sqlite3")
    identities = LiveAttemptIdentities("session-1", "task-1", 1)
    store.append_session(
        evaluation_session_id="session-1",
        suite_id="live-pilot.v1",
        tenant_id="tenant-alpha",
        config_sha256="a" * 64,
        created_at=NOW,
    )
    store.append_attempt(identities, created_at=NOW)
    store.append_turn(identities, 1, created_at=NOW)
    return store, identities


def _intent(
    identities: LiveAttemptIdentities,
    reservation: dict[str, int | float],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": MODEL_INVOCATION_INTENT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": "tenant-alpha",
        "evaluation_session_id": identities.evaluation_session_id,
        "suite_id": "live-pilot.v1",
        "evaluation_task_id": identities.evaluation_task_id,
        "attempt_id": identities.attempt_id,
        "logical_turn_id": identities.logical_turn_id(1),
        "invocation_id": identities.invocation_id(1),
        "context_manifest_id": "context-1",
        "context_sha256": "b" * 64,
        "prompt_template_id": "live-pilot-prompt.v1",
        "prompt_template_sha256": "c" * 64,
        "source_sha256s": ["d" * 64],
        "provider_profile_id": "openai-compatible.v1",
        "provider_profile_sha256": "e" * 64,
        "model_id_sha256": "f" * 64,
        "price_profile_id": "price-1",
        "price_profile_sha256": "1" * 64,
        "reservation": reservation,
        "created_at": NOW,
        "intent_sha256": "",
    }
    payload["intent_sha256"] = canonical_sha256(payload, without="intent_sha256")
    return payload


def _observation(
    identities: LiveAttemptIdentities,
    *,
    status: str = "completed",
    failure: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": MODEL_INVOCATION_OBSERVATION_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": "tenant-alpha",
        "evaluation_session_id": identities.evaluation_session_id,
        "suite_id": "live-pilot.v1",
        "evaluation_task_id": identities.evaluation_task_id,
        "attempt_id": identities.attempt_id,
        "logical_turn_id": identities.logical_turn_id(1),
        "invocation_id": identities.invocation_id(1),
        "observation_id": stable_identifier(
            "model-observation", {"invocation_id": identities.invocation_id(1)}
        ),
        "status": status,
        "request_reference_sha256": "2" * 64,
        "response_sha256": "3" * 64 if status == "completed" else None,
        "usage": {
            "available": status == "completed",
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
        },
        "provider_latency_ms": 50,
        "estimated_cost": 0.00004,
        "currency": "USD",
        "failure_classification": failure,
        "observed_at": LATER,
        "observation_sha256": "",
    }
    payload["observation_sha256"] = canonical_sha256(payload, without="observation_sha256")
    return payload


def test_stable_identities_and_append_only_restart_are_idempotent(tmp_path: Path) -> None:
    store, identities = _make_store(tmp_path)
    assert identities.attempt_id == LiveAttemptIdentities("session-1", "task-1", 1).attempt_id
    assert identities.attempt_id != LiveAttemptIdentities("session-1", "task-1", 2).attempt_id

    ledger = LiveBudgetLedger(store, identities.attempt_id, _budget(), _price())
    reservation = ledger.reserve_provider_call(
        identities.invocation_id(1),
        input_tokens=30,
        output_tokens=20,
        current_wall_time_ms=0,
        created_at=NOW,
    )
    intent = _intent(identities, reservation.as_contract_dict())
    store.append_intent(intent)
    observation = _observation(identities)
    store.append_observation(observation)
    store.record_normalized_action(identities.logical_turn_id(1), "4" * 64)
    ledger.settle_provider_call(
        reservation,
        input_tokens=20,
        output_tokens=10,
        provider_latency_ms=50,
        retry_count=0,
        created_at=LATER,
    )

    restarted = LiveEvaluationStore(store.path)
    restarted.append_session(
        evaluation_session_id="session-1",
        suite_id="live-pilot.v1",
        tenant_id="tenant-alpha",
        config_sha256="a" * 64,
        created_at=NOW,
    )
    restarted.append_attempt(identities, created_at=NOW)
    restarted.append_turn(identities, 1, created_at=NOW)
    restarted.append_intent(intent)
    restarted.append_observation(observation)

    recovery = restarted.recover_attempt(identities.attempt_id, observed_at=LATER)
    snapshot = LiveBudgetLedger(restarted, identities.attempt_id, _budget(), _price()).snapshot()
    assert recovery == {"recovery": "reuse_observed", "observations": [observation]}
    assert snapshot["provider_call_count"] == 1
    assert snapshot["total_tokens"] == 30


def test_immutable_conflicts_and_foreign_keys_fail_closed(tmp_path: Path) -> None:
    store, identities = _make_store(tmp_path)
    with pytest.raises(LiveStoreError, match="immutable_conflict"):
        store.append_session(
            evaluation_session_id="session-1",
            suite_id="different-suite",
            tenant_id="tenant-alpha",
            config_sha256="a" * 64,
            created_at=NOW,
        )

    foreign = LiveAttemptIdentities("missing-session", "task-1", 1)
    with pytest.raises(LiveStoreError, match="integrity_error"):
        store.append_attempt(foreign, created_at=NOW)

    store.record_normalized_action(identities.logical_turn_id(1), "4" * 64)
    with pytest.raises(LiveStoreError, match="action_conflict"):
        store.record_normalized_action(identities.logical_turn_id(1), "5" * 64)


def test_intent_without_observation_closes_unknown_without_retry(tmp_path: Path) -> None:
    store, identities = _make_store(tmp_path)
    ledger = LiveBudgetLedger(store, identities.attempt_id, _budget(), _price())
    reservation = ledger.reserve_provider_call(
        identities.invocation_id(1),
        input_tokens=30,
        output_tokens=20,
        current_wall_time_ms=0,
        created_at=NOW,
    )
    store.append_intent(_intent(identities, reservation.as_contract_dict()))

    recovery = LiveEvaluationStore(store.path).recover_attempt(
        identities.attempt_id, observed_at=LATER
    )
    snapshot = store.attempt_snapshot(identities.attempt_id)
    budget = ledger.snapshot()

    assert recovery["recovery"] == "closed_unknown"
    assert recovery["observation"]["status"] == "provider_outcome_unknown"
    assert snapshot["attempt"]["status"] == "closed"
    assert len(snapshot["observations"]) == 1
    assert budget["provider_call_count"] == 1
    assert budget["total_tokens"] == 50
    assert budget["retry_count"] == 0


def test_budget_reservation_settlement_retry_and_overage_are_exactly_once(
    tmp_path: Path,
) -> None:
    store, identities = _make_store(tmp_path)
    ledger = LiveBudgetLedger(store, identities.attempt_id, _budget(), _price())
    first = ledger.reserve_provider_call(
        identities.invocation_id(1),
        input_tokens=30,
        output_tokens=20,
        current_wall_time_ms=0,
        created_at=NOW,
    )
    ledger.settle_provider_call(
        first,
        input_tokens=20,
        output_tokens=10,
        provider_latency_ms=50,
        retry_count=1,
        created_at=LATER,
    )
    ledger.settle_provider_call(
        first,
        input_tokens=20,
        output_tokens=10,
        provider_latency_ms=50,
        retry_count=1,
        created_at=LATER,
    )
    ledger.consume_action("a" * 64, NOW)
    ledger.consume_action("a" * 64, NOW)
    assert ledger.snapshot()["action_count"] == 1
    assert ledger.snapshot()["retry_count"] == 1

    with pytest.raises(LiveBudgetExceeded, match="live_budget_exhausted"):
        ledger.reserve_provider_call(
            identities.invocation_id(1, 2),
            input_tokens=30,
            output_tokens=20,
            current_wall_time_ms=0,
            created_at=NOW,
            retry_count=1,
        )

    second = ledger.reserve_provider_call(
        identities.invocation_id(1, 2),
        input_tokens=30,
        output_tokens=20,
        current_wall_time_ms=0,
        created_at=NOW,
    )
    with pytest.raises(LiveBudgetIntegrityError, match="exceeded_reservation"):
        ledger.settle_provider_call(
            second,
            input_tokens=31,
            output_tokens=20,
            provider_latency_ms=50,
            retry_count=0,
            created_at=LATER,
        )
