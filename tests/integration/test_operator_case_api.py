from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from weflow_contracts import validate_operator_case_snapshot
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app
from weflow_testkit import (
    OPERATOR_CASE_NOT_FOUND,
    OperatorCaseReportError,
    RepositoryOperatorCaseReportSource,
    read_operator_case_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 8, 5, tzinfo=UTC)
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}
ROUTE = "/v1/operator/cases/api-503.v1"
FIXTURE = (
    ROOT / "fixtures" / "contracts" / "v1" / "semantic" / "operator-case-snapshot.json"
)


def _snapshot() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _client(tmp_path: Path, *, operator_case_reader=...) -> tuple[TestClient, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    store_path = tmp_path / "operator-api.sqlite3"
    ledger = SQLiteCaseLedger(
        store_path,
        clock=FixedClock(FIXED_TIME),
        contract_root=ROOT,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    kwargs = {}
    if operator_case_reader is not ...:
        kwargs["operator_case_reader"] = operator_case_reader
    app = create_app(
        root=ROOT,
        ledger=ledger,
        workflow=workflow,
        actor_registry=SyntheticActorRegistry.default(),
        **kwargs,
    )
    return TestClient(app), store_path


def _file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _missing_reader() -> dict[str, object]:
    raise OperatorCaseReportError(OPERATOR_CASE_NOT_FOUND)


def test_authorized_operator_case_read_is_fixed_validated_and_side_effect_free(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    client, store_path = _client(
        tmp_path,
        operator_case_reader=lambda: deepcopy(snapshot),
    )
    evaluation_report = ROOT / "reports" / "change-6-evaluation-benchmark-core-acceptance.json"
    default_store = ROOT / ".weflow" / "case-ledger.sqlite3"
    before_store = _file_sha256(store_path)
    before_evaluation = _file_sha256(evaluation_report)
    before_default = _file_sha256(default_store)

    response = client.get(ROUTE, headers=ACTOR_A)
    openapi = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json() == snapshot
    validate_operator_case_snapshot(response.json(), ROOT)
    schema = openapi.json()["components"]["schemas"]["WeFlowOperatorCaseSnapshotV1"]
    assert not list(Draft202012Validator(schema).iter_errors(response.json()))
    route = next(route for route in client.app.routes if route.path == ROUTE)
    assert route.methods == {"GET"}
    rendered = response.text
    assert "D:\\" not in rendered
    assert "raw_payload" not in rendered
    assert "customer_resolved" not in rendered
    assert _file_sha256(store_path) == before_store
    assert _file_sha256(evaluation_report) == before_evaluation
    assert _file_sha256(default_store) == before_default


def test_importing_platform_api_factory_does_not_read_or_create_operator_state() -> None:
    default_store = ROOT / ".weflow" / "case-ledger.sqlite3"
    operator_report = (
        ROOT / "reports" / "add-offline-operator-case-timeline-acceptance.json"
    )
    before_default = _file_sha256(default_store)
    before_report = _file_sha256(operator_report)

    completed = subprocess.run(
        [sys.executable, "-c", "import weflow_platform_api"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert _file_sha256(default_store) == before_default
    assert _file_sha256(operator_report) == before_report


def test_foreign_and_missing_operator_case_reads_are_indistinguishable(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path, operator_case_reader=_snapshot)
    missing_client, _ = _client(
        tmp_path / "missing",
        operator_case_reader=_missing_reader,
    )

    foreign = client.get(ROUTE, headers=ACTOR_B)
    missing = missing_client.get(ROUTE, headers=ACTOR_A)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"reason_code": "operator_case_not_found"}
    assert "tenant-alpha" not in foreign.text
    assert _snapshot()["case"]["case_id"] not in foreign.text


def test_unknown_operator_actor_is_denied_before_read(tmp_path: Path) -> None:
    calls = 0

    def reader() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _snapshot()

    client, _ = _client(tmp_path, operator_case_reader=reader)

    response = client.get(
        ROUTE,
        headers={"X-WeFlow-Synthetic-Actor": "unknown"},
    )

    assert response.status_code == 403
    assert response.json() == {"reason_code": "tenant_identity_mismatch"}
    assert calls == 0


@pytest.mark.parametrize(
    "kind",
    ["malformed", "duplicate_key", "tampered", "unsafe", "stale", "detached"],
)
def test_operator_case_integrity_failures_return_only_not_ready(
    tmp_path: Path, kind: str
) -> None:
    snapshot = _snapshot()

    def malformed_reader() -> dict[str, object]:
        return {"raw_payload": "blocked"}

    def snapshot_reader() -> dict[str, object]:
        return snapshot

    if kind == "malformed":
        reader = malformed_reader
    elif kind == "tampered":
        snapshot["snapshot_sha256"] = "f" * 64
        reader = snapshot_reader
    elif kind == "stale":
        snapshot["case"]["workflow_version"] = 11
        reader = snapshot_reader
    elif kind == "detached":
        snapshot["replay"]["replayed_root_sha256"] = "e" * 64
        reader = snapshot_reader
    else:
        reports = tmp_path / "reports"
        reports.mkdir(parents=True)
        if kind == "duplicate_key":
            (reports / "duplicate.json").write_text(
                '{"accepted":true,"accepted":true}',
                encoding="utf-8",
            )
            source = RepositoryOperatorCaseReportSource(
                tmp_path,
                "reports/duplicate.json",
                allow_test_override=True,
            )
        else:
            source = RepositoryOperatorCaseReportSource(
                tmp_path,
                "../unsafe.json",
                allow_test_override=True,
            )
        def report_reader() -> dict[str, object]:
            return read_operator_case_snapshot(ROOT, report_source=source)

        reader = report_reader
    client, store_path = _client(tmp_path / "api", operator_case_reader=reader)
    before_store = _file_sha256(store_path)

    response = client.get(ROUTE, headers=ACTOR_A)

    assert response.status_code == 503
    assert response.json() == {"reason_code": "operator_case_not_ready"}
    assert "blocked" not in response.text
    assert "unsafe" not in response.text
    assert _file_sha256(store_path) == before_store


def test_operator_selectors_paths_bodies_and_methods_never_reach_reader(
    tmp_path: Path,
) -> None:
    calls = 0

    def reader() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _snapshot()

    client, store_path = _client(tmp_path, operator_case_reader=reader)
    before_store = _file_sha256(store_path)
    selected = [
        client.get(f"{ROUTE}?{key}=forged", headers=ACTOR_A)
        for key in ("path", "report", "tenant", "case", "snapshot", "version")
    ]
    body = client.request("GET", ROUTE, headers=ACTOR_A, content=b'{"case":"forged"}')
    alternates = [
        client.get("/v1/operator/cases/another-case", headers=ACTOR_A),
        client.get("/v1/operator/cases/api-503.v2", headers=ACTOR_A),
    ]
    methods = [
        client.request(method, ROUTE, headers=ACTOR_A, json={"case": "forged"})
        for method in ("POST", "PUT", "PATCH", "DELETE")
    ]

    assert all(response.status_code == 422 for response in (*selected, body))
    assert all(
        response.json() == {"reason_code": "operator_case_request_invalid"}
        for response in (*selected, body)
    )
    assert all(response.status_code == 404 for response in alternates)
    assert all(response.status_code == 405 for response in methods)
    assert calls == 0
    assert _file_sha256(store_path) == before_store
    for response in (*selected, body, *alternates, *methods):
        assert "forged" not in response.text
        assert "another-case" not in response.text


def test_optional_operator_surface_does_not_affect_health_or_evaluation(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path, operator_case_reader=None)

    ready = client.get("/health/ready")
    capabilities = client.get("/foundation/capabilities")
    evaluation = client.get("/v1/evaluations/offline-seed.v1", headers=ACTOR_A)
    operator = client.get(ROUTE, headers=ACTOR_A)

    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert capabilities.status_code == 200
    assert evaluation.status_code == 200
    assert operator.status_code == 404
    assert operator.json() == {"reason_code": "operator_case_not_found"}
