from __future__ import annotations

import sys
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import QQHandlerEventRejected
from weflow_control_kernel.qq_handler_service import QQHandlerWorkflowService

UNIT = Path(__file__).resolve().parents[1] / "unit"
if str(UNIT) not in sys.path:
    sys.path.insert(0, str(UNIT))

from test_qq_handler_workflow import (  # noqa: E402
    CASE_ID,
    c2c_event,
    group_event,
    pair_handler,
)


def ready_service(tmp_path: Path):
    cfg, journal, clock, binding = pair_handler(tmp_path)
    journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-synthetic-1",
        source_message_id_hash="a" * 64,
        content="SYNTHETIC_ISSUE_API_503",
    )
    return journal, clock, QQHandlerWorkflowService(
        config=cfg, binding=binding, journal=journal
    )


def test_c2c_exact_replay_is_idempotent_and_new_session_can_reset_sequence(
    tmp_path: Path,
) -> None:
    journal, clock, service = ready_service(tmp_path)
    pull = c2c_event(content=f"WF-PULL {CASE_ID} 1", message_id="order-pull", timestamp=clock())
    pull["s"] = 20
    first = service.handle_private_event(pull)
    duplicate = service.handle_private_event(pull)
    assert first.command == duplicate.command
    assert duplicate.duplicate is True

    reset = c2c_event(
        content=f"WF-ACCEPT {CASE_ID} 1", message_id="order-reset", timestamp=clock()
    )
    reset["s"] = 19
    accepted = service.handle_private_event(reset)
    assert accepted.command["command"] == "accept"
    assert journal.case_projection(CASE_ID)["status"] == "ACCEPTED"
    with journal._connect() as connection:
        cursor = connection.execute(
            "SELECT last_sequence FROM qq_handler_event_cursors WHERE surface='c2c'"
        ).fetchone()
    assert cursor[0] == 20


def test_group_approval_requires_positive_monotonic_sequence(tmp_path: Path) -> None:
    _, clock, service = ready_service(tmp_path)
    malformed = group_event(
        content=(
            "@机器人 WF-APPROVE qqhar_11111111111111111111111111111111 "
            "111111111111 1"
        ),
        message_id="approval-no-sequence",
        timestamp=clock(),
    )
    malformed["s"] = 0
    with pytest.raises(QQHandlerEventRejected, match="sequence_invalid"):
        service.handle_group_approval(malformed)
