"""Fixture-only deterministic policy, approval, and local-delivery simulator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    SQLiteDurableWorkflow,
    WorkflowError,
)
from weflow_control_kernel.ledger import SQLiteCaseLedger, SyntheticActorRegistry
from weflow_control_kernel.policy import (
    API_503_DELIVERY_BUDGET,
    API_503_DELIVERY_RESOURCE_ID,
    API_503_POLICY_FIXTURE_ID,
    API_503_POLICY_VERSION,
    FIXTURE_APPROVER_ROLE,
    FIXTURE_CONTROLLER_ROLE,
)

from .investigation import SyntheticInvestigationSimulator

JsonObject = dict[str, Any]


class PolicyApprovalFixtureError(ValueError):
    """Safe failure for malformed or non-allowlisted simulator fixture metadata."""


def _find_repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "fixtures" / "policy").is_dir() and (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate
    raise RuntimeError("WeFlow repository root could not be located")


def load_policy_approval_fixture(fixture_id: str, root: Path | None = None) -> JsonObject:
    """Load exactly the named safe API-503 fixture metadata, never customer content."""

    if fixture_id != API_503_POLICY_FIXTURE_ID:
        raise PolicyApprovalFixtureError("policy_fixture_not_allowlisted")
    path = (root or _find_repository_root()) / "fixtures" / "policy" / f"{fixture_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PolicyApprovalFixtureError("policy_fixture_not_found") from error
    expected = {
        "fixture_id",
        "synthetic",
        "investigation_fixture_id",
        "tenant_id",
        "controller_subject_id",
        "controller_role",
        "approver_actor_id",
        "approver_role",
        "policy_version",
        "delivery_resource_id",
        "data_classification",
        "delivery_budget",
        "fixed_at",
        "network_required",
        "credentials_required",
        "customer_resolution",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise PolicyApprovalFixtureError("invalid_policy_fixture")
    if (
        payload.get("fixture_id") != API_503_POLICY_FIXTURE_ID
        or payload.get("synthetic") is not True
        or payload.get("investigation_fixture_id") != "api-503-investigation"
        or payload.get("tenant_id") != "tenant-alpha"
        or payload.get("controller_subject_id") != "fixture-controller-alpha"
        or payload.get("controller_role") != FIXTURE_CONTROLLER_ROLE
        or not isinstance(payload.get("approver_actor_id"), str)
        or payload.get("approver_role") != FIXTURE_APPROVER_ROLE
        or payload.get("policy_version") != API_503_POLICY_VERSION
        or payload.get("delivery_resource_id") != API_503_DELIVERY_RESOURCE_ID
        or payload.get("data_classification") != "synthetic"
        or payload.get("delivery_budget") != API_503_DELIVERY_BUDGET
        or payload.get("network_required") is not False
        or payload.get("credentials_required") is not False
        or payload.get("customer_resolution") is not False
    ):
        raise PolicyApprovalFixtureError("invalid_policy_fixture")
    try:
        datetime.fromisoformat(str(payload["fixed_at"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise PolicyApprovalFixtureError("invalid_policy_fixture") from error
    return dict(payload)


class SyntheticPolicyApprovalSimulator:
    """Runs the fixed Change 4 vertical slice without a network or live connector."""

    def __init__(
        self,
        registry: SyntheticActorRegistry | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        self.root = root
        self.registry = registry or SyntheticActorRegistry.default()
        self.investigation = SyntheticInvestigationSimulator(self.registry, root=root)

    def run_fixture(
        self,
        ledger: SQLiteCaseLedger,
        workflow: SQLiteDurableWorkflow,
        fixture_id: str = API_503_POLICY_FIXTURE_ID,
        *,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject:
        """Drive the fixed replay path through control-owned approval and local delivery."""

        fixture = load_policy_approval_fixture(fixture_id, self.root)
        investigation = self.investigation.run_fixture(
            ledger,
            workflow,
            str(fixture["investigation_fixture_id"]),
        )
        if investigation.get("state") != "RESPONSE_READY":
            raise WorkflowError("policy_fixture_predecessor_invalid")
        case_id = str(investigation["case_id"])
        projection = workflow.activate_policy_approval(
            str(fixture["tenant_id"]),
            case_id,
            fixture_id=fixture_id,
            fault_profile=fault_profile,
        )
        facts = workflow.policy_approval_facts_for_case(str(fixture["tenant_id"]), case_id)
        if projection.get("state") != "AWAITING_APPROVAL" or facts is None:
            raise WorkflowError("policy_fixture_activation_invalid")
        request = facts.get("approval_request")
        if not isinstance(request, Mapping) or not isinstance(
            request.get("approval_request_id"), str
        ):
            raise WorkflowError("policy_fixture_request_missing")
        principal = self.registry.resolve_principal(str(fixture["approver_actor_id"]))
        if (
            principal.tenant_id != fixture["tenant_id"]
            or principal.role != fixture["approver_role"]
        ):
            raise WorkflowError("policy_fixture_principal_invalid")
        outcome = workflow.submit_approval_decision(
            principal.tenant_id,
            case_id,
            approval_request_id=str(request["approval_request_id"]),
            decision="approved",
            expected_workflow_version=int(projection["workflow_version"]),
            approver_id=principal.actor_id,
            approver_role=principal.role,
            fault_profile=fault_profile,
        )
        final_facts = workflow.policy_approval_facts_for_case(principal.tenant_id, case_id)
        if final_facts is None:
            raise WorkflowError("policy_fixture_facts_missing")
        delivery = final_facts.get("outbound_delivery")
        return {
            "report_type": "weflow-synthetic-policy-approval-delivery.v1",
            "fixture_id": fixture_id,
            "case_id": case_id,
            "workflow_id": final_facts["workflow_id"],
            "state": outcome.projection["state"],
            "workflow_version": outcome.projection["workflow_version"],
            "authorization_binding_sha256": (
                None
                if final_facts["authorization_binding"] is None
                else final_facts["authorization_binding"]["authorization_binding_sha256"]
            ),
            "approval_request_id": request["approval_request_id"],
            "approval_decision": None
            if final_facts["approval_decision"] is None
            else final_facts["approval_decision"]["decision"],
            "delivery_id": None if delivery is None else delivery.get("completion_id"),
            "delivery_recorded": False if delivery is None else delivery.get("delivery_recorded"),
            "source_counts": workflow.source_counts(principal.tenant_id),
            "fixture_local": True,
            "network_required": False,
            "credentials_required": False,
            "real_external_write": False,
            "customer_resolution": False,
        }
