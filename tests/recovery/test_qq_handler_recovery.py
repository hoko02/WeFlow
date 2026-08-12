from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import QQHandlerAuthorizationDenied
from weflow_control_kernel.qq_handler_service import (
    QQHandlerWorkflowService,
)
from weflow_control_kernel.qq_handler_transport import FakeQQHandlerTransport

UNIT_TESTS = Path(__file__).resolve().parents[1] / "unit"
sys.path.insert(0, str(UNIT_TESTS))

from test_qq_handler_workflow import (  # noqa: E402
    CASE_ID,
    c2c_event,
    group_event,
    pair_handler,
)


def ready_case(tmp_path: Path):
    cfg, journal, clock, binding = pair_handler(tmp_path)
    issue = journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-1",
        source_message_id_hash="6" * 64,
        content="private issue",
    )
    service = QQHandlerWorkflowService(config=cfg, binding=binding, journal=journal)
    return cfg, journal, clock, binding, issue, service


def approved_case(tmp_path: Path):
    cfg, journal, clock, binding, issue, service = ready_case(tmp_path)
    service.handle_private_event(
        c2c_event(content=f"WF-ACCEPT {CASE_ID} 1", message_id="recover-accept", timestamp=clock())
    )
    draft = service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 2\ncontrolled final candidate",
            message_id="recover-draft",
            timestamp=clock(),
        )
    )
    metadata = draft.content.split("WF-APPROVE ", 1)[1].split()
    approval = service.handle_group_approval(
        group_event(
            content=f"@机器人 WF-APPROVE {' '.join(metadata)}",
            message_id="recover-approval",
            timestamp=clock(),
        )
    )
    return cfg, journal, clock, binding, issue, service, approval


def test_notification_crash_after_started_is_persisted_unknown_and_never_retried(
    tmp_path: Path,
) -> None:
    cfg, journal, clock, binding, _, _ = ready_case(tmp_path)
    intent = journal.create_notification_intent(CASE_ID, binding)
    with closing(sqlite3.connect(journal.path)) as connection:
        connection.execute(
            "INSERT INTO qq_handler_notification_attempts VALUES(?,?,?,NULL)",
            (
                intent["intent_id"],
                "STARTED",
                clock().isoformat().replace("+00:00", "Z"),
            ),
        )
        connection.commit()
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")

    first = journal.execute_notification(intent, binding=binding, transport=transport)
    second = journal.execute_notification(intent, binding=binding, transport=transport)

    assert first["status"] == "unknown"
    assert second == first
    assert transport.notification_calls == 0
    with closing(sqlite3.connect(journal.path)) as connection:
        result_json = connection.execute(
            "SELECT result_json FROM qq_handler_notification_attempts WHERE intent_id=?",
            (intent["intent_id"],),
        ).fetchone()[0]
    assert json.loads(result_json)["status"] == "unknown"


@pytest.mark.parametrize(
    "status",
    ["accepted", "rejected", "rate_limited", "timed_out", "disconnected", "unknown"],
)
def test_notification_outcome_classes_close_the_single_attempt_budget(
    tmp_path: Path, status: str
) -> None:
    cfg, journal, _, binding, _, _ = ready_case(tmp_path)
    intent = journal.create_notification_intent(CASE_ID, binding)
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1", notification_status=status)
    first = journal.execute_notification(intent, binding=binding, transport=transport)
    second = journal.execute_notification(intent, binding=binding, transport=transport)
    assert first == second
    assert first["provider_accepted"] is (status == "accepted")
    assert first["delivered"] is False
    assert transport.notification_calls == 1


def test_expired_passive_window_requires_new_private_command_without_active_fallback(
    tmp_path: Path,
) -> None:
    cfg, _, clock, _, _, service = ready_case(tmp_path)
    old = clock()
    clock.advance(hours=2)
    pull = service.handle_private_event(
        c2c_event(content=f"WF-PULL {CASE_ID} 1", message_id="old-pull", timestamp=old)
    )
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")
    result = service.execute_private_response(pull, transport=transport)
    assert result["status"] == "expired_window"
    assert transport.passive_c2c_calls == 0
    assert transport.notification_calls == 0


def test_ambiguous_final_reply_never_creates_a_second_provider_effect(tmp_path: Path) -> None:
    cfg, _, _, _, _, service, approval = approved_case(tmp_path)
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1", lose_passive_response=True)

    first = service.execute_final_response(approval, transport=transport)
    second = service.execute_final_response(approval, transport=transport)

    assert first["status"] == "unknown"
    assert second == first
    assert first["provider_accepted"] is False
    assert transport.passive_group_calls == 1
    assert len(transport.effects) == 1


def test_local_reconcile_observes_provider_duplicate_without_second_send(tmp_path: Path) -> None:
    cfg, _, _, _, _, service, approval = approved_case(tmp_path)
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")
    key = (
        "group",
        cfg.group_openid,
        approval.final_intent["source_message_id"],
        approval.final_intent["reply_msg_seq"],
    )
    transport.effects[key] = "already-visible-provider-message"

    result = service.execute_final_response(approval, transport=transport)

    assert result["status"] == "duplicate"
    assert result["provider_accepted"] is True
    assert transport.passive_group_calls == 0


def test_restart_after_acceptance_reads_completion_and_terminal_deletion_evidence(
    tmp_path: Path,
) -> None:
    cfg, journal, _, binding, issue, service, approval = approved_case(tmp_path)
    first_transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")
    first = service.execute_final_response(approval, transport=first_transport)
    restarted_journal = type(journal)(
        journal.path, clock=journal._clock, contract_root=cfg.repository_root
    )
    restarted_service = QQHandlerWorkflowService(
        config=cfg, binding=binding, journal=restarted_journal
    )
    second_transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")
    second = restarted_service.execute_final_response(approval, transport=second_transport)

    assert first == second
    assert second_transport.passive_group_calls == 0
    with pytest.raises(QQHandlerAuthorizationDenied, match="private_artifact_unavailable"):
        journal.artifact_content(issue["artifact_id"])
    assert journal.safe_counts()["deletion_count"] >= 2


def test_candidate_edit_after_approval_invalidates_old_final_authority(tmp_path: Path) -> None:
    _, journal, clock, binding, _, service, approval = approved_case(tmp_path)
    service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 3\nreplacement after approval",
            message_id="post-approval-edit",
            timestamp=clock(),
        )
    )
    with pytest.raises(QQHandlerAuthorizationDenied, match="final_decision_stale"):
        journal.final_delivery_intent(approval.decision, binding=binding)
