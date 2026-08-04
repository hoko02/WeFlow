import json
from datetime import UTC, datetime
from pathlib import Path

from weflow_agent_runtime.main import main as agent_runtime_main
from weflow_business_simulator import SyntheticIntakeSimulator
from weflow_business_simulator.main import main as simulator_main
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_worker.main import main as control_worker_main

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)


def ticket_ready_store(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "investigation-runtime.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=FixedClock(FIXED_TIME), contract_root=ROOT)
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    accepted = SyntheticIntakeSimulator(root=ROOT).submit_fixture(ledger, "api-503-first-delivery")
    projection = workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    assert projection is not None and projection["state"] == "TICKET_READY"
    return path, accepted.case_id


def test_agent_runtime_and_control_worker_expose_only_offline_investigation_recovery(
    tmp_path: Path, capsys
) -> None:
    path, case_id = ticket_ready_store(tmp_path)

    agent_code = agent_runtime_main(
        [
            "--investigation-fixture",
            "api-503-investigation",
            "--tenant-id",
            "tenant-alpha",
            "--case-id",
            case_id,
            "--store",
            str(path),
        ]
    )
    agent_report = json.loads(capsys.readouterr().out)
    worker_code = control_worker_main(
        ["--run-once", "--report-investigations", "--store", str(path)]
    )
    worker_report = json.loads(capsys.readouterr().out)

    assert agent_code == 0
    assert agent_report["state"] == "RESPONSE_READY"
    assert agent_report["verifier_outcome"] == "verified"
    assert agent_report["model_invocation"] is False
    assert agent_report["external_write"] is False
    assert worker_code == 0
    assert worker_report["replay_investigation_recovery"] is True
    assert worker_report["recovered_investigations"] == 1
    assert worker_report["real_provider_enabled"] is False
    assert worker_report["external_write"] is False


def test_simulator_runs_api_503_investigation_with_safe_machine_readable_report(capsys) -> None:
    code = simulator_main(["--investigation-fixture", "api-503-investigation"])
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert report["report_type"] == "weflow-synthetic-investigation-inspection.v1"
    assert report["state"] == "RESPONSE_READY"
    assert report["tool_evidence_count"] == 3
    assert report["agent_step_count"] == 4
    assert len(str(report["inspection_sha256"])) == 64
    assert report["model_invocation"] is False
    assert report["external_write"] is False
    rendered = json.dumps(report, sort_keys=True)
    for forbidden in ("customer-api-503-alpha", "provider_token", "private prompt", "raw_message"):
        assert forbidden not in rendered


def test_agent_runtime_requires_explicit_tenant_and_case_scope(capsys) -> None:
    code = agent_runtime_main(["--investigation-fixture", "api-503-investigation"])
    report = json.loads(capsys.readouterr().out)

    assert code == 2
    assert report == {
        "report_type": "weflow-replay-investigation.v1",
        "fixture_id": "api-503-investigation",
        "accepted": False,
        "reason_code": "investigation_scope_required",
        "model_invocation": False,
        "external_write": False,
        "approval": False,
        "outbound_delivery": False,
        "customer_resolution": False,
    }