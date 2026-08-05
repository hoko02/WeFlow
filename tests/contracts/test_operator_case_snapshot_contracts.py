from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    finalize_operator_case_snapshot,
    operator_case_entry_id,
    validate_operator_case_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def _valid_snapshot() -> dict[str, object]:
    return json.loads(
        (FIXTURE_ROOT / "semantic" / "operator-case-snapshot.json").read_text(
            encoding="utf-8"
        )
    )


def _refinalize(snapshot: dict[str, object]) -> dict[str, object]:
    return finalize_operator_case_snapshot(snapshot)


def _relink(snapshot: dict[str, object]) -> None:
    prior: str | None = None
    for sequence, entry in enumerate(snapshot["timeline"], start=1):
        entry["sequence"] = sequence
        entry["entry_id"] = operator_case_entry_id(
            sequence=sequence,
            source_kind=entry["source_kind"],
            source_id=entry["source_id"],
            source_sha256=entry["source_sha256"],
        )
        entry["predecessor_entry_id"] = prior
        prior = entry["entry_id"]


def _entry(snapshot: dict[str, object], source_kind: str) -> dict[str, object]:
    return next(
        item for item in snapshot["timeline"] if item["source_kind"] == source_kind
    )


def _invalid_snapshot(kind: str) -> dict[str, object]:
    snapshot = deepcopy(_valid_snapshot())
    if kind == "foreign_identity":
        snapshot["tenant_id"] = "tenant-foreign"
    elif kind == "detached_source_hash":
        _entry(snapshot, "tool_result")["source_sha256"] = "f" * 64
        _relink(snapshot)
        snapshot = _refinalize(snapshot)
    elif kind == "detached_evidence_root":
        snapshot["evidence"]["root_sha256"] = "e" * 64
        snapshot = _refinalize(snapshot)
    elif kind == "detached_replay_root":
        snapshot["replay"]["replayed_root_sha256"] = "d" * 64
        snapshot = _refinalize(snapshot)
    elif kind == "snapshot_hash":
        snapshot["snapshot_sha256"] = "c" * 64
    elif kind == "missing_entry":
        snapshot["timeline"] = [
            item for item in snapshot["timeline"] if item["source_kind"] != "capability_grant"
        ]
        _relink(snapshot)
        snapshot = _refinalize(snapshot)
    elif kind == "duplicate_entry":
        snapshot["timeline"].insert(2, deepcopy(snapshot["timeline"][1]))
        _relink(snapshot)
        snapshot = _refinalize(snapshot)
    elif kind == "duplicate_source":
        snapshot["timeline"][2]["source_id"] = snapshot["timeline"][1]["source_id"]
        snapshot["timeline"][2]["source_kind"] = snapshot["timeline"][1]["source_kind"]
        snapshot["timeline"][2]["phase"] = snapshot["timeline"][1]["phase"]
        _relink(snapshot)
        snapshot = _refinalize(snapshot)
    elif kind == "out_of_order_entry":
        snapshot["timeline"][0], snapshot["timeline"][-2] = (
            snapshot["timeline"][-2],
            snapshot["timeline"][0],
        )
        _relink(snapshot)
        snapshot = _refinalize(snapshot)
    elif kind == "predecessor_mismatch":
        snapshot["timeline"][1]["predecessor_entry_id"] = None
        snapshot = _refinalize(snapshot)
    elif kind == "count_mismatch":
        snapshot["counts"]["timeline_entry_count"] += 1
        snapshot = _refinalize(snapshot)
    elif kind == "stale_approval_as_success":
        approval = _entry(snapshot, "approval_decision")
        approval["observation"] = "stale"
        approval["reason_code"] = "stale_approval"
        snapshot = _refinalize(snapshot)
    elif kind == "policy_denial_as_success":
        policy = _entry(snapshot, "policy_decision")
        policy["observation"] = "denied"
        policy["reason_code"] = "policy_denied"
        snapshot = _refinalize(snapshot)
    elif kind == "raw_field":
        snapshot["raw_payload"] = "blocked"
    elif kind == "secret_like_field":
        snapshot["provider_token"] = "blocked"
    elif kind == "executable_field":
        _entry(snapshot, "agent_step")["reason_code"] = "<script>alert(1)</script>"
    elif kind == "absolute_path":
        snapshot["fixture_source_path"] = "C:/private/fixture.json"
    elif kind == "escaping_path":
        snapshot["fixture_source_path"] = "../fixtures/policy/fixture.json"
    elif kind == "caller_authority":
        snapshot["caller_role"] = "operator"
    elif kind == "live_provider":
        snapshot["capabilities"]["live_provider"] = True
    elif kind == "customer_success":
        snapshot["capabilities"]["customer_resolution"] = True
    elif kind == "mutation_capability":
        snapshot["capabilities"]["workflow_authority"] = True
    elif kind == "effect_capability":
        snapshot["capabilities"]["retry_authority"] = True
    elif kind == "unsupported_recovery":
        delivery = _entry(snapshot, "delivery_completion")
        delivery["recovery_status"] = "recovered"
        delivery["reason_code"] = "recovered_after_interruption"
        snapshot = _refinalize(snapshot)
    else:  # pragma: no cover - names are closed by the checked-in matrix
        raise AssertionError(f"unknown invalid operator snapshot kind: {kind}")
    return snapshot


def test_valid_operator_case_snapshot_is_accepted() -> None:
    snapshot = _valid_snapshot()

    validate_operator_case_snapshot(snapshot, ROOT)
    assert snapshot["current_state_label"] == "DELIVERY_RECORDED (fixture-local)"
    assert snapshot["counts"]["timeline_entry_count"] == 49


def test_operator_case_snapshot_is_closed_to_arbitrary_maps() -> None:
    snapshot = _valid_snapshot()
    snapshot["timeline"][0]["payload"] = {"raw": "blocked"}

    with pytest.raises(ContractValidationError, match="additionalProperties"):
        validate_operator_case_snapshot(snapshot, ROOT)


@pytest.mark.parametrize(
    "kind",
    json.loads(
        (
            FIXTURE_ROOT
            / "invalid"
            / "operator-case-snapshot-invalid-cases.json"
        ).read_text(encoding="utf-8")
    ).values(),
)
def test_invalid_operator_case_snapshot_is_rejected(kind: str) -> None:
    with pytest.raises(ContractValidationError):
        validate_operator_case_snapshot(_invalid_snapshot(kind), ROOT)
