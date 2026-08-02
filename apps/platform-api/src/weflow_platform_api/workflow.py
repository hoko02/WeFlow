"""Narrow tenant-derived observation and command routes for Change 2 workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from weflow_control_kernel.durable_workflow import (
    SQLiteDurableWorkflow,
    WorkflowError,
    WorkflowNotFound,
)
from weflow_control_kernel.ledger import IntakeRejected, SyntheticActorRegistry

from .case_intake import error_response

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class WorkflowBoundary:
    """Keeps the public API unable to mutate Cases, events, or ticket records directly."""

    workflow: SQLiteDurableWorkflow | None
    registry: SyntheticActorRegistry
    initialization_reason: str | None = None

    @property
    def ready(self) -> bool:
        return self.workflow is not None and self.initialization_reason is None

    def tenant_for_actor(self, actor_id: str | None) -> str:
        return self.registry.resolve(actor_id)


def _tenant_or_error(boundary: WorkflowBoundary, actor_id: str | None) -> str | JSONResponse:
    try:
        return boundary.tenant_for_actor(actor_id)
    except IntakeRejected:
        return error_response(403, "tenant_identity_mismatch")


def _workflow_or_error(boundary: WorkflowBoundary) -> SQLiteDurableWorkflow | JSONResponse:
    if boundary.workflow is None:
        return error_response(503, boundary.initialization_reason or "workflow_not_ready")
    return boundary.workflow


def _workflow_error_response(error: WorkflowError) -> JSONResponse:
    if isinstance(error, WorkflowNotFound) or error.reason_code == "workflow_not_found":
        return error_response(404, "workflow_not_found")
    if error.reason_code in {
        "workflow_version_conflict",
        "workflow_command_conflict",
        "workflow_command_recovery_conflict",
        "workflow_transition_not_allowed",
        "workflow_event_predecessor_mismatch",
    }:
        return error_response(409, error.reason_code)
    if error.reason_code in {
        "workflow_command_not_allowlisted",
        "workflow_command_invalid",
        "workflow_state_not_allowlisted",
    }:
        return error_response(422, error.reason_code)
    return error_response(503, "workflow_not_ready")


def install_workflow_routes(app: FastAPI, boundary: WorkflowBoundary) -> None:
    """Install only workflow reads and three allowlisted synthetic commands."""

    @app.get("/v1/cases/{case_id}/workflow", tags=["durable-workflow"])
    def get_workflow(
        case_id: str,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        workflow = _workflow_or_error(boundary)
        if isinstance(workflow, JSONResponse):
            return workflow
        tenant_id = _tenant_or_error(boundary, x_weflow_synthetic_actor)
        if isinstance(tenant_id, JSONResponse):
            return tenant_id
        try:
            projection = workflow.get_workflow_for_case(tenant_id, case_id)
        except WorkflowError as error:
            return _workflow_error_response(error)
        if projection is None:
            return error_response(404, "workflow_not_found")
        return JSONResponse(content=projection)

    @app.get("/v1/cases/{case_id}/workflow/checkpoints", tags=["durable-workflow"])
    def get_workflow_checkpoints(
        case_id: str,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        workflow = _workflow_or_error(boundary)
        if isinstance(workflow, JSONResponse):
            return workflow
        tenant_id = _tenant_or_error(boundary, x_weflow_synthetic_actor)
        if isinstance(tenant_id, JSONResponse):
            return tenant_id
        try:
            checkpoints = workflow.list_workflow_checkpoints_for_case(tenant_id, case_id)
        except WorkflowError as error:
            return _workflow_error_response(error)
        if checkpoints is None:
            return error_response(404, "workflow_not_found")
        return JSONResponse(content={"checkpoints": checkpoints})

    @app.post("/v1/cases/{case_id}/workflow/commands", tags=["durable-workflow"])
    async def submit_workflow_command(
        case_id: str,
        request: Request,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        workflow = _workflow_or_error(boundary)
        if isinstance(workflow, JSONResponse):
            return workflow
        tenant_id = _tenant_or_error(boundary, x_weflow_synthetic_actor)
        if isinstance(tenant_id, JSONResponse):
            return tenant_id
        try:
            payload = await request.json()
        except ValueError:
            return error_response(422, "workflow_command_invalid")
        required = {"command_id", "command_type", "expected_workflow_version"}
        if (
            not isinstance(payload, Mapping)
            or set(payload) != required
            or not isinstance(payload.get("command_id"), str)
            or not isinstance(payload.get("command_type"), str)
            or not isinstance(payload.get("expected_workflow_version"), int)
        ):
            return error_response(422, "workflow_command_invalid")
        try:
            result = workflow.submit_command(
                tenant_id,
                case_id,
                command_id=str(payload["command_id"]),
                command_type=str(payload["command_type"]),
                expected_workflow_version=int(payload["expected_workflow_version"]),
            )
        except WorkflowError as error:
            return _workflow_error_response(error)
        return JSONResponse(
            status_code=200,
            content={
                "disposition": result.disposition,
                "projection": result.projection,
            },
        )
