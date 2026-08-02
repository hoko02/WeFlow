from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from weflow_business_simulator import load_intake_fixture
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app

ROOT = Path(__file__).resolve().parents[2]
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}
FIXED_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)


def make_client(tmp_path: Path) -> tuple[TestClient, SQLiteDurableWorkflow]:
    ledger = SQLiteCaseLedger(
        tmp_path / "workflow-api.sqlite3",
        clock=FixedClock(FIXED_TIME),
        contract_root=ROOT,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    client = TestClient(
        create_app(
            root=ROOT,
            ledger=ledger,
            workflow=workflow,
            actor_registry=SyntheticActorRegistry.default(),
        )
    )
    return client, workflow


def accept_case(client: TestClient) -> dict[str, object]:
    fixture = load_intake_fixture("api-503-first-delivery", ROOT)
    response = client.post(
        "/v1/synthetic-im/intake", headers=ACTOR_A, json=fixture["inbound_message"]
    )
    assert response.status_code == 201
    return response.json()


def test_workflow_observation_is_tenant_scoped_and_uses_canonical_contracts(tmp_path: Path) -> None:
    client, workflow = make_client(tmp_path)
    accepted = accept_case(client)
    projection = workflow.run_case(
        "tenant-alpha",
        str(accepted["case_id"]),
        str(accepted["case_revision_id"]),
    )
    assert projection is not None

    observed = client.get(f"/v1/cases/{accepted['case_id']}/workflow", headers=ACTOR_A)
    checkpoints = client.get(
        f"/v1/cases/{accepted['case_id']}/workflow/checkpoints", headers=ACTOR_A
    )
    foreign = client.get(f"/v1/cases/{accepted['case_id']}/workflow", headers=ACTOR_B)
    absent = client.get("/v1/cases/case-never-existed/workflow", headers=ACTOR_B)
    openapi = client.get("/openapi.json")

    assert observed.status_code == 200
    assert observed.json()["state"] == "TICKET_READY"
    assert checkpoints.status_code == 200
    assert checkpoints.json()["checkpoints"][-1]["current_state"] == "TICKET_READY"
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json() == {"reason_code": "workflow_not_found"}
    schema = openapi.json()["components"]["schemas"]["WeFlowWorkflowProjectionV1"]
    assert not list(Draft202012Validator(schema).iter_errors(observed.json()))
    assert openapi.json()["paths"]["/v1/cases/{case_id}/workflow"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {"$ref": "#/components/schemas/WeFlowWorkflowProjectionV1"}


def test_workflow_command_surface_is_allowlisted_versioned_and_non_mutating(tmp_path: Path) -> None:
    client, workflow = make_client(tmp_path)
    accepted = accept_case(client)
    workflow.activate_case(
        "tenant-alpha",
        str(accepted["case_id"]),
        str(accepted["case_revision_id"]),
    )
    command_path = f"/v1/cases/{accepted['case_id']}/workflow/commands"
    command = {
        "command_id": "pause-api-001",
        "command_type": "pause",
        "expected_workflow_version": 0,
    }

    paused = client.post(command_path, headers=ACTOR_A, json=command)
    duplicate = client.post(command_path, headers=ACTOR_A, json=command)
    stale = client.post(
        command_path,
        headers=ACTOR_A,
        json={
            "command_id": "pause-api-stale",
            "command_type": "pause",
            "expected_workflow_version": 0,
        },
    )
    raw_payload = client.post(
        command_path,
        headers=ACTOR_A,
        json={**command, "raw_message": "customer-private-content"},
    )

    assert paused.status_code == 200
    assert paused.json()["disposition"] == "accepted"
    assert paused.json()["projection"]["state"] == "PAUSED"
    assert duplicate.status_code == 200
    assert duplicate.json()["disposition"] == "deduplicated"
    assert stale.status_code == 409
    assert stale.json() == {"reason_code": "workflow_version_conflict"}
    assert raw_payload.status_code == 422
    assert raw_payload.json() == {"reason_code": "workflow_command_invalid"}
    assert "customer-private-content" not in raw_payload.text

    route_paths = {route.path for route in client.app.routes}
    assert "/v1/cases/{case_id}/workflow/commands" in route_paths
    assert not any(
        forbidden in path
        for path in route_paths
        for forbidden in ("approval", "outbound", "delivery", "ticket")
    )


def test_capability_boundary_advertises_only_fixture_local_durable_workflow(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    capabilities = client.get("/foundation/capabilities")

    assert capabilities.status_code == 200
    assert capabilities.json()["synthetic_case_intake_implemented"] is True
    assert capabilities.json()["durable_support_workflow_implemented"] is True
    assert capabilities.json()["business_workflow_implemented"] is False
    assert capabilities.json()["external_writes_enabled"] is False
