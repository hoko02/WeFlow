"""Deterministic offline acceptance for QQ handler approval and delivery Stage 2."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from weflow_control_kernel import (
    QQ_HANDLER_REQUIRED_CAPABILITIES,
    FakeQQHandlerTransport,
    QQHandlerAuthorizationDenied,
    QQHandlerConfig,
    QQHandlerWorkflowService,
    SQLiteQQHandlerJournal,
    begin_handler_pairing,
    normalize_handler_pairing_event,
)

JsonObject = dict[str, Any]
NOW = datetime(2026, 8, 11, tzinfo=UTC)
CASE_ID = "case_222222222222222222222222"


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _event(
    *, surface: str, content: str, message_id: str, clock: MutableClock, sequence: int
) -> JsonObject:
    data: JsonObject = {
        "id": message_id,
        "content": content,
        "timestamp": clock().isoformat().replace("+00:00", "Z"),
        "author": (
            {"member_openid": "synthetic-handler-member"}
            if surface == "group"
            else {"user_openid": "synthetic-handler-user"}
        ),
    }
    if surface == "group":
        data["group_openid"] = "synthetic-handler-group"
    return {
        "t": "GROUP_AT_MESSAGE_CREATE" if surface == "group" else "C2C_MESSAGE_CREATE",
        "s": sequence,
        "d": data,
    }


def _stage1_locator(
    journal: SQLiteQQHandlerJournal, config: QQHandlerConfig, clock: MutableClock
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
                config.stage1_pairing_id,
                config.app_id_hash,
                config.tenant_id,
                config.tenant_id_hash,
                config.group_openid,
                config.group_openid_hash,
                (clock() + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "COMPLETED",
            ),
        )
        connection.commit()


def run_qq_handler_offline_acceptance(root: Path) -> JsonObject:
    with TemporaryDirectory(prefix="weflow-qq-handler-") as temporary:
        workspace = Path(temporary)
        clock = MutableClock()
        config = QQHandlerConfig(
            app_id="synthetic-handler-app",
            client_secret="not-a-real-secret",
            tenant_id="tenant-synthetic-handler",
            stage1_pairing_id="qqpair_22222222222222222222222222222222",
            group_openid="synthetic-handler-group",
            identity_salt="synthetic-handler-identity-salt-32-bytes",
            store_path=workspace / ".weflow" / "qq-sandbox.sqlite3",
            repository_root=root,
            capabilities=QQ_HANDLER_REQUIRED_CAPABILITIES,
        )
        journal = SQLiteQQHandlerJournal(config.store_path, clock=clock, contract_root=root)
        _stage1_locator(journal, config, clock)
        tokens = iter(("G" * 32, "C" * 32))
        session = begin_handler_pairing(
            config,
            clock=clock,
            token_factory=lambda: next(tokens),
            contract_root=root,
        )
        journal.record_pairing_session(session)
        for challenge, event in (
            (
                session.group,
                _event(
                    surface="group",
                    content=f"@机器人 {session.group.plaintext}",
                    message_id="synthetic-group-pair",
                    clock=clock,
                    sequence=1,
                ),
            ),
            (
                session.c2c,
                _event(
                    surface="c2c",
                    content=session.c2c.plaintext,
                    message_id="synthetic-c2c-pair",
                    clock=clock,
                    sequence=2,
                ),
            ),
        ):
            journal.record_pairing_observation(
                challenge,
                normalize_handler_pairing_event(
                    event, config=config, challenge=challenge, now=clock()
                ),
            )
        binding = journal.confirm_handler_binding(
            config=config,
            pairing_session_id=session.session_id,
            operator_confirmation="CONFIRM-DUAL-QQ-HANDLER",
        )
        journal.create_issue_artifact(
            binding=binding,
            case_id=CASE_ID,
            case_revision_id="case-revision-synthetic-1",
            source_message_id_hash="a" * 64,
            content="SYNTHETIC_ISSUE_API_503",
        )
        service = QQHandlerWorkflowService(config=config, binding=binding, journal=journal)
        transport = FakeQQHandlerTransport(config.group_openid, "synthetic-handler-user")
        notification = journal.execute_notification(
            journal.create_notification_intent(CASE_ID, binding),
            binding=binding,
            transport=transport,
        )

        pull_event = _event(
            surface="c2c",
            content=f"WF-PULL {CASE_ID} 1",
            message_id="synthetic-pull",
            clock=clock,
            sequence=3,
        )
        pull = service.handle_private_event(pull_event)
        service.execute_private_response(pull, transport=transport)
        duplicate = service.handle_private_event(pull_event)
        service.execute_private_response(duplicate, transport=transport)
        accepted = service.handle_private_event(
            _event(
                surface="c2c",
                content=f"WF-ACCEPT {CASE_ID} 1",
                message_id="synthetic-accept",
                clock=clock,
                sequence=4,
            )
        )
        service.execute_private_response(accepted, transport=transport)
        first_draft = service.handle_private_event(
            _event(
                surface="c2c",
                content=f"WF-DRAFT {CASE_ID} 2\nSYNTHETIC_RESPONSE_V1",
                message_id="synthetic-draft-1",
                clock=clock,
                sequence=5,
            )
        )
        service.execute_private_response(first_draft, transport=transport)
        edited = service.handle_private_event(
            _event(
                surface="c2c",
                content=f"WF-DRAFT {CASE_ID} 3\nSYNTHETIC_RESPONSE_V2",
                message_id="synthetic-draft-2",
                clock=clock,
                sequence=6,
            )
        )
        service.execute_private_response(edited, transport=transport)
        metadata = edited.content.split("WF-APPROVE ", 1)[1].split()

        rejected_count = 0
        foreign = _event(
            surface="group",
            content=f"@机器人 WF-APPROVE {' '.join(metadata)}",
            message_id="synthetic-foreign-approval",
            clock=clock,
            sequence=7,
        )
        foreign["d"]["author"] = {"member_openid": "synthetic-foreign-member"}
        try:
            service.handle_group_approval(foreign)
        except QQHandlerAuthorizationDenied:
            rejected_count += 1
        approval = service.handle_group_approval(
            _event(
                surface="group",
                content=f"@机器人 WF-APPROVE {' '.join(metadata)}",
                message_id="synthetic-approval",
                clock=clock,
                sequence=8,
            )
        )
        final = service.execute_final_response(approval, transport=transport)
        report = journal.build_acceptance_report(
            config=config,
            binding=binding,
            mode="offline-fake",
            case_id=CASE_ID,
            notification_status=notification["status"],
            private_workflow_verified=True,
            group_approval_verified=True,
            final_provider_accepted=final["provider_accepted"],
            duplicate_event_count=1,
            rejected_event_count=rejected_count,
            artifact_deletion_verified=journal.deleted_artifact_count(CASE_ID) >= 3,
        )
        serialized = json.dumps(report, sort_keys=True, separators=(",", ":"))
        forbidden = (
            config.client_secret,
            config.identity_salt,
            config.group_openid,
            "synthetic-handler-member",
            "synthetic-handler-user",
            "SYNTHETIC_ISSUE_API_503",
            "SYNTHETIC_RESPONSE_V2",
        )
        if any(value in serialized for value in forbidden):
            raise RuntimeError("qq_handler_acceptance_privacy_violation")
        return report


__all__ = ["run_qq_handler_offline_acceptance"]
