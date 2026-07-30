import socket
from pathlib import Path

import pytest
from weflow_agent_runtime import run_replay
from weflow_business_simulator import load_replay_fixture
from weflow_testkit import FaultProfile, fault_report

ROOT = Path(__file__).resolve().parents[2]


def test_replay_fixture_uses_no_network_or_model_client_when_faults_are_injected(
    monkeypatch,
) -> None:
    fixture = load_replay_fixture("foundation-happy-path", ROOT)

    def network_forbidden(*_: object, **__: object) -> None:
        raise AssertionError("replay must not initialize a network client")

    monkeypatch.setattr(socket, "create_connection", network_forbidden)
    for profile in FaultProfile:
        result = run_replay({**fixture, "fault_profile": profile.value})

        assert result["source"] == "synthetic-fixture"
        assert result["fault_metadata"] == fault_report(profile)
        assert result["external_write_executed"] is False
        assert result["case_completion_declared"] is False
        assert result["authorization"] == "not-applicable"


def test_replay_authority_claims_are_not_accepted_as_permission_or_success() -> None:
    fixture = load_replay_fixture("foundation-happy-path", ROOT)
    for field in (
        "capability_grant",
        "policy_decision",
        "approval",
        "approval_decision",
        "verifier_result",
    ):
        result = run_replay({**fixture, field: {"synthetic": True}})

        assert result["authorization"] == "denied"
        assert result["reason_code"] == "replay_authority_claim_not_authoritative"
        assert result["external_write_executed"] is False
        assert result["case_completion_declared"] is False


@pytest.mark.parametrize("field", ("purported_approval", "case_completed", "completion", "success"))
def test_replay_completion_like_claims_are_rejected(field: str) -> None:
    fixture = load_replay_fixture("foundation-happy-path", ROOT)
    result = run_replay({**fixture, field: True})

    assert result["authorization"] == "denied"
    assert result["reason_code"] == "self_approval_not_authoritative"
    assert result["case_completion_declared"] is False


def test_unknown_fault_profile_is_denied_without_echoing_the_input() -> None:
    fixture = load_replay_fixture("foundation-happy-path", ROOT)
    result = run_replay({**fixture, "fault_profile": "untrusted-value"})

    assert result["authorization"] == "denied"
    assert result["reason_code"] == "unknown_fault_profile"
    assert "untrusted-value" not in str(result)
