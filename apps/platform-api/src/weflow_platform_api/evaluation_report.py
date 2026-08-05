"""Tenant-derived, read-only Platform API boundary for offline evaluation evidence."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from weflow_contracts import ContractValidationError
from weflow_contracts.evaluation import validate_evaluation_suite_snapshot
from weflow_control_kernel.ledger import IntakeRejected, SyntheticActorRegistry
from weflow_testkit.evaluation_report import (
    EVALUATION_REPORT_NOT_FOUND,
    EVALUATION_REPORT_NOT_READY,
    EvaluationReportError,
)

from .case_intake import error_response

JsonObject = dict[str, Any]
EvaluationSnapshotReader = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True)
class EvaluationReportBoundary:
    """Validate reader output and derive tenant scope outside the HTTP handler."""

    reader: EvaluationSnapshotReader | None
    registry: SyntheticActorRegistry
    contract_root: Path

    def tenant_for_actor(self, actor_id: str | None) -> str:
        return self.registry.resolve(actor_id)

    def read_for_tenant(self, tenant_id: str) -> JsonObject:
        if self.reader is None:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_FOUND)
        try:
            snapshot = dict(self.reader())
            validate_evaluation_suite_snapshot(snapshot, self.contract_root)
        except EvaluationReportError:
            raise
        except (ContractValidationError, TypeError, ValueError) as error:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_READY) from error
        if snapshot.get("tenant_id") != tenant_id:
            raise EvaluationReportError(EVALUATION_REPORT_NOT_FOUND)
        return snapshot


def install_evaluation_report_routes(
    app: FastAPI,
    boundary: EvaluationReportBoundary,
) -> None:
    """Install the single supported suite route with no caller-selected report input."""

    @app.get("/v1/evaluations/offline-seed.v1", tags=["evaluation-report"])
    def get_offline_seed_evaluation(
        request: Request,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        if request.query_params:
            return error_response(422, "evaluation_request_invalid")
        try:
            tenant_id = boundary.tenant_for_actor(x_weflow_synthetic_actor)
        except IntakeRejected:
            return error_response(403, "tenant_identity_mismatch")
        try:
            snapshot = boundary.read_for_tenant(tenant_id)
        except EvaluationReportError as error:
            if error.reason_code == EVALUATION_REPORT_NOT_FOUND:
                return error_response(404, EVALUATION_REPORT_NOT_FOUND)
            return error_response(503, EVALUATION_REPORT_NOT_READY)
        return JSONResponse(content=snapshot)
