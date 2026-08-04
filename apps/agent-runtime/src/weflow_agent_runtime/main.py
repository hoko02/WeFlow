"""Replay-only Agent Runtime process boundary with loopback health and local
investigation commands."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from weflow_control_kernel.config import ConfigurationDenied
from weflow_control_kernel.durable_workflow import SQLiteDurableWorkflow, WorkflowError
from weflow_control_kernel.health_server import serve_health
from weflow_control_kernel.ledger import SQLiteCaseLedger, default_case_store_path
from weflow_control_kernel.status import build_service_status, find_repository_root

from .investigation import run_investigation_replay
from .runtime import run_replay

SERVICE_NAME = "agent-runtime"
DEFAULT_PORT = 8002


def _investigation_error_report(fixture_id: str, reason_code: str) -> dict[str, object]:
    return {
        "report_type": "weflow-replay-investigation.v1",
        "fixture_id": fixture_id,
        "accepted": False,
        "reason_code": reason_code,
        "model_invocation": False,
        "external_write": False,
        "approval": False,
        "outbound_delivery": False,
        "customer_resolution": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="serve local health endpoints only")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--fixture", help="emit a retained synthetic replay result without starting a service"
    )
    parser.add_argument(
        "--investigation-fixture",
        help="run or resume one checked-in replay investigation for an existing TICKET_READY Case",
    )
    parser.add_argument("--tenant-id", help="required tenant scope for --investigation-fixture")
    parser.add_argument("--case-id", help="required Case scope for --investigation-fixture")
    parser.add_argument("--store", type=Path, help="override the local SQLite store path")
    arguments = parser.parse_args(argv)
    if arguments.fixture and arguments.investigation_fixture:
        parser.error("--fixture and --investigation-fixture cannot be combined")
    if arguments.serve:
        serve_health(SERVICE_NAME, arguments.port)
        return 0
    if arguments.investigation_fixture:
        fixture_id = str(arguments.investigation_fixture)
        if not arguments.tenant_id or not arguments.case_id:
            report = _investigation_error_report(fixture_id, "investigation_scope_required")
            print(json.dumps(report))
            return 2
        root = find_repository_root()
        try:
            ledger = SQLiteCaseLedger(
                arguments.store or default_case_store_path(root),
                contract_root=root,
            )
            workflow = SQLiteDurableWorkflow(ledger, contract_root=root)
            workflow.recover_all()
            report = run_investigation_replay(
                workflow,
                arguments.tenant_id,
                arguments.case_id,
                fixture_id=fixture_id,
                root=root,
            )
        except ConfigurationDenied as error:
            print(json.dumps(_investigation_error_report(fixture_id, error.reason_code)))
            return 2
        except WorkflowError as error:
            print(json.dumps(_investigation_error_report(fixture_id, error.reason_code)))
            return 2
        except ValueError:
            report = _investigation_error_report(fixture_id, "investigation_fixture_invalid")
            print(json.dumps(report))
            return 2
        print(json.dumps(report, ensure_ascii=False))
        return 0
    if arguments.fixture:
        print(json.dumps(run_replay({"fixture_id": arguments.fixture}), ensure_ascii=False))
        return 0
    print(json.dumps(build_service_status(SERVICE_NAME), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())