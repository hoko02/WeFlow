import copy
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    FixtureClock,
    SQLiteDurableWorkflow,
    WorkflowError,
    WorkflowInterrupted,
    WorkflowNotFound,
)
from weflow_control_kernel.ledger import FixedClock, LedgerIntegrityError, SQLiteCaseLedger

ROOT = Path(__file__).resolve().parents[2]
LEDGER_CLOCK = FixedClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))


def inbound_event() -> dict[str, object]:
    return {
        "schema_id": "https://weflow.local/contracts/v1/inbound-message-event.schema.json",
        "schema_version": "v1",
        "tenant_id": "tenant-alpha",
        "channel": "synthetic-im",
        "channel_event_id": "workflow-im-event-001",
        "conversation_id": "workflow-conversation-alpha",
        "sender_id": "sender-alpha",
        "customer_id": "customer-alpha",
        "conversation_sequence": 1,
        "occurred_at": "2026-07-29T00:00:00Z",
        "received_at": "2026-07-29T00:00:01Z",
        "correlation_id": "trace-workflow-alpha-001",
        "content_classification": "synthetic",
        "content_sha256": "f" * 64,
    }


def test_offline_workflow_reaches_ticket_ready_only_after_local_effect_evidence(
    tmp_path: Path,
) -> None:
    ledger = SQLiteCaseLedger(
        tmp_path / "workflow.sqlite3",
        clock=LEDGER_CLOCK,
        contract_root=ROOT,
    )
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )

    projection = workflow.run_case(
        "tenant-alpha",
        accepted.case_id,
        accepted.case_revision_id,
    )

    assert projection is not None
    assert projection["state"] == "TICKET_READY"
    assert ledger.get_case_projection("tenant-alpha", accepted.case_id)["state"] == "TICKET_READY"
    counts = workflow.source_counts("tenant-alpha")
    assert counts["workflow_activations"] == 1
    assert counts["workflow_checkpoints"] >= 1
    assert counts["side_effect_intents"] == 2
    assert counts["side_effect_completions"] == 2
    assert counts["fixture_ticket_operations"] == 2


@pytest.mark.parametrize(
    "fault_point",
    [
        "activation",
        "checkpoint",
        "intent",
        "reconcile",
        "execute",
        "lost-response",
        "observation",
        "completion",
    ],
)
def test_recovery_after_each_durable_boundary_does_not_duplicate_local_ticket_operation(
    tmp_path: Path,
    fault_point: str,
) -> None:
    path = tmp_path / f"workflow-{fault_point}.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    clock = FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))
    workflow = SQLiteDurableWorkflow(ledger, clock=clock, contract_root=ROOT)

    with pytest.raises(WorkflowInterrupted, match=f"fault_injected:{fault_point}"):
        workflow.run_case(
            "tenant-alpha",
            accepted.case_id,
            accepted.case_revision_id,
            fault_profile=FaultProfile.after(fault_point),
        )

    restarted_ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    recovered = SQLiteDurableWorkflow(restarted_ledger, clock=clock, contract_root=ROOT)
    projection = recovered.recover_all()[0]

    assert projection is not None
    assert projection["state"] == "TICKET_READY"
    assert recovered.source_counts("tenant-alpha")["fixture_ticket_operations"] == 2
    assert (
        restarted_ledger.get_case_projection("tenant-alpha", accepted.case_id)["state"]
        == "TICKET_READY"
    )


def test_pause_resume_commands_are_expected_versioned_and_idempotent(tmp_path: Path) -> None:
    ledger = SQLiteCaseLedger(tmp_path / "commands.sqlite3", clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    workflow.activate_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)

    paused = workflow.submit_command(
        "tenant-alpha",
        accepted.case_id,
        command_id="pause-001",
        command_type="pause",
        expected_workflow_version=0,
    )
    assert paused.projection["state"] == "PAUSED"
    resumed = workflow.submit_command(
        "tenant-alpha",
        accepted.case_id,
        command_id="resume-001",
        command_type="resume",
        expected_workflow_version=paused.projection["workflow_version"],
    )
    assert resumed.projection["state"] == "RECEIVED"
    duplicate = workflow.submit_command(
        "tenant-alpha",
        accepted.case_id,
        command_id="resume-001",
        command_type="resume",
        expected_workflow_version=paused.projection["workflow_version"],
    )
    assert duplicate.disposition == "deduplicated"
    with pytest.raises(WorkflowError, match="workflow_version_conflict"):
        workflow.submit_command(
            "tenant-alpha",
            accepted.case_id,
            command_id="stale-pause",
            command_type="pause",
            expected_workflow_version=0,
        )
    with pytest.raises(WorkflowNotFound, match="workflow_not_found"):
        workflow.submit_command(
            "tenant-bravo",
            accepted.case_id,
            command_id="foreign-pause",
            command_type="pause",
            expected_workflow_version=0,
        )


def test_cancel_never_bypasses_an_unresolved_effect(tmp_path: Path) -> None:
    ledger = SQLiteCaseLedger(tmp_path / "cancel.sqlite3", clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    clock = FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))
    workflow = SQLiteDurableWorkflow(ledger, clock=clock, contract_root=ROOT)
    with pytest.raises(WorkflowInterrupted, match="fault_injected:intent"):
        workflow.run_case(
            "tenant-alpha",
            accepted.case_id,
            accepted.case_revision_id,
            fault_profile=FaultProfile.after("intent"),
        )

    result = workflow.submit_command(
        "tenant-alpha",
        accepted.case_id,
        command_id="cancel-001",
        command_type="cancel",
        expected_workflow_version=0,
    )

    assert result.disposition == "requires_reconciliation"
    assert result.projection["state"] == "NEEDS_RECONCILIATION"
    assert (
        ledger.get_case_projection("tenant-alpha", accepted.case_id)["state"]
        == "NEEDS_RECONCILIATION"
    )


def test_synthetic_sla_survives_restart_and_blocks_unfinished_work(tmp_path: Path) -> None:
    path = tmp_path / "sla.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    clock = FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))
    workflow = SQLiteDurableWorkflow(ledger, clock=clock, contract_root=ROOT)
    policy = workflow.default_sla_policy("tenant-alpha", created_at="2026-07-29T00:00:00Z")
    policy["deadline_seconds"] = 1
    with pytest.raises(WorkflowInterrupted, match="fault_injected:activation"):
        workflow.run_case(
            "tenant-alpha",
            accepted.case_id,
            accepted.case_revision_id,
            sla_policy=policy,
            fault_profile=FaultProfile.after("activation"),
        )

    clock.advance(seconds=2)
    restarted = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT),
        clock=clock,
        contract_root=ROOT,
    )
    projection = restarted.recover_all()[0]

    assert projection is not None
    assert projection["state"] == "WAITING_FOR_OPERATOR"
    assert restarted.source_counts("tenant-alpha")["workflow_sla_events"] == 1
    assert restarted.source_counts("tenant-alpha")["fixture_ticket_operations"] == 0


def test_workflow_snapshot_replays_linked_case_state_and_legacy_snapshot_stays_workflow_free(
    tmp_path: Path,
) -> None:
    ledger = SQLiteCaseLedger(tmp_path / "source.sqlite3", clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    snapshot = workflow.export_snapshot("tenant-alpha")

    restored = SQLiteDurableWorkflow.restore_snapshot(
        snapshot,
        tmp_path / "restored.sqlite3",
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )

    assert restored.export_snapshot("tenant-alpha") == snapshot
    assert (
        restored.get_workflow_for_case("tenant-alpha", accepted.case_id)["state"] == "TICKET_READY"
    )
    assert restored.ledger.get_case_projection("tenant-alpha", accepted.case_id)["state"] == (
        "TICKET_READY"
    )

    legacy = SQLiteCaseLedger.restore_snapshot(
        ledger.export_snapshot("tenant-alpha"),
        tmp_path / "legacy.sqlite3",
        clock=LEDGER_CLOCK,
        contract_root=ROOT,
    )
    legacy_workflow = SQLiteDurableWorkflow(
        legacy,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    assert legacy_workflow.source_counts("tenant-alpha")["workflow_activations"] == 0


def test_recovery_scans_one_unclaimed_case_and_exact_inbound_replay_stays_idempotent(
    tmp_path: Path,
) -> None:
    ledger = SQLiteCaseLedger(tmp_path / "scan.sqlite3", clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )

    first = workflow.recover_all()
    retry = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    second = workflow.recover_all()

    assert first[0] is not None and first[0]["state"] == "TICKET_READY"
    assert retry.disposition == "deduplicated"
    assert retry.case_id == accepted.case_id
    assert second[0] is not None and second[0]["state"] == "TICKET_READY"
    assert workflow.source_counts("tenant-alpha")["workflow_activations"] == 1
    assert workflow.source_counts("tenant-alpha")["fixture_ticket_operations"] == 2


def test_persisted_command_recovers_after_interruption_before_its_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "command-recovery.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    workflow.activate_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)

    def interrupt_after_command(*_args: object, **_kwargs: object) -> None:
        raise WorkflowInterrupted("fault_injected:command-persisted")

    monkeypatch.setattr(workflow, "_apply_persisted_command", interrupt_after_command)
    with pytest.raises(WorkflowInterrupted, match="fault_injected:command-persisted"):
        workflow.submit_command(
            "tenant-alpha",
            accepted.case_id,
            command_id="pause-after-persist",
            command_type="pause",
            expected_workflow_version=0,
        )

    restarted = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT),
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    projection = restarted.recover_all()[0]

    assert projection is not None
    assert projection["state"] == "PAUSED"
    assert restarted.source_counts("tenant-alpha")["workflow_commands"] == 1
    restarted.validate_projection_agreement()


def test_reconciliation_timeout_stays_safe_then_recovers_from_the_same_intent(
    tmp_path: Path,
) -> None:
    ledger = SQLiteCaseLedger(tmp_path / "timeout.sqlite3", clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )

    blocked = workflow.run_case(
        "tenant-alpha",
        accepted.case_id,
        accepted.case_revision_id,
        fault_profile=FaultProfile.named("reconciliation-timeout"),
    )
    recovered = workflow.recover_all()[0]

    assert blocked is not None and blocked["state"] == "NEEDS_RECONCILIATION"
    assert recovered is not None and recovered["state"] == "TICKET_READY"
    assert workflow.source_counts("tenant-alpha")["fixture_ticket_operations"] == 2
    workflow.validate_projection_agreement()


def test_stale_fixture_ticket_version_enters_reconciliation_without_a_blind_handoff_retry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stale-ticket.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    with pytest.raises(WorkflowInterrupted, match="fault_injected:completion"):
        workflow.run_case(
            "tenant-alpha",
            accepted.case_id,
            accepted.case_revision_id,
            fault_profile=FaultProfile.after("completion"),
        )

    connection = sqlite3.connect(path)
    try:
        ticket = connection.execute(
            "SELECT ticket_id, natural_key FROM fixture_ticket_revisions WHERE version = 1"
        ).fetchone()
        assert ticket is not None
        connection.execute(
            """
            INSERT INTO fixture_ticket_revisions (
                tenant_id, ticket_id, natural_key, version, content_sha256, operation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tenant-alpha",
                ticket[0],
                ticket[1],
                2,
                "c" * 64,
                "fixture-conflict",
                "2026-07-29T00:00:03Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    restarted = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT),
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    projection = restarted.recover_all()[0]

    assert projection is not None and projection["state"] == "NEEDS_RECONCILIATION"
    assert restarted.source_counts("tenant-alpha")["fixture_ticket_operations"] == 1
    restarted.validate_projection_agreement()


def test_workflow_journal_rejects_append_only_violations_and_source_tampering(
    tmp_path: Path,
) -> None:
    path = tmp_path / "integrity.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)

    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="append_only_violation"):
            connection.execute("UPDATE workflow_checkpoints SET content_sha256 = '0'")
        connection.execute("DROP TRIGGER workflow_checkpoints_no_update")
        connection.execute("UPDATE workflow_checkpoints SET content_sha256 = ?", ("0" * 64,))
        connection.commit()
    finally:
        connection.close()

    reopened_ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    with pytest.raises(WorkflowError, match="workflow_journal_invalid"):
        SQLiteDurableWorkflow(
            reopened_ledger,
            clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
            contract_root=ROOT,
        )


def test_unsupported_workflow_journal_schema_fails_closed_before_rebuild(tmp_path: Path) -> None:
    path = tmp_path / "unsupported-journal.sqlite3"
    SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER workflow_journal_metadata_no_update")
        connection.execute(
            "UPDATE workflow_journal_metadata SET schema_version = "
            "'weflow-durable-workflow-journal.v999'"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(LedgerIntegrityError, match="workflow_journal_schema_unsupported"):
        SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)


def test_snapshot_hash_and_linked_case_event_tampering_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "snapshot-source.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT)
    accepted = ledger.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    tampered_snapshot = copy.deepcopy(workflow.export_snapshot("tenant-alpha"))
    tampered_snapshot["workflow_journal"]["workflow_runs"][0]["reason_code"] = "tampered"

    with pytest.raises(WorkflowError, match="workflow_snapshot_hash_mismatch"):
        SQLiteDurableWorkflow.restore_snapshot(
            tampered_snapshot,
            tmp_path / "tampered.sqlite3",
            contract_root=ROOT,
        )

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER business_events_no_update")
        connection.execute(
            "UPDATE business_events SET workflow_checkpoint_id = 'checkpoint-tampered' "
            "WHERE workflow_id IS NOT NULL"
        )
        connection.commit()
    finally:
        connection.close()

    reopened = SQLiteDurableWorkflow(
        SQLiteCaseLedger(path, clock=LEDGER_CLOCK, contract_root=ROOT),
        clock=FixtureClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)),
        contract_root=ROOT,
    )
    with pytest.raises(WorkflowError, match="workflow_case_projection_mismatch"):
        reopened.validate_projection_agreement()
