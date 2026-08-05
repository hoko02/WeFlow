import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "reconciliation_verification.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("weflow_reconciliation_verification", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aggregate_verification_records_a_completed_zero_exit_run(monkeypatch) -> None:
    module = _load_module()
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
    process = SimpleNamespace(wait=lambda timeout: 0)

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(
        module,
        "_environment",
        lambda: {"node_available": True, "node_version": "v22.21.1", "docker_available": False},
    )
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    report = module.run_aggregate_verification(ROOT)

    assert report["outcome"] == "passed"
    assert report["exit_code"] == 0
    assert report["cleanup"] == {"required": False, "completed": True}
    assert calls[0][0] == module.COMMAND
    assert calls[0][1]["stdout"] is subprocess.DEVNULL
    assert calls[0][1]["stderr"] is subprocess.DEVNULL


def test_aggregate_verification_records_timeout_and_owned_process_cleanup(monkeypatch) -> None:
    module = _load_module()

    def timed_out(timeout):
        raise subprocess.TimeoutExpired(module.COMMAND, timeout)

    process = SimpleNamespace(wait=timed_out, pid=456)
    monkeypatch.setattr(
        module,
        "_environment",
        lambda: {"node_available": False, "node_version": None, "docker_available": False},
    )
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(module, "_terminate_process_tree", lambda owned: owned is process)

    report = module.run_aggregate_verification(ROOT)

    assert report["outcome"] == "timed_out"
    assert report["exit_code"] is None
    assert report["cleanup"] == {"required": True, "completed": True}
    assert "node_unavailable" in report["limitations"]
