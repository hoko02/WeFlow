# ruff: noqa: E501
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from weflow_business_simulator.policy_approval import SyntheticPolicyApprovalSimulator
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 8, 4, tzinfo=UTC)
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}


def test_evidence_report_route_is_read_only_and_tenant_derived(tmp_path: Path) -> None:
    ledger = SQLiteCaseLedger(
        tmp_path / "evidence-api.sqlite3", clock=FixedClock(FIXED_TIME), contract_root=ROOT
    )
    workflow = SQLiteDurableWorkflow(ledger, clock=FixtureClock(FIXED_TIME), contract_root=ROOT)
    client = TestClient(
        create_app(
            root=ROOT,
            ledger=ledger,
            workflow=workflow,
            actor_registry=SyntheticActorRegistry.default(),
        )
    )
    source = SyntheticPolicyApprovalSimulator(root=ROOT).run_fixture(ledger, workflow)
    case_id = str(source["case_id"])
    path = f"/v1/cases/{case_id}/workflow/evidence"

    before = client.get(path, headers=ACTOR_A)
    persisted = workflow.extract_evidence_trajectory("tenant-alpha", case_id)
    observed = client.get(path, headers=ACTOR_A)
    foreign = client.get(path, headers=ACTOR_B)
    absent = client.get("/v1/cases/case-never-existed/workflow/evidence", headers=ACTOR_B)
    mutation = client.post(path, headers=ACTOR_A, json={"trajectory_id": "forged"})
    selected_inputs = [
        client.get(f"{path}?{key}=forged", headers=ACTOR_A)
        for key in ("authority", "profile_id", "node_id", "include_raw")
    ]

    assert before.status_code == 404
    assert observed.status_code == 200
    assert observed.json() == persisted["report"]
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json() == {"reason_code": "workflow_not_found"}
    assert mutation.status_code == 405
    assert all(response.status_code == 422 for response in selected_inputs)
    assert all(
        response.json() == {"reason_code": "evidence_request_invalid"}
        for response in selected_inputs
    )
    rendered = json.dumps(observed.json(), sort_keys=True)
    for forbidden in (
        "customer-api-503-alpha",
        "provider_token",
        "raw_message",
        "trajectory_id=forged",
    ):
        assert forbidden not in rendered
    route = next(route for route in client.app.routes if route.path.endswith("/workflow/evidence"))
    assert route.methods == {"GET"}
