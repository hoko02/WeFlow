"""Optional Temporal service-boundary driver for the same durable SQLite journal."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from .durable_workflow import SQLiteDurableWorkflow, WorkflowError
from .ledger import SQLiteCaseLedger

TEMPORAL_TASK_QUEUE = "weflow-durable-support-workflow-v1"
TEMPORAL_TARGET = "127.0.0.1:7233"


class TemporalDriverUnavailable(WorkflowError):
    """A redacted readiness failure; no fallback effect is ever executed."""


def _require_loopback_target(target: str) -> None:
    """Reject a Temporal endpoint outside the explicit local service boundary."""

    normalized = target.lower()
    if not (
        normalized.startswith("127.0.0.1:")
        or normalized.startswith("localhost:")
        or normalized.startswith("[::1]:")
    ):
        raise TemporalDriverUnavailable("temporal_target_not_loopback")


def _temporal_imports() -> tuple[Any, Any, Any, Any]:
    try:
        from temporalio import activity, workflow
        from temporalio.client import Client
        from temporalio.worker import Worker
    except ImportError as error:
        raise TemporalDriverUnavailable("temporal_sdk_unavailable") from error
    return activity, workflow, Client, Worker


@dataclass(frozen=True)
class TemporalWorkflowRequest:
    """Safe activity material: identifiers and the local store path, never customer content."""

    store_path: str
    tenant_id: str
    workflow_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "store_path": self.store_path,
            "tenant_id": self.tenant_id,
            "workflow_id": self.workflow_id,
        }


@dataclass(frozen=True)
class TemporalServiceBoundaryDriver:
    """Schedules the local reducer through Temporal without making it the audit ledger."""

    store_path: Path
    contract_root: Path
    target: str = TEMPORAL_TARGET
    task_queue: str = TEMPORAL_TASK_QUEUE
    timeout_seconds: float = 3.0

    async def readiness(self) -> dict[str, object]:
        """Connect only to the declared loopback Temporal endpoint with a bounded timeout."""

        _require_loopback_target(self.target)
        _, _, client_type, _ = _temporal_imports()
        try:
            await asyncio.wait_for(
                client_type.connect(self.target),
                timeout=self.timeout_seconds,
            )
        except (TimeoutError, OSError, RuntimeError) as error:
            raise TemporalDriverUnavailable("temporal_driver_not_ready") from error
        return {
            "driver": "temporal",
            "ready": True,
            "task_queue": self.task_queue,
            "external_write": False,
            "model_invocation": False,
        }

    async def start_workflow(self, tenant_id: str, workflow_id: str) -> str:
        """Start one deterministic driver workflow; the activity still writes the local journal."""

        _require_loopback_target(self.target)
        _, _, client_type, _ = _temporal_imports()
        try:
            client = await asyncio.wait_for(
                client_type.connect(self.target),
                timeout=self.timeout_seconds,
            )
            workflow_definition, _ = self.definitions()
            handle = await client.start_workflow(
                workflow_definition.run,
                TemporalWorkflowRequest(
                    store_path=str(self.store_path),
                    tenant_id=tenant_id,
                    workflow_id=workflow_id,
                ).as_dict(),
                id=f"weflow-{workflow_id}",
                task_queue=self.task_queue,
            )
        except (TimeoutError, OSError, RuntimeError) as error:
            raise TemporalDriverUnavailable("temporal_driver_not_ready") from error
        return str(handle.id)

    def definitions(self) -> tuple[type[Any], Any]:
        """Build import-late definitions; offline mode does not require the Temporal SDK."""

        activity, workflow, _, _ = _temporal_imports()
        store_path = self.store_path
        contract_root = self.contract_root

        @activity.defn(name="weflow.recover_durable_workflow.v1")
        async def recover_durable_workflow(request: dict[str, str]) -> dict[str, object]:
            requested_path = Path(request.get("store_path", ""))
            if requested_path.resolve() != store_path.resolve():
                raise RuntimeError("temporal_workflow_store_mismatch")
            tenant_id = request.get("tenant_id")
            workflow_id = request.get("workflow_id")
            if not tenant_id or not workflow_id:
                raise RuntimeError("temporal_workflow_request_invalid")
            ledger = SQLiteCaseLedger(requested_path, contract_root=contract_root)
            driver = SQLiteDurableWorkflow(ledger, contract_root=contract_root)
            projection = driver.recover_workflow(tenant_id, workflow_id)
            return {
                "workflow_id": workflow_id,
                "state": None if projection is None else projection["state"],
                "external_write": False,
                "customer_resolution": False,
            }

        @workflow.defn(name="WeFlowDurableSupportWorkflow")
        class DurableSupportWorkflow:
            @workflow.run
            async def run(self, request: dict[str, str]) -> dict[str, object]:
                return await workflow.execute_activity(
                    recover_durable_workflow,
                    request,
                    start_to_close_timeout=timedelta(seconds=30),
                )

        return DurableSupportWorkflow, recover_durable_workflow

    async def run_worker(self) -> None:
        """Run the explicit Temporal worker; callers opt in only in service-boundary mode."""

        _require_loopback_target(self.target)
        _, _, client_type, worker_type = _temporal_imports()
        try:
            client = await asyncio.wait_for(
                client_type.connect(self.target),
                timeout=self.timeout_seconds,
            )
        except (TimeoutError, OSError, RuntimeError) as error:
            raise TemporalDriverUnavailable("temporal_driver_not_ready") from error
        workflow_definition, recovery_activity = self.definitions()
        worker = worker_type(
            client,
            task_queue=self.task_queue,
            workflows=[workflow_definition],
            activities=[recovery_activity],
        )
        await worker.run()
