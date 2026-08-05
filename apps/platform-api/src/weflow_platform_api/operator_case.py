"""Tenant-derived, fixed, read-only Platform API boundary for Operator Case evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from weflow_contracts import ContractValidationError, validate_operator_case_snapshot
from weflow_control_kernel.ledger import IntakeRejected, SyntheticActorRegistry
from weflow_testkit import (
    OPERATOR_CASE_NOT_FOUND,
    OPERATOR_CASE_NOT_READY,
    OperatorCaseReportError,
)

from .case_intake import error_response

JsonObject = dict[str, Any]
OperatorCaseSnapshotReader = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True)
class OperatorCaseBoundary:
    """Validate injected read output and enforce actor-derived tenant scope."""

    reader: OperatorCaseSnapshotReader | None
    registry: SyntheticActorRegistry
    contract_root: Path

    def tenant_for_actor(self, actor_id: str | None) -> str:
        return self.registry.resolve(actor_id)

    def read_for_tenant(self, tenant_id: str) -> JsonObject:
        if self.reader is None:
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_FOUND)
        try:
            snapshot = dict(self.reader())
            validate_operator_case_snapshot(snapshot, self.contract_root)
        except OperatorCaseReportError:
            raise
        except (ContractValidationError, TypeError, ValueError) as error:
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY) from error
        if snapshot.get("tenant_id") != tenant_id:
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_FOUND)
        return snapshot


def install_operator_case_routes(
    app: FastAPI,
    boundary: OperatorCaseBoundary,
) -> None:
    """Install the sole fixed Operator Case route; it never accepts a selector."""

    @app.get("/v1/operator/cases/api-503.v1", tags=["operator-case"])
    async def get_api_503_operator_case(
        request: Request,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        if request.query_params or await request.body():
            return error_response(422, "operator_case_request_invalid")
        try:
            tenant_id = boundary.tenant_for_actor(x_weflow_synthetic_actor)
        except IntakeRejected:
            return error_response(403, "tenant_identity_mismatch")
        try:
            snapshot = boundary.read_for_tenant(tenant_id)
        except OperatorCaseReportError as error:
            if error.reason_code == OPERATOR_CASE_NOT_FOUND:
                return error_response(404, OPERATOR_CASE_NOT_FOUND)
            return error_response(503, OPERATOR_CASE_NOT_READY)
        return JSONResponse(content=snapshot)
