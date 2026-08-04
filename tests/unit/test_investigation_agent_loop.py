import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_agent_runtime import (
    load_investigation_tool_fixture,
    load_investigation_transcript,
    run_investigation_replay,
)
from weflow_business_simulator import SyntheticIntakeSimulator, SyntheticInvestigationSimulator
from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    FixtureClock,
    SQLiteDurableWorkflow,
    WorkflowError,
    WorkflowInterrupted,
)
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)


def make_stack(tmp_path: Path) -> tuple[SQLiteCaseLedger, SQLiteDurableWorkflow]:
    ledger = SQLiteCaseLedger(
        tmp_path / "investigation.sqlite3",
        clock=FixedClock(FIXED_TIME),
        contract_root=ROOT,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    return ledger, workflow


def ticket_ready_case(
    ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow
) -> tuple[str, str]:
    accepted = SyntheticIntakeSimulator(root=ROOT).submit_fixture(ledger, "api-503-first-delivery")
    projection = workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    assert projection is not None and projection["state"] == "TICKET_READY"
    return accepted.case_id, accepted.case_revision_id


def test_named_api_503_fixtures_are_hash_only_and_replay_to_response_ready(tmp_path: Path) -> None:
    transcript = load_investigation_transcript("api-503-investigation", ROOT)
    tools = load_investigation_tool_fixture("api-503-investigation", ROOT)
    rendered = json.dumps({"transcript": transcript, "tools": tools}, sort_keys=True)

    assert transcript["intake_fixture_id"] == "api-503-first-delivery"
    assert tuple(transcript["required_tools"]) == ("crm", "monitoring", "knowledge")
    assert "raw_" not in rendered
    assert "provider_token" not in rendered
    ledger, workflow = make_stack(tmp_path)
    report = SyntheticInvestigationSimulator(root=ROOT).run_fixture(
        ledger, workflow, "api-503-investigation"
    )

    assert report["state"] == "RESPONSE_READY"
    assert report["verifier_outcome"] == "verified"
    assert report["agent_step_count"] == 4
    assert report["tool_evidence_count"] == 3
    facts = workflow.investigation_facts_for_case("tenant-alpha", str(report["case_id"]))
    assert facts is not None
    assert [record["tool_name"] for record in facts["tool_evidence"]] == [
        "crm",
        "monitoring",
        "knowledge",
    ]
    projection = ledger.get_case_projection("tenant-alpha", str(report["case_id"]))
    assert projection is not None and projection["state"] == "RESPONSE_READY"


@pytest.mark.parametrize("fault_point", ["agent-action", "tool-result", "candidate", "verifier"])
def test_recovery_after_investigation_durable_boundaries_deduplicates_facts(
    tmp_path: Path,
    fault_point: str,
) -> None:
    path = tmp_path / f"investigation-{fault_point}.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=FixedClock(FIXED_TIME), contract_root=ROOT)
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    case_id, _ = ticket_ready_case(ledger, workflow)

    with pytest.raises(WorkflowInterrupted, match=f"fault_injected:{fault_point}"):
        run_investigation_replay(
            workflow,
            "tenant-alpha",
            case_id,
            root=ROOT,
            fault_profile=FaultProfile.after(fault_point),
        )

    restarted = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=FixedClock(FIXED_TIME), contract_root=ROOT),
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    restarted.recover_all()
    report = run_investigation_replay(restarted, "tenant-alpha", case_id, root=ROOT)
    counts = restarted.source_counts("tenant-alpha")

    assert report["state"] == "RESPONSE_READY"
    assert counts["agent_steps"] == 4
    assert counts["investigation_tool_requests"] == 3
    assert counts["investigation_tool_results"] == 3
    assert counts["investigation_candidates"] == 1
    assert counts["investigation_verifier_outcomes"] == 1
    restarted.validate_projection_agreement()


def test_agent_authority_claim_and_foreign_facts_fail_closed(tmp_path: Path) -> None:
    ledger, workflow = make_stack(tmp_path)
    case_id, _ = ticket_ready_case(ledger, workflow)
    transcript = load_investigation_transcript("api-503-investigation", ROOT)
    from weflow_agent_runtime import compile_context_manifest

    manifest = compile_context_manifest(workflow, "tenant-alpha", case_id, transcript)
    workflow.begin_investigation(
        "tenant-alpha", case_id, manifest, transcript_id="api-503-investigation"
    )
    malformed = {
        "schema_id": "https://weflow.local/contracts/v1/agent-action.schema.json",
        "schema_version": "v1",
        "tenant_id": "tenant-alpha",
        "case_id": case_id,
        "case_revision_id": manifest["case_revision_id"],
        "workflow_id": manifest["workflow_id"],
        "checkpoint_id": manifest["checkpoint_id"],
        "context_manifest_id": manifest["context_manifest_id"],
        "step_id": "step-authority",
        "action_type": "response_candidate",
        "action_sha256": "e" * 64,
        "created_at": manifest["created_at"],
        "target_state": "RESPONSE_READY",
    }

    with pytest.raises(WorkflowError, match="agent_action_invalid"):
        workflow.record_agent_action("tenant-alpha", case_id, malformed)

    assert workflow.investigation_facts_for_case("tenant-bravo", case_id) is None
    assert workflow.get_workflow_for_case("tenant-bravo", case_id) is None
    assert workflow.get_workflow_for_case("tenant-alpha", case_id)["state"] == "INVESTIGATING"


def test_no_progress_gate_returns_needs_operator_without_verifier_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger, workflow = make_stack(tmp_path)
    case_id, _ = ticket_ready_case(ledger, workflow)
    transcript = dict(load_investigation_transcript("api-503-investigation", ROOT))
    transcript["actions"] = ["read_crm", "read_crm", "needs_operator"]
    transcript["action_budget"] = 3
    transcript["tool_budget"] = 2
    transcript["no_progress_limit"] = 2
    import weflow_agent_runtime.investigation as investigation

    monkeypatch.setattr(investigation, "load_investigation_transcript", lambda *_: transcript)
    report = investigation.run_investigation_replay(
        workflow, "tenant-alpha", case_id, root=ROOT
    )

    assert report["terminal_outcome"] == "needs_operator"
    assert report["reason_code"] == "no_progress_limit_reached"
    assert workflow.get_workflow_for_case("tenant-alpha", case_id)["state"] == "INVESTIGATING"
    assert workflow.source_counts("tenant-alpha")["investigation_verifier_outcomes"] == 0


def test_gateway_and_provider_boundary_deny_foreign_tools_and_live_provider(tmp_path: Path) -> None:
    from weflow_agent_runtime import (
        FixtureInvestigationToolGateway,
        compile_context_manifest,
        load_investigation_tool_fixture,
    )
    from weflow_control_kernel.config import ConfigurationDenied

    ledger, workflow = make_stack(tmp_path)
    case_id, _ = ticket_ready_case(ledger, workflow)
    transcript = load_investigation_transcript("api-503-investigation", ROOT)
    manifest = compile_context_manifest(workflow, "tenant-alpha", case_id, transcript)
    gateway = FixtureInvestigationToolGateway(
        load_investigation_tool_fixture("api-503-investigation", ROOT),
        transcript["candidate"],
    )

    with pytest.raises(WorkflowError, match="investigation_tool_denied"):
        gateway.read(manifest, {"action_type": "write_crm"})
    foreign_manifest = {**manifest, "tenant_id": "tenant-bravo"}
    with pytest.raises(WorkflowError, match="investigation_tool_denied"):
        gateway.read(foreign_manifest, {"action_type": "read_crm"})
    with pytest.raises(ConfigurationDenied, match="replay_only"):
        run_investigation_replay(
            workflow,
            "tenant-alpha",
            case_id,
            root=ROOT,
            environment={"WEFLOW_PROVIDER_MODE": "live-provider"},
        )

    assert workflow.investigation_facts_for_case("tenant-alpha", case_id) is None
    assert workflow.get_workflow_for_case("tenant-alpha", case_id)["state"] == "TICKET_READY"


def test_unverified_candidate_stays_in_investigating_and_safe_snapshot_has_no_raw_content(
    tmp_path: Path,
) -> None:
    from weflow_agent_runtime import (
        FixtureInvestigationToolGateway,
        ReplayInvestigationAgent,
        compile_context_manifest,
    )

    ledger, workflow = make_stack(tmp_path)
    case_id, _ = ticket_ready_case(ledger, workflow)
    transcript = load_investigation_transcript("api-503-investigation", ROOT)
    manifest = compile_context_manifest(workflow, "tenant-alpha", case_id, transcript)
    workflow.begin_investigation(
        "tenant-alpha", case_id, manifest, transcript_id="api-503-investigation"
    )
    for action in ReplayInvestigationAgent(transcript).actions(manifest):
        workflow.record_agent_action("tenant-alpha", case_id, action)
    gateway = FixtureInvestigationToolGateway(
        load_investigation_tool_fixture("api-503-investigation", ROOT),
        transcript["candidate"],
    )
    candidate = gateway.candidate(manifest, ["f" * 64])
    workflow.record_response_candidate("tenant-alpha", case_id, candidate)
    outcome = workflow.verify_response_candidate(
        "tenant-alpha", case_id, str(candidate["candidate_id"])
    )
    snapshot = workflow.export_investigation_inspection("tenant-alpha", case_id)
    assert snapshot is not None

    assert outcome["outcome"] == "rejected"
    assert outcome["reason_code"] == "required_evidence_missing"
    assert workflow.get_workflow_for_case("tenant-alpha", case_id)["state"] == "INVESTIGATING"
    assert snapshot["inspection_schema_version"] == "weflow-investigation-inspection.v1"
    assert len(snapshot["agent_steps"]) == 4
    assert snapshot["response_candidate"] is not None
    assert snapshot["verifier_outcome"] is not None
    assert len(snapshot["content_sha256"]) == 64
    rendered = json.dumps(snapshot, sort_keys=True)
    for forbidden in ("customer-api-503-alpha", "provider_token", "private prompt", "raw_message"):
        assert forbidden not in rendered

def test_runtime_enforces_action_and_tool_budgets_outside_replay_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import weflow_agent_runtime.investigation as investigation

    action_directory = tmp_path / "action-budget"
    action_directory.mkdir()
    action_ledger, action_workflow = make_stack(action_directory)
    action_case_id, _ = ticket_ready_case(action_ledger, action_workflow)
    action_transcript = dict(load_investigation_transcript("api-503-investigation", ROOT))
    action_transcript.update(
        {
            "actions": ["read_crm", "needs_operator"],
            "action_budget": 1,
            "tool_budget": 1,
            "no_progress_limit": 3,
        }
    )
    monkeypatch.setattr(
        investigation,
        "load_investigation_transcript",
        lambda *_: action_transcript,
    )
    action_report = investigation.run_investigation_replay(
        action_workflow, "tenant-alpha", action_case_id, root=ROOT
    )

    assert action_report["terminal_outcome"] == "needs_operator"
    assert action_report["reason_code"] == "action_budget_exceeded"
    assert action_workflow.source_counts("tenant-alpha")["agent_steps"] == 1

    tool_directory = tmp_path / "tool-budget"
    tool_directory.mkdir()
    tool_ledger, tool_workflow = make_stack(tool_directory)
    tool_case_id, _ = ticket_ready_case(tool_ledger, tool_workflow)
    tool_transcript = dict(load_investigation_transcript("api-503-investigation", ROOT))
    tool_transcript.update(
        {
            "actions": ["read_crm", "read_monitoring", "needs_operator"],
            "action_budget": 3,
            "tool_budget": 1,
            "no_progress_limit": 3,
        }
    )
    monkeypatch.setattr(
        investigation,
        "load_investigation_transcript",
        lambda *_: tool_transcript,
    )
    tool_report = investigation.run_investigation_replay(
        tool_workflow, "tenant-alpha", tool_case_id, root=ROOT
    )

    assert tool_report["terminal_outcome"] == "needs_operator"
    assert tool_report["reason_code"] == "tool_budget_exceeded"
    assert tool_workflow.source_counts("tenant-alpha")["agent_steps"] == 2
    assert tool_workflow.source_counts("tenant-alpha")["investigation_tool_results"] == 1