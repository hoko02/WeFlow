from __future__ import annotations

import sys
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import (
    QQHandlerAuthorizationDenied,
    QQHandlerEventRejected,
    parse_private_command,
)
from weflow_control_kernel.qq_handler_service import QQHandlerWorkflowService

UNIT = Path(__file__).resolve().parent
if str(UNIT) not in sys.path:
    sys.path.insert(0, str(UNIT))

from test_qq_handler_workflow import CASE_ID, c2c_event, pair_handler  # noqa: E402


def test_reject_requires_one_bounded_safe_reason_code() -> None:
    parsed = parse_private_command(f"WF-REJECT {CASE_ID} 1 not_my_scope")
    assert parsed.command == "reject"
    assert parsed.body == "not_my_scope"
    for malformed in (
        f"WF-REJECT {CASE_ID} 1",
        f"WF-REJECT {CASE_ID} 1 NOT_ALLOWED",
        f"WF-REJECT {CASE_ID} 1 not_my_scope\nSYNTHETIC_BODY",
    ):
        with pytest.raises(QQHandlerEventRejected):
            parse_private_command(malformed)


def test_reject_reason_is_content_free_metadata_and_schedules_private_deletion(
    tmp_path: Path,
) -> None:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    issue = journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-synthetic-1",
        source_message_id_hash="e" * 64,
        content="SYNTHETIC_ISSUE_API_503",
    )
    service = QQHandlerWorkflowService(config=cfg, binding=binding, journal=journal)
    response = service.handle_private_event(
        c2c_event(
            content=f"WF-REJECT {CASE_ID} 1 not_my_scope",
            message_id="synthetic-reject-command",
            timestamp=clock(),
        )
    )

    assert response.command["rejection_reason_code"] == "not_my_scope"
    assert response.command["candidate_artifact_id"] is None
    assert journal.case_projection(CASE_ID)["status"] == "REJECTED"
    with pytest.raises(QQHandlerAuthorizationDenied, match="private_artifact_unavailable"):
        journal.artifact_content(issue["artifact_id"])
