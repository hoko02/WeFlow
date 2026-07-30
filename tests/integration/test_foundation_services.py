import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from weflow_agent_runtime import run_replay
from weflow_business_simulator import load_replay_fixture
from weflow_control_kernel.status import SERVICE_NAMES, build_service_status
from weflow_extension_sdk import ExternalWriteExecutorUnavailable, ReplayProvider
from weflow_platform_api import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_platform_api_health_matches_the_canonical_health_schema() -> None:
    client = TestClient(create_app(root=ROOT))

    live = client.get("/health/live")
    ready = client.get("/health/ready")
    openapi = client.get("/openapi.json")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert openapi.status_code == 200
    assert "/health/live" in openapi.json()["paths"]
    assert "/health/ready" in openapi.json()["paths"]
    assert "HealthStatusResponse" in openapi.json()["components"]["schemas"]
    canonical = openapi.json()["components"]["schemas"]["WeFlowHealthStatusV1"]
    assert canonical["$id"] == "https://weflow.local/contracts/v1/health-status.schema.json"
    health_response = openapi.json()["paths"]["/health/ready"]["get"]["responses"]["200"]
    assert health_response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WeFlowHealthStatusV1"
    }

    schema = json.loads(
        (ROOT / "contracts/jsonschema/v1/health-status.schema.json").read_text(encoding="utf-8")
    )
    assert not list(Draft202012Validator(schema).iter_errors(ready.json()))


def test_platform_api_allows_only_the_loopback_console_origin() -> None:
    client = TestClient(create_app(root=ROOT))

    allowed = client.get("/health/ready", headers={"Origin": "http://127.0.0.1:5173"})
    denied = client.get("/health/ready", headers={"Origin": "http://localhost:5173"})

    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in denied.headers


def test_platform_api_keeps_a_forbidden_provider_not_ready_and_redacted() -> None:
    client = TestClient(create_app({"WEFLOW_PROVIDER_MODE": "live-provider"}, root=ROOT))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["policy_denial"]["capability"] == "live_provider"
    assert "live-provider" not in response.text


def test_all_declared_skeletons_are_ready_in_offline_mode() -> None:
    statuses = [build_service_status(service_name, root=ROOT) for service_name in SERVICE_NAMES]

    assert all(status["live"] and status["ready"] for status in statuses)
    assert all(status["state"] == "ready" for status in statuses)
    assert all("no-business-workflow" in status["limitations"] for status in statuses)


def test_runtime_replay_rejects_external_action_and_self_approval() -> None:
    fixture = load_replay_fixture("foundation-happy-path", ROOT)
    external_result = run_replay({**fixture, "proposed_action": "create-ticket"})
    self_approval_result = run_replay({**fixture, "purported_approval": True})

    assert external_result["external_write_executed"] is False
    assert external_result["case_completion_declared"] is False
    assert external_result["authorization"] == "denied"
    assert external_result["reason_code"] == "external_write_executor_not_registered"
    assert self_approval_result["authorization"] == "denied"
    assert self_approval_result["reason_code"] == "self_approval_not_authoritative"


def test_replay_provider_has_no_external_write_executor() -> None:
    with pytest.raises(ExternalWriteExecutorUnavailable):
        ReplayProvider().execute_external_write()
