"""Deterministic Change 2 control worker with an offline recovery driver."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from weflow_control_kernel.config import ConfigurationDenied, load_config
from weflow_control_kernel.durable_workflow import SQLiteDurableWorkflow, WorkflowError
from weflow_control_kernel.health_server import serve_health
from weflow_control_kernel.ledger import SQLiteCaseLedger, default_case_store_path
from weflow_control_kernel.status import build_service_status, find_repository_root
from weflow_control_kernel.temporal_driver import (
    TemporalDriverUnavailable,
    TemporalServiceBoundaryDriver,
)

SERVICE_NAME = "control-worker"
DEFAULT_PORT = 8001


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help="serve local health endpoints only")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--run-once", action="store_true", help="scan and recover local workflows once"
    )
    parser.add_argument(
        "--temporal-worker",
        action="store_true",
        help="run the explicit local Temporal driver in service-boundary mode",
    )
    parser.add_argument("--store", type=Path, help="override the local SQLite store path")
    arguments = parser.parse_args(argv)
    if arguments.serve:
        serve_health(SERVICE_NAME, arguments.port)
        return 0
    if arguments.run_once or arguments.temporal_worker:
        root = find_repository_root()
        try:
            config = load_config()
        except ConfigurationDenied as error:
            print(
                json.dumps(
                    {
                        "report_type": "weflow-control-worker-run.v1",
                        "workflow_ready": False,
                        "reason_code": error.reason_code,
                        "external_write": False,
                        "model_invocation": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        if config.mode == "service-boundary":
            driver = TemporalServiceBoundaryDriver(
                store_path=arguments.store or default_case_store_path(root),
                contract_root=root,
                timeout_seconds=config.service_boundary_timeout_seconds,
            )
            try:
                if arguments.temporal_worker:
                    asyncio.run(driver.run_worker())
                    return 0
                readiness = asyncio.run(driver.readiness())
            except TemporalDriverUnavailable as error:
                status = build_service_status(SERVICE_NAME, root=root)
                print(
                    json.dumps(
                        {
                            "report_type": "weflow-control-worker-run.v1",
                            "workflow_ready": False,
                            "reason_code": error.reason_code,
                            "dependencies": status["components"],
                            "external_write": False,
                            "model_invocation": False,
                        },
                        ensure_ascii=False,
                    )
                )
                return 2
            print(
                json.dumps(
                    {
                        "report_type": "weflow-control-worker-run.v1",
                        "workflow_ready": True,
                        "driver": readiness["driver"],
                        "task_queue": readiness["task_queue"],
                        "external_write": False,
                        "model_invocation": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if arguments.temporal_worker:
            print(
                json.dumps(
                    {
                        "report_type": "weflow-control-worker-run.v1",
                        "workflow_ready": False,
                        "reason_code": "temporal_driver_requires_service_boundary",
                        "external_write": False,
                        "model_invocation": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        try:
            ledger = SQLiteCaseLedger(
                arguments.store or default_case_store_path(root),
                contract_root=root,
            )
            workflow = SQLiteDurableWorkflow(ledger, contract_root=root)
            recovered = workflow.recover_all()
            print(
                json.dumps(
                    {
                        "report_type": "weflow-control-worker-run.v1",
                        "workflow_ready": True,
                        "recovered_workflows": len(recovered),
                        "external_write": False,
                        "model_invocation": False,
                        "customer_resolution": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        except WorkflowError as error:
            print(
                json.dumps(
                    {
                        "report_type": "weflow-control-worker-run.v1",
                        "workflow_ready": False,
                        "reason_code": error.reason_code,
                        "external_write": False,
                        "model_invocation": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 2
    print(json.dumps(build_service_status(SERVICE_NAME), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
