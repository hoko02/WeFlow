"""Fixture-only simulator boundary for intake, durable workflow, and replay
investigation evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.health_server import serve_health
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.status import build_service_status, find_repository_root

from .investigation import SyntheticInvestigationSimulator
from .policy_approval import SyntheticPolicyApprovalSimulator
from .workflow import SyntheticWorkflowSimulator

SERVICE_NAME = "business-simulator"
DEFAULT_PORT = 8003
SIMULATOR_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="serve local health endpoints only")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workflow-fixture", help="run one checked-in synthetic workflow fixture")
    parser.add_argument(
        "--investigation-fixture",
        help="run one checked-in bounded replay investigation fixture",
    )
    parser.add_argument(
        "--policy-approval-fixture",
        help="run the named fixture-local policy/approval/delivery slice",
    )
    parser.add_argument("--store", type=Path, help="override the local SQLite store path")
    arguments = parser.parse_args(argv)
    selected_fixtures = (
        bool(arguments.workflow_fixture)
        + bool(arguments.investigation_fixture)
        + bool(arguments.policy_approval_fixture)
    )
    if selected_fixtures > 1:
        parser.error("only one fixture selector can be used at a time")
    if arguments.serve:
        serve_health(SERVICE_NAME, arguments.port)
        return 0
    if selected_fixtures:
        root = find_repository_root()
        temporary_store: TemporaryDirectory[str] | None = None
        if arguments.store is None:
            temporary_store = TemporaryDirectory(prefix="weflow-simulator-fixture-")
            store_path = Path(temporary_store.name) / "workflow.sqlite3"
        else:
            store_path = arguments.store
        try:
            ledger = SQLiteCaseLedger(
                store_path,
                clock=FixedClock(SIMULATOR_TIME),
                contract_root=root,
            )
            workflow = SQLiteDurableWorkflow(
                ledger,
                clock=FixtureClock(SIMULATOR_TIME),
                contract_root=root,
            )
            if arguments.workflow_fixture:
                report = SyntheticWorkflowSimulator(root=root).run_fixture(
                    ledger,
                    workflow,
                    arguments.workflow_fixture,
                )
            elif arguments.investigation_fixture:
                report = SyntheticInvestigationSimulator(root=root).run_fixture(
                    ledger,
                    workflow,
                    str(arguments.investigation_fixture),
                )
            else:
                report = SyntheticPolicyApprovalSimulator(root=root).run_fixture(
                    ledger,
                    workflow,
                    str(arguments.policy_approval_fixture),
                )
        finally:
            if temporary_store is not None:
                temporary_store.cleanup()
        print(json.dumps(report, ensure_ascii=False))
        return 0
    print(json.dumps(build_service_status(SERVICE_NAME), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())