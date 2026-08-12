from __future__ import annotations

import json
import sys
from pathlib import Path

from weflow_control_kernel.qq_model import (
    QQ_STAGE3_MODEL_CAPABILITIES,
    QQ_STAGE3_QQ_CAPABILITIES,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dev  # noqa: E402


def test_ordinary_command_rejects_stage3_capabilities_before_dispatch(monkeypatch, capsys) -> None:
    monkeypatch.setenv("WEFLOW_QQ_CAPABILITIES", ",".join(QQ_STAGE3_QQ_CAPABILITIES))
    monkeypatch.setenv("WEFLOW_QQ_MODEL_CAPABILITIES", ",".join(QQ_STAGE3_MODEL_CAPABILITIES))
    assert dev.main(["check"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason_code"] == "stage3_configuration_forbidden_for_command"
    assert report["network_contacted"] is False
    assert report["external_write"] is False
    assert report["model_invocation"] is False


def test_ordinary_command_rejects_live_model_credential_without_echo(monkeypatch, capsys) -> None:
    sentinel = "not-a-real-secret"
    monkeypatch.setenv("WEFLOW_LIVE_MODEL_API_KEY", sentinel)
    assert dev.main(["check"]) == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["reason_code"] == "live_model_credential_forbidden_for_command"
    assert sentinel not in output


def test_isolated_live_evaluation_still_rejects_combined_stage3_authority(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("WEFLOW_QQ_MODEL_CAPABILITIES", ",".join(QQ_STAGE3_MODEL_CAPABILITIES))
    assert dev.main(["live-model-evaluation-acceptance"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason_code"] == "stage3_configuration_forbidden_for_command"


def test_parser_construction_does_not_import_combined_live_runner() -> None:
    sys.modules.pop("weflow_control_worker.qq_model_runner", None)
    dev.build_parser()
    assert "weflow_control_worker.qq_model_runner" not in sys.modules
