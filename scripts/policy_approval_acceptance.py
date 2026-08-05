"""Offline deterministic Change 4 policy/approval/local-delivery acceptance evidence."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from weflow_agent_runtime import run_investigation_replay
from weflow_business_simulator import SyntheticIntakeSimulator, SyntheticPolicyApprovalSimulator
from weflow_contracts import approval_is_authorized
from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    FixtureClock,
    SQLiteDurableWorkflow,
    WorkflowInterrupted,
)
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.policy import API_503_POLICY_FIXTURE_ID, FIXTURE_APPROVER_ROLE
from weflow_testkit.benchmark_observation import (
    BenchmarkObservation,
    make_benchmark_observation,
)

FIXTURE_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)
FAULT_POINTS = (
    "policy",
    "approval-request",
    "approval-decision",
    "delivery-intent",
    "delivery-execute",
    "delivery-lost-response",
    "delivery-observation",
    "delivery-completion",
    "delivery-transition",
    "reconciliation-timeout",
)


JsonObject = dict[str, Any]


def _new_store(
    root: Path, path: Path
) -> tuple[SQLiteCaseLedger, SQLiteDurableWorkflow, FixtureClock]:
    clock = FixtureClock(FIXTURE_TIME)
    ledger = SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root)
    workflow = SQLiteDurableWorkflow(ledger, clock=clock, contract_root=root)
    return ledger, workflow, clock


def _safe_counts(counts: JsonObject) -> dict[str, int]:
    names = (
        "policy_approval_activations",
        "capability_grants",
        "capability_grant_status_events",
        "policy_decisions",
        "authorization_bindings",
        "approval_requests",
        "approval_decisions",
        "outbound_delivery_intents",
        "outbound_delivery_observations",
        "outbound_delivery_completions",
        "fixture_delivery_records",
        "fixture_delivery_operations",
    )
    return {name: int(counts[name]) for name in names}


def _response_ready_case(
    root: Path, ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow
) -> str:
    accepted = SyntheticIntakeSimulator(root=root).submit_fixture(ledger, "api-503-first-delivery")
    projection = workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    if projection is None or projection["state"] != "TICKET_READY":
        raise RuntimeError("policy_approval_predecessor_not_ticket_ready")
    report = run_investigation_replay(workflow, "tenant-alpha", accepted.case_id, root=root)
    if report.get("state") != "RESPONSE_READY":
        raise RuntimeError("policy_approval_predecessor_not_response_ready")
    return accepted.case_id


def _request_id_and_projection(
    workflow: SQLiteDurableWorkflow, case_id: str
) -> tuple[str, JsonObject]:
    facts = workflow.policy_approval_facts_for_case("tenant-alpha", case_id)
    projection = workflow.get_workflow_for_case("tenant-alpha", case_id)
    if facts is None or projection is None or facts.get("approval_request") is None:
        raise RuntimeError("policy_approval_request_missing")
    request = facts["approval_request"]
    if not isinstance(request, dict) or not isinstance(request.get("approval_request_id"), str):
        raise RuntimeError("policy_approval_request_invalid")
    return str(request["approval_request_id"]), projection


def _approve(
    workflow: SQLiteDurableWorkflow,
    case_id: str,
    *,
    fault_profile: FaultProfile | None = None,
) -> JsonObject:
    request_id, projection = _request_id_and_projection(workflow, case_id)
    return workflow.submit_approval_decision(
        "tenant-alpha",
        case_id,
        approval_request_id=request_id,
        decision="approved",
        expected_workflow_version=int(projection["workflow_version"]),
        approver_id="fixture-approver-alpha",
        approver_role=FIXTURE_APPROVER_ROLE,
        fault_profile=fault_profile,
    ).projection


def _assert_one_delivery(
    workflow: SQLiteDurableWorkflow, case_id: str
) -> tuple[JsonObject, dict[str, int]]:
    projection = workflow.get_workflow_for_case("tenant-alpha", case_id)
    counts = _safe_counts(workflow.source_counts("tenant-alpha"))
    if projection is None or projection["state"] != "DELIVERY_RECORDED":
        raise RuntimeError("policy_approval_recovery_not_delivery_recorded")
    expected = {
        "policy_approval_activations": 1,
        "capability_grants": 1,
        "capability_grant_status_events": 0,
        "policy_decisions": 1,
        "authorization_bindings": 1,
        "approval_requests": 1,
        "approval_decisions": 1,
        "outbound_delivery_intents": 1,
        "outbound_delivery_completions": 1,
        "fixture_delivery_records": 1,
        "fixture_delivery_operations": 1,
    }
    if any(counts[name] != value for name, value in expected.items()):
        raise RuntimeError("policy_approval_duplicate_or_incomplete_effect")
    if counts["outbound_delivery_observations"] < 1:
        raise RuntimeError("policy_approval_observation_missing")
    workflow.validate_projection_agreement()
    return projection, counts


def _baseline(root: Path, path: Path) -> JsonObject:
    ledger, workflow, _ = _new_store(root, path)
    report = SyntheticPolicyApprovalSimulator(root=root).run_fixture(
        ledger, workflow, API_503_POLICY_FIXTURE_ID
    )
    projection, counts = _assert_one_delivery(workflow, str(report["case_id"]))
    return {
        "fixture_id": report["fixture_id"],
        "state": projection["state"],
        "workflow_version": projection["workflow_version"],
        "source_counts": counts,
        "fixture_local": report["fixture_local"],
        "network_required": report["network_required"],
        "credentials_required": report["credentials_required"],
        "real_external_write": report["real_external_write"],
        "customer_resolution": report["customer_resolution"],
    }


def _fault_recovery(root: Path, point: str, path: Path) -> JsonObject:
    ledger, workflow, clock = _new_store(root, path)
    case_id = _response_ready_case(root, ledger, workflow)
    if point == "reconciliation-timeout":
        projection = workflow.activate_policy_approval("tenant-alpha", case_id)
        if projection["state"] != "AWAITING_APPROVAL":
            raise RuntimeError("reconciliation_timeout_predecessor_invalid")
        blocked = _approve(
            workflow, case_id, fault_profile=FaultProfile.named("reconciliation-timeout")
        )
        if blocked["state"] != "NEEDS_RECONCILIATION":
            raise RuntimeError("reconciliation_timeout_not_blocked")
    else:
        interrupted = False
        try:
            projection = workflow.activate_policy_approval(
                "tenant-alpha", case_id, fault_profile=FaultProfile.after(point)
            )
            if projection["state"] == "AWAITING_APPROVAL":
                _approve(workflow, case_id, fault_profile=FaultProfile.after(point))
        except WorkflowInterrupted:
            interrupted = True
        if not interrupted:
            raise RuntimeError("declared_policy_approval_fault_did_not_interrupt")

    restarted = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root),
        clock=clock,
        contract_root=root,
    )
    restarted.recover_all()
    projection = restarted.get_workflow_for_case("tenant-alpha", case_id)
    if projection is None:
        raise RuntimeError("policy_approval_recovery_projection_missing")
    if projection["state"] == "AWAITING_APPROVAL":
        _approve(restarted, case_id)
    restarted.recover_all()
    projection, counts = _assert_one_delivery(restarted, case_id)
    return {
        "fault_point": point,
        "state": projection["state"],
        "delivery_record_count": counts["fixture_delivery_records"],
        "delivery_operation_count": counts["fixture_delivery_operations"],
        "delivery_intent_count": counts["outbound_delivery_intents"],
        "delivery_completion_count": counts["outbound_delivery_completions"],
        "duplicate_delivery": False,
        "reconciliation_timeout": point == "reconciliation-timeout",
    }


def _authorization_denial(root: Path, path: Path) -> JsonObject:
    ledger, workflow, _ = _new_store(root, path)
    case_id = _response_ready_case(root, ledger, workflow)
    projection = workflow.activate_policy_approval("tenant-alpha", case_id)
    if projection["state"] != "AWAITING_APPROVAL":
        raise RuntimeError("policy_approval_denial_predecessor_invalid")
    workflow.revoke_fixture_grant("tenant-alpha", case_id)
    result = _approve(workflow, case_id)
    counts = _safe_counts(workflow.source_counts("tenant-alpha"))
    if result["state"] != "WAITING_FOR_OPERATOR" or counts["fixture_delivery_records"] != 0:
        raise RuntimeError("policy_approval_denial_not_safe")
    workflow.validate_projection_agreement()
    return {
        "state": result["state"],
        "reason_code": "authorization_denied_grant_revoked",
        "approval_decision_count": counts["approval_decisions"],
        "delivery_intent_count": counts["outbound_delivery_intents"],
        "delivery_record_count": counts["fixture_delivery_records"],
        "real_external_write": False,
        "customer_resolution": False,
    }


def _assert_redacted(report: JsonObject) -> None:
    rendered = json.dumps(report, sort_keys=True)
    for forbidden in (
        "customer-api-503-alpha",
        "provider_token",
        "private prompt",
        "raw_message",
        "fixture-controller-alpha",
    ):
        if forbidden in rendered:
            raise RuntimeError("policy_approval_acceptance_report_not_redacted")


def run_policy_approval_benchmark_observation(
    root: Path,
    task: JsonObject,
    fixture: JsonObject,
    store_path: Path,
) -> BenchmarkObservation:
    """Return actual authorization, approval and fixture-local delivery facts."""

    if fixture.get("fixture_id") != task.get("fixture_source_id"):
        raise RuntimeError("benchmark_policy_fixture_identity_invalid")
    fault_point = task.get("fault_profile_id")
    tool_count = 0
    if fault_point == "stale-approval":
        authorized = approval_is_authorized(
            fixture["request"],
            fixture["decision"],
            current_case_revision_id=str(fixture["current_case_revision_id"]),
            current_evidence_hashes=fixture["current_evidence_hashes"],
            now=FIXTURE_TIME,
        )
        state = "AWAITING_APPROVAL" if authorized else "APPROVAL_INVALIDATED"
        outcome = "fixture_delivery_recorded" if authorized else "authorization_denied"
        effects = 0
        approval_valid = not authorized
        evidence_valid = not authorized
    else:
        if fault_point is None:
            observed = _baseline(root, store_path)
        elif fault_point == "grant-revoked":
            observed = _authorization_denial(root, store_path)
        elif fault_point == "delivery-lost-response":
            observed = _fault_recovery(root, fault_point, store_path)
        else:
            raise RuntimeError("benchmark_policy_fault_unsupported")
        state = str(observed["state"])
        _ledger, inspection, _clock = _new_store(root, store_path)
        counts = inspection.source_counts("tenant-alpha")
        tool_count = int(counts["investigation_tool_results"])
        effects = int(counts["fixture_delivery_records"])
        approval_valid = int(counts["approval_decisions"]) == 1
        evidence_valid = True
        if fault_point == "grant-revoked":
            outcome = (
                "authorization_denied"
                if str(observed["reason_code"]).startswith("authorization_denied")
                and effects == 0
                else state.lower()
            )
        elif fault_point == "delivery-lost-response":
            outcome = (
                "recovered_after_interruption"
                if state == "DELIVERY_RECORDED"
                and observed.get("duplicate_delivery") is False
                else state.lower()
            )
        else:
            outcome = (
                "fixture_delivery_recorded"
                if state == "DELIVERY_RECORDED" and observed.get("fixture_local") is True
                else state.lower()
            )
    return make_benchmark_observation(
        tenant_id="tenant-alpha",
        state=state,
        outcome=outcome,
        evidence_valid=evidence_valid,
        approval_valid=approval_valid,
        local_effect_count=effects,
        tool_call_count=tool_count,
    )


def run_policy_approval_acceptance(root: Path) -> JsonObject:
    """Prove the Change 4 slice offline, deterministically, and without live writes."""

    with TemporaryDirectory(prefix="weflow-change-4-") as temporary:
        temporary_root = Path(temporary)
        baseline_a = _baseline(root, temporary_root / "baseline-a.sqlite3")
        baseline_b = _baseline(root, temporary_root / "baseline-b.sqlite3")
        if baseline_a != baseline_b:
            raise RuntimeError("policy_approval_baseline_nondeterministic")
        fault_results = [
            _fault_recovery(root, point, temporary_root / f"fault-{point}.sqlite3")
            for point in FAULT_POINTS
        ]
        denial = _authorization_denial(root, temporary_root / "authorization-denial.sqlite3")
    report: JsonObject = {
        "report_type": "weflow-change-4-policy-approval-acceptance.v1",
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "fixture_outcomes": {
            "api_503_policy_approval_delivery": baseline_a,
            "fault_recovery": fault_results,
            "authorization_denial": denial,
        },
        "determinism": {
            "repeated_baseline_equal": True,
            "intentional_nondeterministic_fields": [],
        },
        "environment_limits": {
            "docker_available": shutil.which("docker") is not None,
            "docker_required": False,
            "docker_service_boundary_verified": False,
            "node_available": shutil.which("node") is not None,
            "node_required_for_core_acceptance": False,
            "node_required_for_typescript_and_console_checks": True,
        },
        "capabilities": {
            "fixture_policy_approval_delivery_implemented": True,
            "fixture_approval_enabled": True,
            "fixture_outbound_delivery_enabled": True,
            "live_approval_enabled": False,
            "live_outbound_delivery_enabled": False,
            "business_workflow_implemented": False,
            "real_provider_enabled": False,
            "external_writes_enabled": False,
            "customer_resolution_enabled": False,
            "model_invocation": False,
        },
    }
    _assert_redacted(report)
    return report
