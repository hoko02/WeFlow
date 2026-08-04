"""Offline deterministic simulator for the bounded replay investigation fixture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from weflow_agent_runtime import (
    load_investigation_tool_fixture,
    load_investigation_transcript,
    run_investigation_replay,
)
from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    SQLiteDurableWorkflow,
    WorkflowInterrupted,
)
from weflow_control_kernel.ledger import SQLiteCaseLedger, SyntheticActorRegistry

from .intake import SyntheticIntakeSimulator

JsonObject = dict[str, Any]


def load_investigation_fixture(fixture_id: str, root: Path | None = None) -> JsonObject:
    """Return only safe fixture identity and declared replay limits for inspection."""

    transcript = load_investigation_transcript(fixture_id, root)
    tools = load_investigation_tool_fixture(fixture_id, root)
    return {
        "fixture_id": transcript["fixture_id"],
        "synthetic": transcript["synthetic"],
        "intake_fixture_id": transcript["intake_fixture_id"],
        "tenant_id": tools["tenant_id"],
        "actions": list(transcript["actions"]),
        "required_tools": list(transcript["required_tools"]),
        "action_budget": transcript["action_budget"],
        "tool_budget": transcript["tool_budget"],
        "no_progress_limit": transcript["no_progress_limit"],
    }


class SyntheticInvestigationSimulator:
    """Runs a named API-503 fixture through intake, durable control, and Replay Agent."""

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
        *,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject:
        fixture = load_investigation_fixture(fixture_id, self.root)
        inbound = self.intake.fixture_request(str(fixture["intake_fixture_id"]))
        tenant_id = self.registry.resolve(str(inbound["actor_id"]))
        if tenant_id != fixture["tenant_id"]:
            raise ValueError("investigation_fixture_tenant_mismatch")
        accepted = self.intake.submit_fixture(ledger, str(fixture["intake_fixture_id"]))
        projection = workflow.run_case(tenant_id, accepted.case_id, accepted.case_revision_id)
        if projection is None or projection["state"] != "TICKET_READY":
            raise ValueError("investigation_fixture_predecessor_invalid")
        result = run_investigation_replay(
            workflow,
            tenant_id,
            accepted.case_id,
            fixture_id=fixture_id,
            root=self.root,
            fault_profile=fault_profile,
        )
        facts = workflow.investigation_facts_for_case(tenant_id, accepted.case_id)
        inspection = workflow.export_investigation_inspection(tenant_id, accepted.case_id)
        return {
            "report_type": "weflow-synthetic-investigation-inspection.v1",
            "fixture_id": fixture_id,
            "case_id": accepted.case_id,
            "workflow_id": None if facts is None else facts["workflow_id"],
            "state": result.get("state"),
            "terminal_outcome": result["terminal_outcome"],
            "verifier_outcome": result.get("verifier_outcome"),
            "tool_evidence_count": 0 if facts is None else len(facts["tool_evidence"]),
            "agent_step_count": 0 if facts is None else len(facts["agent_steps"]),
            "inspection_sha256": None if inspection is None else inspection["content_sha256"],
            "source_counts": workflow.source_counts(tenant_id),
            "model_invocation": False,
            "external_write": False,
            "approval": False,
            "outbound_delivery": False,
            "customer_resolution": False,
        }

    def recover_fixture(
        self,
        workflow: SQLiteDurableWorkflow,
        tenant_id: str,
        case_id: str,
        fixture_id: str,
    ) -> JsonObject:
        """Resume a faulted replay from durable facts without repeating a fixture read."""

        try:
            return run_investigation_replay(
                workflow,
                tenant_id,
                case_id,
                fixture_id=fixture_id,
                root=self.root,
            )
        except WorkflowInterrupted as error:
            raise ValueError("investigation_fixture_recovery_interrupted") from error
