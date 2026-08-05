import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
DEV_PATH = ROOT / "scripts" / "dev.py"


def _load_dev_module():
    spec = importlib.util.spec_from_file_location("weflow_dev", DEV_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_accepts_required_command_surface() -> None:
    dev = _load_dev_module()
    parser = dev.build_parser()

    assert parser.parse_args(["check"]).command == "check"
    assert parser.parse_args(["up", "--mode", "offline"]).mode == "offline"
    assert parser.parse_args(["compose", "status"]).action == "status"
    assert parser.parse_args(["case-intake-acceptance"]).command == "case-intake-acceptance"
    assert (
        parser.parse_args(["durable-workflow-acceptance"]).command == "durable-workflow-acceptance"
    )
    assert parser.parse_args(["archive-evidence-check"]).command == "archive-evidence-check"
    assert (
        parser.parse_args(["reconciliation-verification"]).command
        == "reconciliation-verification"
    )


def test_environment_check_rejects_forbidden_provider_without_echoing_value(monkeypatch) -> None:
    dev = _load_dev_module()
    monkeypatch.setattr(dev.shutil, "which", lambda _: "available")
    environment = {
        "WEFLOW_MODE": "offline",
        "WEFLOW_PROVIDER_MODE": "live-model",
        "WEFLOW_PROVIDER_ALLOW_LIVE": "false",
    }

    code, report = dev.check_environment(environment)

    assert code == 2
    assert report["policy_denial"] == {
        "capability": "live_provider",
        "reason_code": "replay_only",
        "status": "denied",
    }
    assert "live-model" not in str(report)


def test_lint_runs_secret_hygiene_before_language_checks(monkeypatch) -> None:
    dev = _load_dev_module()
    calls: list[list[str]] = []

    def record(command: list[str]) -> int:
        calls.append(command)
        return 0

    monkeypatch.setattr(dev, "_run", record)

    assert dev.command_lint(dev.build_parser().parse_args(["lint"])) == 0
    assert calls[0] == [dev.sys.executable, "scripts/scan_secrets.py"]
    assert calls[1] == ["uv", "run", "ruff", "check", "."]
    assert calls[2] == ["pnpm", "lint"]


def test_compose_up_uses_detached_local_command(monkeypatch) -> None:
    dev = _load_dev_module()
    calls: list[list[str]] = []
    monkeypatch.setattr(dev.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(dev, "_run", lambda command: calls.append(command) or 0)

    assert dev.command_compose(dev.build_parser().parse_args(["compose", "up"])) == 0
    assert calls == [
        ["docker", "compose", "-f", "deploy/compose/docker-compose.yml", "up", "--detach"]
    ]


def test_windows_cmd_shim_uses_the_local_command_interpreter(monkeypatch) -> None:
    dev = _load_dev_module()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(dev.os, "name", "nt")
    monkeypatch.setattr(dev.shutil, "which", lambda _: r"C:\\tools\\pnpm.cmd")
    monkeypatch.setattr(dev.subprocess, "run", fake_run)

    assert dev._run(["pnpm", "--version"]) == 0
    assert calls == [
        ([r"C:\\tools\\pnpm.cmd", "--version"], {"cwd": ROOT, "check": False, "shell": True})
    ]
