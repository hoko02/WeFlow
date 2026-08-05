from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from weflow_contracts.evaluation import validate_evaluation_suite_snapshot
from weflow_testkit import evaluation_benchmark
from weflow_testkit.evaluation_report import (
    EVALUATION_REPORT_NOT_FOUND,
    EVALUATION_REPORT_NOT_READY,
    EvaluationReportError,
    RepositoryEvaluationReportSource,
    read_evaluation_suite_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_REPORT = ROOT / "reports" / "change-6-evaluation-benchmark-core-acceptance.json"


def _canonical_payload() -> dict[str, object]:
    return json.loads(CANONICAL_REPORT.read_text(encoding="utf-8"))


def _source(
    temporary_root: Path,
    *,
    payload: object | None = None,
    text: str | None = None,
) -> RepositoryEvaluationReportSource:
    reports = temporary_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / "fixture-report.json"
    path.write_text(
        text if text is not None else json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )
    return RepositoryEvaluationReportSource(
        temporary_root,
        "reports/fixture-report.json",
        allow_test_override=True,
    )


def test_canonical_report_derives_a_deterministic_read_only_snapshot(monkeypatch) -> None:
    before = CANONICAL_REPORT.read_bytes()

    def fail_if_store_is_opened(*_args, **_kwargs):
        raise AssertionError("report reads must not open a task store")

    monkeypatch.setattr(evaluation_benchmark.sqlite3, "connect", fail_if_store_is_opened)
    first = read_evaluation_suite_snapshot(ROOT)
    second = read_evaluation_suite_snapshot(ROOT)

    assert first == second
    assert first["task_count"] == 12
    assert first["passed_task_count"] == 12
    assert first["failed_task_count"] == 0
    assert first["unscored_task_count"] == 0
    assert first["task_result_ids"] == [task["evaluation_result_id"] for task in first["tasks"]]
    assert CANONICAL_REPORT.read_bytes() == before
    validate_evaluation_suite_snapshot(first, ROOT)


def test_snapshot_projection_contains_only_bounded_safe_evidence() -> None:
    snapshot = read_evaluation_suite_snapshot(ROOT)
    rendered = json.dumps(snapshot, sort_keys=True).lower()

    assert all(task["fixture_source_path"].startswith("fixtures/") for task in snapshot["tasks"])
    assert all(
        task["policy_source_path"].startswith("evals/sources/") for task in snapshot["tasks"]
    )
    for forbidden in (
        "raw_payload",
        "provider_token",
        "caller_role",
        "customer_resolved",
        "live_provider_enabled",
        "external_writes_enabled",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    "mutation",
    [
        "not_accepted",
        "unsafe_field",
        "stale_source",
        "detached_result",
        "detached_metrics",
        "unsafe_state",
        "duplicate_task",
        "nondeterministic",
    ],
)
def test_integrity_mutations_emit_no_snapshot(tmp_path: Path, mutation: str) -> None:
    payload = deepcopy(_canonical_payload())
    diagnostic = payload["task_diagnostics"][0]
    if mutation == "not_accepted":
        payload["accepted"] = False
    elif mutation == "unsafe_field":
        diagnostic["raw_payload"] = "blocked"
    elif mutation == "stale_source":
        diagnostic["fixture_sha256"] = "f" * 64
    elif mutation == "detached_result":
        diagnostic["evaluation_result"]["suite_report_id"] = "report:detached"
    elif mutation == "detached_metrics":
        diagnostic["metrics"]["evaluation_task_id"] = "another-task"
    elif mutation == "unsafe_state":
        diagnostic["observation"]["state"] = "PRIVATE_STATE"
    elif mutation == "duplicate_task":
        payload["task_diagnostics"][1] = deepcopy(diagnostic)
    elif mutation == "nondeterministic":
        payload["determinism"]["repeated_baseline_equal"] = False

    with pytest.raises(EvaluationReportError) as error:
        read_evaluation_suite_snapshot(ROOT, report_source=_source(tmp_path, payload=payload))

    assert error.value.reason_code == EVALUATION_REPORT_NOT_READY


@pytest.mark.parametrize(
    "text",
    [
        "not-json",
        "[]",
        '{"accepted":true,"accepted":true}',
    ],
)
def test_malformed_or_duplicate_json_is_not_ready(tmp_path: Path, text: str) -> None:
    with pytest.raises(EvaluationReportError) as error:
        read_evaluation_suite_snapshot(ROOT, report_source=_source(tmp_path, text=text))

    assert error.value.reason_code == EVALUATION_REPORT_NOT_READY


def test_missing_report_is_non_disclosing(tmp_path: Path) -> None:
    source = RepositoryEvaluationReportSource(
        tmp_path,
        "reports/missing.json",
        allow_test_override=True,
    )

    with pytest.raises(EvaluationReportError) as error:
        read_evaluation_suite_snapshot(ROOT, report_source=source)

    assert error.value.reason_code == EVALUATION_REPORT_NOT_FOUND
    assert "missing" not in str(error.value)


@pytest.mark.parametrize(
    "relative_path",
    ["../private.json", "/absolute/report.json", "reports/../private.json", "C:/private.json"],
)
def test_unsafe_report_source_path_is_rejected_without_echo(
    tmp_path: Path, relative_path: str
) -> None:
    source = RepositoryEvaluationReportSource(
        tmp_path,
        relative_path,
        allow_test_override=True,
    )

    with pytest.raises(EvaluationReportError) as error:
        read_evaluation_suite_snapshot(ROOT, report_source=source)

    assert error.value.reason_code == EVALUATION_REPORT_NOT_READY
    assert relative_path not in str(error.value)


def test_noncanonical_source_requires_explicit_test_override(tmp_path: Path) -> None:
    source = _source(tmp_path, payload=_canonical_payload())
    denied = RepositoryEvaluationReportSource(source.root, source.relative_path)

    with pytest.raises(EvaluationReportError) as error:
        read_evaluation_suite_snapshot(ROOT, report_source=denied)

    assert error.value.reason_code == EVALUATION_REPORT_NOT_READY
