# ruff: noqa: E501
"""Machine-readable offline acceptance evidence for Change 5 trajectories and replay."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from weflow_business_simulator import SyntheticEvidenceTrajectorySimulator
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_testkit.benchmark_observation import (
    BenchmarkObservation,
    make_benchmark_observation,
)

JsonObject = dict[str, Any]
FIXTURE_TIME = datetime(2026, 8, 4, tzinfo=UTC)


def _new_store(root: Path, path: Path) -> tuple[SQLiteCaseLedger, SQLiteDurableWorkflow]:
    ledger = SQLiteCaseLedger(path, clock=FixedClock(FIXTURE_TIME), contract_root=root)
    workflow = SQLiteDurableWorkflow(ledger, clock=FixtureClock(FIXTURE_TIME), contract_root=root)
    return ledger, workflow


def _replay(workflow: SQLiteDurableWorkflow, result: JsonObject) -> JsonObject:
    replay = workflow.replay_evidence_trajectory("tenant-alpha", str(result["trajectory_id"]))
    replay_result = replay.get("replay_result")
    if (
        not isinstance(replay_result, dict)
        or replay_result.get("verification_outcome") != "verified"
    ):
        raise RuntimeError("evidence_trajectory_replay_not_verified")
    return {
        "outcome": result["outcome"],
        "failure_code": result["failure_code"],
        "trajectory_root_sha256": result["trajectory_root_sha256"],
        "node_count": result["node_count"],
        "replayed_root_sha256": replay_result["replayed_root_sha256"],
        "verification_outcome": replay_result["verification_outcome"],
        "network_required": False,
        "model_invocation": False,
        "external_write": False,
        "customer_resolution": False,
    }


def _authorized(root: Path, path: Path) -> JsonObject:
    ledger, workflow = _new_store(root, path)
    scenario = SyntheticEvidenceTrajectorySimulator(root=root)
    result = scenario.authorized(ledger, workflow)
    repeated = workflow.extract_evidence_trajectory("tenant-alpha", str(result["case_id"]))
    if repeated.get("idempotent") is not True:
        raise RuntimeError("evidence_report_not_idempotent")
    return _replay(workflow, result)


def _denial(root: Path, path: Path) -> JsonObject:
    ledger, workflow = _new_store(root, path)
    result = SyntheticEvidenceTrajectorySimulator(root=root).authorization_denied(ledger, workflow)
    report = _replay(workflow, result)
    if report["outcome"] != "authorization_denied":
        raise RuntimeError("evidence_authorization_denial_not_classified")
    return report


def _recovery(root: Path, path: Path) -> JsonObject:
    ledger, workflow = _new_store(root, path)
    result = SyntheticEvidenceTrajectorySimulator(root=root).interrupted_recovery(ledger, workflow)
    report = _replay(workflow, result)
    if report["outcome"] != "recovered_after_interruption":
        raise RuntimeError("evidence_recovery_not_classified")
    return report


def _tampered(root: Path, path: Path) -> JsonObject:
    ledger, workflow = _new_store(root, path)
    result = SyntheticEvidenceTrajectorySimulator(root=root).authorized(ledger, workflow)
    trajectory_id = str(result["trajectory_id"])
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER evidence_trajectories_no_update")
        row = connection.execute(
            "SELECT payload_json FROM evidence_trajectories WHERE tenant_id = ? AND trajectory_id = ?",
            ("tenant-alpha", trajectory_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("evidence_tamper_predecessor_missing")
        payload = json.loads(str(row[0]))
        payload["root_sha256"] = "f" * 64
        connection.execute(
            "UPDATE evidence_trajectories SET root_sha256 = ?, payload_json = ? WHERE tenant_id = ? AND trajectory_id = ?",
            (
                "f" * 64,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                "tenant-alpha",
                trajectory_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    replay = workflow.replay_evidence_trajectory("tenant-alpha", trajectory_id)
    if replay.get("outcome") != "lineage_invalid":
        raise RuntimeError("evidence_tamper_not_denied")
    return replay


def _assert_redacted(report: JsonObject) -> None:
    rendered = json.dumps(report, sort_keys=True)
    for forbidden in (
        "customer-api-503-alpha",
        "provider_token",
        "private prompt",
        "raw_message",
        "fixture-controller-alpha",
        "customer_resolved",
    ):
        if forbidden in rendered:
            raise RuntimeError("evidence_acceptance_report_not_redacted")


def run_evidence_trajectory_benchmark_observation(
    root: Path,
    task: JsonObject,
    fixture: JsonObject,
    store_path: Path,
) -> BenchmarkObservation:
    """Return the actual verification-only replay outcome for a tampered trajectory."""

    if (
        fixture.get("fixture_id") != task.get("fixture_source_id")
        or fixture.get("fault_profile_id") != task.get("fault_profile_id")
    ):
        raise RuntimeError("benchmark_evidence_fixture_identity_invalid")
    if task.get("fault_profile_id") != "tampered-lineage":
        raise RuntimeError("benchmark_evidence_fault_unsupported")
    observed = _tampered(root, store_path)
    outcome = str(observed["outcome"])
    evidence_valid = outcome == "lineage_invalid"
    state = "TRAJECTORY_REPLAY_REJECTED" if evidence_valid else "TRAJECTORY_REPLAY_VERIFIED"
    return make_benchmark_observation(
        tenant_id="tenant-alpha",
        state=state,
        outcome=outcome,
        evidence_valid=evidence_valid,
        approval_valid=False,
        local_effect_count=0,
        tool_call_count=0,
    )


def run_evidence_trajectory_acceptance(
    root: Path, *, configuration: dict[str, object] | None = None
) -> JsonObject:
    """Run only the checked-in, offline evidence/replay vertical slice."""

    if configuration not in (None, {}, {"mode": "offline"}):
        raise RuntimeError("offline_evidence_configuration_denied")
    with TemporaryDirectory(prefix="weflow-change-5-") as temporary:
        temporary_root = Path(temporary)
        baseline_a = _authorized(root, temporary_root / "baseline-a.sqlite3")
        baseline_b = _authorized(root, temporary_root / "baseline-b.sqlite3")
        if baseline_a != baseline_b:
            raise RuntimeError("evidence_trajectory_baseline_nondeterministic")
        denial = _denial(root, temporary_root / "authorization-denial.sqlite3")
        recovery = _recovery(root, temporary_root / "recovery.sqlite3")
        tamper = _tampered(root, temporary_root / "tamper.sqlite3")
    report: JsonObject = {
        "report_type": "weflow-change-5-evidence-trajectory-acceptance.v1",
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "fixture_outcomes": {
            "authorized": baseline_a,
            "authorization_denial": denial,
            "interrupted_recovery": recovery,
            "tampered_lineage": tamper,
        },
        "determinism": {"repeated_baseline_equal": True, "intentional_nondeterministic_fields": []},
        "environment_limits": {
            "docker_available": shutil.which("docker") is not None,
            "docker_required": False,
            "node_available": shutil.which("node") is not None,
            "node_required_for_core_acceptance": False,
            "network_allowed": False,
        },
        "capabilities": {
            "fixture_evidence_trajectory_replay_implemented": True,
            "live_trace_exporter_enabled": False,
            "real_provider_enabled": False,
            "external_writes_enabled": False,
            "model_invocation": False,
            "customer_resolution_enabled": False,
            "multi_agent_enabled": False,
        },
    }
    _assert_redacted(report)
    return report
