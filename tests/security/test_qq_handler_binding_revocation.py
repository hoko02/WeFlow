from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import weflow_control_kernel.qq_handler as qq_handler_module
import weflow_control_kernel.qq_pairing as qq_pairing_module
import weflow_control_worker.qq_handler_runner as qq_handler_runner
from weflow_control_kernel.qq_handler import (
    QQ_HANDLER_REVOCATION_CONFIRMATION,
    QQHandlerAuthorizationDenied,
    begin_handler_pairing,
    normalize_handler_pairing_event,
)

ROOT = Path(__file__).resolve().parents[2]
UNIT = ROOT / "tests" / "unit"
SCRIPTS = ROOT / "scripts"
for directory in (UNIT, SCRIPTS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import dev  # noqa: E402
from test_qq_handler_workflow import (  # noqa: E402
    insert_stage1_locator,
    pair_handler,
)


def _observe_replacement(cfg, journal, clock, session) -> None:
    events = (
        (
            session.group,
            {
                "t": "GROUP_AT_MESSAGE_CREATE",
                "s": 501,
                "d": {
                    "id": "group-rebind-msg",
                    "content": f"@机器人 {session.group.plaintext}",
                    "timestamp": clock().isoformat().replace("+00:00", "Z"),
                    "group_openid": cfg.group_openid,
                    "author": {"member_openid": "member-raw-1"},
                },
            },
        ),
        (
            session.c2c,
            {
                "t": "C2C_MESSAGE_CREATE",
                "s": 502,
                "d": {
                    "id": "c2c-rebind-msg",
                    "content": session.c2c.plaintext,
                    "timestamp": clock().isoformat().replace("+00:00", "Z"),
                    "author": {"user_openid": "user-raw-1"},
                },
            },
        ),
    )
    for challenge, event in events:
        journal.record_pairing_observation(
            challenge,
            normalize_handler_pairing_event(
                event,
                config=cfg,
                challenge=challenge,
                now=clock(),
            ),
        )


def test_local_revocation_is_idempotent_scrubs_locators_and_permits_rebinding(
    tmp_path: Path,
) -> None:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    refreshed = replace(
        cfg,
        stage1_pairing_id="qqpair_22222222222222222222222222222222",
    )
    insert_stage1_locator(journal, refreshed, clock)
    with closing(sqlite3.connect(journal.path)) as connection:
        immutable_record = connection.execute(
            "SELECT record_json FROM qq_handler_bindings WHERE handler_binding_id=?",
            (binding["handler_binding_id"],),
        ).fetchone()[0]

    report = journal.revoke_handler_binding(
        config=refreshed,
        handler_binding_id=binding["handler_binding_id"],
        operator_confirmation=QQ_HANDLER_REVOCATION_CONFIRMATION,
    )

    assert report["revoked"] is True
    assert report["already_revoked"] is False
    assert report["locator_deactivation_count"] == 2
    assert report["network_contacted"] is False
    assert report["qq_write_attempted"] is False
    assert report["external_write_attempted"] is False
    assert report["case_mutation"] is False
    assert report["model_invocation"] is False
    with pytest.raises(QQHandlerAuthorizationDenied, match="handler_binding_inactive"):
        journal.active_binding(binding["handler_binding_id"])
    for kind in ("group-member", "c2c-user"):
        with pytest.raises(
            QQHandlerAuthorizationDenied,
            match="handler_private_locator_inactive",
        ):
            journal.private_locator(binding["handler_binding_id"], kind)

    repeated = journal.revoke_handler_binding(
        config=refreshed,
        handler_binding_id=binding["handler_binding_id"],
        operator_confirmation=QQ_HANDLER_REVOCATION_CONFIRMATION,
    )
    assert repeated["already_revoked"] is True
    assert repeated["revocation_event_id"] == report["revocation_event_id"]

    with closing(sqlite3.connect(journal.path)) as connection:
        connection.row_factory = sqlite3.Row
        stored_binding = connection.execute(
            "SELECT status, record_json FROM qq_handler_bindings WHERE handler_binding_id=?",
            (binding["handler_binding_id"],),
        ).fetchone()
        locators = connection.execute(
            "SELECT provider_locator, status FROM qq_handler_private_locators "
            "WHERE handler_binding_id=? ORDER BY locator_kind",
            (binding["handler_binding_id"],),
        ).fetchall()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM qq_handler_events WHERE aggregate_id=? "
            "AND event_kind='HANDLER_BINDING_REVOKED'",
            (binding["handler_binding_id"],),
        ).fetchone()[0]
    assert stored_binding["status"] == "ACTIVE"
    assert stored_binding["record_json"] == immutable_record
    assert [(row["provider_locator"], row["status"]) for row in locators] == [
        ("", "REVOKED"),
        ("", "REVOKED"),
    ]
    assert event_count == 1

    tokens = iter(("r" * 32, "s" * 32))
    session = begin_handler_pairing(
        refreshed,
        clock=clock,
        token_factory=lambda: next(tokens),
        contract_root=ROOT,
    )
    journal.record_pairing_session(session)
    _observe_replacement(refreshed, journal, clock, session)
    replacement = journal.confirm_handler_binding(
        config=refreshed,
        pairing_session_id=session.session_id,
        operator_confirmation="CONFIRM-DUAL-QQ-HANDLER",
    )
    assert replacement["handler_binding_id"] != binding["handler_binding_id"]
    assert replacement["stage1_pairing_id"] == refreshed.stage1_pairing_id


def test_local_revocation_rejects_wrong_confirmation_and_foreign_scope(
    tmp_path: Path,
) -> None:
    cfg, journal, _, binding = pair_handler(tmp_path)
    with pytest.raises(
        QQHandlerAuthorizationDenied,
        match="handler_local_revocation_confirmation_required",
    ):
        journal.revoke_handler_binding(
            config=cfg,
            handler_binding_id=binding["handler_binding_id"],
            operator_confirmation="REVOKE",
        )
    with pytest.raises(
        QQHandlerAuthorizationDenied,
        match="handler_revocation_scope_mismatch",
    ):
        journal.revoke_handler_binding(
            config=replace(cfg, group_openid="foreign-group"),
            handler_binding_id=binding["handler_binding_id"],
            operator_confirmation=QQ_HANDLER_REVOCATION_CONFIRMATION,
        )

    assert journal.active_binding(binding["handler_binding_id"])
    with closing(sqlite3.connect(journal.path)) as connection:
        event_count = connection.execute(
            "SELECT COUNT(*) FROM qq_handler_events WHERE event_kind='HANDLER_BINDING_REVOKED'"
        ).fetchone()[0]
        locator_rows = connection.execute(
            "SELECT provider_locator, status FROM qq_handler_private_locators "
            "WHERE handler_binding_id=?",
            (binding["handler_binding_id"],),
        ).fetchall()
    assert event_count == 0
    assert all(value and status == "ACTIVE" for value, status in locator_rows)


def test_revoke_command_stays_local_and_reports_only_safe_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    binding_id = "qqhbind_" + "1" * 32
    fake_config = SimpleNamespace(
        safe_readiness=lambda **_: {"ready": True},
    )

    class FakeJournal:
        def revoke_handler_binding(self, **kwargs):
            assert kwargs["config"] is fake_config
            assert kwargs["handler_binding_id"] == binding_id
            assert kwargs["operator_confirmation"] == QQ_HANDLER_REVOCATION_CONFIRMATION
            return {
                "report_type": "weflow-qq-handler-binding-revocation.v1",
                "handler_binding_id": binding_id,
                "revocation_event_id": "qqhe_" + "2" * 32,
                "revoked": True,
                "already_revoked": False,
                "locator_deactivation_count": 2,
                "reason_code": "handler_binding_revoked_by_local_operator",
                "network_contacted": False,
                "qq_write_attempted": False,
                "external_write_attempted": False,
                "case_mutation": False,
                "model_invocation": False,
                "production_ready": False,
            }

    monkeypatch.setattr(
        qq_pairing_module,
        "resolve_stage1_pairing_environment",
        lambda *_args, **_kwargs: {
            "WEFLOW_QQ_SANDBOX_GROUP_OPENID": "private-group-not-reported",
            "WEFLOW_QQ_HANDLER_BINDING_ID": binding_id,
        },
    )
    monkeypatch.setattr(
        qq_handler_module.QQHandlerConfig,
        "from_environment",
        classmethod(lambda _cls, **_kwargs: fake_config),
    )
    monkeypatch.setattr(
        qq_handler_runner,
        "build_handler_journal",
        lambda _config: FakeJournal(),
    )
    monkeypatch.setattr(
        qq_handler_runner._LiveGateway,
        "__init__",
        lambda *_args, **_kwargs: pytest.fail("revocation constructed live gateway"),
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: QQ_HANDLER_REVOCATION_CONFIRMATION)
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    arguments = argparse.Namespace(
        offline_acceptance=False,
        confirm_live_qq=True,
        store=".weflow/qq-sandbox.sqlite3",
        handler_binding_id=binding_id,
        readiness_only=False,
        pair_handler=False,
        revoke_handler_binding=True,
        probe_c2c=False,
        probe_group_approval=False,
        output=None,
    )

    code = dev.command_qq_handler_approval(arguments)
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert report["revoked"] is True
    assert report["network_contacted"] is False
    assert report["qq_write_attempted"] is False
    assert report["external_write_attempted"] is False
    assert report["case_mutation"] is False
    assert report["model_invocation"] is False
    serialized = json.dumps(report, sort_keys=True)
    for forbidden in (
        "private-group-not-reported",
        "member_openid",
        "user_openid",
        "provider_locator",
        "client_secret",
        "content",
    ):
        assert forbidden not in serialized


def test_runbook_documents_scope_bound_local_revocation() -> None:
    text = (
        ROOT / "docs" / "development" / "qq-sandbox-handler-approval-and-delivery.md"
    ).read_text(encoding="utf-8")

    for required in (
        "--revoke-handler-binding",
        QQ_HANDLER_REVOCATION_CONFIRMATION,
        "network_contacted=false",
        "qq_write_attempted=false",
        "case_mutation=false",
        "不要修改或删除 SQLite",
        "不属于允许的恢复路径",
    ):
        assert required in text
