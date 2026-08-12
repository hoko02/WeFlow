import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dev  # noqa: E402


def test_live_pairing_denies_before_adapter_import_without_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("WEFLOW_QQ_APP_ID", "app")
    monkeypatch.setenv("WEFLOW_QQ_CLIENT_SECRET", "secret")
    monkeypatch.setenv("WEFLOW_QQ_TENANT_ID", "tenant")
    monkeypatch.setenv("WEFLOW_QQ_CAPABILITIES", "qq.group_pair.read")
    assert dev.main(["qq-sandbox-pair-group"]) == 2


def test_ordinary_command_rejects_pairing_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEFLOW_QQ_CAPABILITIES", "qq.group_pair.read")
    assert dev.main(["check"]) == 2


def test_pairing_rejects_group_model_and_write_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "WEFLOW_QQ_APP_ID": "app",
        "WEFLOW_QQ_CLIENT_SECRET": "secret",
        "WEFLOW_QQ_TENANT_ID": "tenant",
        "WEFLOW_QQ_CAPABILITIES": "qq.group_pair.read",
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID": "caller-group",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert dev.main(["qq-sandbox-pair-group", "--confirm-live-qq-pairing"]) == 2
