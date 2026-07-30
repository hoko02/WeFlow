import importlib.util
from pathlib import Path

from weflow_control_kernel.status import build_service_status

ROOT = Path(__file__).resolve().parents[2]


def _load_dev_module():
    path = ROOT / "scripts" / "dev.py"
    spec = importlib.util.spec_from_file_location("weflow_dev_for_compose", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compose_definition_declares_local_only_required_dependencies() -> None:
    compose = (ROOT / "deploy/compose/docker-compose.yml").read_text(encoding="utf-8")

    for service in ("postgres:", "temporal:", "minio:", "otel-collector:"):
        assert service in compose
    assert "127.0.0.1:5432:5432" in compose
    assert "127.0.0.1:7233:7233" in compose
    assert "127.0.0.1:9000:9000" in compose
    assert "127.0.0.1:4317:4317" in compose


def test_service_boundary_mode_fails_ready_when_local_dependencies_are_missing() -> None:
    status = build_service_status(
        "platform-api",
        environment={
            "WEFLOW_MODE": "service-boundary",
            "WEFLOW_SERVICE_BOUNDARY_TIMEOUT_SECONDS": "0.01",
        },
        root=ROOT,
    )

    assert not status["ready"]
    assert status["state"] == "not-ready"
    assert all(
        component["reason_code"]
        in {
            "local_dependency_unavailable",
            "local_dependency_timeout",
        }
        for component in status["components"]
    )


def test_compose_command_reports_a_redacted_docker_unavailable_reason(monkeypatch, capsys) -> None:
    dev = _load_dev_module()
    monkeypatch.setattr(dev.shutil, "which", lambda _: None)
    arguments = dev.build_parser().parse_args(["compose", "status"])

    assert arguments.handler(arguments) == 2
    output = capsys.readouterr().out
    assert "docker_unavailable" in output
    assert "connection" not in output.lower()
