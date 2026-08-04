"""Truthful liveness/readiness reporting for skeleton service boundaries."""

from __future__ import annotations

import socket
from collections.abc import Mapping
from pathlib import Path

from .config import ConfigurationDenied, load_config

SERVICE_NAMES = (
    "platform-api",
    "control-worker",
    "agent-runtime",
    "business-simulator",
    "web-console",
)

_LIMITATIONS = [
    "fixture-local-durable-workflow-only",
    "no-business-workflow",
    "fixture-local-replay-agent-only",
    "live_provider_disabled",
    "fixture-local-policy-approval-delivery-only",
    "no-live-approval-service",
    "no-real-outbound-delivery",
    "no-customer-resolution",
    "no-external-writes",
]

_LOCAL_DEPENDENCIES = {
    "postgres": ("127.0.0.1", 5432),
    "temporal": ("127.0.0.1", 7233),
    "object-store": ("127.0.0.1", 9000),
    "otel-collector": ("127.0.0.1", 4317),
}


def find_repository_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__).resolve()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "contracts").is_dir():
            return candidate
    raise RuntimeError("WeFlow repository root could not be located")


def _component(name: str, ready: bool, reason_code: str | None = None) -> dict[str, object]:
    return {
        "name": name,
        "ready": ready,
        "reason_code": reason_code,
    }


def _offline_components(root: Path) -> list[dict[str, object]]:
    contracts_ready = (root / "contracts" / "jsonschema" / "v1").is_dir()
    fixtures_ready = (root / "fixtures" / "replay").is_dir()
    investigation_fixtures_ready = (root / "fixtures" / "investigation").is_dir()
    policy_fixture_ready = (
        root / "fixtures" / "policy" / "api-503-policy-approval-delivery.json"
    ).is_file()
    return [
        _component(
            "contract-assets", contracts_ready, None if contracts_ready else "assets_missing"
        ),
        _component(
            "replay-fixtures", fixtures_ready, None if fixtures_ready else "fixtures_missing"
        ),
        _component(
            "investigation-fixtures",
            investigation_fixtures_ready,
            None if investigation_fixtures_ready else "fixtures_missing",
        ),
        _component(
            "policy-approval-delivery-fixture",
            policy_fixture_ready,
            None if policy_fixture_ready else "fixtures_missing",
        ),
    ]


def probe_local_dependency(
    name: str,
    endpoint: tuple[str, int],
    timeout_seconds: float,
) -> dict[str, object]:
    """Probe only a declared loopback dependency, with a bounded deadline."""

    host, _ = endpoint
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("local_dependency_probe_requires_loopback")
    try:
        with socket.create_connection(endpoint, timeout=timeout_seconds):
            return _component(name, True)
    except TimeoutError:
        return _component(name, False, "local_dependency_timeout")
    except OSError:
        return _component(name, False, "local_dependency_unavailable")


def _service_boundary_components(timeout_seconds: float) -> list[dict[str, object]]:
    return [
        probe_local_dependency(name, endpoint, timeout_seconds)
        for name, endpoint in _LOCAL_DEPENDENCIES.items()
    ]


def build_service_status(
    service_name: str,
    environment: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    """Build a redacted operational report; this never reports business success."""

    if service_name not in SERVICE_NAMES:
        raise ValueError(f"Unknown WeFlow service: {service_name}")

    repository_root = root or find_repository_root()
    try:
        config = load_config(environment)
    except ConfigurationDenied as denial:
        return {
            "service": service_name,
            "live": True,
            "ready": False,
            "state": "configuration-denied",
            "mode": "unknown",
            "components": [_component("configuration", False, denial.reason_code)],
            "policy_denial": denial.as_dict(),
            "limitations": _LIMITATIONS,
        }

    components = (
        _offline_components(repository_root)
        if config.mode == "offline"
        else _service_boundary_components(config.service_boundary_timeout_seconds)
    )
    ready = all(bool(component["ready"]) for component in components)
    return {
        "service": service_name,
        "live": True,
        "ready": ready,
        "state": "ready" if ready else "not-ready",
        "mode": config.mode,
        "components": components,
        "policy_denial": None,
        "limitations": _LIMITATIONS,
    }


def build_foundation_report(
    environment: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    """Return machine-readable operational evidence for the bounded Change 4 harness."""

    repository_root = root or find_repository_root()
    statuses = [
        build_service_status(name, environment=environment, root=repository_root)
        for name in SERVICE_NAMES
    ]
    durable_workflow_assets = all(
        (repository_root / "contracts" / "jsonschema" / "v1" / filename).is_file()
        for filename in (
            "workflow-projection.schema.json",
            "workflow-checkpoint.schema.json",
            "workflow-command.schema.json",
            "side-effect-intent.schema.json",
        )
    )
    replay_investigation_assets = all(
        (repository_root / "contracts" / "jsonschema" / "v1" / filename).is_file()
        for filename in (
            "context-manifest.schema.json",
            "agent-action.schema.json",
            "tool-request.schema.json",
            "tool-result.schema.json",
            "response-candidate.schema.json",
            "verifier-outcome.schema.json",
        )
    ) and all(
        (repository_root / "fixtures" / "investigation" / filename).is_file()
        for filename in (
            "api-503-investigation.transcript.json",
            "api-503-investigation.tools.json",
        )
    )
    fixture_policy_approval_delivery_assets = (
        all(
            (repository_root / "contracts" / "jsonschema" / "v1" / filename).is_file()
            for filename in (
                "authorization-binding.schema.json",
                "outbound-delivery-intent.schema.json",
                "outbound-delivery-observation.schema.json",
                "outbound-delivery-completion.schema.json",
            )
        )
        and (
            repository_root / "fixtures" / "policy" / "api-503-policy-approval-delivery.json"
        ).is_file()
    )
    return {
        "report_type": "weflow-foundation-health.v1",
        "operational_ready": all(bool(status["ready"]) for status in statuses),
        "business_workflow_implemented": False,
        "durable_support_workflow_implemented": durable_workflow_assets,
        "replay_investigation_agent_implemented": replay_investigation_assets,
        "response_candidate_verification_implemented": replay_investigation_assets,
        "fixture_policy_approval_delivery_implemented": fixture_policy_approval_delivery_assets,
        "fixture_approval_enabled": fixture_policy_approval_delivery_assets,
        "fixture_outbound_delivery_enabled": fixture_policy_approval_delivery_assets,
        "live_approval_enabled": False,
        "live_outbound_delivery_enabled": False,
        "real_provider_enabled": False,
        "multi_agent_enabled": False,
        "external_writes_enabled": False,
        "approval_enabled": False,
        "outbound_delivery_enabled": False,
        "customer_resolution_enabled": False,
        "services": statuses,
    }
