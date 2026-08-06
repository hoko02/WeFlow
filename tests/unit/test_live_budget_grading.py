from copy import deepcopy

from weflow_testkit.live_budget_grading import validate_budget_integrity


def evidence() -> tuple[dict, dict, dict]:
    profile = {
        "provider_call_limit": 2,
        "retry_limit": 1,
        "input_token_limit": 100,
        "output_token_limit": 50,
        "total_token_limit": 150,
        "action_limit": 2,
        "tool_limit": 1,
        "no_progress_limit": 1,
        "estimated_cost_limit": 0.1,
        "wall_time_ms": 1_000,
    }
    result = {
        "end_to_end_latency_ms": 50,
        "budget": {
            "provider_call_count": 1,
            "retry_count": 0,
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
            "action_count": 1,
            "tool_count": 1,
            "no_progress_count": 0,
            "estimated_cost": 0.001,
        },
    }
    snapshot = {
        "observations": [{"observation_id": "observation-1"}],
        "budget_events": [
            {
                "event_kind": "provider_reserved",
                "invocation_id": "invocation-1",
                "payload": {
                    "input_tokens": 30,
                    "output_tokens": 20,
                    "total_tokens": 50,
                    "estimated_cost": 0.002,
                },
            },
            {
                "event_kind": "provider_settled",
                "invocation_id": "invocation-1",
                "payload": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "total_tokens": 30,
                    "estimated_cost": 0.001,
                },
            },
        ],
    }
    return profile, result, snapshot


def test_budget_integrity_accepts_exact_accounting_and_rejects_tampering() -> None:
    profile, result, snapshot = evidence()
    assert validate_budget_integrity(profile, result, snapshot) is True

    over_settlement = deepcopy(snapshot)
    over_settlement["budget_events"][1]["payload"]["input_tokens"] = 31
    assert validate_budget_integrity(profile, result, over_settlement) is False

    over_cost = deepcopy(result)
    over_cost["budget"]["estimated_cost"] = 1.0
    assert validate_budget_integrity(profile, over_cost, snapshot) is False

    missing_observation = deepcopy(snapshot)
    missing_observation["observations"] = []
    assert validate_budget_integrity(profile, result, missing_observation) is False
