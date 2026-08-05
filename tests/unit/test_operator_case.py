from __future__ import annotations

import json
from pathlib import Path

import pytest
from weflow_business_simulator import (
    OperatorCaseSourceError,
    build_operator_case_snapshot,
    run_operator_case_source,
)
from weflow_contracts import validate_operator_case_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _bytes_or_none(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def test_two_fresh_operator_case_sources_produce_equal_real_snapshots(
    tmp_path: Path,
) -> None:
    default_store = ROOT / ".weflow" / "case-ledger.sqlite3"
    default_before = _bytes_or_none(default_store)

    first_source = run_operator_case_source(ROOT, tmp_path / "first.sqlite3")
    second_source = run_operator_case_source(ROOT, tmp_path / "second.sqlite3")
    first = build_operator_case_snapshot(first_source, ROOT)
    second = build_operator_case_snapshot(second_source, ROOT)

    validate_operator_case_snapshot(first, ROOT)
    validate_operator_case_snapshot(second, ROOT)
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
    assert first["counts"] == {
        "timeline_entry_count": 49,
        "case_event_count": 9,
        "case_revision_count": 1,
        "workflow_checkpoint_count": 13,
        "agent_step_count": 4,
        "tool_result_count": 3,
        "local_ticket_effect_count": 2,
        "fixture_delivery_effect_count": 1,
        "evidence_node_count": 48,
        "replay_result_count": 1,
    }
    assert first_source.duplicate_natural_identity_count == 0
    assert first_source.duplicate_idempotency_key_count == 0
    assert _bytes_or_none(default_store) == default_before


def test_every_operator_timeline_entry_maps_to_one_actual_public_source(
    tmp_path: Path,
) -> None:
    source = run_operator_case_source(ROOT, tmp_path / "source.sqlite3")
    snapshot = build_operator_case_snapshot(source, ROOT)
    expected = [
        (
            node["source_kind"],
            node["source_id"],
            node["content_sha256"],
        )
        for node in source.trajectory["nodes"]
    ]
    expected.append(
        (
            "replay_result",
            f"replay_result:{source.replay_result['replay_result_id']}",
            source.replay_result["result_sha256"],
        )
    )
    actual = [
        (entry["source_kind"], entry["source_id"], entry["source_sha256"])
        for entry in snapshot["timeline"]
    ]

    assert actual == expected
    assert len({entry["source_id"] for entry in snapshot["timeline"]}) == len(actual)
    assert snapshot["current_state_label"] == "DELIVERY_RECORDED (fixture-local)"
    assert snapshot["capabilities"]["external_write"] is False
    assert snapshot["capabilities"]["customer_resolution"] is False
    assert snapshot["capabilities"]["case_completion"] is False


def test_operator_source_requires_an_injected_fresh_non_default_store(
    tmp_path: Path,
) -> None:
    occupied = tmp_path / "occupied.sqlite3"
    occupied.write_bytes(b"existing")

    with pytest.raises(OperatorCaseSourceError, match="store_not_fresh"):
        run_operator_case_source(ROOT, occupied)
    with pytest.raises(OperatorCaseSourceError, match="store_not_fresh"):
        run_operator_case_source(ROOT, ROOT / ".weflow" / "case-ledger.sqlite3")


def test_operator_source_boundary_contains_no_private_sql_or_expected_mirror() -> None:
    source = (
        ROOT
        / "apps"
        / "business-simulator"
        / "src"
        / "weflow_business_simulator"
        / "operator_case.py"
    ).read_text(encoding="utf-8")

    assert "._connect(" not in source
    assert "import sqlite3" not in source
    assert "SELECT " not in source
    assert "expected_outcome" not in source
    assert "provider_adapter" not in source.lower()
    assert "openai" not in source.lower()
    assert "httpx" not in source.lower()
