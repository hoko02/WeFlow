from __future__ import annotations

import itertools
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import (
    QQ_HANDLER_REQUIRED_CAPABILITIES,
    QQHandlerAuthorizationDenied,
    QQHandlerConfig,
    QQHandlerEventRejected,
    SQLiteQQHandlerJournal,
    begin_handler_pairing,
    normalize_handler_pairing_event,
    normalize_private_content,
    parse_group_approval,
    parse_private_command,
)
from weflow_control_kernel.qq_handler_service import QQHandlerWorkflowService
from weflow_control_kernel.qq_handler_transport import FakeQQHandlerTransport

ROOT = Path(__file__).resolve().parents[2]
CASE_ID = "case_111111111111111111111111"
_C2C_SEQUENCES = itertools.count(10)
_GROUP_SEQUENCES = itertools.count(10_000)


@dataclass
class MutableClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: int) -> None:
        self.value += timedelta(**kwargs)


def config(tmp_path: Path, clock: MutableClock) -> tuple[QQHandlerConfig, SQLiteQQHandlerJournal]:
    store = tmp_path / ".weflow" / "qq-sandbox.sqlite3"
    value = QQHandlerConfig(
        app_id="app-stage2",
        client_secret="not-a-real-secret",
        tenant_id="tenant-alpha",
        stage1_pairing_id="qqpair_11111111111111111111111111111111",
        group_openid="group-raw-1",
        identity_salt="s" * 32,
        store_path=store,
        repository_root=ROOT,
        capabilities=QQ_HANDLER_REQUIRED_CAPABILITIES,
    )
    return value, SQLiteQQHandlerJournal(store, clock=clock, contract_root=ROOT)


def insert_stage1_locator(
    journal: SQLiteQQHandlerJournal, cfg: QQHandlerConfig, clock: MutableClock
) -> None:
    with closing(sqlite3.connect(journal.path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS qq_pairing_locators(
                pairing_id TEXT PRIMARY KEY, app_id_hash TEXT NOT NULL,
                tenant_id TEXT NOT NULL, tenant_id_hash TEXT NOT NULL,
                group_openid TEXT NOT NULL, group_openid_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL, status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO qq_pairing_locators VALUES(?,?,?,?,?,?,?,?)",
            (
                cfg.stage1_pairing_id,
                cfg.app_id_hash,
                cfg.tenant_id,
                cfg.tenant_id_hash,
                cfg.group_openid,
                cfg.group_openid_hash,
                (clock() + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "COMPLETED",
            ),
        )
        connection.commit()


def pair_handler(
    tmp_path: Path,
) -> tuple[
    QQHandlerConfig,
    SQLiteQQHandlerJournal,
    MutableClock,
    dict[str, object],
]:
    clock = MutableClock(datetime(2026, 8, 11, tzinfo=UTC))
    cfg, journal = config(tmp_path, clock)
    insert_stage1_locator(journal, cfg, clock)
    tokens = iter(("g" * 32, "c" * 32))
    session = begin_handler_pairing(
        cfg, clock=clock, token_factory=lambda: next(tokens), contract_root=ROOT
    )
    journal.record_pairing_session(session)
    group_event = {
        "t": "GROUP_AT_MESSAGE_CREATE",
        "s": 1,
        "d": {
            "id": "group-pair-msg",
            "content": f"@机器人 {session.group.plaintext}",
            "timestamp": "2026-08-11T00:00:01Z",
            "group_openid": cfg.group_openid,
            "author": {
                "member_openid": "member-raw-1",
                "member_role": "MEMBER",
                "nickname": "display-only",
            },
        },
    }
    c2c_event = {
        "t": "C2C_MESSAGE_CREATE",
        "s": 2,
        "d": {
            "id": "c2c-pair-msg",
            "content": session.c2c.plaintext,
            "timestamp": "2026-08-11T00:00:02Z",
            "author": {"user_openid": "user-raw-1", "nickname": "display-only"},
        },
    }
    clock.advance(seconds=3)
    journal.record_pairing_observation(
        session.group,
        normalize_handler_pairing_event(
            group_event, config=cfg, challenge=session.group, now=clock()
        ),
    )
    journal.record_pairing_observation(
        session.c2c,
        normalize_handler_pairing_event(c2c_event, config=cfg, challenge=session.c2c, now=clock()),
    )
    binding = journal.confirm_handler_binding(
        config=cfg,
        pairing_session_id=session.session_id,
        operator_confirmation="CONFIRM-DUAL-QQ-HANDLER",
    )
    return cfg, journal, clock, binding


def c2c_event(*, content: str, message_id: str, timestamp: datetime) -> dict[str, object]:
    return {
        "t": "C2C_MESSAGE_CREATE",
        "s": next(_C2C_SEQUENCES),
        "d": {
            "id": message_id,
            "content": content,
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "author": {"user_openid": "user-raw-1"},
        },
    }


def group_event(*, content: str, message_id: str, timestamp: datetime) -> dict[str, object]:
    return {
        "t": "GROUP_AT_MESSAGE_CREATE",
        "s": next(_GROUP_SEQUENCES),
        "d": {
            "id": message_id,
            "content": content,
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "group_openid": "group-raw-1",
            "author": {"member_openid": "member-raw-1"},
        },
    }


def test_dual_pairing_persists_hashes_and_private_locators(tmp_path: Path) -> None:
    cfg, journal, _, binding = pair_handler(tmp_path)

    assert binding["assurance_level"] == "operator_confirmed_dual_challenge"
    assert binding["group_member_identity_hash"] not in {"member-raw-1", "user-raw-1"}
    assert binding["c2c_user_identity_hash"] not in {"member-raw-1", "user-raw-1"}
    assert journal.private_locator(binding["handler_binding_id"], "c2c-user") == "user-raw-1"
    report = journal.build_acceptance_report(config=cfg, binding=binding, mode="offline-fake")
    assert report["dual_surface_binding_verified"] is True
    assert report["production_ready"] is False
    serialized = str(report)
    assert "member-raw-1" not in serialized
    assert "user-raw-1" not in serialized


def test_acceptance_report_scopes_notification_attempts_to_case_and_binding(
    tmp_path: Path,
) -> None:
    cfg, journal, _, binding = pair_handler(tmp_path)
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")
    first_case = CASE_ID
    second_case = "case_222222222222222222222222"
    for index, case_id in enumerate((first_case, second_case), start=1):
        journal.create_issue_artifact(
            binding=binding,
            case_id=case_id,
            case_revision_id=f"case-revision-{index}",
            source_message_id_hash=str(index) * 64,
            content=f"SYNTHETIC_ISSUE_API_503_{index}",
        )
        journal.execute_notification(
            journal.create_notification_intent(case_id, binding),
            binding=binding,
            transport=transport,
        )

    assert journal.safe_counts()["notification_attempt_count"] == 2
    report = journal.build_acceptance_report(
        config=cfg,
        binding=binding,
        mode="offline-fake",
        case_id=second_case,
        notification_status="accepted",
    )

    assert report["notification_attempt_count"] == 1


def test_private_content_normalization_is_bounded_and_deterministic() -> None:
    assert normalize_private_content("ＡＰＩ   503\r\n password=secret", candidate=False) == (
        "API 503\npassword=[REDACTED]"
    )
    assert len(normalize_private_content("😀", candidate=True)) == 1
    with pytest.raises(QQHandlerEventRejected, match="private_content_oversized"):
        normalize_private_content("字" * 1201, candidate=True)
    with pytest.raises(QQHandlerEventRejected, match="candidate_prohibited_content"):
        normalize_private_content("client_secret=do-not-send", candidate=True)


def test_closed_command_parsers_reject_unknown_and_group_plaintext() -> None:
    assert parse_private_command(f"WF-PULL {CASE_ID} 1").command == "pull"
    assert parse_private_command(f"WF-DRAFT {CASE_ID} 2\n请稍后重试").body == "请稍后重试"
    approval = parse_group_approval(
        "@机器人 WF-APPROVE qqhar_11111111111111111111111111111111 abcdefabcdef 3"
    )
    assert approval.expected_version == 3
    with pytest.raises(QQHandlerEventRejected, match="private_command_unknown_or_malformed"):
        parse_private_command(f"WF-SEND {CASE_ID} 1")
    with pytest.raises(QQHandlerEventRejected, match="group_approval_unknown_or_malformed"):
        parse_group_approval(
            "@机器人 WF-APPROVE qqhar_11111111111111111111111111111111 abcdefabcdef 3 草稿正文"
        )


def test_private_pull_accept_draft_edit_group_approval_and_final_reply(tmp_path: Path) -> None:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    issue = journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-1",
        source_message_id_hash="1" * 64,
        content="广告系统出现了 API 503 错误，password=private",
    )
    service = QQHandlerWorkflowService(config=cfg, binding=binding, journal=journal)
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")

    pull = service.handle_private_event(
        c2c_event(content=f"WF-PULL {CASE_ID} 1", message_id="pull-1", timestamp=clock())
    )
    assert issue["artifact_id"] == pull.passive_intent["content_artifact_id"]
    assert "客户问题（仅私聊）" in pull.content
    assert "private" not in pull.content
    assert service.execute_private_response(pull, transport=transport)["provider_accepted"]

    duplicate_pull = service.handle_private_event(
        c2c_event(content=f"WF-PULL {CASE_ID} 1", message_id="pull-1", timestamp=clock())
    )
    assert duplicate_pull.duplicate is True
    assert service.execute_private_response(duplicate_pull, transport=transport)[
        "provider_accepted"
    ]
    assert transport.passive_c2c_calls == 1

    accepted = service.handle_private_event(
        c2c_event(content=f"WF-ACCEPT {CASE_ID} 1", message_id="accept-1", timestamp=clock())
    )
    assert accepted.passive_intent["workflow_version"] == 2
    service.execute_private_response(accepted, transport=transport)

    first_draft = service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 2\n已定位为上游服务波动，请稍后重试。",
            message_id="draft-1",
            timestamp=clock(),
        )
    )
    assert "草稿预览（仅私聊）" in first_draft.content
    assert "WF-APPROVE" in first_draft.content
    service.execute_private_response(first_draft, transport=transport)

    edited = service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 3\n已定位为上游短时波动，建议一分钟后重试。",
            message_id="draft-2",
            timestamp=clock(),
        )
    )
    service.execute_private_response(edited, transport=transport)
    metadata = edited.content.split("WF-APPROVE ", 1)[1].split()
    approval = service.handle_group_approval(
        group_event(
            content=f"@机器人 WF-APPROVE {metadata[0]} {metadata[1]} {metadata[2]}",
            message_id="approve-1",
            timestamp=clock(),
        )
    )
    result = service.execute_final_response(approval, transport=transport)

    assert result["provider_accepted"] is True
    assert result["customer_receipt_verified"] is False
    assert result["issue_resolution"] is False
    assert result["case_completion"] is False
    assert transport.passive_group_contents == ["已定位为上游短时波动,建议一分钟后重试。"]
    assert all("客户问题" not in value for value in transport.passive_group_contents)


def test_foreign_private_user_and_group_member_fail_without_case_disclosure(
    tmp_path: Path,
) -> None:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-1",
        source_message_id_hash="2" * 64,
        content="private issue",
    )
    service = QQHandlerWorkflowService(config=cfg, binding=binding, journal=journal)
    foreign = c2c_event(content=f"WF-PULL {CASE_ID} 1", message_id="foreign-1", timestamp=clock())
    foreign["d"]["author"]["user_openid"] = "foreign-user"  # type: ignore[index]
    with pytest.raises(QQHandlerAuthorizationDenied) as error:
        service.handle_private_event(foreign)
    assert CASE_ID not in error.value.reason_code


def test_notification_is_minimal_and_at_most_once_after_ambiguous_transport(
    tmp_path: Path,
) -> None:
    cfg, journal, _, binding = pair_handler(tmp_path)
    journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-1",
        source_message_id_hash="3" * 64,
        content="private issue must not notify",
    )
    intent = journal.create_notification_intent(CASE_ID, binding)
    transport = FakeQQHandlerTransport(
        cfg.group_openid, "user-raw-1", lose_notification_response=True
    )

    first = journal.execute_notification(intent, binding=binding, transport=transport)
    second = journal.execute_notification(intent, binding=binding, transport=transport)

    assert first["status"] == "unknown"
    assert second == first
    assert transport.notification_calls == 1
    assert "private issue" not in transport.notification_contents[0]
    assert first["delivered"] is False
