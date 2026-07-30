"""Narrow local-only Platform API routes for synthetic Case intake."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from weflow_control_kernel.ledger import (
    CaseLedger,
    IntakeRejected,
    LedgerIntegrityError,
    SyntheticActorRegistry,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class CaseIntakeBoundary:
    """Holds the deterministic local ledger and fixture-only actor resolver."""

    ledger: CaseLedger | None
    registry: SyntheticActorRegistry
    initialization_reason: str | None = None

    @property
    def ready(self) -> bool:
        return self.ledger is not None and self.initialization_reason is None

    def tenant_for_actor(self, actor_id: str | None) -> str:
        return self.registry.resolve(actor_id)


def error_response(status_code: int, reason_code: str) -> JSONResponse:
    """Return an allowlisted error payload without request or configuration values."""

    return JSONResponse(status_code=status_code, content={"reason_code": reason_code})


def _ledger_or_error(boundary: CaseIntakeBoundary) -> CaseLedger | JSONResponse:
    if boundary.ledger is None:
        return error_response(503, boundary.initialization_reason or "ledger_not_ready")
    return boundary.ledger


def _tenant_or_error(
    boundary: CaseIntakeBoundary,
    actor_id: str | None,
) -> str | JSONResponse:
    try:
        return boundary.tenant_for_actor(actor_id)
    except IntakeRejected:
        return error_response(403, "tenant_identity_mismatch")


def _rejection_response(error: IntakeRejected) -> JSONResponse:
    if error.reason_code == "tenant_identity_mismatch":
        return error_response(403, error.reason_code)
    if error.reason_code in {"inbound_event_conflict", "inbound_out_of_order"}:
        return error_response(409, error.reason_code)
    return error_response(422, error.reason_code)


def install_case_intake_routes(app: FastAPI, boundary: CaseIntakeBoundary) -> None:
    """Install the intentionally narrow Change 1 Case intake/read route set."""

    @app.post("/v1/synthetic-im/intake", tags=["case-intake"])
    async def intake(
        request: Request,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        ledger = _ledger_or_error(boundary)
        if isinstance(ledger, JSONResponse):
            return ledger
        tenant_id = _tenant_or_error(boundary, x_weflow_synthetic_actor)
        if isinstance(tenant_id, JSONResponse):
            return tenant_id
        try:
            payload = await request.json()
        except ValueError:
            return error_response(422, "invalid_inbound_event")
        if not isinstance(payload, Mapping):
            return error_response(422, "invalid_inbound_event")
        try:
            result = ledger.intake(payload, effective_tenant_id=tenant_id)
        except IntakeRejected as error:
            return _rejection_response(error)
        except LedgerIntegrityError:
            return error_response(503, "ledger_not_ready")
        return JSONResponse(
            status_code=201 if result.disposition == "accepted" else 200,
            content=result.as_dict(),
        )

    @app.get("/v1/cases/{case_id}", tags=["case-intake"])
    def get_case(
        case_id: str,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        ledger = _ledger_or_error(boundary)
        if isinstance(ledger, JSONResponse):
            return ledger
        tenant_id = _tenant_or_error(boundary, x_weflow_synthetic_actor)
        if isinstance(tenant_id, JSONResponse):
            return tenant_id
        try:
            projection = ledger.get_case_projection(tenant_id, case_id)
        except LedgerIntegrityError:
            return error_response(503, "ledger_not_ready")
        if projection is None:
            return error_response(404, "case_not_found")
        return JSONResponse(content=projection)

    @app.get("/v1/cases/{case_id}/revisions", tags=["case-intake"])
    def get_revisions(
        case_id: str,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        ledger = _ledger_or_error(boundary)
        if isinstance(ledger, JSONResponse):
            return ledger
        tenant_id = _tenant_or_error(boundary, x_weflow_synthetic_actor)
        if isinstance(tenant_id, JSONResponse):
            return tenant_id
        try:
            if ledger.get_case_projection(tenant_id, case_id) is None:
                return error_response(404, "case_not_found")
            return JSONResponse(
                content={"revisions": ledger.list_case_revisions(tenant_id, case_id)}
            )
        except LedgerIntegrityError:
            return error_response(503, "ledger_not_ready")

    @app.get("/v1/cases/{case_id}/events", tags=["case-intake"])
    def get_events(
        case_id: str,
        x_weflow_synthetic_actor: str | None = Header(default=None),
    ) -> JSONResponse:
        ledger = _ledger_or_error(boundary)
        if isinstance(ledger, JSONResponse):
            return ledger
        tenant_id = _tenant_or_error(boundary, x_weflow_synthetic_actor)
        if isinstance(tenant_id, JSONResponse):
            return tenant_id
        try:
            if ledger.get_case_projection(tenant_id, case_id) is None:
                return error_response(404, "case_not_found")
            return JSONResponse(content={"events": ledger.list_case_events(tenant_id, case_id)})
        except LedgerIntegrityError:
            return error_response(503, "ledger_not_ready")
