# ruff: noqa: E501
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_business_simulator.policy_approval import SyntheticPolicyApprovalSimulator
from weflow_control_kernel.durable_workflow import SQLiteDurableWorkflow
from weflow_control_kernel.ledger import SQLiteCaseLedger

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_TIME = datetime(2026, 8, 4, tzinfo=UTC)


def _new_fixture(path: Path) -> tuple[SQLiteDurableWorkflow, str]:
    def clock() -> datetime:
        return FIXTURE_TIME

    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=ROOT)
    workflow = SQLiteDurableWorkflow(ledger, clock=clock, contract_root=ROOT)
    run = SyntheticPolicyApprovalSimulator(root=ROOT).run_fixture(ledger, workflow)
    return workflow, str(run["case_id"])


def _control_counts(workflow: SQLiteDurableWorkflow) -> dict[str, int]:
    counts = workflow.source_counts("tenant-alpha")
    return {
        name: counts[name]
        for name in (
            "workflow_activations",
            "workflow_runs",
            "workflow_checkpoints",
            "policy_approval_activations",
            "capability_grants",
            "approval_requests",
            "approval_decisions",
            "outbound_delivery_intents",
            "outbound_delivery_completions",
            "fixture_delivery_records",
        )
    }


def test_evidence_extraction_is_idempotent_and_does_not_mutate_control(tmp_path: Path) -> None:
    workflow, case_id = _new_fixture(tmp_path / "evidence.sqlite3")
    before = _control_counts(workflow)
    projection = workflow.get_workflow_for_case("tenant-alpha", case_id)
    assert projection is not None

    first = workflow.extract_evidence_trajectory("tenant-alpha", case_id)
    second = workflow.extract_evidence_trajectory("tenant-alpha", case_id)

    assert first["report"]["outcome"] == "fixture_delivery_recorded"
    assert first["report"]["node_count"] >= 20
    assert {
        "accepted_intake",
        "case_revision",
        "case_event",
        "workflow_activation",
        "workflow_checkpoint",
        "context_manifest",
        "agent_step",
        "tool_request",
        "tool_result",
        "evidence",
        "response_candidate",
        "verifier_outcome",
        "policy_activation",
        "capability_grant",
        "policy_decision",
        "authorization_binding",
        "approval_request",
        "approval_decision",
        "delivery_intent",
        "delivery_completion",
    } <= {node["source_kind"] for node in first["trajectory"]["nodes"]}
    assert second["idempotent"] is True
    assert second["report"] == first["report"]
    assert _control_counts(workflow) == before
    latest = workflow.get_workflow_for_case("tenant-alpha", case_id)
    assert latest == projection
    assert workflow.evidence_report_for_case("tenant-alpha", case_id) == first["report"]
    assert workflow.evidence_report_for_case("tenant-other", case_id) is None
    connection = sqlite3.connect(tmp_path / "evidence.sqlite3")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append_only_violation"):
            connection.execute("UPDATE evidence_reports SET report_id = report_id")
    finally:
        connection.close()


def test_evidence_replay_is_deterministic_and_redacted(tmp_path: Path) -> None:
    workflow, case_id = _new_fixture(tmp_path / "replay.sqlite3")
    extracted = workflow.extract_evidence_trajectory("tenant-alpha", case_id)
    before = _control_counts(workflow)
    trajectory_id = str(extracted["trajectory"]["trajectory_id"])

    first = workflow.replay_evidence_trajectory("tenant-alpha", trajectory_id)
    second = workflow.replay_evidence_trajectory("tenant-alpha", trajectory_id)

    assert first["replay_result"] == second["replay_result"]
    assert first["replay_result"]["verification_outcome"] == "verified"
    assert (
        first["replay_result"]["recorded_root_sha256"]
        == first["replay_result"]["replayed_root_sha256"]
    )
    assert _control_counts(workflow) == before
    rendered = json.dumps(first, sort_keys=True)
    for forbidden in ("customer-api-503-alpha", "provider_token", "raw_message", "private prompt"):
        assert forbidden not in rendered


def test_tampered_manifest_fails_closed_without_workflow_mutation(tmp_path: Path) -> None:
    workflow, case_id = _new_fixture(tmp_path / "tamper.sqlite3")
    extracted = workflow.extract_evidence_trajectory("tenant-alpha", case_id)
    trajectory_id = str(extracted["trajectory"]["trajectory_id"])
    before = _control_counts(workflow)
    connection = sqlite3.connect(tmp_path / "tamper.sqlite3")
    try:
        connection.execute("DROP TRIGGER evidence_trajectories_no_update")
        payload = dict(extracted["trajectory"])
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

    assert replay["outcome"] == "lineage_invalid"
    assert replay["failure_code"] == "lineage_invalid"
    assert _control_counts(workflow) == before
