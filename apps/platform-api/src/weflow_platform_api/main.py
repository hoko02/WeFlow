"""Platform API: safe diagnostics plus deterministic synthetic Case intake."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from weflow_contracts import load_contract_schemas
from weflow_control_kernel.durable_workflow import SQLiteDurableWorkflow, WorkflowError
from weflow_control_kernel.ledger import (
    CaseLedger,
    LedgerIntegrityError,
    SQLiteCaseLedger,
    SyntheticActorRegistry,
    default_case_store_path,
)
from weflow_control_kernel.status import (
    build_foundation_report,
    build_service_status,
    find_repository_root,
)

from .case_intake import CaseIntakeBoundary, install_case_intake_routes
from .workflow import WorkflowBoundary, install_workflow_routes


class ComponentStatusResponse(BaseModel):
    name: str
    ready: bool
    reason_code: str | None = None


class PolicyDenialResponse(BaseModel):
    capability: str
    reason_code: str
    status: str


class HealthStatusResponse(BaseModel):
    service: str
    live: bool
    ready: bool
    state: str
    mode: str
    components: list[ComponentStatusResponse]
    policy_denial: PolicyDenialResponse | None = None
    limitations: list[str]


class FoundationCapabilitiesResponse(BaseModel):
    business_workflow_implemented: bool
    external_writes_enabled: bool
    operational_ready: bool
    synthetic_case_intake_implemented: bool
    durable_support_workflow_implemented: bool


HEALTH_SCHEMA_ID = "https://weflow.local/contracts/v1/health-status.schema.json"
INBOUND_SCHEMA_ID = "https://weflow.local/contracts/v1/inbound-message-event.schema.json"
CASE_PROJECTION_SCHEMA_ID = "https://weflow.local/contracts/v1/case-projection.schema.json"
WORKFLOW_PROJECTION_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-projection.schema.json"
WORKFLOW_CHECKPOINT_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-checkpoint.schema.json"
WORKFLOW_COMMAND_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-command.schema.json"


def _install_canonical_openapi(app: FastAPI, root: Path) -> None:
    """Expose canonical health/intake schemas rather than duplicate API-only models."""

    def custom_openapi() -> dict[str, object]:
        if app.openapi_schema is not None:
            return app.openapi_schema

        document = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = document.setdefault("components", {}).setdefault("schemas", {})
        contracts = load_contract_schemas(root)
        components["WeFlowHealthStatusV1"] = deepcopy(contracts[HEALTH_SCHEMA_ID])
        components["WeFlowInboundMessageEventV1"] = deepcopy(contracts[INBOUND_SCHEMA_ID])
        components["WeFlowCaseProjectionV1"] = deepcopy(contracts[CASE_PROJECTION_SCHEMA_ID])
        components["WeFlowWorkflowProjectionV1"] = deepcopy(
            contracts[WORKFLOW_PROJECTION_SCHEMA_ID]
        )
        components["WeFlowWorkflowCheckpointV1"] = deepcopy(
            contracts[WORKFLOW_CHECKPOINT_SCHEMA_ID]
        )
        components["WeFlowWorkflowCommandV1"] = deepcopy(contracts[WORKFLOW_COMMAND_SCHEMA_ID])
        health_reference = {"$ref": "#/components/schemas/WeFlowHealthStatusV1"}
        for path in ("/health/live", "/health/ready"):
            responses = document["paths"][path]["get"].setdefault("responses", {})
            for status_code in ("200", "503"):
                response = responses.setdefault(
                    status_code,
                    {"description": "Platform health status"},
                )
                response["content"] = {"application/json": {"schema": health_reference}}

        intake_path = document["paths"]["/v1/synthetic-im/intake"]["post"]
        intake_path["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/WeFlowInboundMessageEventV1"}
                }
            },
        }
        case_responses = document["paths"]["/v1/cases/{case_id}"]["get"].setdefault(
            "responses",
            {},
        )
        case_responses["200"] = {
            "description": "Tenant-scoped derived Case projection",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/WeFlowCaseProjectionV1"}
                }
            },
        }
        workflow_responses = document["paths"]["/v1/cases/{case_id}/workflow"]["get"].setdefault(
            "responses",
            {},
        )
        workflow_responses["200"] = {
            "description": "Tenant-scoped durable workflow projection",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/WeFlowWorkflowProjectionV1"}
                }
            },
        }
        app.openapi_schema = document
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def _status_with_ledger(
    boundary: CaseIntakeBoundary,
    workflow_boundary: WorkflowBoundary,
    environment: Mapping[str, str] | None,
    root: Path,
) -> dict[str, object]:
    status = build_service_status("platform-api", environment=environment, root=root)
    components = list(status["components"])
    components.append(
        {
            "name": "case-ledger",
            "ready": boundary.ready,
            "reason_code": None if boundary.ready else boundary.initialization_reason,
        }
    )
    components.append(
        {
            "name": "durable-workflow",
            "ready": workflow_boundary.ready,
            "reason_code": (
                None if workflow_boundary.ready else workflow_boundary.initialization_reason
            ),
        }
    )
    status["components"] = components
    if not boundary.ready or not workflow_boundary.ready:
        status["ready"] = False
        status["state"] = "not-ready"
    status["limitations"] = [
        *status["limitations"],
        "synthetic-case-intake-only",
        "fixture-local-durable-workflow-only",
    ]
    return status


def create_app(
    environment: Mapping[str, str] | None = None,
    root: Path | None = None,
    *,
    ledger: CaseLedger | None = None,
    workflow: SQLiteDurableWorkflow | None = None,
    actor_registry: SyntheticActorRegistry | None = None,
) -> FastAPI:
    repository_root = root or find_repository_root()
    try:
        resolved_ledger = ledger or SQLiteCaseLedger(
            default_case_store_path(repository_root),
            contract_root=repository_root,
        )
        initialization_reason = None
    except LedgerIntegrityError as error:
        resolved_ledger = None
        initialization_reason = error.reason_code
    boundary = CaseIntakeBoundary(
        ledger=resolved_ledger,
        registry=actor_registry or SyntheticActorRegistry.default(),
        initialization_reason=initialization_reason,
    )
    try:
        if workflow is not None:
            resolved_workflow = workflow
        elif isinstance(resolved_ledger, SQLiteCaseLedger):
            resolved_workflow = SQLiteDurableWorkflow(
                resolved_ledger,
                contract_root=repository_root,
            )
        else:
            resolved_workflow = None
        workflow_initialization_reason = None
    except WorkflowError as error:
        resolved_workflow = None
        workflow_initialization_reason = error.reason_code
    workflow_boundary = WorkflowBoundary(
        workflow=resolved_workflow,
        registry=actor_registry or SyntheticActorRegistry.default(),
        initialization_reason=workflow_initialization_reason,
    )
    app = FastAPI(
        title="WeFlow Platform API",
        version="0.2.0",
        description=(
            "Change 2 fixture-local durable workflow observation/commands and Change 1 intake. "
            "No support resolution, approval, provider, or external write is implemented."
        ),
    )
    app.state.case_intake_boundary = boundary
    app.state.workflow_boundary = workflow_boundary

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["X-WeFlow-Synthetic-Actor"],
    )
    _install_canonical_openapi(app, repository_root)

    @app.get("/health/live", response_model=HealthStatusResponse, tags=["foundation"])
    def liveness() -> dict[str, object]:
        return _status_with_ledger(boundary, workflow_boundary, environment, repository_root)

    @app.get(
        "/health/ready",
        response_model=HealthStatusResponse,
        responses={503: {"model": HealthStatusResponse}},
        tags=["foundation"],
    )
    def readiness() -> JSONResponse:
        status = _status_with_ledger(boundary, workflow_boundary, environment, repository_root)
        return JSONResponse(status_code=200 if status["ready"] else 503, content=status)

    @app.get(
        "/foundation/capabilities",
        response_model=FoundationCapabilitiesResponse,
        tags=["foundation"],
    )
    def foundation_capabilities() -> dict[str, object]:
        report = build_foundation_report(environment=environment, root=repository_root)
        return {
            "business_workflow_implemented": report["business_workflow_implemented"],
            "external_writes_enabled": report["external_writes_enabled"],
            "operational_ready": report["operational_ready"] and boundary.ready,
            "synthetic_case_intake_implemented": boundary.ready,
            "durable_support_workflow_implemented": workflow_boundary.ready,
        }

    install_case_intake_routes(app, boundary)
    install_workflow_routes(app, workflow_boundary)
    return app


app = create_app()
