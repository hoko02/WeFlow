"""Fixture-only workflow driver helpers for the Change 2 offline simulator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    SQLiteDurableWorkflow,
    WorkflowInterrupted,
)
from weflow_control_kernel.ledger import SQLiteCaseLedger, SyntheticActorRegistry

from .intake import SyntheticIntakeSimulator

JsonObject = dict[str, Any]


def _find_repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "fixtures" / "workflow").is_dir() and (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate
    raise RuntimeError("WeFlow repository root could not be located")


def load_workflow_fixture(fixture_id: str, root: Path | None = None) -> JsonObject:
    """Load a named, checked-in workflow fixture without accepting arbitrary paths."""

    if not fixture_id or any(character in fixture_id for character in "/\\"):
        raise ValueError("invalid_workflow_fixture_id")
    path = (root or _find_repository_root()) / "fixtures" / "workflow" / f"{fixture_id}.json"
    if not path.is_file():
        raise ValueError("workflow_fixture_not_found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("invalid_workflow_fixture") from error
    required = {
        "fixture_id",
        "synthetic",
        "intake_fixture_id",
        "sla_deadline_seconds",
        "advance_clock_seconds",
        "fault_profile",
        "expected_state",
    }
    if set(payload) != required or payload.get("fixture_id") != fixture_id:
        raise ValueError("invalid_workflow_fixture")
    if (
        payload.get("synthetic") is not True
        or not isinstance(payload.get("intake_fixture_id"), str)
        or not isinstance(payload.get("sla_deadline_seconds"), int)
        or payload["sla_deadline_seconds"] <= 0
        or not isinstance(payload.get("advance_clock_seconds"), int)
        or payload["advance_clock_seconds"] < 0
        or payload.get("fault_profile")
        not in {None, *FaultProfile._POINTS, "reconciliation-timeout"}
        or payload.get("expected_state")
        not in {"TICKET_READY", "WAITING_FOR_OPERATOR", "NEEDS_RECONCILIATION"}
    ):
        raise ValueError("invalid_workflow_fixture")
    return payload


class SyntheticWorkflowSimulator:
    """Runs only named synthetic workflow fixtures and exposes safe inspection evidence."""

    def __init__(
        self,
        registry: SyntheticActorRegistry | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        self.root = root
        self.registry = registry or SyntheticActorRegistry.default()
        self.intake = SyntheticIntakeSimulator(self.registry, root=root)

    def run_fixture(
        self,
        ledger: SQLiteCaseLedger,
        workflow: SQLiteDurableWorkflow,
        fixture_id: str,
    ) -> JsonObject:
        fixture = load_workflow_fixture(fixture_id, self.root)
        inbound = self.intake.fixture_request(str(fixture["intake_fixture_id"]))
        tenant_id = self.registry.resolve(str(inbound["actor_id"]))
        intake_result = self.intake.submit_fixture(ledger, str(fixture["intake_fixture_id"]))
        policy = workflow.default_sla_policy(tenant_id)
        policy["policy_id"] = f"fixture-{fixture_id}"
        policy["deadline_seconds"] = fixture["sla_deadline_seconds"]
        fault_name = fixture["fault_profile"]
        fault_profile = None if fault_name is None else FaultProfile.named(str(fault_name))
        try:
            projection = workflow.run_case(
                tenant_id,
                intake_result.case_id,
                intake_result.case_revision_id,
                sla_policy=policy,
                fault_profile=fault_profile,
            )
            disposition = "completed"
        except WorkflowInterrupted as error:
            clock = workflow._clock
            advance = getattr(clock, "advance", None)
            if int(fixture["advance_clock_seconds"]) > 0:
                if not callable(advance):
                    raise ValueError("workflow_fixture_clock_not_injectable")
                advance(seconds=int(fixture["advance_clock_seconds"]))
            restarted_ledger = SQLiteCaseLedger(
                ledger.path,
                clock=ledger._clock,
                contract_root=self.root or _find_repository_root(),
            )
            restarted = SQLiteDurableWorkflow(
                restarted_ledger,
                clock=clock,
                contract_root=self.root or _find_repository_root(),
            )
            restarted.recover_all()
            projection = restarted.get_workflow_for_case(tenant_id, intake_result.case_id)
            workflow = restarted
            disposition = f"recovered:{error.reason_code}"
        if projection is None or projection.get("state") != fixture["expected_state"]:
            raise ValueError("workflow_fixture_expectation_failed")
        return self.inspect(
            workflow,
            fixture_id=fixture_id,
            tenant_id=tenant_id,
            case_id=intake_result.case_id,
            projection=projection,
            disposition=disposition,
            expected_state=str(fixture["expected_state"]),
        )

    @staticmethod
    def inspect(
        workflow: SQLiteDurableWorkflow,
        *,
        fixture_id: str,
        tenant_id: str,
        case_id: str,
        projection: Mapping[str, Any] | None,
        disposition: str,
        expected_state: str,
    ) -> JsonObject:
        """Return counts and safe identifiers only; raw fixture content never escapes."""

        return {
            "report_type": "weflow-synthetic-workflow-inspection.v1",
            "fixture_id": fixture_id,
            "disposition": disposition,
            "case_id": case_id,
            "workflow_id": None if projection is None else projection.get("workflow_id"),
            "state": None if projection is None else projection.get("state"),
            "expected_state": expected_state,
            "matches_expected_state": projection is not None
            and projection.get("state") == expected_state,
            "workflow_version": None if projection is None else projection.get("workflow_version"),
            "source_counts": workflow.source_counts(tenant_id),
            "model_invocation": False,
            "external_write": False,
            "customer_resolution": False,
        }

    @staticmethod
    def export_snapshot(workflow: SQLiteDurableWorkflow, tenant_id: str) -> JsonObject:
        return workflow.export_snapshot(tenant_id)
