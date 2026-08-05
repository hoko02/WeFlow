from __future__ import annotations

import json
from pathlib import Path

import pytest
from weflow_testkit import (
    OPERATOR_CASE_NOT_FOUND,
    OPERATOR_CASE_NOT_READY,
    OperatorCaseReportError,
    RepositoryOperatorCaseReportSource,
    read_operator_case_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT / "fixtures" / "contracts" / "v1" / "semantic" / "operator-case-snapshot.json"
)


def _snapshot() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _acceptance(snapshot: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "report_type": "weflow-offline-operator-case-timeline-acceptance.v1",
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "operator_case_snapshot": snapshot or _snapshot(),
        "determinism": {
            "repeated_baseline_equal": True,
            "intentional_nondeterministic_fields": [],
        },
        "side_effect_counts": {
            "default_store_mutation_count": 0,
            "source_report_mutation_count": 0,
            "duplicate_natural_identity_count": 0,
            "duplicate_idempotency_key_count": 0,
            "network_request_count": 0,
            "model_invocation_count": 0,
            "provider_initialization_count": 0,
            "external_write_attempt_count": 0,
            "unauthorized_effect_count": 0,
        },
        "negative_matrix": {"missing": OPERATOR_CASE_NOT_FOUND},
        "capabilities": {
            "offline_operator_case_timeline_implemented": True,
            "fixture_local_delivery_only": True,
            "replay_verification_only": True,
            "live_provider_enabled": False,
            "external_writes_enabled": False,
            "customer_receipt_enabled": False,
            "customer_resolution_enabled": False,
            "business_workflow_complete": False,
            "multi_agent_enabled": False,
        },
    }


def _source(tmp_path: Path, text: str, name: str = "operator.json"):
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    (reports / name).write_text(text, encoding="utf-8")
    return RepositoryOperatorCaseReportSource(
        tmp_path,
        f"reports/{name}",
        allow_test_override=True,
    )


def test_repository_operator_case_reader_returns_a_validated_copy(tmp_path: Path) -> None:
    original = _acceptance()
    source = _source(tmp_path, json.dumps(original, sort_keys=True))

    first = read_operator_case_snapshot(ROOT, report_source=source)
    first["case"]["workflow_version"] = 999
    second = read_operator_case_snapshot(ROOT, report_source=source)

    assert second["case"]["workflow_version"] == 12
    assert second["counts"]["timeline_entry_count"] == 49


def test_repository_operator_case_reader_classifies_missing_without_creating(
    tmp_path: Path,
) -> None:
    source = RepositoryOperatorCaseReportSource(
        tmp_path,
        "reports/missing.json",
        allow_test_override=True,
    )

    with pytest.raises(OperatorCaseReportError) as error:
        read_operator_case_snapshot(ROOT, report_source=source)

    assert error.value.reason_code == OPERATOR_CASE_NOT_FOUND
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "kind",
    ["malformed", "duplicate_key", "unsafe_field", "stale", "detached", "partial"],
)
def test_repository_operator_case_reader_rejects_integrity_failures(
    tmp_path: Path, kind: str
) -> None:
    report = _acceptance()
    if kind == "malformed":
        text = "{"
    elif kind == "duplicate_key":
        text = '{"accepted":true,"accepted":true}'
    else:
        if kind == "unsafe_field":
            report["raw_payload"] = "blocked"
        elif kind == "stale":
            report["operator_case_snapshot"]["case"]["workflow_version"] = 11
        elif kind == "detached":
            report["operator_case_snapshot"]["replay"]["replayed_root_sha256"] = "f" * 64
        elif kind == "partial":
            del report["operator_case_snapshot"]["timeline"]
        text = json.dumps(report, sort_keys=True)
    source = _source(tmp_path, text)

    with pytest.raises(OperatorCaseReportError) as error:
        read_operator_case_snapshot(ROOT, report_source=source)

    assert error.value.reason_code == OPERATOR_CASE_NOT_READY


@pytest.mark.parametrize(
    "relative_path",
    [
        "../operator.json",
        "reports/../operator.json",
        "C:/private/operator.json",
        r"reports\operator.json",
    ],
)
def test_repository_operator_case_reader_rejects_unsafe_paths(
    tmp_path: Path, relative_path: str
) -> None:
    source = RepositoryOperatorCaseReportSource(
        tmp_path,
        relative_path,
        allow_test_override=True,
    )

    with pytest.raises(OperatorCaseReportError) as error:
        read_operator_case_snapshot(ROOT, report_source=source)

    assert error.value.reason_code == OPERATOR_CASE_NOT_READY


def test_repository_operator_case_reader_rejects_noncanonical_path_without_opt_in(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, json.dumps(_acceptance()))
    denied = RepositoryOperatorCaseReportSource(source.root, source.relative_path)

    with pytest.raises(OperatorCaseReportError) as error:
        read_operator_case_snapshot(ROOT, report_source=denied)

    assert error.value.reason_code == OPERATOR_CASE_NOT_READY
