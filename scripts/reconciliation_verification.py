#!/usr/bin/env python
"""Run the offline aggregate verification suite with a bounded, redacted result."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTER_TIMEOUT_SECONDS = 900
COMMAND = ("uv", "run", "python", "scripts/dev.py", "test")


def _node_version() -> str | None:
    if shutil.which("node") is None:
        return None
    try:
        completed = subprocess.run(
            ["node", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = completed.stdout.strip()
    if completed.returncode != 0 or not version.startswith("v"):
        return None
    return version


def _environment() -> dict[str, object]:
    return {
        "node_available": shutil.which("node") is not None,
        "node_version": _node_version(),
        "docker_available": shutil.which("docker") is not None,
    }


def _limitations(environment: dict[str, object]) -> list[str]:
    limitations = ["offline_only", "network_not_required", "model_credentials_not_required"]
    if environment["docker_available"] is False:
        limitations.append("docker_unavailable")
    node_version = environment["node_version"]
    if node_version is None:
        limitations.append("node_unavailable")
    else:
        limitations.append(f"node_version_{str(node_version).replace('.', '_')}_observed")
    return limitations


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> bool:
    """Terminate only the process group created by this runner."""

    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
        return completed.returncode == 0
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def _process_kwargs() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _report(
    *,
    environment: dict[str, object],
    outcome: str,
    elapsed_seconds: float,
    exit_code: int | None,
    cleanup: dict[str, bool],
    extra_limitations: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "report_type": "weflow-change-4-5-reconciliation-verification.v1",
        "command": " ".join(COMMAND),
        "outcome": outcome,
        "elapsed_seconds": elapsed_seconds,
        "exit_code": exit_code,
        "outer_timeout_seconds": OUTER_TIMEOUT_SECONDS,
        "cleanup": cleanup,
        "environment": environment,
        "limitations": _limitations(environment) + list(extra_limitations),
    }


def run_aggregate_verification(root: Path = ROOT) -> dict[str, Any]:
    """Run the declared test surface and retain only safe command facts."""

    environment = _environment()
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            COMMAND,
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_process_kwargs(),
        )
    except OSError:
        return _report(
            environment=environment,
            outcome="unavailable",
            elapsed_seconds=round(time.monotonic() - started, 6),
            exit_code=None,
            cleanup={"required": False, "completed": True},
            extra_limitations=("aggregate_command_unavailable",),
        )

    try:
        exit_code = process.wait(timeout=OUTER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return _report(
            environment=environment,
            outcome="timed_out",
            elapsed_seconds=round(time.monotonic() - started, 6),
            exit_code=None,
            cleanup={"required": True, "completed": _terminate_process_tree(process)},
        )
    return _report(
        environment=environment,
        outcome="passed" if exit_code == 0 else "failed",
        elapsed_seconds=round(time.monotonic() - started, 6),
        exit_code=exit_code,
        cleanup={"required": False, "completed": True},
    )


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    report = run_aggregate_verification()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["outcome"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
