from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest
from test_qq_handler_security import ROOT
from weflow_control_kernel.qq_handler import (
    QQHandlerAuthorizationDenied,
    QQHandlerEventRejected,
    begin_handler_pairing,
    normalize_handler_pairing_event,
)

UNIT = Path(__file__).resolve().parents[1] / "unit"
if str(UNIT) not in sys.path:
    sys.path.insert(0, str(UNIT))

from test_qq_handler_workflow import config, insert_stage1_locator, pair_handler  # noqa: E402


def observe_both(cfg, journal, clock, session, *, suffix: str) -> None:
    events = (
        (
            session.group,
            {
                "t": "GROUP_AT_MESSAGE_CREATE",
                "s": 100,
                "d": {
                    "id": f"group-{suffix}",
                    "content": f"@机器人 {session.group.plaintext}",
                    "timestamp": clock().isoformat().replace("+00:00", "Z"),
                    "group_openid": cfg.group_openid,
                    "author": {"member_openid": f"member-{suffix}"},
                },
            },
        ),
        (
            session.c2c,
            {
                "t": "C2C_MESSAGE_CREATE",
                "s": 101,
                "d": {
                    "id": f"c2c-{suffix}",
                    "content": session.c2c.plaintext,
                    "timestamp": clock().isoformat().replace("+00:00", "Z"),
                    "author": {"user_openid": f"user-{suffix}"},
                },
            },
        ),
    )
    for challenge, event in events:
        journal.record_pairing_observation(
            challenge,
            normalize_handler_pairing_event(
                event, config=cfg, challenge=challenge, now=clock()
            ),
        )


@pytest.mark.parametrize("field", ["app_id", "tenant_id"])
def test_dual_pairing_cannot_be_confirmed_under_changed_app_or_tenant(
    tmp_path: Path, field: str
) -> None:
    _, _, seed_clock, _ = pair_handler(tmp_path / "seed")
    cfg, journal = config(tmp_path, seed_clock)
    insert_stage1_locator(journal, cfg, seed_clock)
    tokens = iter(("a" * 32, "b" * 32))
    session = begin_handler_pairing(
        cfg, clock=seed_clock, token_factory=lambda: next(tokens), contract_root=ROOT
    )
    journal.record_pairing_session(session)
    observe_both(cfg, journal, seed_clock, session, suffix="mismatch")
    changed = replace(cfg, **{field: f"changed-{field}"})

    with pytest.raises(QQHandlerAuthorizationDenied, match="configuration_mismatch"):
        journal.confirm_handler_binding(
            config=changed,
            pairing_session_id=session.session_id,
            operator_confirmation="CONFIRM-DUAL-QQ-HANDLER",
        )


def test_active_binding_blocks_unauthorized_rebinding(tmp_path: Path) -> None:
    cfg, journal, clock, _ = pair_handler(tmp_path)
    tokens = iter(("x" * 32, "y" * 32))
    session = begin_handler_pairing(
        cfg, clock=clock, token_factory=lambda: next(tokens), contract_root=ROOT
    )
    journal.record_pairing_session(session)
    observe_both(cfg, journal, clock, session, suffix="replacement")

    with pytest.raises(QQHandlerAuthorizationDenied, match="unauthorized_rebinding"):
        journal.confirm_handler_binding(
            config=cfg,
            pairing_session_id=session.session_id,
            operator_confirmation="CONFIRM-DUAL-QQ-HANDLER",
        )


def test_c2c_challenge_rejects_valid_looking_foreign_token(tmp_path: Path) -> None:
    cfg, journal, clock, _ = pair_handler(tmp_path / "seed")
    tokens = iter(("m" * 32, "n" * 32))
    session = begin_handler_pairing(
        cfg, clock=clock, token_factory=lambda: next(tokens), contract_root=ROOT
    )
    journal.record_pairing_session(session)
    foreign = {
        "t": "C2C_MESSAGE_CREATE",
        "s": 200,
        "d": {
            "id": "foreign-c2c-token",
            "content": "WFH-C2C-" + "z" * 32,
            "timestamp": clock().isoformat().replace("+00:00", "Z"),
            "author": {"user_openid": "foreign-user"},
        },
    }
    with pytest.raises(QQHandlerEventRejected, match="challenge_mismatch"):
        normalize_handler_pairing_event(
            foreign, config=cfg, challenge=session.c2c, now=clock()
        )
