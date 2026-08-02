"""Local-only process orchestration for the fixture-backed Change 2 harness."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIRECTORY = ROOT / ".weflow"
STATE_FILE = STATE_DIRECTORY / "processes.json"
LOG_DIRECTORY = STATE_DIRECTORY / "logs"

_LIMITATIONS = [
    "fixture-local-durable-workflow-only",
    "no-business-workflow",
    "no-agent-or-provider",
    "no-approval-or-outbound-delivery",
    "no-customer-resolution",
    "no-external-writes",
]


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    port: int
    command: tuple[str, ...]
    health_path: str = "/health/ready"


def service_definitions() -> tuple[ServiceDefinition, ...]:
    return (
        ServiceDefinition(
            "platform-api",
            8000,
            (
                "uv",
                "run",
                "--package",
                "weflow-platform-api",
                "uvicorn",
                "weflow_platform_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ),
        ),
        ServiceDefinition(
            "control-worker",
            8001,
            (
                "uv",
                "run",
                "--package",
                "weflow-control-worker",
                "python",
                "-m",
                "weflow_control_worker.main",
                "--serve",
                "--port",
                "8001",
            ),
        ),
        ServiceDefinition(
            "agent-runtime",
            8002,
            (
                "uv",
                "run",
                "--package",
                "weflow-agent-runtime",
                "python",
                "-m",
                "weflow_agent_runtime.main",
                "--serve",
                "--port",
                "8002",
            ),
        ),
        ServiceDefinition(
            "business-simulator",
            8003,
            (
                "uv",
                "run",
                "--package",
                "weflow-business-simulator",
                "python",
                "-m",
                "weflow_business_simulator.main",
                "--serve",
                "--port",
                "8003",
            ),
        ),
        ServiceDefinition(
            "web-console",
            5173,
            (
                shutil.which("pnpm") or "pnpm",
                "--filter",
                "@weflow/web-console",
                "dev",
                "--",
                "--port",
                "5173",
                "--strictPort",
            ),
            "/",
        ),
    )


def _read_state() -> dict[str, Any] | None:
    if not STATE_FILE.is_file():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_state(state: dict[str, Any]) -> None:
    STATE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def _remove_state() -> None:
    if STATE_FILE.is_file():
        STATE_FILE.unlink()


def _environment(mode: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "WEFLOW_MODE": mode,
            "WEFLOW_PROVIDER_MODE": "replay",
            "WEFLOW_PROVIDER_ALLOW_LIVE": "false",
            "WEFLOW_EXTERNAL_WRITE_ENABLED": "false",
            "WEFLOW_MULTI_AGENT_ENABLED": "false",
        }
    )
    return environment


def _spawn(definition: ServiceDefinition, environment: dict[str, str]) -> subprocess.Popen[bytes]:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIRECTORY / f"{definition.name}.log"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with log_path.open("ab") as log_file:
        return subprocess.Popen(
            definition.command,
            cwd=ROOT,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )


def _probe(definition: ServiceDefinition) -> dict[str, Any]:
    url = f"http://127.0.0.1:{definition.port}{definition.health_path}"
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:  # noqa: S310 - loopback only
            body = response.read().decode("utf-8")
            if definition.health_path == "/":
                return {
                    "service": definition.name,
                    "live": True,
                    "ready": 200 <= response.status < 300,
                    "state": "ready" if 200 <= response.status < 300 else "not-ready",
                    "mode": "offline",
                    "components": [{"name": "vite-dev-server", "ready": True, "reason_code": None}],
                    "policy_denial": None,
                    "limitations": _LIMITATIONS,
                }
            payload = json.loads(body)
            return payload
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return {
            "service": definition.name,
            "live": False,
            "ready": False,
            "state": "not-started",
            "mode": "unknown",
            "components": [
                {"name": "process", "ready": False, "reason_code": "loopback_health_unavailable"}
            ],
            "policy_denial": None,
            "limitations": _LIMITATIONS,
        }


def _wait_for_ready(
    definitions: tuple[ServiceDefinition, ...], timeout_seconds: float = 15.0
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    statuses = [_probe(definition) for definition in definitions]
    while time.monotonic() < deadline and not all(status.get("ready") for status in statuses):
        time.sleep(0.2)
        statuses = [_probe(definition) for definition in definitions]
    return statuses


def start_services(mode: str) -> dict[str, Any]:
    existing = _read_state()
    if existing is not None:
        return {
            "report_type": "weflow-process-start.v1",
            "started": False,
            "reason_code": "existing_process_state",
            "services": runtime_report()["services"],
        }

    definitions = service_definitions()
    environment = _environment(mode)
    processes: list[dict[str, Any]] = []
    try:
        for definition in definitions:
            process = _spawn(definition, environment)
            processes.append({"name": definition.name, "pid": process.pid, "port": definition.port})
        _write_state({"mode": mode, "services": processes})
        statuses = _wait_for_ready(definitions)
        ready = all(status.get("ready") for status in statuses)
        if not ready:
            stop_services()
        return {
            "report_type": "weflow-process-start.v1",
            "started": ready,
            "mode": mode,
            "services": statuses,
            "business_workflow_implemented": False,
            "durable_support_workflow_implemented": True,
            "external_writes_enabled": False,
        }
    except OSError:
        terminated = _terminate_entries(processes)
        _remove_state()
        return {
            "report_type": "weflow-process-start.v1",
            "started": False,
            "reason_code": "process_spawn_failed",
            "services": terminated,
        }


def _terminate_entries(processes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for process in processes:
        name = str(process.get("name", "unknown"))
        pid = process.get("pid")
        stopped = False
        if isinstance(pid, int) and pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
                stopped = True
            except OSError:
                stopped = True
        results.append({"service": name, "stopped": stopped})
    return results


def stop_services() -> dict[str, Any]:
    state = _read_state()
    if state is None:
        return {"report_type": "weflow-process-stop.v1", "stopped": True, "services": []}

    results = _terminate_entries(list(state.get("services", [])))
    _remove_state()
    return {
        "report_type": "weflow-process-stop.v1",
        "stopped": all(item["stopped"] for item in results),
        "services": results,
    }


def runtime_report() -> dict[str, Any]:
    state = _read_state()
    definitions = service_definitions()
    if state is None:
        statuses = [
            {
                "service": definition.name,
                "live": False,
                "ready": False,
                "state": "not-started",
                "mode": "unknown",
                "components": [{"name": "process", "ready": False, "reason_code": "not_started"}],
                "policy_denial": None,
                "limitations": _LIMITATIONS,
            }
            for definition in definitions
        ]
        mode = "offline"
    else:
        statuses = [_probe(definition) for definition in definitions]
        mode = str(state.get("mode", "offline"))
    return {
        "report_type": "weflow-foundation-health.v1",
        "processes_started": state is not None,
        "operational_ready": all(status.get("ready") for status in statuses),
        "business_workflow_implemented": False,
        "durable_support_workflow_implemented": True,
        "external_writes_enabled": False,
        "mode": mode,
        "services": statuses,
    }
