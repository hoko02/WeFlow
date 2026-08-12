from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import QQ_HANDLER_REQUIRED_CAPABILITIES
from weflow_control_kernel.qq_pairing import QQGroupPairingConfig, QQPairingActivationDenied
from weflow_control_kernel.qq_sandbox import QQActivationDenied, QQSandboxConfig

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dev  # noqa: E402


def test_ordinary_command_rejects_stage2_configuration_before_dispatch(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("WEFLOW_QQ_HANDLER_BINDING_ID", "qqhbind_" + "1" * 32)
    monkeypatch.setenv(
        "WEFLOW_QQ_CAPABILITIES", ",".join(QQ_HANDLER_REQUIRED_CAPABILITIES)
    )

    code = dev.main(["check"])
    report = json.loads(capsys.readouterr().out)

    assert code == 2
    assert report["reason_code"] == "handler_configuration_forbidden_for_command"
    assert report["network_contacted"] is False
    assert report["external_write"] is False
    assert report["model_invocation"] is False


def test_stage1_configs_reject_stage2_capability_profile(tmp_path: Path) -> None:
    values = {
        "WEFLOW_QQ_APP_ID": "synthetic-app",
        "WEFLOW_QQ_CLIENT_SECRET": "not-a-real-secret",
        "WEFLOW_QQ_TENANT_ID": "synthetic-tenant",
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID": "synthetic-group",
        "WEFLOW_QQ_IDENTITY_SALT": "s" * 32,
        "WEFLOW_QQ_CAPABILITIES": ",".join(QQ_HANDLER_REQUIRED_CAPABILITIES),
    }
    with pytest.raises(QQActivationDenied, match="capability_scope_denied"):
        QQSandboxConfig.from_environment(
            confirm_live=True,
            environ=values,
            live_model_enabled=False,
            other_external_write_enabled=False,
        )
    pairing_values = {
        key: values[key]
        for key in ("WEFLOW_QQ_APP_ID", "WEFLOW_QQ_CLIENT_SECRET", "WEFLOW_QQ_TENANT_ID")
    }
    pairing_values["WEFLOW_QQ_CAPABILITIES"] = values["WEFLOW_QQ_CAPABILITIES"]
    with pytest.raises(QQPairingActivationDenied, match="capability_scope_denied"):
        QQGroupPairingConfig.from_environment(
            confirm_live_pairing=True,
            store_path=tmp_path / ".weflow" / "qq-sandbox.sqlite3",
            repository_root=tmp_path,
            environ=pairing_values,
            model_enabled=False,
            external_write_enabled=False,
            multi_agent_enabled=False,
        )


def test_stage1_runners_do_not_import_stage2_transport_or_workflow() -> None:
    for relative in (
        "apps/control-worker/src/weflow_control_worker/qq_runner.py",
        "apps/control-worker/src/weflow_control_worker/qq_pairing_runner.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "qq_handler_adapter" not in source
        assert "qq_handler_runner" not in source
        assert "QQHandlerWorkflowService" not in source
