import json
import subprocess
import sys
from pathlib import Path

from weflow_agent_runtime import run_replay
from weflow_business_simulator import load_replay_fixture
from weflow_testkit import FaultProfile, fault_report

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def run_dev(*arguments: str, expected: int) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(DEV), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == expected, completed.stdout
    return completed


def report(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(completed.stdout)


def test_offline_foundation_acceptance_requires_no_network_model_credentials_or_docker() -> None:
    environment = report(run_dev("check", expected=0))
    assert environment["network_required"] is False
    assert environment["docker_required"] is False
    assert environment["model_credentials_required"] is False
    assert environment["policy_denial"] is None

    run_dev("contracts", expected=0)
    run_dev("down", expected=0)
    try:
        start = report(run_dev("up", "--mode", "offline", expected=0))
        health = report(run_dev("health", expected=0))
        fixture = load_replay_fixture("foundation-happy-path", ROOT)
        replay = run_replay({**fixture, "fault_profile": FaultProfile.DUPLICATE_DELIVERY.value})

        assert start["started"] is True
        assert health["operational_ready"] is True
        assert all(service["ready"] for service in health["services"])
        assert replay["fault_metadata"] == fault_report(FaultProfile.DUPLICATE_DELIVERY)
        assert replay["external_write_executed"] is False
        assert replay["case_completion_declared"] is False
    finally:
        run_dev("down", expected=0)
