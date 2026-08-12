from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV_PATH = ROOT / "scripts" / "dev.py"
QQ_ENVIRONMENT = {
    "WEFLOW_QQ_APP_ID": "qq-app-sandbox",
    "WEFLOW_QQ_CLIENT_SECRET": "not-a-real-secret",
    "WEFLOW_QQ_SANDBOX_GROUP_OPENID": "qq-group-sandbox",
    "WEFLOW_QQ_TENANT_ID": "tenant-alpha",
    "WEFLOW_QQ_IDENTITY_SALT": "process-only-salt",
}


def _load_dev_module():
    spec = importlib.util.spec_from_file_location("weflow_dev_qq_isolation", DEV_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_qq_command_requires_exact_confirmation_before_adapter_import(monkeypatch, capsys) -> None:
    dev = _load_dev_module()
    for key, value in QQ_ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    imported: list[str] = []
    original_import = builtins.__import__

    def record_import(name: str, *args: object, **kwargs: object):
        imported.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", record_import)
    assert dev.main(["qq-sandbox-intake-ack"]) == 2
    report = capsys.readouterr().out
    assert "explicit_confirmation_required" in report
    assert "not-a-real-secret" not in report
    assert not any(name.startswith("weflow_control_worker.qq_runner") for name in imported)


def test_ordinary_command_denies_qq_configuration_before_handler(monkeypatch, capsys) -> None:
    dev = _load_dev_module()
    for key, value in QQ_ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    called = False

    def should_not_run(_: object) -> int:
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(dev, "command_check", should_not_run)
    assert dev.main(["check"]) == 2
    assert called is False
    report = capsys.readouterr().out
    assert "qq_configuration_forbidden_for_command" in report
    assert "qq-group-sandbox" not in report
    assert '"network_contacted": false' in report.lower()


def test_qq_plus_model_or_other_write_is_denied_before_adapter_import(monkeypatch, capsys) -> None:
    dev = _load_dev_module()
    for key, value in QQ_ENVIRONMENT.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("WEFLOW_LIVE_MODEL_API_KEY", "model-secret-never-echoed")
    assert dev.main(["qq-sandbox-intake-ack", "--confirm-live-qq"]) == 2
    report = capsys.readouterr().out
    assert "qq_capability_scope_denied" in report
    assert "model-secret-never-echoed" not in report
    assert '"network_contacted": false' in report.lower()


def test_pairing_selector_readiness_only_resolves_without_gateway_import(
    monkeypatch, capsys
) -> None:
    dev = _load_dev_module()
    from weflow_control_kernel import qq_pairing

    pairing_id = "qqpair_" + "1" * 32
    for key in (
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID",
        "WEFLOW_QQ_TENANT_ID",
        "WEFLOW_PROVIDER_API_KEY",
        "WEFLOW_LIVE_MODEL_API_KEY",
        "WEFLOW_PROVIDER_ALLOW_LIVE",
        "WEFLOW_EXTERNAL_WRITE_ENABLED",
        "WEFLOW_MULTI_AGENT_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WEFLOW_PROVIDER_MODE", "replay")
    monkeypatch.setenv("WEFLOW_QQ_APP_ID", "qq-app-sandbox")
    monkeypatch.setenv("WEFLOW_QQ_CLIENT_SECRET", "not-a-real-secret")
    monkeypatch.setenv("WEFLOW_QQ_SANDBOX_PAIRING_ID", pairing_id)
    monkeypatch.setenv("WEFLOW_QQ_IDENTITY_SALT", "process-only-salt")
    monkeypatch.setenv("WEFLOW_QQ_CAPABILITIES", "qq.group_at.read,qq.passive_ack.execute")

    def resolve(values, *, store_path):
        del store_path
        resolved = dict(values)
        resolved["WEFLOW_QQ_SANDBOX_GROUP_OPENID"] = "resolved-private-group"
        resolved["WEFLOW_QQ_TENANT_ID"] = "resolved-tenant"
        return resolved

    monkeypatch.setattr(qq_pairing, "resolve_stage1_pairing_environment", resolve)
    imported: list[str] = []
    original_import = builtins.__import__

    def record_import(name: str, *args: object, **kwargs: object):
        imported.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", record_import)
    assert dev.main(["qq-sandbox-intake-ack", "--confirm-live-qq", "--readiness-only"]) == 0
    report = capsys.readouterr().out
    assert '"selector_mode": "safe-pairing-id"' in report
    assert pairing_id in report
    assert '"network_contacted": false' in report.lower()
    assert '"stage1_verified": false' in report.lower()
    assert "resolved-private-group" not in report
    assert "not-a-real-secret" not in report
    assert not any(name.startswith("weflow_control_worker.qq_runner") for name in imported)


def test_normal_processes_do_not_import_or_register_real_qq_adapter() -> None:
    paths = [
        ROOT / "apps" / "agent-runtime" / "src" / "weflow_agent_runtime" / "main.py",
        ROOT / "apps" / "business-simulator" / "src" / "weflow_business_simulator" / "main.py",
        ROOT / "apps" / "control-worker" / "src" / "weflow_control_worker" / "main.py",
        ROOT / "scripts" / "live_model_cli.py",
        ROOT / "scripts" / "evaluation_benchmark_acceptance.py",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "qq_adapter" not in source
        assert "build_real_qq_gateway_runner" not in source
