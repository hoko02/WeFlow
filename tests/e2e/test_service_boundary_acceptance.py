import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from weflow_control_kernel import status as status_module
from weflow_control_kernel.status import build_service_status
from weflow_telemetry import failure_evidence

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def docker_is_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        ).returncode
        == 0
    )


pytestmark = pytest.mark.skipif(
    not docker_is_ready(),
    reason="Docker unavailable: service-boundary acceptance requires local Compose dependencies.",
)


def run_dev(*arguments: str, expected: int) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(DEV), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == expected, completed.stdout
    return json.loads(completed.stdout) if completed.stdout.lstrip().startswith("{") else {}


def test_service_boundary_dependencies_and_timeout_evidence_remain_local_only(monkeypatch) -> None:
    run_dev("down", expected=0)
    run_dev("compose", "up", expected=0)
    try:
        deadline = time.monotonic() + 60
        status = build_service_status(
            "platform-api",
            environment={
                "WEFLOW_MODE": "service-boundary",
                "WEFLOW_SERVICE_BOUNDARY_TIMEOUT_SECONDS": "0.25",
            },
            root=ROOT,
        )
        while time.monotonic() < deadline and not status["ready"]:
            time.sleep(0.5)
            status = build_service_status(
                "platform-api",
                environment={
                    "WEFLOW_MODE": "service-boundary",
                    "WEFLOW_SERVICE_BOUNDARY_TIMEOUT_SECONDS": "0.25",
                },
                root=ROOT,
            )

        assert status["ready"] is True
        assert all(component["ready"] for component in status["components"])
        start = run_dev("up", "--mode", "service-boundary", expected=0)
        health = run_dev("health", expected=0)
        assert start["started"] is True
        assert health["operational_ready"] is True

        def timeout(_: tuple[str, int], timeout: float) -> None:
            raise TimeoutError(f"deadline:{timeout}")

        monkeypatch.setattr(status_module.socket, "create_connection", timeout)
        injected = build_service_status(
            "platform-api",
            environment={
                "WEFLOW_MODE": "service-boundary",
                "WEFLOW_SERVICE_BOUNDARY_TIMEOUT_SECONDS": "0.01",
            },
            root=ROOT,
        )
        evidence = failure_evidence(
            service="platform-api",
            mode="service-boundary",
            component="postgres",
            reason_code="local_dependency_timeout",
            correlation_id="compose-timeout-fixture",
            raw_error="postgresql://" + "weflow:not-a-secret@127.0.0.1:5432/weflow",
        )
        assert injected["ready"] is False
        assert all(
            component["reason_code"] == "local_dependency_timeout"
            for component in injected["components"]
        )
        assert "not-a-secret" not in json.dumps(evidence, sort_keys=True)
    finally:
        run_dev("down", expected=0)
        run_dev("compose", "down", expected=0)
