"""Fixture-only simulator process boundary for intake and durable workflow evidence."""

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

from .workflow import SyntheticWorkflowSimulator

SERVICE_NAME = "business-simulator"
DEFAULT_PORT = 8003
SIMULATOR_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="serve local health endpoints only")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--workflow-fixture", help="run one checked-in synthetic workflow fixture")
    parser.add_argument("--store", type=Path, help="override the local SQLite store path")
    arguments = parser.parse_args(argv)
    if arguments.serve:
        serve_health(SERVICE_NAME, arguments.port)
        return 0
    if arguments.workflow_fixture:
        root = find_repository_root()
        temporary_store: TemporaryDirectory[str] | None = None
        if arguments.store is None:
            temporary_store = TemporaryDirectory(prefix="weflow-workflow-fixture-")
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
            report = SyntheticWorkflowSimulator(root=root).run_fixture(
                ledger,
                workflow,
                arguments.workflow_fixture,
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
