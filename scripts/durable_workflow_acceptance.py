"""Offline, deterministic Change 2 durable-workflow acceptance evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from weflow_business_simulator import SyntheticIntakeSimulator
from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    FixtureClock,
    SQLiteDurableWorkflow,
    WorkflowInterrupted,
)
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_testkit.benchmark_observation import (
    BenchmarkObservation,
    make_benchmark_observation,
)

FIXTURE_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)
FAULT_POINTS = (
    "activation",
    "checkpoint",
    "intent",
    "reconcile",
    "execute",
    "lost-response",
    "observation",
    "completion",
)


def _new_store(
    root: Path, path: Path
) -> tuple[SQLiteCaseLedger, SQLiteDurableWorkflow, FixtureClock]:
    clock = FixtureClock(FIXTURE_TIME)
    ledger = SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root)
    workflow = SQLiteDurableWorkflow(ledger, clock=clock, contract_root=root)
    return ledger, workflow, clock


def _accepted_case(root: Path, ledger: SQLiteCaseLedger):
    return SyntheticIntakeSimulator(root=root).submit_fixture(ledger, "api-503-first-delivery")


def _baseline(root: Path, path: Path) -> dict[str, object]:
    ledger, workflow, _ = _new_store(root, path)
    accepted = _accepted_case(root, ledger)
    projection = workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    if projection is None or projection["state"] != "TICKET_READY":
        raise RuntimeError("workflow_baseline_not_ticket_ready")
    workflow.validate_projection_agreement()
    return {
        "state": projection["state"],
        "workflow_id": projection["workflow_id"],
        "workflow_version": projection["workflow_version"],
        "checkpoint_sequence": projection["latest_checkpoint_sequence"],
        "source_counts": workflow.source_counts("tenant-alpha"),
        "reconciliation": workflow.ticket_reconciliation_summary(
            "tenant-alpha", str(projection["workflow_id"])
        ),
    }


def _fault_recovery(root: Path, point: str, path: Path) -> dict[str, object]:
    ledger, workflow, clock = _new_store(root, path)
    accepted = _accepted_case(root, ledger)
    try:
        workflow.run_case(
            "tenant-alpha",
            accepted.case_id,
            accepted.case_revision_id,
            fault_profile=FaultProfile.after(point),
        )
    except WorkflowInterrupted:
        pass
    else:
        raise RuntimeError("declared_fault_did_not_interrupt")
    restarted_ledger = SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root)
    restarted = SQLiteDurableWorkflow(restarted_ledger, clock=clock, contract_root=root)
    recovered = restarted.recover_all()[0]
    if recovered is None or recovered["state"] != "TICKET_READY":
        raise RuntimeError("fault_recovery_not_ticket_ready")
    reconciliation = restarted.ticket_reconciliation_summary(
        "tenant-alpha", str(recovered["workflow_id"])
    )
    if reconciliation["operation_count"] != 2:
        raise RuntimeError("fault_recovery_duplicate_ticket_operation")
    restarted.validate_projection_agreement()
    return {
        "fault_point": point,
        "state": recovered["state"],
        "operation_count": reconciliation["operation_count"],
        "checkpoint_sequence": recovered["latest_checkpoint_sequence"],
    }


def _sla_recovery(root: Path, path: Path) -> dict[str, object]:
    ledger, workflow, clock = _new_store(root, path)
    accepted = _accepted_case(root, ledger)
    policy = workflow.default_sla_policy("tenant-alpha", created_at="2026-07-29T00:00:00Z")
    policy["deadline_seconds"] = 1
    try:
        workflow.run_case(
            "tenant-alpha",
            accepted.case_id,
            accepted.case_revision_id,
            sla_policy=policy,
            fault_profile=FaultProfile.after("activation"),
        )
    except WorkflowInterrupted:
        pass
    clock.advance(seconds=2)
    restarted = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root),
        clock=clock,
        contract_root=root,
    )
    projection = restarted.recover_all()[0]
    if projection is None or projection["state"] != "WAITING_FOR_OPERATOR":
        raise RuntimeError("synthetic_sla_not_waiting_for_operator")
    counts = restarted.source_counts("tenant-alpha")
    if counts["workflow_sla_events"] != 1 or counts["fixture_ticket_operations"] != 0:
        raise RuntimeError("synthetic_sla_evidence_invalid")
    restarted.validate_projection_agreement()
    return {
        "state": projection["state"],
        "sla_event_count": counts["workflow_sla_events"],
        "ticket_operation_count": counts["fixture_ticket_operations"],
    }


def run_durable_workflow_benchmark_observation(
    root: Path,
    task: dict[str, object],
    fixture: dict[str, object],
    store_path: Path,
) -> BenchmarkObservation:
    """Return actual workflow projection and local operation facts for one task."""

    source_id = fixture.get("fixture_id")
    if source_id != task.get("fixture_source_id"):
        raise RuntimeError("benchmark_workflow_fixture_identity_invalid")
    if source_id == "ticket-handoff":
        observed = _baseline(root, store_path)
        effects = int(observed["reconciliation"]["operation_count"])
    elif source_id == "sla-expiry":
        observed = _sla_recovery(root, store_path)
        effects = int(observed["ticket_operation_count"])
    else:
        raise RuntimeError("benchmark_workflow_fixture_unsupported")
    state = str(observed["state"])
    return make_benchmark_observation(
        tenant_id="tenant-alpha",
        state=state,
        outcome=state.lower(),
        evidence_valid=True,
        approval_valid=False,
        local_effect_count=effects,
        tool_call_count=0,
    )


def run_durable_workflow_acceptance(root: Path) -> dict[str, object]:
    """Run the Change 2 local acceptance with no model, network, Docker, or credentials."""

    with TemporaryDirectory(prefix="weflow-change-2-") as temporary:
        temporary_root = Path(temporary)
        baseline_a = _baseline(root, temporary_root / "baseline-a.sqlite3")
        baseline_b = _baseline(root, temporary_root / "baseline-b.sqlite3")
        if baseline_a != baseline_b:
            raise RuntimeError("workflow_baseline_nondeterministic")
        fault_results = [
            _fault_recovery(root, point, temporary_root / f"fault-{point}.sqlite3")
            for point in FAULT_POINTS
        ]
        sla_result = _sla_recovery(root, temporary_root / "sla.sqlite3")
    return {
        "report_type": "weflow-change-2-durable-workflow-acceptance.v1",
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "fixture_outcomes": {
            "ticket_handoff": baseline_a,
            "fault_recovery": fault_results,
            "synthetic_sla": sla_result,
        },
        "determinism": {
            "repeated_baseline_equal": True,
            "intentional_nondeterministic_fields": [],
        },
        "capabilities": {
            "durable_support_workflow_implemented": True,
            "business_workflow_implemented": False,
            "external_writes_enabled": False,
            "model_invocation": False,
            "approval": False,
            "outbound_delivery": False,
            "customer_resolution": False,
        },
    }
