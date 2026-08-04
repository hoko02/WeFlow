# ruff: noqa: E501
"""Fixture-local evidence trajectory scenarios for the Change 5 acceptance runner."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    SQLiteDurableWorkflow,
    WorkflowInterrupted,
)
from weflow_control_kernel.ledger import SQLiteCaseLedger, SyntheticActorRegistry

from .policy_approval import SyntheticPolicyApprovalSimulator

JsonObject = dict[str, Any]


class SyntheticEvidenceTrajectorySimulator:
    """Derive only the three named safe evidence outcomes from the existing fixture."""

    def __init__(
        self, registry: SyntheticActorRegistry | None = None, *, root: Path | None = None
    ) -> None:
        self.registry = registry or SyntheticActorRegistry.default()
        self.root = root
        self.policy = SyntheticPolicyApprovalSimulator(self.registry, root=root)

    def authorized(self, ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow) -> JsonObject:
        source = self.policy.run_fixture(ledger, workflow)
        evidence = workflow.extract_evidence_trajectory("tenant-alpha", str(source["case_id"]))
        return self._result(source, evidence)

    def authorization_denied(
        self, ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow
    ) -> JsonObject:
        investigation = self.policy.investigation.run_fixture(
            ledger, workflow, "api-503-investigation"
        )
        case_id = str(investigation["case_id"])
        projection = workflow.activate_policy_approval("tenant-alpha", case_id)
        workflow.revoke_fixture_grant("tenant-alpha", case_id)
        facts = workflow.policy_approval_facts_for_case("tenant-alpha", case_id)
        if facts is None or not isinstance(facts.get("approval_request"), Mapping):
            raise RuntimeError("evidence_denial_request_missing")
        principal = self.registry.resolve_principal("fixture-approver-alpha")
        workflow.submit_approval_decision(
            principal.tenant_id,
            case_id,
            approval_request_id=str(facts["approval_request"]["approval_request_id"]),
            decision="approved",
            expected_workflow_version=int(projection["workflow_version"]),
            approver_id=principal.actor_id,
            approver_role=principal.role,
        )
        evidence = workflow.extract_evidence_trajectory("tenant-alpha", case_id)
        return self._result(
            {"fixture_id": "api-503-policy-approval-delivery", "case_id": case_id}, evidence
        )

    def interrupted_recovery(
        self, ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow
    ) -> JsonObject:
        try:
            self.policy.run_fixture(
                ledger, workflow, fault_profile=FaultProfile.after("delivery-lost-response")
            )
        except WorkflowInterrupted:
            pass
        workflow.recover_all()
        connection = workflow._connect()
        try:
            rows = connection.execute(
                "SELECT case_id FROM workflow_activations WHERE tenant_id = ? ORDER BY case_id",
                ("tenant-alpha",),
            ).fetchall()
        finally:
            connection.close()
        if len(rows) != 1:
            raise RuntimeError("evidence_recovery_case_missing")
        case_id = str(rows[0]["case_id"])
        evidence = workflow.extract_evidence_trajectory(
            "tenant-alpha", case_id, requested_outcome="recovered_after_interruption"
        )
        return self._result(
            {"fixture_id": "api-503-policy-approval-delivery", "case_id": case_id}, evidence
        )

    @staticmethod
    def _result(source: Mapping[str, Any], evidence: Mapping[str, Any]) -> JsonObject:
        report = evidence.get("report")
        trajectory = evidence.get("trajectory")
        if not isinstance(report, Mapping) or not isinstance(trajectory, Mapping):
            raise RuntimeError("evidence_fixture_lineage_invalid")
        return {
            "fixture_id": source["fixture_id"],
            "case_id": source["case_id"],
            "trajectory_id": trajectory["trajectory_id"],
            "trajectory_root_sha256": trajectory["root_sha256"],
            "outcome": report["outcome"],
            "failure_code": report["failure_code"],
            "node_count": report["node_count"],
            "network_required": False,
            "model_invocation": False,
            "external_write": False,
            "customer_resolution": False,
        }
