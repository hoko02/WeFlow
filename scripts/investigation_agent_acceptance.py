"""Offline, deterministic Change 3 replay-investigation acceptance evidence."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from weflow_agent_runtime import run_investigation_replay
from weflow_business_simulator import SyntheticIntakeSimulator, SyntheticInvestigationSimulator
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

FIXTURE_ID = "api-503-investigation"
FIXTURE_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)
FAULT_POINTS = ("agent-action", "tool-result", "candidate", "verifier")


def _new_store(
    root: Path, path: Path
) -> tuple[SQLiteCaseLedger, SQLiteDurableWorkflow, FixtureClock]:
    clock = FixtureClock(FIXTURE_TIME)
    ledger = SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root)
    workflow = SQLiteDurableWorkflow(ledger, clock=clock, contract_root=root)
    return ledger, workflow, clock


def _ticket_ready_case(root: Path, ledger: SQLiteCaseLedger, workflow: SQLiteDurableWorkflow):
    accepted = SyntheticIntakeSimulator(root=root).submit_fixture(ledger, "api-503-first-delivery")
    projection = workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    if projection is None or projection["state"] != "TICKET_READY":
        raise RuntimeError("investigation_predecessor_not_ticket_ready")
    return accepted


def _safe_counts(counts: dict[str, object]) -> dict[str, int]:
    names = (
        "agent_steps",
        "investigation_tool_requests",
        "investigation_tool_results",
        "investigation_candidates",
        "investigation_verifier_outcomes",
    )
    return {name: int(counts[name]) for name in names}


def _baseline(root: Path, path: Path) -> dict[str, object]:
    ledger, workflow, _ = _new_store(root, path)
    report = SyntheticInvestigationSimulator(root=root).run_fixture(ledger, workflow, FIXTURE_ID)
    facts = workflow.investigation_facts_for_case("tenant-alpha", str(report["case_id"]))
    if facts is None or report["state"] != "RESPONSE_READY":
        raise RuntimeError("investigation_baseline_not_response_ready")
    evidence_hashes = [str(item["content_sha256"]) for item in facts["tool_evidence"]]
    if (
        report["terminal_outcome"] != "response_candidate"
        or report["verifier_outcome"] != "verified"
        or len(evidence_hashes) != 3
        or _safe_counts(report["source_counts"])
        != {
            "agent_steps": 4,
            "investigation_tool_requests": 3,
            "investigation_tool_results": 3,
            "investigation_candidates": 1,
            "investigation_verifier_outcomes": 1,
        }
    ):
        raise RuntimeError("investigation_baseline_evidence_invalid")
    workflow.validate_projection_agreement()
    return {
        "state": report["state"],
        "terminal_outcome": report["terminal_outcome"],
        "verifier_outcome": report["verifier_outcome"],
        "tool_evidence_count": report["tool_evidence_count"],
        "agent_step_count": report["agent_step_count"],
        "evidence_hashes": evidence_hashes,
        "source_counts": _safe_counts(report["source_counts"]),
    }


def _fault_recovery(root: Path, point: str, path: Path) -> dict[str, object]:
    ledger, workflow, clock = _new_store(root, path)
    accepted = _ticket_ready_case(root, ledger, workflow)
    try:
        run_investigation_replay(
            workflow,
            "tenant-alpha",
            accepted.case_id,
            fixture_id=FIXTURE_ID,
            root=root,
            fault_profile=FaultProfile.after(point),
        )
    except WorkflowInterrupted:
        pass
    else:
        raise RuntimeError("declared_investigation_fault_did_not_interrupt")
    restarted = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root),
        clock=clock,
        contract_root=root,
    )
    restarted.recover_all()
    report = run_investigation_replay(
        restarted,
        "tenant-alpha",
        accepted.case_id,
        fixture_id=FIXTURE_ID,
        root=root,
    )
    counts = _safe_counts(restarted.source_counts("tenant-alpha"))
    expected_counts = {
        "agent_steps": 4,
        "investigation_tool_requests": 3,
        "investigation_tool_results": 3,
        "investigation_candidates": 1,
        "investigation_verifier_outcomes": 1,
    }
    if report.get("state") != "RESPONSE_READY" or counts != expected_counts:
        raise RuntimeError("investigation_fault_recovery_duplicate_or_incomplete")
    restarted.validate_projection_agreement()
    return {
        "fault_point": point,
        "state": report["state"],
        "source_counts": counts,
        "duplicate_tool_result": False,
        "duplicate_response_ready_transition": False,
    }


def _assert_redacted(report: dict[str, object]) -> None:
    rendered = json.dumps(report, sort_keys=True)
    for forbidden in (
        "customer-api-503-alpha",
        "provider_token",
        "private prompt",
        "raw_message",
    ):
        if forbidden in rendered:
            raise RuntimeError("investigation_acceptance_report_not_redacted")


def run_investigation_benchmark_observation(
    root: Path,
    task: dict[str, object],
    fixture: dict[str, object],
    store_path: Path,
) -> BenchmarkObservation:
    """Return persisted investigation state and verifier/tool facts for one task."""

    if (
        fixture.get("fixture_id") != FIXTURE_ID
        or fixture.get("fixture_id") != task.get("fixture_source_id")
    ):
        raise RuntimeError("benchmark_investigation_fixture_identity_invalid")
    fault_point = task.get("fault_profile_id")
    if fault_point is None:
        observed = _baseline(root, store_path)
        tool_count = int(observed["tool_evidence_count"])
        evidence_valid = observed["verifier_outcome"] == "verified" and tool_count == 3
    elif fault_point == "candidate":
        observed = _fault_recovery(root, fault_point, store_path)
        counts = observed["source_counts"]
        tool_count = int(counts["investigation_tool_results"])
        evidence_valid = tool_count == 3 and observed["state"] == "RESPONSE_READY"
    else:
        raise RuntimeError("benchmark_investigation_fault_unsupported")
    state = str(observed["state"])
    return make_benchmark_observation(
        tenant_id="tenant-alpha",
        state=state,
        outcome=state.lower(),
        evidence_valid=evidence_valid,
        approval_valid=False,
        local_effect_count=0,
        tool_call_count=tool_count,
    )


def run_investigation_agent_acceptance(root: Path) -> dict[str, object]:
    """Run Change 3 local acceptance with no Docker, network, model, or credentials."""

    with TemporaryDirectory(prefix="weflow-change-3-") as temporary:
        temporary_root = Path(temporary)
        baseline_a = _baseline(root, temporary_root / "baseline-a.sqlite3")
        baseline_b = _baseline(root, temporary_root / "baseline-b.sqlite3")
        if baseline_a != baseline_b:
            raise RuntimeError("investigation_baseline_nondeterministic")
        fault_results = [
            _fault_recovery(root, point, temporary_root / f"fault-{point}.sqlite3")
            for point in FAULT_POINTS
        ]
    report = {
        "report_type": "weflow-change-3-investigation-agent-acceptance.v1",
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "fixture_outcomes": {
            "api_503_investigation": baseline_a,
            "fault_recovery": fault_results,
        },
        "determinism": {
            "repeated_baseline_equal": True,
            "intentional_nondeterministic_fields": [],
        },
        "environment_limits": {
            "docker_available": shutil.which("docker") is not None,
            "docker_required": False,
            "node_available": shutil.which("node") is not None,
            "node_required_for_core_acceptance": False,
            "node_required_for_typescript_and_console_checks": True,
        },
        "capabilities": {
            "replay_investigation_agent_implemented": True,
            "response_candidate_verification_implemented": True,
            "business_workflow_implemented": False,
            "real_provider_enabled": False,
            "multi_agent_enabled": False,
            "external_writes_enabled": False,
            "model_invocation": False,
            "approval": False,
            "outbound_delivery": False,
            "customer_resolution": False,
        },
    }
    _assert_redacted(report)
    return report