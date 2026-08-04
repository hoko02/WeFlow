import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from weflow_control_kernel.status import SERVICE_NAMES

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def run_dev(*arguments: str, expected: int) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(DEV), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == expected, completed.stdout
    return json.loads(completed.stdout)


def test_health_command_emits_a_redacted_machine_readable_foundation_report() -> None:
    run_dev("down", expected=0)
    report = run_dev("health", expected=2)

    schema = json.loads(
        (ROOT / "contracts/jsonschema/v1/health-status.schema.json").read_text(encoding="utf-8")
    )
    assert report["report_type"] == "weflow-foundation-health.v1"
    assert report["processes_started"] is False
    assert report["operational_ready"] is False
    assert report["business_workflow_implemented"] is False
    assert report["durable_support_workflow_implemented"] is True
    assert report["replay_investigation_agent_implemented"] is True
    assert report["response_candidate_verification_implemented"] is True
    assert report["fixture_policy_approval_delivery_implemented"] is True
    assert report["fixture_approval_enabled"] is True
    assert report["fixture_outbound_delivery_enabled"] is True
    assert report["live_approval_enabled"] is False
    assert report["live_outbound_delivery_enabled"] is False
    assert report["real_provider_enabled"] is False
    assert report["multi_agent_enabled"] is False
    assert report["external_writes_enabled"] is False
    assert report["approval_enabled"] is False
    assert report["outbound_delivery_enabled"] is False
    assert report["customer_resolution_enabled"] is False
    assert [service["service"] for service in report["services"]] == list(SERVICE_NAMES)
    assert all(
        not list(Draft202012Validator(schema).iter_errors(service))
        for service in report["services"]
    )
    assert "pid" not in json.dumps(report, sort_keys=True).lower()
