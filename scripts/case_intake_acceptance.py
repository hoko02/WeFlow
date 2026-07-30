"""Offline evidence runner for Change 1 synthetic Case intake."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient
from weflow_business_simulator import SyntheticIntakeSimulator
from weflow_control_kernel.ledger import (
    FixedClock,
    SQLiteCaseLedger,
    SyntheticActorRegistry,
)
from weflow_platform_api import create_app

JsonObject = dict[str, Any]
FIXTURE_IDS = (
    "api-503-first-delivery",
    "api-503-duplicate-delivery",
    "api-503-out-of-order",
)
FIXED_CLOCK = FixedClock(datetime(2026, 7, 29, 0, 0, 2, tzinfo=UTC))


def _require(condition: bool, reason_code: str) -> None:
    if not condition:
        raise RuntimeError(reason_code)


def _submit_fixture(client: TestClient, fixture: Mapping[str, Any]) -> tuple[int, JsonObject]:
    actor_id = fixture.get("actor_id")
    inbound_message = fixture.get("inbound_message")
    _require(isinstance(actor_id, str), "fixture_invalid")
    _require(isinstance(inbound_message, Mapping), "fixture_invalid")
    response = client.post(
        "/v1/synthetic-im/intake",
        headers={"X-WeFlow-Synthetic-Actor": actor_id},
        json=dict(inbound_message),
    )
    payload = response.json()
    _require(isinstance(payload, dict), "api_response_invalid")
    return response.status_code, payload


def run_case_intake_acceptance(root: Path) -> JsonObject:
    """Run the fixture-only acceptance sequence without network or credentials."""

    registry = SyntheticActorRegistry.default()
    simulator = SyntheticIntakeSimulator(registry, root=root)
    with TemporaryDirectory(prefix="weflow-change-1-") as temporary_directory:
        workspace = Path(temporary_directory)
        store = SQLiteCaseLedger(
            workspace / "case-ledger.sqlite3",
            clock=FIXED_CLOCK,
            contract_root=root,
        )
        client = TestClient(
            create_app(
                root=root,
                ledger=store,
                actor_registry=registry,
            )
        )
        fixture_results: JsonObject = {}
        accepted: JsonObject | None = None
        first_fixture: JsonObject | None = None

        for fixture_id in FIXTURE_IDS:
            fixture = simulator.fixture_request(fixture_id)
            status_code, result = _submit_fixture(client, fixture)
            expected = fixture.get("expected")
            _require(isinstance(expected, Mapping), "fixture_invalid")
            if "disposition" in expected:
                expected_disposition = expected["disposition"]
                _require(
                    status_code == (201 if expected_disposition == "accepted" else 200),
                    "fixture_http_status_unexpected",
                )
                _require(
                    result.get("disposition") == expected_disposition,
                    "fixture_disposition_unexpected",
                )
            else:
                _require(status_code == 409, "fixture_http_status_unexpected")
                _require(
                    result.get("reason_code") == expected.get("reason_code"),
                    "fixture_reason_unexpected",
                )
            fixture_results[fixture_id] = {
                "http_status": status_code,
                "outcome": result.get("disposition", result.get("reason_code")),
            }
            if fixture_id == "api-503-first-delivery":
                accepted = result
                first_fixture = fixture

        _require(accepted is not None and first_fixture is not None, "first_delivery_missing")
        case_id = accepted.get("case_id")
        _require(isinstance(case_id, str), "accepted_case_reference_missing")
        actor_id = first_fixture.get("actor_id")
        _require(isinstance(actor_id, str), "fixture_invalid")
        headers = {"X-WeFlow-Synthetic-Actor": actor_id}
        case_response = client.get(f"/v1/cases/{case_id}", headers=headers)
        events_response = client.get(f"/v1/cases/{case_id}/events", headers=headers)
        _require(case_response.status_code == 200, "case_projection_unavailable")
        _require(events_response.status_code == 200, "case_events_unavailable")
        case_projection = case_response.json()
        events_payload = events_response.json()
        _require(case_projection.get("state") == "RECEIVED", "case_state_unexpected")
        event_types = [event.get("event_type") for event in events_payload.get("events", [])]
        expected_event_types = first_fixture["expected"].get("event_types")
        _require(event_types == expected_event_types, "case_event_sequence_unexpected")

        tenant_id = registry.resolve(actor_id)
        source_counts = store.source_counts(tenant_id)
        _require(
            source_counts
            == {
                "inbound_receipts": 1,
                "cases": 1,
                "case_revisions": 1,
                "business_events": 3,
                "case_projection": 1,
            },
            "source_counts_unexpected",
        )
        snapshot = simulator.export_snapshot(store, actor_id)
        restored = SQLiteCaseLedger.restore_snapshot(
            snapshot,
            workspace / "restored-case-ledger.sqlite3",
            clock=FIXED_CLOCK,
            contract_root=root,
        )
        _require(restored.source_counts(tenant_id) == source_counts, "snapshot_restore_unexpected")
        _require(restored.export_snapshot(tenant_id) == snapshot, "snapshot_hash_unstable")

        capabilities = client.get("/foundation/capabilities")
        _require(capabilities.status_code == 200, "capabilities_unavailable")
        capability_payload = capabilities.json()
        _require(
            capability_payload.get("synthetic_case_intake_implemented") is True,
            "capability_not_declared",
        )
        _require(
            capability_payload.get("business_workflow_implemented") is False,
            "workflow_capability_overclaimed",
        )
        _require(
            capability_payload.get("external_writes_enabled") is False,
            "external_write_capability_overclaimed",
        )
        return {
            "report_type": "weflow-change-1-acceptance.v1",
            "accepted": True,
            "mode": "offline",
            "network_required": False,
            "model_credentials_required": False,
            "docker_required": False,
            "fixture_results": fixture_results,
            "source_counts": source_counts,
            "snapshot": {
                "content_sha256": snapshot["content_sha256"],
                "restored": True,
                "tenant_count": 1,
            },
            "capabilities": {
                "synthetic_case_intake_implemented": True,
                "business_workflow_implemented": False,
                "external_writes_enabled": False,
            },
            "model_invoked": False,
            "workflow_started": False,
            "approval_started": False,
            "customer_resolution_declared": False,
        }
