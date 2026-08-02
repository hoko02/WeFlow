from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_business_simulator import (
    SyntheticIntakeSimulator,
    SyntheticWorkflowSimulator,
    load_intake_fixture,
    load_workflow_fixture,
)
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger

ROOT = Path(__file__).resolve().parents[2]
FIXED_CLOCK = FixedClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))


def test_simulator_submits_only_checked_in_synthetic_fixtures(tmp_path: Path) -> None:
    store = SQLiteCaseLedger(
        tmp_path / "case-ledger.sqlite3",
        clock=FIXED_CLOCK,
        contract_root=ROOT,
    )
    simulator = SyntheticIntakeSimulator(root=ROOT)

    accepted = simulator.submit_fixture(store, "api-503-first-delivery")
    deduplicated = simulator.submit_fixture(store, "api-503-duplicate-delivery")

    assert accepted.disposition == "accepted"
    assert deduplicated.disposition == "deduplicated"
    assert deduplicated.case_id == accepted.case_id
    assert store.source_counts("tenant-alpha")["business_events"] == 3


def test_fixture_loader_rejects_paths_and_non_synthetic_shapes() -> None:
    with pytest.raises(ValueError, match="invalid_fixture_id"):
        load_intake_fixture("../api-503-first-delivery", ROOT)


@pytest.mark.parametrize(
    ("fixture_id", "expected_state"),
    [
        ("ticket-handoff", "TICKET_READY"),
        ("lost-response-recovery", "TICKET_READY"),
        ("sla-expiry", "WAITING_FOR_OPERATOR"),
    ],
)
def test_workflow_simulator_runs_only_named_fixtures_and_recovers_faults(
    tmp_path: Path,
    fixture_id: str,
    expected_state: str,
) -> None:
    ledger = SQLiteCaseLedger(
        tmp_path / f"{fixture_id}.sqlite3",
        clock=FIXED_CLOCK,
        contract_root=ROOT,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )

    report = SyntheticWorkflowSimulator(root=ROOT).run_fixture(ledger, workflow, fixture_id)

    assert report["state"] == expected_state
    assert report["matches_expected_state"] is True
    assert report["external_write"] is False
    assert report["model_invocation"] is False
    assert report["customer_resolution"] is False


def test_workflow_fixture_loader_rejects_paths_and_unknown_names() -> None:
    with pytest.raises(ValueError, match="invalid_workflow_fixture_id"):
        load_workflow_fixture("../ticket-handoff", ROOT)
    with pytest.raises(ValueError, match="workflow_fixture_not_found"):
        load_workflow_fixture("not-a-fixture", ROOT)
