import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weflow_agent_runtime import run_investigation_replay
from weflow_business_simulator import (
    SyntheticIntakeSimulator,
    SyntheticPolicyApprovalSimulator,
    load_policy_approval_fixture,
)
from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    FixtureClock,
    SQLiteDurableWorkflow,
    WorkflowError,
    WorkflowNotFound,
)
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_control_kernel.policy import (
    API_503_DELIVERY_RESOURCE_ID,
    FIXTURE_APPROVER_ROLE,
    FIXTURE_CONTROLLER_ROLE,
    evaluate_fixture_policy,
    issue_fixture_grant,
)

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)


def make_stack(tmp_path: Path) -> tuple[SQLiteCaseLedger, SQLiteDurableWorkflow]:
    ledger = SQLiteCaseLedger(
        tmp_path / "policy-approval.sqlite3",
        clock=FixedClock(FIXED_TIME),
        contract_root=ROOT,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    return ledger, workflow


def response_ready_case(
    ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow
) -> tuple[str, str]:
    accepted = SyntheticIntakeSimulator(root=ROOT).submit_fixture(ledger, "api-503-first-delivery")
    workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    replay = run_investigation_replay(workflow, "tenant-alpha", accepted.case_id, root=ROOT)
    assert replay["state"] == "RESPONSE_READY"
    return accepted.case_id, accepted.case_revision_id


def awaiting_approval(
    ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow
) -> tuple[str, dict[str, object], dict[str, object]]:
    case_id, _ = response_ready_case(ledger, workflow)
    projection = workflow.activate_policy_approval("tenant-alpha", case_id)
    facts = workflow.policy_approval_facts_for_case("tenant-alpha", case_id)
    assert projection["state"] == "AWAITING_APPROVAL"
    assert facts is not None and facts["approval_request"] is not None
    return case_id, projection, facts


def approve(
    workflow: SQLiteDurableWorkflow,
    case_id: str,
    projection: dict[str, object],
    facts: dict[str, object],
) -> object:
    request = facts["approval_request"]
    assert isinstance(request, dict)
    return workflow.submit_approval_decision(
        "tenant-alpha",
        case_id,
        approval_request_id=str(request["approval_request_id"]),
        decision="approved",
        expected_workflow_version=int(projection["workflow_version"]),
        approver_id="fixture-approver-alpha",
        approver_role=FIXTURE_APPROVER_ROLE,
    )


def test_named_api_503_policy_fixture_runs_only_the_local_control_slice(tmp_path: Path) -> None:
    fixture = load_policy_approval_fixture("api-503-policy-approval-delivery", ROOT)
    rendered = json.dumps(fixture, sort_keys=True)
    assert fixture["network_required"] is False
    assert fixture["credentials_required"] is False
    assert fixture["customer_resolution"] is False
    for forbidden in ("raw_", "customer-api-503-alpha", "provider_token", "prompt"):
        assert forbidden not in rendered

    ledger, workflow = make_stack(tmp_path)
    report = SyntheticPolicyApprovalSimulator(root=ROOT).run_fixture(ledger, workflow)

    assert report["state"] == "DELIVERY_RECORDED"
    assert report["fixture_local"] is True
    assert report["network_required"] is False
    assert report["credentials_required"] is False
    assert report["real_external_write"] is False
    assert report["customer_resolution"] is False
    assert report["delivery_recorded"] is True
    assert report["source_counts"]["fixture_delivery_records"] == 1
    workflow.validate_projection_agreement()


def test_response_ready_remains_inert_until_explicit_change_four_activation(tmp_path: Path) -> None:
    ledger, workflow = make_stack(tmp_path)
    case_id, _ = response_ready_case(ledger, workflow)

    workflow.recover_all()
    projection = workflow.get_workflow_for_case("tenant-alpha", case_id)
    counts = workflow.source_counts("tenant-alpha")

    assert projection is not None and projection["state"] == "RESPONSE_READY"
    assert workflow.policy_approval_facts_for_case("tenant-alpha", case_id) is None
    for table in (
        "policy_approval_activations",
        "capability_grants",
        "policy_decisions",
        "authorization_bindings",
        "approval_requests",
        "approval_decisions",
        "outbound_delivery_intents",
        "fixture_delivery_records",
    ):
        assert counts[table] == 0


def test_policy_evaluator_is_default_deny_for_scope_role_expiry_and_classification() -> None:
    grant = issue_fixture_grant(
        tenant_id="tenant-alpha",
        subject_id="fixture-controller-alpha",
        role=FIXTURE_CONTROLLER_ROLE,
        now=FIXED_TIME,
    )
    material = {
        "tenant_id": "tenant-alpha",
        "subject_id": "fixture-controller-alpha",
        "role": FIXTURE_CONTROLLER_ROLE,
        "action": "outbound_delivery.execute",
        "case_id": "case-safe",
        "case_revision_id": "case_revision-safe",
        "workflow_id": "workflow-safe",
        "checkpoint_id": "checkpoint-safe",
        "workflow_version": 7,
        "candidate_hash": "a" * 64,
        "evidence_hashes": ["b" * 64],
        "grant": grant,
        "resource_id": API_503_DELIVERY_RESOURCE_ID,
        "data_classification": "synthetic",
        "remaining_budget": 1,
        "now": FIXED_TIME,
    }
    allowed = evaluate_fixture_policy(**material)
    assert allowed["decision"] == "allow"

    denied = [
        evaluate_fixture_policy(**{**material, "grant": None}),
        evaluate_fixture_policy(**{**material, "tenant_id": "tenant-bravo"}),
        evaluate_fixture_policy(
            **{
                **material,
                "subject_id": "fixture-approver-alpha",
                "role": FIXTURE_APPROVER_ROLE,
                "grant": issue_fixture_grant(
                    tenant_id="tenant-alpha",
                    subject_id="fixture-approver-alpha",
                    role=FIXTURE_APPROVER_ROLE,
                    now=FIXED_TIME,
                ),
            }
        ),
        evaluate_fixture_policy(**{**material, "data_classification": "secret"}),
        evaluate_fixture_policy(**{**material, "remaining_budget": 0}),
        evaluate_fixture_policy(
            **{
                **material,
                "grant": issue_fixture_grant(
                    tenant_id="tenant-alpha",
                    subject_id="fixture-controller-alpha",
                    role=FIXTURE_CONTROLLER_ROLE,
                    now=FIXED_TIME,
                    expires_at=FIXED_TIME - timedelta(seconds=1),
                ),
            }
        ),
        evaluate_fixture_policy(**{**material, "grant": {**grant, "expires_at": "invalid"}}),
    ]
    assert all(decision["decision"] == "deny" for decision in denied)
    assert {decision["reason_code"] for decision in denied} >= {
        "policy_grant_missing",
        "policy_identity_or_causation_denied",
        "policy_role_denied",
        "policy_classification_denied",
        "policy_budget_denied",
        "policy_grant_expired",
        "policy_grant_invalid",
    }


def test_approval_is_role_bound_idempotent_and_conflicts_fail_closed(tmp_path: Path) -> None:
    ledger, workflow = make_stack(tmp_path)
    case_id, projection, facts = awaiting_approval(ledger, workflow)
    request = facts["approval_request"]
    assert isinstance(request, dict)

    accepted = approve(workflow, case_id, projection, facts)
    duplicate = workflow.submit_approval_decision(
        "tenant-alpha",
        case_id,
        approval_request_id=str(request["approval_request_id"]),
        decision="approved",
        expected_workflow_version=int(projection["workflow_version"]),
        approver_id="fixture-approver-alpha",
        approver_role=FIXTURE_APPROVER_ROLE,
    )

    assert accepted.disposition == "accepted"
    assert accepted.projection["state"] == "DELIVERY_RECORDED"
    assert duplicate.disposition == "deduplicated"
    assert duplicate.projection["state"] == "DELIVERY_RECORDED"
    counts = workflow.source_counts("tenant-alpha")
    assert counts["approval_decisions"] == 1
    assert counts["outbound_delivery_intents"] == 1
    assert counts["fixture_delivery_records"] == 1

    with pytest.raises(WorkflowError, match="approval_decision_conflict"):
        workflow.submit_approval_decision(
            "tenant-alpha",
            case_id,
            approval_request_id=str(request["approval_request_id"]),
            decision="rejected",
            expected_workflow_version=int(projection["workflow_version"]),
            approver_id="fixture-approver-alpha",
            approver_role=FIXTURE_APPROVER_ROLE,
        )
    assert workflow.source_counts("tenant-alpha")["fixture_delivery_records"] == 1


def test_wrong_role_foreign_tenant_rejection_and_revocation_do_not_deliver(tmp_path: Path) -> None:
    ledger, workflow = make_stack(tmp_path)
    case_id, projection, facts = awaiting_approval(ledger, workflow)
    request = facts["approval_request"]
    assert isinstance(request, dict)

    with pytest.raises(WorkflowError, match="approval_actor_not_authorized"):
        workflow.submit_approval_decision(
            "tenant-alpha",
            case_id,
            approval_request_id=str(request["approval_request_id"]),
            decision="approved",
            expected_workflow_version=int(projection["workflow_version"]),
            approver_id="fixture-observer-alpha",
            approver_role="fixture-observer",
        )
    with pytest.raises(WorkflowNotFound, match="workflow_not_found"):
        workflow.submit_approval_decision(
            "tenant-bravo",
            case_id,
            approval_request_id=str(request["approval_request_id"]),
            decision="approved",
            expected_workflow_version=int(projection["workflow_version"]),
            approver_id="fixture-approver-bravo",
            approver_role=FIXTURE_APPROVER_ROLE,
        )

    workflow.revoke_fixture_grant("tenant-alpha", case_id)
    result = approve(workflow, case_id, projection, facts)
    counts = workflow.source_counts("tenant-alpha")

    assert result.projection["state"] == "WAITING_FOR_OPERATOR"
    assert counts["approval_decisions"] == 1
    assert counts["outbound_delivery_intents"] == 0
    assert counts["fixture_delivery_records"] == 0
    facts_after = workflow.policy_approval_facts_for_case("tenant-alpha", case_id)
    assert facts_after is not None
    assert facts_after["capability_grant"]["status"] == "revoked"
    workflow.validate_projection_agreement()


def test_change_four_journal_records_are_append_only(tmp_path: Path) -> None:
    ledger, workflow = make_stack(tmp_path)
    case_id, projection, facts = awaiting_approval(ledger, workflow)
    approve(workflow, case_id, projection, facts)

    connection = sqlite3.connect(ledger.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            connection.execute("UPDATE approval_decisions SET decision = 'rejected'")
    finally:
        connection.close()
    workflow.validate_projection_agreement()


def test_registry_derives_only_server_owned_fixture_principals() -> None:
    registry = SyntheticActorRegistry.default()
    approver = registry.resolve_principal("fixture-approver-alpha")
    operator = registry.resolve_principal("simulator-tenant-a")
    assert (approver.tenant_id, approver.role) == ("tenant-alpha", FIXTURE_APPROVER_ROLE)
    assert (operator.tenant_id, operator.role) == ("tenant-alpha", "fixture-operator")


def test_unknown_delivery_reconciles_without_blind_resend_or_cancel_bypass(tmp_path: Path) -> None:
    ledger, workflow = make_stack(tmp_path)
    case_id, projection, facts = awaiting_approval(ledger, workflow)
    request = facts["approval_request"]
    assert isinstance(request, dict)

    blocked = workflow.submit_approval_decision(
        "tenant-alpha",
        case_id,
        approval_request_id=str(request["approval_request_id"]),
        decision="approved",
        expected_workflow_version=int(projection["workflow_version"]),
        approver_id="fixture-approver-alpha",
        approver_role=FIXTURE_APPROVER_ROLE,
        fault_profile=FaultProfile.named("reconciliation-timeout"),
    )
    counts_before = workflow.source_counts("tenant-alpha")
    assert blocked.projection["state"] == "NEEDS_RECONCILIATION"
    assert counts_before["outbound_delivery_intents"] == 1
    assert counts_before["fixture_delivery_records"] == 0

    cancel = workflow.submit_command(
        "tenant-alpha",
        case_id,
        command_id="cancel-pending-delivery",
        command_type="cancel",
        expected_workflow_version=int(blocked.projection["workflow_version"]),
    )
    assert cancel.disposition == "requires_reconciliation"
    assert cancel.projection["state"] == "NEEDS_RECONCILIATION"
    assert workflow.source_counts("tenant-alpha")["fixture_delivery_records"] == 0

    workflow.recover_all()
    recovered = workflow.get_workflow_for_case("tenant-alpha", case_id)
    counts_after = workflow.source_counts("tenant-alpha")
    assert recovered is not None and recovered["state"] == "DELIVERY_RECORDED"
    assert counts_after["fixture_delivery_records"] == 1
    assert counts_after["fixture_delivery_operations"] == 1
    workflow.validate_projection_agreement()
