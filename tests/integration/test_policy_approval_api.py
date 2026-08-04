import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from weflow_agent_runtime import run_investigation_replay
from weflow_business_simulator import load_intake_fixture
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC)
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
APPROVER_A = {"X-WeFlow-Synthetic-Actor": "fixture-approver-alpha"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}
APPROVER_B = {"X-WeFlow-Synthetic-Actor": "fixture-approver-bravo"}


def make_client(tmp_path: Path) -> tuple[TestClient, SQLiteDurableWorkflow]:
    ledger = SQLiteCaseLedger(
        tmp_path / "policy-approval-api.sqlite3",
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


def activate_fixture_path(
    client: TestClient, workflow: SQLiteDurableWorkflow
) -> tuple[str, dict[str, object]]:
    inbound = load_intake_fixture("api-503-first-delivery", ROOT)["inbound_message"]
    accepted = client.post("/v1/synthetic-im/intake", headers=ACTOR_A, json=inbound)
    assert accepted.status_code == 201
    case_id = str(accepted.json()["case_id"])
    case_revision_id = str(accepted.json()["case_revision_id"])
    workflow.run_case("tenant-alpha", case_id, case_revision_id)
    replay = run_investigation_replay(workflow, "tenant-alpha", case_id, root=ROOT)
    assert replay["state"] == "RESPONSE_READY"
    projection = workflow.activate_policy_approval("tenant-alpha", case_id)
    assert projection["state"] == "AWAITING_APPROVAL"
    return case_id, projection


def test_policy_approval_reads_and_decisions_are_tenant_role_derived_and_redacted(
    tmp_path: Path,
) -> None:
    client, workflow = make_client(tmp_path)
    case_id, projection = activate_fixture_path(client, workflow)
    approval_path = f"/v1/cases/{case_id}/workflow/approval"
    decision_path = f"/v1/cases/{case_id}/workflow/approval/decisions"
    delivery_path = f"/v1/cases/{case_id}/workflow/delivery"

    observed = client.get(approval_path, headers=ACTOR_A)
    foreign = client.get(approval_path, headers=ACTOR_B)
    absent = client.get("/v1/cases/case-never-existed/workflow/approval", headers=ACTOR_B)

    assert observed.status_code == 200
    facts = observed.json()["approval"]
    request_id = facts["approval_request"]["approval_request_id"]
    assert facts["state"] == "AWAITING_APPROVAL"
    assert facts["fixture_local"] is True
    assert facts["real_external_write"] is False
    assert facts["customer_resolution"] is False
    rendered = json.dumps(facts, sort_keys=True)
    for forbidden in ("customer-api-503-alpha", "provider_token", "raw_message", "prompt"):
        assert forbidden not in rendered
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json() == {"reason_code": "workflow_not_found"}

    payload = {
        "approval_request_id": request_id,
        "decision": "approve",
        "expected_workflow_version": projection["workflow_version"],
    }
    forged = client.post(
        decision_path,
        headers=APPROVER_A,
        json={**payload, "tenant_id": "tenant-bravo"},
    )
    wrong_role = client.post(decision_path, headers=ACTOR_A, json=payload)
    foreign_decision = client.post(decision_path, headers=APPROVER_B, json=payload)

    assert forged.status_code == 422
    assert forged.json() == {"reason_code": "approval_decision_invalid"}
    assert wrong_role.status_code == 403
    assert wrong_role.json() == {"reason_code": "approval_not_authorized"}
    assert foreign_decision.status_code == 404
    assert foreign_decision.json() == {"reason_code": "workflow_not_found"}
    assert workflow.source_counts("tenant-alpha")["approval_decisions"] == 0
    assert workflow.source_counts("tenant-alpha")["fixture_delivery_records"] == 0

    approved = client.post(decision_path, headers=APPROVER_A, json=payload)
    duplicate = client.post(decision_path, headers=APPROVER_A, json=payload)
    delivered = client.get(delivery_path, headers=ACTOR_A)

    assert approved.status_code == 200
    assert approved.json()["disposition"] == "accepted"
    assert approved.json()["projection"]["state"] == "DELIVERY_RECORDED"
    assert duplicate.status_code == 200
    assert duplicate.json()["disposition"] == "deduplicated"
    assert delivered.status_code == 200
    assert delivered.json()["delivery"]["delivery_recorded"] is True
    assert delivered.json()["fixture_local"] is True
    assert delivered.json()["real_external_write"] is False
    assert delivered.json()["customer_resolution"] is False
    assert workflow.source_counts("tenant-alpha")["approval_decisions"] == 1
    assert workflow.source_counts("tenant-alpha")["fixture_delivery_records"] == 1


def test_approval_api_rejects_caller_selected_authority_and_hides_absent_delivery(
    tmp_path: Path,
) -> None:
    client, workflow = make_client(tmp_path)
    case_id, projection = activate_fixture_path(client, workflow)
    approval = client.get(f"/v1/cases/{case_id}/workflow/approval", headers=ACTOR_A).json()[
        "approval"
    ]
    request_id = approval["approval_request"]["approval_request_id"]
    decision_path = f"/v1/cases/{case_id}/workflow/approval/decisions"
    base = {
        "approval_request_id": request_id,
        "decision": "reject",
        "expected_workflow_version": projection["workflow_version"],
    }

    for forbidden_key in (
        "role",
        "grant_id",
        "policy_version",
        "candidate_hash",
        "evidence_hashes",
        "delivery_resource_id",
        "target_state",
    ):
        response = client.post(
            decision_path,
            headers=APPROVER_A,
            json={**base, forbidden_key: "forged"},
        )
        assert response.status_code == 422
        assert response.json() == {"reason_code": "approval_decision_invalid"}

    rejected = client.post(decision_path, headers=APPROVER_A, json=base)
    delivery = client.get(f"/v1/cases/{case_id}/workflow/delivery", headers=ACTOR_A)
    foreign_delivery = client.get(f"/v1/cases/{case_id}/workflow/delivery", headers=ACTOR_B)
    absent_delivery = client.get("/v1/cases/case-never-existed/workflow/delivery", headers=ACTOR_B)

    assert rejected.status_code == 200
    assert rejected.json()["projection"]["state"] == "WAITING_FOR_OPERATOR"
    assert delivery.status_code == 200
    assert delivery.json()["delivery"] is None
    assert foreign_delivery.status_code == absent_delivery.status_code == 404
    assert (
        foreign_delivery.json() == absent_delivery.json() == {"reason_code": "workflow_not_found"}
    )
    assert workflow.source_counts("tenant-alpha")["fixture_delivery_records"] == 0
