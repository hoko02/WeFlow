from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from weflow_contracts import ContractValidationError
from weflow_contracts.evaluation import (
    canonical_sha256,
    validate_evaluation_suite_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def _valid_snapshot() -> dict[str, object]:
    return json.loads(
        (FIXTURE_ROOT / "semantic" / "evaluation-suite-snapshot.json").read_text(encoding="utf-8")
    )


def _rehash(snapshot: dict[str, object]) -> None:
    snapshot["snapshot_sha256"] = canonical_sha256(snapshot, without="snapshot_sha256")


def _invalid_snapshot(kind: str) -> dict[str, object]:
    snapshot = deepcopy(_valid_snapshot())
    task = snapshot["tasks"][0]
    if kind == "task_tenant":
        task["tenant_id"] = "tenant-foreign"
        _rehash(snapshot)
    elif kind == "report_hash":
        snapshot["report_sha256"] = "1" * 64
        _rehash(snapshot)
    elif kind == "suite_hash":
        snapshot["suite_sha256"] = "2" * 64
    elif kind == "source_hash":
        task["fixture_sha256"] = "3" * 64
    elif kind == "result_id":
        task["evaluation_result_id"] = "evaluation-result:detached"
        _rehash(snapshot)
    elif kind == "duplicate_task":
        snapshot["tasks"].append(deepcopy(task))
        snapshot["task_count"] = 2
        snapshot["passed_task_count"] = 2
        snapshot["task_result_ids"].append(task["evaluation_result_id"])
        _rehash(snapshot)
    elif kind == "count":
        snapshot["passed_task_count"] = 0
        snapshot["failed_task_count"] = 1
        _rehash(snapshot)
    elif kind == "failed_gate_score":
        task["hard_gates"][0]["passed"] = False
        task["hard_gate_passed"] = False
        _rehash(snapshot)
    elif kind == "absolute_path":
        task["fixture_source_path"] = "C:/private/fixture.json"
    elif kind == "raw":
        task["raw_payload"] = "blocked"
    elif kind == "secret":
        task["provider_token"] = "blocked"
    elif kind == "authority":
        snapshot["caller_role"] = "operator"
    elif kind == "live_provider":
        snapshot["live_provider_enabled"] = True
    elif kind == "customer_success":
        snapshot["customer_resolved"] = True
    elif kind == "external_write":
        snapshot["capability_flags"]["external_write"] = True
    else:  # pragma: no cover - the fixture names are closed by this test
        raise AssertionError(f"unknown invalid snapshot kind: {kind}")
    return snapshot


def test_valid_snapshot_is_accepted_by_schema_and_semantics() -> None:
    validate_evaluation_suite_snapshot(_valid_snapshot(), ROOT)


def test_snapshot_is_closed_to_undeclared_fields() -> None:
    snapshot = _valid_snapshot()
    snapshot["raw_payload"] = "blocked"

    with pytest.raises(ContractValidationError, match="additionalProperties"):
        validate_evaluation_suite_snapshot(snapshot, ROOT)


@pytest.mark.parametrize(
    "kind",
    json.loads(
        (FIXTURE_ROOT / "invalid" / "evaluation-suite-snapshot-invalid-cases.json").read_text(
            encoding="utf-8"
        )
    ).values(),
)
def test_invalid_snapshot_fixture_is_rejected_cross_field(kind: str) -> None:
    with pytest.raises(ContractValidationError):
        validate_evaluation_suite_snapshot(_invalid_snapshot(kind), ROOT)
