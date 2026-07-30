import copy
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from weflow_business_simulator import load_intake_fixture
from weflow_control_kernel.ledger import (
    FixedClock,
    SQLiteCaseLedger,
    SyntheticActorRegistry,
)
from weflow_platform_api import create_app

ROOT = Path(__file__).resolve().parents[2]
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}
FIXED_CLOCK = FixedClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))


def make_client(tmp_path: Path) -> tuple[TestClient, SQLiteCaseLedger]:
    store = SQLiteCaseLedger(
        tmp_path / "case-ledger.sqlite3",
        clock=FIXED_CLOCK,
        contract_root=ROOT,
    )
    return (
        TestClient(
            create_app(
                root=ROOT,
                ledger=store,
                actor_registry=SyntheticActorRegistry.default(),
            )
        ),
        store,
    )


def fixture(name: str) -> dict[str, object]:
    return load_intake_fixture(name, ROOT)


def test_api_accepts_synthetic_intake_and_exposes_canonical_case_projection(tmp_path: Path) -> None:
    client, store = make_client(tmp_path)
    first = fixture("api-503-first-delivery")

    response = client.post(
        "/v1/synthetic-im/intake",
        headers=ACTOR_A,
        json=first["inbound_message"],
    )

    assert response.status_code == 201
    result = response.json()
    assert result["disposition"] == "accepted"
    assert len(result["event_ids"]) == 3

    case = client.get(f"/v1/cases/{result['case_id']}", headers=ACTOR_A)
    revisions = client.get(f"/v1/cases/{result['case_id']}/revisions", headers=ACTOR_A)
    events = client.get(f"/v1/cases/{result['case_id']}/events", headers=ACTOR_A)
    openapi = client.get("/openapi.json")

    assert case.status_code == 200
    assert revisions.status_code == 200
    assert events.status_code == 200
    assert case.json()["state"] == "RECEIVED"
    assert revisions.json()["revisions"][0]["revision"] == 1
    assert [event["event_type"] for event in events.json()["events"]] == [
        "inbound.received.v1",
        "case.revision-created.v1",
        "case.state-transitioned.v1",
    ]
    projection_schema = openapi.json()["components"]["schemas"]["WeFlowCaseProjectionV1"]
    assert not list(Draft202012Validator(projection_schema).iter_errors(case.json()))
    intake_body = openapi.json()["paths"]["/v1/synthetic-im/intake"]["post"]["requestBody"]
    assert intake_body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WeFlowInboundMessageEventV1"
    }
    assert store.source_counts("tenant-alpha")["business_events"] == 3


def test_api_duplicate_conflict_and_ordering_outcomes_are_safe_and_deterministic(
    tmp_path: Path,
) -> None:
    client, store = make_client(tmp_path)
    first = fixture("api-503-first-delivery")
    duplicate = fixture("api-503-duplicate-delivery")
    out_of_order = fixture("api-503-out-of-order")

    accepted = client.post(
        "/v1/synthetic-im/intake", headers=ACTOR_A, json=first["inbound_message"]
    )
    deduplicated = client.post(
        "/v1/synthetic-im/intake",
        headers=ACTOR_A,
        json=duplicate["inbound_message"],
    )
    conflict_payload = copy.deepcopy(first["inbound_message"])
    conflict_payload["content_sha256"] = "e" * 64
    conflict = client.post("/v1/synthetic-im/intake", headers=ACTOR_A, json=conflict_payload)
    ordering = client.post(
        "/v1/synthetic-im/intake",
        headers=ACTOR_A,
        json=out_of_order["inbound_message"],
    )

    assert accepted.status_code == 201
    assert deduplicated.status_code == 200
    assert deduplicated.json()["disposition"] == "deduplicated"
    assert deduplicated.json()["case_id"] == accepted.json()["case_id"]
    assert conflict.status_code == 409
    assert conflict.json() == {"reason_code": "inbound_event_conflict"}
    assert ordering.status_code == 409
    assert ordering.json() == {"reason_code": "inbound_out_of_order"}
    assert store.source_counts("tenant-alpha")["business_events"] == 3


def test_api_tenant_boundary_and_invalid_input_do_not_disclose_raw_data(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    first = fixture("api-503-first-delivery")
    accepted = client.post(
        "/v1/synthetic-im/intake", headers=ACTOR_A, json=first["inbound_message"]
    )
    case_id = accepted.json()["case_id"]

    foreign = client.get(f"/v1/cases/{case_id}", headers=ACTOR_B)
    absent = client.get("/v1/cases/case-never-existed", headers=ACTOR_B)
    mismatch_payload = copy.deepcopy(first["inbound_message"])
    mismatch_payload["tenant_id"] = "tenant-bravo"
    mismatch = client.post("/v1/synthetic-im/intake", headers=ACTOR_A, json=mismatch_payload)
    raw_field_payload = copy.deepcopy(first["inbound_message"])
    raw_field_payload["body"] = "forbidden"
    invalid = client.post("/v1/synthetic-im/intake", headers=ACTOR_A, json=raw_field_payload)

    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json() == {"reason_code": "case_not_found"}
    assert mismatch.status_code == 403
    assert mismatch.json() == {"reason_code": "tenant_identity_mismatch"}
    assert invalid.status_code == 422
    assert invalid.json() == {"reason_code": "invalid_inbound_event"}
    assert "forbidden" not in invalid.text
    assert "tenant-alpha" not in foreign.text


def test_capability_report_marks_only_synthetic_intake_as_implemented(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)

    capabilities = client.get("/foundation/capabilities")

    assert capabilities.status_code == 200
    assert capabilities.json()["synthetic_case_intake_implemented"] is True
    assert capabilities.json()["business_workflow_implemented"] is False
    assert capabilities.json()["external_writes_enabled"] is False
