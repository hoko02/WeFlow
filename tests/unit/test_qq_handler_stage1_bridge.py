from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from test_qq_handler_runner import config, event
from weflow_control_kernel.ledger import SQLiteCaseLedger
from weflow_control_worker.qq_handler_runner import accept_live_stage1_intake


def test_stage2_live_event_first_becomes_one_deduplicated_stage1_case(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    ledger = SQLiteCaseLedger(cfg.store_path, contract_root=cfg.repository_root)
    raw_event = event()

    first = accept_live_stage1_intake(raw_event, config=cfg, ledger=ledger)
    second = accept_live_stage1_intake(raw_event, config=cfg, ledger=ledger)

    assert first["stage1_intake_disposition"] == "accepted"
    assert second["stage1_intake_disposition"] == "deduplicated"
    assert first["case_id"] == second["case_id"]
    assert first["case_revision_id"] == second["case_revision_id"]
    projection = ledger.get_case_projection(cfg.tenant_id, first["case_id"])
    assert projection is not None
    assert projection["case_id"] == first["case_id"]
    assert projection["latest_case_revision_id"] == first["case_revision_id"]
    snapshot = ledger.export_snapshot(cfg.tenant_id)
    assert "SYNTHETIC_ISSUE_API_503" not in str(snapshot)


def test_stage1_bridge_does_not_create_acknowledgement_or_stage2_effects(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    ledger = SQLiteCaseLedger(cfg.store_path, contract_root=cfg.repository_root)

    accept_live_stage1_intake(event(), config=cfg, ledger=ledger)

    counts = ledger.source_counts(cfg.tenant_id)
    assert counts["cases"] == 1
    assert counts["case_revisions"] == 1
    assert counts["business_events"] == 3
    assert counts["inbound_receipts"] == 1
    assert counts["case_projection"] == 1
    with closing(sqlite3.connect(cfg.store_path)) as connection:
        acknowledgement_tables = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name LIKE 'qq_acknowledgement_%'"
        ).fetchone()[0]
    assert acknowledgement_tables == 0


def test_stage1_bridge_accepts_session_sequence_reset_and_preserves_high_water(
    tmp_path: Path,
) -> None:
    cfg = config(tmp_path)
    ledger = SQLiteCaseLedger(cfg.store_path, contract_root=cfg.repository_root)
    first = event()
    second = event("@机器人 SYNTHETIC_ISSUE_API_503_SECOND")
    second["s"] = 10
    second["d"]["id"] = "synthetic-intake-message-second"  # type: ignore[index]

    accept_live_stage1_intake(first, config=cfg, ledger=ledger)
    accept_live_stage1_intake(second, config=cfg, ledger=ledger)

    restarted = SQLiteCaseLedger(cfg.store_path, contract_root=cfg.repository_root)
    assert restarted.source_counts(cfg.tenant_id)["cases"] == 2

    stale = event("@机器人 SYNTHETIC_ISSUE_API_503_STALE")
    stale["s"] = 5
    stale["d"]["id"] = "synthetic-intake-message-stale"  # type: ignore[index]
    accept_live_stage1_intake(stale, config=cfg, ledger=restarted)
    assert restarted.source_counts(cfg.tenant_id)["cases"] == 3
    with closing(sqlite3.connect(cfg.store_path)) as connection:
        high_water = connection.execute(
            "SELECT last_sequence FROM conversation_cursors WHERE channel='qq-sandbox'"
        ).fetchone()
    assert high_water is not None
    assert high_water[0] == 10
