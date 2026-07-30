import copy
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from weflow_business_simulator import load_intake_fixture
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app

ROOT = Path(__file__).resolve().parents[2]
FIXED_CLOCK = FixedClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}


def test_case_intake_rejects_raw_prompt_and_does_not_disclose_cross_tenant_case(
    tmp_path: Path,
) -> None:
    store = SQLiteCaseLedger(
        tmp_path / "case-ledger.sqlite3",
        clock=FIXED_CLOCK,
        contract_root=ROOT,
    )
    client = TestClient(
        create_app(
            root=ROOT,
            ledger=store,
            actor_registry=SyntheticActorRegistry.default(),
        )
    )
    fixture = load_intake_fixture("api-503-first-delivery", ROOT)
    inbound_message = fixture["inbound_message"]
    accepted = client.post("/v1/synthetic-im/intake", headers=ACTOR_A, json=inbound_message)
    case_id = accepted.json()["case_id"]

    raw_prompt = copy.deepcopy(inbound_message)
    raw_prompt["prompt"] = "private prompt material must never be echoed"
    rejected = client.post("/v1/synthetic-im/intake", headers=ACTOR_A, json=raw_prompt)
    foreign = client.get(f"/v1/cases/{case_id}", headers=ACTOR_B)
    absent = client.get("/v1/cases/case-never-existed", headers=ACTOR_B)
    snapshot = store.export_snapshot("tenant-alpha")
    capabilities = client.get("/foundation/capabilities")

    assert rejected.status_code == 422
    assert rejected.json() == {"reason_code": "invalid_inbound_event"}
    assert "private prompt material" not in rejected.text
    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json() == {"reason_code": "case_not_found"}
    assert "customer-api-503-alpha" not in foreign.text
    assert '"prompt"' not in str(snapshot)
    assert capabilities.json()["business_workflow_implemented"] is False
    assert capabilities.json()["external_writes_enabled"] is False
