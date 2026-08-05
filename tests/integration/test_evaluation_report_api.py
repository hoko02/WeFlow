from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from weflow_contracts.evaluation import (
    canonical_sha256,
    validate_evaluation_suite_snapshot,
)
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app
from weflow_testkit.evaluation_report import (
    EVALUATION_REPORT_NOT_FOUND,
    EvaluationReportError,
    read_evaluation_suite_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 8, 5, tzinfo=UTC)
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}
ROUTE = "/v1/evaluations/offline-seed.v1"


def _client(tmp_path: Path, *, evaluation_reader=...) -> tuple[TestClient, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    store_path = tmp_path / "evaluation-api.sqlite3"
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
    if evaluation_reader is not ...:
        kwargs["evaluation_reader"] = evaluation_reader
    app = create_app(
        root=ROOT,
        ledger=ledger,
        workflow=workflow,
        actor_registry=SyntheticActorRegistry.default(),
        **kwargs,
    )
    return TestClient(app), store_path


def _missing_reader() -> dict[str, object]:
    raise EvaluationReportError(EVALUATION_REPORT_NOT_FOUND)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_authorized_evaluation_read_is_fixed_validated_and_side_effect_free(
    tmp_path: Path,
) -> None:
    snapshot = read_evaluation_suite_snapshot(ROOT)
    client, store_path = _client(
        tmp_path,
        evaluation_reader=lambda: deepcopy(snapshot),
    )
    report_path = ROOT / "reports" / "change-6-evaluation-benchmark-core-acceptance.json"
    before_store = _file_sha256(store_path)
    before_report = _file_sha256(report_path)

    response = client.get(ROUTE, headers=ACTOR_A)
    openapi = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json() == snapshot
    validate_evaluation_suite_snapshot(response.json(), ROOT)
    schema = openapi.json()["components"]["schemas"]["WeFlowEvaluationSuiteSnapshotV1"]
    assert not list(Draft202012Validator(schema).iter_errors(response.json()))
    assert _file_sha256(store_path) == before_store
    assert _file_sha256(report_path) == before_report
    route = next(route for route in client.app.routes if route.path == ROUTE)
    assert route.methods == {"GET"}


def test_default_application_reader_uses_only_the_canonical_report(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)

    response = client.get(ROUTE, headers=ACTOR_A)

    assert response.status_code == 200
    assert response.json()["suite_id"] == "offline-seed.v1"
    assert response.json()["task_count"] == 12


def test_foreign_and_missing_reads_are_indistinguishable(tmp_path: Path) -> None:
    snapshot = read_evaluation_suite_snapshot(ROOT)
    client, _ = _client(tmp_path, evaluation_reader=lambda: deepcopy(snapshot))
    missing_client, _ = _client(tmp_path / "missing", evaluation_reader=_missing_reader)

    foreign = client.get(ROUTE, headers=ACTOR_B)
    missing = missing_client.get(ROUTE, headers=ACTOR_A)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"reason_code": "evaluation_report_not_found"}
    assert "tenant-alpha" not in foreign.text
    assert "report" not in json.dumps(foreign.json()).replace("evaluation_report_not_found", "")


def test_unknown_actor_and_invalid_snapshot_fail_closed(tmp_path: Path) -> None:
    snapshot = read_evaluation_suite_snapshot(ROOT)
    invalid = deepcopy(snapshot)
    invalid["raw_payload"] = "blocked"
    client, _ = _client(tmp_path, evaluation_reader=lambda: invalid)

    denied = client.get(ROUTE, headers={"X-WeFlow-Synthetic-Actor": "unknown"})
    integrity = client.get(ROUTE, headers=ACTOR_A)

    assert denied.status_code == 403
    assert denied.json() == {"reason_code": "tenant_identity_mismatch"}
    assert integrity.status_code == 503
    assert integrity.json() == {"reason_code": "evaluation_report_not_ready"}
    assert "blocked" not in integrity.text


def test_selectors_alternate_suite_and_methods_never_reach_reader(tmp_path: Path) -> None:
    calls = 0

    def reader() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return read_evaluation_suite_snapshot(ROOT)

    client, store_path = _client(tmp_path, evaluation_reader=reader)
    before_store = _file_sha256(store_path)
    selected = [
        client.get(f"{ROUTE}?{key}=forged", headers=ACTOR_A)
        for key in ("path", "report", "tenant", "suite", "include_raw")
    ]
    alternate = client.get("/v1/evaluations/another-suite", headers=ACTOR_A)
    mutation = client.post(ROUTE, headers=ACTOR_A, json={"path": "forged"})

    assert all(response.status_code == 422 for response in selected)
    assert all(
        response.json() == {"reason_code": "evaluation_request_invalid"} for response in selected
    )
    assert alternate.status_code == 404
    assert mutation.status_code == 405
    assert calls == 0
    assert _file_sha256(store_path) == before_store
    for response in (*selected, alternate, mutation):
        assert "forged" not in response.text
        assert "another-suite" not in response.text


def test_optional_evaluation_surface_does_not_affect_foundation_readiness(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path, evaluation_reader=None)

    ready = client.get("/health/ready")
    capabilities = client.get("/foundation/capabilities")
    evaluation = client.get(ROUTE, headers=ACTOR_A)

    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert capabilities.status_code == 200
    assert evaluation.status_code == 404
    assert evaluation.json() == {"reason_code": "evaluation_report_not_found"}


def test_foreign_snapshot_cannot_be_rebound_by_the_api(tmp_path: Path) -> None:
    snapshot = deepcopy(read_evaluation_suite_snapshot(ROOT))
    snapshot["tenant_id"] = "tenant-bravo"
    for task in snapshot["tasks"]:
        task["tenant_id"] = "tenant-bravo"
    snapshot["snapshot_sha256"] = canonical_sha256(snapshot, without="snapshot_sha256")
    validate_evaluation_suite_snapshot(snapshot, ROOT)
    client, _ = _client(tmp_path, evaluation_reader=lambda: snapshot)

    response = client.get(ROUTE, headers=ACTOR_A)

    assert response.status_code == 404
    assert response.json() == {"reason_code": "evaluation_report_not_found"}
