from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_business_simulator import SyntheticIntakeSimulator, load_intake_fixture
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
