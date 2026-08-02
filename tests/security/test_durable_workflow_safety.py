import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from weflow_business_simulator import SyntheticWorkflowSimulator
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)


def test_durable_workflow_effects_are_fixture_local_and_safe_reports_exclude_raw_content(
    tmp_path: Path,
) -> None:
    ledger = SQLiteCaseLedger(
        tmp_path / "safe-workflow.sqlite3",
        clock=FixedClock(FIXED_TIME),
        contract_root=ROOT,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )

    report = SyntheticWorkflowSimulator(root=ROOT).run_fixture(ledger, workflow, "ticket-handoff")
    snapshot = workflow.export_snapshot("tenant-alpha")
    connection = sqlite3.connect(ledger.path)
    try:
        effects = connection.execute(
            "SELECT effect_kind, operation FROM side_effect_intents ORDER BY operation"
        ).fetchall()
    finally:
        connection.close()

    assert effects == [
        ("fixture-local-ticket", "find-or-create"),
        ("fixture-local-ticket", "workflow-handoff"),
    ]
    assert report["model_invocation"] is False
    assert report["external_write"] is False
    assert report["customer_resolution"] is False
    rendered = json.dumps({"report": report, "snapshot": snapshot}, sort_keys=True)
    for forbidden in (
        "private prompt material",
        "provider_token",
    ):
        assert forbidden not in rendered


def test_durable_workflow_module_has_no_network_model_or_external_executor_dependency() -> None:
    source = (
        ROOT / "packages/python/weflow-control-kernel/src/weflow_control_kernel/durable_workflow.py"
    ).read_text(encoding="utf-8")

    for forbidden_dependency in (
        "requests",
        "httpx",
        "urllib.request",
        "openai",
        "weflow_extension_sdk",
    ):
        assert forbidden_dependency not in source
