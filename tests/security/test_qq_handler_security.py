from __future__ import annotations

import copy
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import (
    QQ_HANDLER_REQUIRED_CAPABILITIES,
    QQHandlerActivationDenied,
    QQHandlerAuthorizationDenied,
    QQHandlerConfig,
    QQHandlerEventRejected,
    QQHandlerStateConflict,
    begin_handler_pairing,
    normalize_handler_pairing_event,
)
from weflow_control_kernel.qq_handler_service import QQHandlerWorkflowService

UNIT_TESTS = Path(__file__).resolve().parents[1] / "unit"
sys.path.insert(0, str(UNIT_TESTS))

from test_qq_handler_workflow import (  # noqa: E402
    CASE_ID,
    MutableClock,
    c2c_event,
    config,
    group_event,
    insert_stage1_locator,
    pair_handler,
)

ROOT = Path(__file__).resolve().parents[2]


def test_stage2_configuration_requires_confirmation_and_exact_capabilities(
    tmp_path: Path,
) -> None:
    environment = {
        "WEFLOW_QQ_APP_ID": "app-stage2",
        "WEFLOW_QQ_CLIENT_SECRET": "not-a-real-secret",
        "WEFLOW_QQ_TENANT_ID": "tenant-alpha",
        "WEFLOW_QQ_SANDBOX_PAIRING_ID": "qqpair_11111111111111111111111111111111",
        "WEFLOW_QQ_IDENTITY_SALT": "s" * 32,
        "WEFLOW_QQ_CAPABILITIES": ",".join(QQ_HANDLER_REQUIRED_CAPABILITIES),
    }
    with pytest.raises(QQHandlerActivationDenied, match="explicit_confirmation"):
        QQHandlerConfig.from_environment(
            confirm_live_qq=False,
            store_path=".weflow/qq-sandbox.sqlite3",
            repository_root=ROOT,
            group_openid="group-raw-1",
            environ=environment,
        )

    over_scoped = dict(environment)
    over_scoped["WEFLOW_QQ_CAPABILITIES"] += ",qq.arbitrary.send"
    with pytest.raises(QQHandlerActivationDenied, match="capability_scope_denied"):
        QQHandlerConfig.from_environment(
            confirm_live_qq=True,
            store_path=tmp_path / ".weflow" / "qq-sandbox.sqlite3",
            repository_root=tmp_path,
            group_openid="group-raw-1",
            environ=over_scoped,
        )


def test_one_sided_expired_foreign_and_replayed_pairing_fail_closed(tmp_path: Path) -> None:
    clock = MutableClock(pair_handler(tmp_path / "seed")[2]())
    cfg, journal = config(tmp_path, clock)
    insert_stage1_locator(journal, cfg, clock)
    tokens = iter(("g" * 32, "c" * 32))
    session = begin_handler_pairing(
        cfg, clock=clock, token_factory=lambda: next(tokens), contract_root=ROOT
    )
    journal.record_pairing_session(session)
    group = {
        "t": "GROUP_AT_MESSAGE_CREATE",
        "s": 1,
        "d": {
            "id": "pair-group",
            "content": f"@机器人 {session.group.plaintext}",
            "timestamp": clock().isoformat().replace("+00:00", "Z"),
            "group_openid": cfg.group_openid,
            "author": {
                "member_openid": "member-one",
                "nickname": "same-display-name",
                "member_role": "OWNER",
            },
        },
    }
    observation = normalize_handler_pairing_event(
        group, config=cfg, challenge=session.group, now=clock()
    )
    journal.record_pairing_observation(session.group, observation)
    with pytest.raises(QQHandlerAuthorizationDenied, match="dual_challenge_incomplete"):
        journal.confirm_handler_binding(
            config=cfg,
            pairing_session_id=session.session_id,
            operator_confirmation="CONFIRM-DUAL-QQ-HANDLER",
        )

    replay = copy.deepcopy(group)
    replay["d"]["id"] = "pair-group-replay"
    replay["d"]["author"]["member_openid"] = "member-two"  # type: ignore[index]
    with pytest.raises(QQHandlerStateConflict, match="replayed"):
        journal.record_pairing_observation(
            session.group,
            normalize_handler_pairing_event(
                replay, config=cfg, challenge=session.group, now=clock()
            ),
        )

    foreign = copy.deepcopy(group)
    foreign["d"]["group_openid"] = "foreign-group"  # type: ignore[index]
    with pytest.raises(QQHandlerEventRejected, match="foreign_group"):
        normalize_handler_pairing_event(foreign, config=cfg, challenge=session.group, now=clock())

    clock.advance(seconds=301)
    with pytest.raises(QQHandlerEventRejected, match="expired"):
        normalize_handler_pairing_event(group, config=cfg, challenge=session.group, now=clock())


def _draft_twice(
    tmp_path: Path,
) -> tuple[QQHandlerWorkflowService, MutableClock, str, str, int]:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-1",
        source_message_id_hash="4" * 64,
        content="restricted issue",
    )
    service = QQHandlerWorkflowService(config=cfg, binding=binding, journal=journal)
    service.handle_private_event(
        c2c_event(content=f"WF-ACCEPT {CASE_ID} 1", message_id="accept-sec", timestamp=clock())
    )
    first = service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 2\nfirst private candidate",
            message_id="draft-sec-1",
            timestamp=clock(),
        )
    )
    first_metadata = first.content.split("WF-APPROVE ", 1)[1].split()
    second = service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 3\nsecond private candidate",
            message_id="draft-sec-2",
            timestamp=clock(),
        )
    )
    second_metadata = second.content.split("WF-APPROVE ", 1)[1].split()
    return (
        service,
        clock,
        " ".join(first_metadata),
        " ".join(second_metadata),
        int(second_metadata[2]),
    )


def test_stale_copied_and_foreign_group_approval_cannot_authorize_delivery(
    tmp_path: Path,
) -> None:
    service, clock, first_metadata, second_metadata, _ = _draft_twice(tmp_path)
    with pytest.raises(QQHandlerAuthorizationDenied, match="stale"):
        service.handle_group_approval(
            group_event(
                content=f"@机器人 WF-APPROVE {first_metadata}",
                message_id="approve-stale",
                timestamp=clock(),
            )
        )

    foreign = group_event(
        content=f"@机器人 WF-APPROVE {second_metadata}",
        message_id="approve-foreign",
        timestamp=clock(),
    )
    foreign["d"]["author"]["member_openid"] = "robot-or-foreign"  # type: ignore[index]
    foreign["d"]["author"]["nickname"] = "same-display-name"  # type: ignore[index]
    foreign["d"]["author"]["member_role"] = "OWNER"  # type: ignore[index]
    with pytest.raises(QQHandlerAuthorizationDenied, match="foreign_member"):
        service.handle_group_approval(foreign)


def test_expired_request_artifact_and_oversized_or_prohibited_drafts_fail_closed(
    tmp_path: Path,
) -> None:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    issue = journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-1",
        source_message_id_hash="5" * 64,
        content="restricted issue",
    )
    service = QQHandlerWorkflowService(config=cfg, binding=binding, journal=journal)
    service.handle_private_event(
        c2c_event(content=f"WF-ACCEPT {CASE_ID} 1", message_id="accept-exp", timestamp=clock())
    )
    oversized = c2c_event(
        content=f"WF-DRAFT {CASE_ID} 2\n" + "x" * 1201,
        message_id="draft-big",
        timestamp=clock(),
    )
    with pytest.raises(QQHandlerEventRejected, match="oversized"):
        service.handle_private_event(oversized)
    prohibited = c2c_event(
        content=f"WF-DRAFT {CASE_ID} 2\nclient_secret=do-not-send",
        message_id="draft-secret",
        timestamp=clock(),
    )
    with pytest.raises(QQHandlerEventRejected, match="prohibited"):
        service.handle_private_event(prohibited)

    draft = service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 2\nprivate candidate",
            message_id="draft-exp",
            timestamp=clock(),
        )
    )
    metadata = draft.content.split("WF-APPROVE ", 1)[1].split()
    clock.advance(minutes=11)
    with pytest.raises(QQHandlerAuthorizationDenied, match="stale"):
        service.handle_group_approval(
            group_event(
                content=f"@机器人 WF-APPROVE {' '.join(metadata)}",
                message_id="approve-expired",
                timestamp=clock(),
            )
        )

    clock.advance(days=1)
    with pytest.raises(QQHandlerAuthorizationDenied, match="private_artifact_unavailable"):
        journal.artifact_content(issue["artifact_id"])


def test_general_metadata_and_reports_exclude_private_text_raw_identity_and_credentials(
    tmp_path: Path,
) -> None:
    cfg, journal, _, binding = pair_handler(tmp_path)
    report = journal.build_acceptance_report(
        config=cfg,
        binding=binding,
        mode="offline-fake",
        private_workflow_verified=True,
    )
    forbidden_values = (
        cfg.client_secret,
        cfg.identity_salt,
        cfg.group_openid,
        "member-raw-1",
        "user-raw-1",
    )
    assert all(value not in str(report) for value in forbidden_values)
    with closing(sqlite3.connect(journal.path)) as connection:
        public_json = " ".join(
            row[0]
            for table, column in (
                ("qq_handler_bindings", "record_json"),
                ("qq_handler_pairing_observations", "record_json"),
                ("qq_handler_events", "metadata_json"),
            )
            for row in connection.execute(f"SELECT {column} FROM {table}").fetchall()
        )
    assert all(value not in public_json for value in forbidden_values)
