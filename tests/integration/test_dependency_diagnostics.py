import json
from pathlib import Path

import pytest
from weflow_contracts import validate_payload
from weflow_control_kernel import probe_local_dependency
from weflow_control_kernel import status as status_module
from weflow_control_kernel.status import build_service_status
from weflow_telemetry import SyntheticArtifactError, failure_evidence, store_synthetic_artifact

ROOT = Path(__file__).resolve().parents[2]


def test_service_boundary_timeout_is_redacted_and_never_probes_an_external_host(
    monkeypatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def timeout(endpoint: tuple[str, int], timeout: float) -> None:
        calls.append(endpoint)
        raise TimeoutError(f"deadline:{timeout}")

    monkeypatch.setattr(status_module.socket, "create_connection", timeout)
    status = build_service_status(
        "platform-api",
        environment={
            "WEFLOW_MODE": "service-boundary",
            "WEFLOW_SERVICE_BOUNDARY_TIMEOUT_SECONDS": "0.01",
        },
        root=ROOT,
    )

    assert status["ready"] is False
    assert {component["reason_code"] for component in status["components"]} == {
        "local_dependency_timeout"
    }
    assert calls == [
        ("127.0.0.1", 5432),
        ("127.0.0.1", 7233),
        ("127.0.0.1", 9000),
        ("127.0.0.1", 4317),
    ]


def test_unavailable_dependency_has_a_distinct_reason_and_external_hosts_are_rejected(
    monkeypatch,
) -> None:
    def unavailable(_: tuple[str, int], timeout: float) -> None:
        raise OSError(f"unavailable:{timeout}")

    monkeypatch.setattr(status_module.socket, "create_connection", unavailable)
    status = build_service_status(
        "platform-api",
        environment={"WEFLOW_MODE": "service-boundary"},
        root=ROOT,
    )

    assert {component["reason_code"] for component in status["components"]} == {
        "local_dependency_unavailable"
    }
    with pytest.raises(ValueError, match="loopback"):
        probe_local_dependency("forbidden", ("example.invalid", 443), 0.01)


def test_failure_evidence_and_synthetic_artifact_metadata_exclude_raw_content(
    tmp_path: Path,
) -> None:
    raw_connection = "postgresql://" + "weflow:not-a-secret@127.0.0.1:5432/weflow"
    raw_customer_text = "Jane Example reports a payment API 503 before launch."
    raw_tool_output = "unrestricted simulator output for tenant A"
    evidence = failure_evidence(
        service="platform-api",
        mode="service-boundary",
        component="postgres",
        reason_code="local_dependency_timeout",
        correlation_id="corr-fixture-001",
        raw_error=f"timeout while opening {raw_connection}: {raw_customer_text}",
        raw_tool_output=raw_tool_output,
    )

    rendered = json.dumps(evidence, sort_keys=True)
    assert evidence["resource"]["service.name"] == "platform-api"
    assert evidence["trace"]["weflow.correlation_id"] == "corr-fixture-001"
    assert evidence["attributes"]["reason_code"] == "local_dependency_timeout"
    assert raw_connection not in rendered
    assert raw_customer_text not in rendered
    assert raw_tool_output not in rendered

    stored = store_synthetic_artifact(
        tmp_path,
        '{"fixture_id":"foundation-happy-path","synthetic":true}',
        tenant_id="synthetic-local",
        media_type="application/json",
        created_at="2026-07-29T00:00:00Z",
        producer="business-simulator",
        correlation_id="corr-fixture-001",
    )
    validate_payload(stored["artifact"], ROOT)
    assert "foundation-happy-path" not in json.dumps(stored, sort_keys=True)
    assert stored["storage"]["source"] == "synthetic-fixture"

    with pytest.raises(SyntheticArtifactError, match="synthetic_fixture_source_required"):
        store_synthetic_artifact(
            tmp_path,
            "not-used",
            tenant_id="synthetic-local",
            media_type="text/plain",
            created_at="2026-07-29T00:00:00Z",
            producer="business-simulator",
            correlation_id="corr-fixture-001",
            source="external-provider",
        )
