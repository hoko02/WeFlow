import copy
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_control_kernel.ledger import (
    FixedClock,
    IntakeRejected,
    LedgerIntegrityError,
    SQLiteCaseLedger,
    SyntheticActorRegistry,
    _sha256,
)

ROOT = Path(__file__).resolve().parents[2]
FIXED_CLOCK = FixedClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))
CONTENT_HASH = "f" * 64


def inbound_event(
    *,
    tenant_id: str = "tenant-alpha",
    channel_event_id: str = "im-event-001",
    conversation_sequence: int = 1,
    content_sha256: str = CONTENT_HASH,
    received_at: str = "2026-07-29T00:00:01Z",
) -> dict[str, object]:
    return {
        "schema_id": "https://weflow.local/contracts/v1/inbound-message-event.schema.json",
        "schema_version": "v1",
        "tenant_id": tenant_id,
        "channel": "synthetic-im",
        "channel_event_id": channel_event_id,
        "conversation_id": "conversation-alpha",
        "sender_id": "sender-alpha",
        "customer_id": "customer-alpha",
        "conversation_sequence": conversation_sequence,
        "occurred_at": "2026-07-29T00:00:00Z",
        "received_at": received_at,
        "correlation_id": "trace-alpha-001",
        "content_classification": "synthetic",
        "content_sha256": content_sha256,
    }


def ledger(tmp_path: Path, name: str = "ledger.sqlite3") -> SQLiteCaseLedger:
    return SQLiteCaseLedger(
        tmp_path / name,
        clock=FIXED_CLOCK,
        contract_root=ROOT,
    )


def test_actor_registry_resolves_only_allowlisted_synthetic_tenants() -> None:
    registry = SyntheticActorRegistry.default()

    assert registry.resolve("simulator-tenant-a") == "tenant-alpha"
    with pytest.raises(IntakeRejected, match="tenant_identity_mismatch"):
        registry.resolve("unmapped-actor")


def test_first_delivery_creates_exactly_one_initial_case_ledger(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    result = store.intake(inbound_event(), effective_tenant_id="tenant-alpha")

    assert result.disposition == "accepted"
    assert store.source_counts("tenant-alpha") == {
        "inbound_receipts": 1,
        "cases": 1,
        "case_revisions": 1,
        "business_events": 3,
        "case_projection": 1,
    }
    projection = store.get_case_projection("tenant-alpha", result.case_id)
    assert projection is not None
    assert projection["state"] == "RECEIVED"
    assert store.list_case_revisions("tenant-alpha", result.case_id)[0]["revision"] == 1
    assert [
        event["event_type"] for event in store.list_case_events("tenant-alpha", result.case_id)
    ] == [
        "inbound.received.v1",
        "case.revision-created.v1",
        "case.state-transitioned.v1",
    ]


def test_identical_retry_is_read_only_but_conflicting_replay_is_rejected(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    accepted = store.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    duplicate = store.intake(
        inbound_event(received_at="2026-07-29T00:01:00Z"),
        effective_tenant_id="tenant-alpha",
    )

    assert duplicate.disposition == "deduplicated"
    assert duplicate.case_id == accepted.case_id
    assert store.source_counts("tenant-alpha")["business_events"] == 3

    with pytest.raises(IntakeRejected, match="inbound_event_conflict"):
        store.intake(
            inbound_event(content_sha256="e" * 64),
            effective_tenant_id="tenant-alpha",
        )
    assert store.source_counts("tenant-alpha")["business_events"] == 3


def test_out_of_order_delivery_is_rejected_without_state_change(tmp_path: Path) -> None:
    store = ledger(tmp_path)

    with pytest.raises(IntakeRejected, match="inbound_out_of_order"):
        store.intake(
            inbound_event(conversation_sequence=2),
            effective_tenant_id="tenant-alpha",
        )
    assert store.source_counts("tenant-alpha") == {
        "inbound_receipts": 0,
        "cases": 0,
        "case_revisions": 0,
        "business_events": 0,
        "case_projection": 0,
    }


def test_source_revisions_and_events_reject_mutation(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    result = store.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    connection = store._connect()
    try:
        with pytest.raises(sqlite3.DatabaseError, match="append_only_violation"):
            connection.execute(
                "UPDATE case_revisions SET reason = ? WHERE case_revision_id = ?",
                ("tamper", result.case_revision_id),
            )
        with pytest.raises(sqlite3.DatabaseError, match="append_only_violation"):
            connection.execute(
                "DELETE FROM business_events WHERE tenant_id = ? AND case_id = ?",
                ("tenant-alpha", result.case_id),
            )
    finally:
        connection.close()

    assert len(store.list_case_events("tenant-alpha", result.case_id)) == 3


def test_restart_rebuilds_projection_and_preserves_duplicate_result(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    accepted = store.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    restarted = ledger(tmp_path)

    assert restarted.get_case_projection(
        "tenant-alpha", accepted.case_id
    ) == store.get_case_projection(
        "tenant-alpha",
        accepted.case_id,
    )
    duplicate = restarted.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    assert duplicate == accepted.__class__(
        disposition="deduplicated",
        case_id=accepted.case_id,
        case_revision_id=accepted.case_revision_id,
        event_ids=accepted.event_ids,
    )


def test_snapshot_restore_is_fresh_deterministic_and_rejects_tampering(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    accepted = store.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    snapshot = store.export_snapshot("tenant-alpha")
    restored = SQLiteCaseLedger.restore_snapshot(
        snapshot,
        tmp_path / "restored.sqlite3",
        clock=FIXED_CLOCK,
        contract_root=ROOT,
    )

    assert restored.export_snapshot("tenant-alpha") == snapshot
    assert (
        restored.intake(inbound_event(), effective_tenant_id="tenant-alpha").disposition
        == "deduplicated"
    )
    assert restored.get_case_projection("tenant-alpha", accepted.case_id) is not None

    mixed_tenant = copy.deepcopy(snapshot)
    mixed_tenant["cases"][0]["tenant_id"] = "tenant-bravo"
    material = dict(mixed_tenant)
    material.pop("content_sha256")
    mixed_tenant["content_sha256"] = _sha256(material)
    with pytest.raises(LedgerIntegrityError, match="snapshot_tenant_mismatch"):
        SQLiteCaseLedger.restore_snapshot(
            mixed_tenant,
            tmp_path / "mixed.sqlite3",
            clock=FIXED_CLOCK,
            contract_root=ROOT,
        )


def test_corrupted_event_payload_fails_closed_on_rebuild(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    result = store.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    connection = store._connect()
    try:
        connection.execute("DROP TRIGGER business_events_no_update")
        connection.execute(
            "UPDATE business_events SET payload_sha256 = ? WHERE event_id = ?",
            ("0" * 64, result.event_ids[0]),
        )
    finally:
        connection.close()

    with pytest.raises(LedgerIntegrityError, match="ledger_invalid"):
        SQLiteCaseLedger(store.path, clock=FIXED_CLOCK, contract_root=ROOT)


def test_intake_transaction_rolls_back_when_projection_build_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ledger(tmp_path)

    def fail_projection(*_arguments: object) -> object:
        raise LedgerIntegrityError("ledger_invalid")

    monkeypatch.setattr(store, "_projection_from_records", fail_projection)
    with pytest.raises(LedgerIntegrityError, match="ledger_invalid"):
        store.intake(inbound_event(), effective_tenant_id="tenant-alpha")

    assert store.source_counts("tenant-alpha") == {
        "inbound_receipts": 0,
        "cases": 0,
        "case_revisions": 0,
        "business_events": 0,
        "case_projection": 0,
    }


def test_snapshot_restore_rejects_inconsistent_receipt_event_references(tmp_path: Path) -> None:
    store = ledger(tmp_path)
    store.intake(inbound_event(), effective_tenant_id="tenant-alpha")
    snapshot = copy.deepcopy(store.export_snapshot("tenant-alpha"))
    snapshot["inbound_receipts"][0]["event_ids_json"] = '["event-inconsistent"]'
    material = dict(snapshot)
    material.pop("content_sha256")
    snapshot["content_sha256"] = _sha256(material)

    with pytest.raises(LedgerIntegrityError, match="ledger_invalid"):
        SQLiteCaseLedger.restore_snapshot(
            snapshot,
            tmp_path / "inconsistent.sqlite3",
            clock=FIXED_CLOCK,
            contract_root=ROOT,
        )
