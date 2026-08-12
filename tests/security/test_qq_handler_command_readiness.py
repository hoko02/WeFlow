from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from weflow_control_kernel.qq_handler import QQ_HANDLER_REQUIRED_CAPABILITIES
from weflow_control_kernel.qq_pairing import SQLiteQQPairingJournal

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dev  # noqa: E402


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_handler_readiness_resolves_selector_without_network_write_or_case_mutation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    store = tmp_path / ".weflow" / "qq-sandbox.sqlite3"
    SQLiteQQPairingJournal(store)
    app_id = "synthetic-readiness-app"
    tenant_id = "synthetic-readiness-tenant"
    group_openid = "synthetic-readiness-group"
    pairing_id = "qqpair_11111111111111111111111111111111"
    with closing(sqlite3.connect(store)) as connection:
        connection.execute(
            "INSERT INTO qq_pairing_locators VALUES(?,?,?,?,?,?,?,?)",
            (
                pairing_id,
                _hash(app_id),
                tenant_id,
                _hash(tenant_id),
                group_openid,
                _hash(group_openid),
                (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "COMPLETED",
            ),
        )
        connection.commit()

    for key in (
        "WEFLOW_PROVIDER_API_KEY",
        "WEFLOW_PROVIDER_ALLOW_LIVE",
        "WEFLOW_EXTERNAL_WRITE_ENABLED",
        "WEFLOW_MULTI_AGENT_ENABLED",
        "WEFLOW_QQ_MAIL_ENABLED",
        "WEFLOW_QQ_ATTACHMENT_ENABLED",
        "WEFLOW_LIVE_MODEL_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WEFLOW_PROVIDER_MODE", "replay")
    monkeypatch.setenv("WEFLOW_QQ_APP_ID", app_id)
    monkeypatch.setenv("WEFLOW_QQ_CLIENT_SECRET", "synthetic-process-only-secret")
    monkeypatch.delenv("WEFLOW_QQ_TENANT_ID", raising=False)
    monkeypatch.setenv("WEFLOW_QQ_SANDBOX_PAIRING_ID", pairing_id)
    monkeypatch.setenv("WEFLOW_QQ_IDENTITY_SALT", "s" * 32)
    monkeypatch.setenv(
        "WEFLOW_QQ_CAPABILITIES", ",".join(QQ_HANDLER_REQUIRED_CAPABILITIES)
    )
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    arguments = argparse.Namespace(
        offline_acceptance=False,
        confirm_live_qq=True,
        store=".weflow/qq-sandbox.sqlite3",
        handler_binding_id=None,
        readiness_only=True,
        pair_handler=False,
        probe_c2c=False,
        output=None,
    )

    code = dev.command_qq_handler_approval(arguments)
    report = json.loads(capsys.readouterr().out)

    assert code == 0, report.get("reason_code")
    assert report["ready"] is True
    assert report["selector_resolved"] is True
    assert report["network_contacted"] is False
    assert report["external_write_attempted"] is False
    assert report["case_mutation"] is False
    assert report["model_invocation"] is False
    with closing(sqlite3.connect(store)) as connection:
        stage2_tables = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'qq_handler_%'"
        ).fetchone()[0]
    assert stage2_tables == 0
