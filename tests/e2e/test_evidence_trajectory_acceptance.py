"""End-to-end acceptance for the fixture-local Change 5 evidence slice."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
DEV = SCRIPTS / "dev.py"


def _acceptance_runner():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    from evidence_trajectory_acceptance import run_evidence_trajectory_acceptance

    return run_evidence_trajectory_acceptance


def test_evidence_trajectory_acceptance_is_offline_deterministic_and_redacted() -> None:
    completed = subprocess.run(
        [sys.executable, str(DEV), "evidence-trajectory-acceptance"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, completed.stdout
    report = json.loads(completed.stdout)
    assert report["accepted"] is True
    assert report["offline"] is True
    assert report["network_required"] is False
    assert report["docker_required"] is False
    assert report["model_credentials_required"] is False
    assert report["determinism"] == {
        "repeated_baseline_equal": True,
        "intentional_nondeterministic_fields": [],
    }
    for fixture_name, expected_outcome in (
        ("authorized", "fixture_delivery_recorded"),
        ("authorization_denial", "authorization_denied"),
        ("interrupted_recovery", "recovered_after_interruption"),
    ):
        fixture = report["fixture_outcomes"][fixture_name]
        assert fixture["outcome"] == expected_outcome
        assert fixture["verification_outcome"] == "verified"
        assert fixture["trajectory_root_sha256"] == fixture["replayed_root_sha256"]
        assert fixture["network_required"] is False
        assert fixture["model_invocation"] is False
        assert fixture["external_write"] is False
        assert fixture["customer_resolution"] is False
    assert report["fixture_outcomes"]["tampered_lineage"] == {
        "outcome": "lineage_invalid",
        "failure_code": "lineage_invalid",
        "network_required": False,
        "model_invocation": False,
        "external_write": False,
        "docker_required": False,
    }
    for forbidden in (
        "customer-api-503-alpha",
        "provider_token",
        "private prompt",
        "raw_message",
        "fixture-controller-alpha",
        "customer_resolved",
    ):
        assert forbidden not in completed.stdout


@pytest.mark.parametrize(
    "configuration",
    (
        {"mode": "service-boundary"},
        {"raw_export": True},
        {"provider": "real"},
    ),
)
def test_evidence_acceptance_rejects_live_or_raw_configuration_before_initialization(
    configuration: dict[str, object],
) -> None:
    with pytest.raises(RuntimeError, match="offline_evidence_configuration_denied"):
        _acceptance_runner()(ROOT, configuration=configuration)
