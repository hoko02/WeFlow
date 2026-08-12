from __future__ import annotations

import sys
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import (
    QQHandlerAuthorizationDenied,
    QQHandlerEventRejected,
)
from weflow_control_kernel.qq_handler_service import QQHandlerWorkflowService

UNIT = Path(__file__).resolve().parents[1] / "unit"
if str(UNIT) not in sys.path:
    sys.path.insert(0, str(UNIT))

from test_qq_handler_workflow import CASE_ID, c2c_event, pair_handler  # noqa: E402


def ready_service(tmp_path: Path):
    cfg, journal, clock, binding = pair_handler(tmp_path)
    journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-synthetic-1",
        source_message_id_hash="b" * 64,
        content="SYNTHETIC_ISSUE_API_503",
    )
    return journal, clock, QQHandlerWorkflowService(
        config=cfg, binding=binding, journal=journal
    )


@pytest.mark.parametrize(
    "content",
    [
        f"WF-PULL {CASE_ID}",
        f"WF-UNKNOWN {CASE_ID} 1",
        f"WF-ACCEPT {CASE_ID} not-a-version",
        f"WF-DRAFT {CASE_ID} 1",
        f"WF-REJECT {CASE_ID} 1\nUNDECLARED_BODY",
    ],
)
def test_private_protocol_rejects_every_malformed_or_unknown_shape(
    tmp_path: Path, content: str
) -> None:
    journal, clock, service = ready_service(tmp_path)
    before = journal.safe_counts()["private_command_count"]

    with pytest.raises(QQHandlerEventRejected):
        service.handle_private_event(
            c2c_event(content=content, message_id="malformed-command", timestamp=clock())
        )

    assert journal.safe_counts()["private_command_count"] == before
    assert journal.case_projection(CASE_ID)["status"] == "READY"


def test_private_protocol_rejects_stale_version_rich_event_and_expired_artifact(
    tmp_path: Path,
) -> None:
    journal, clock, service = ready_service(tmp_path)
    with pytest.raises(QQHandlerAuthorizationDenied, match="version"):
        service.handle_private_event(
            c2c_event(
                content=f"WF-ACCEPT {CASE_ID} 2",
                message_id="stale-version",
                timestamp=clock(),
            )
        )

    rich = c2c_event(
        content=f"WF-PULL {CASE_ID} 1",
        message_id="rich-private-event",
        timestamp=clock(),
    )
    rich["d"]["attachments"] = [{"id": "synthetic-attachment"}]  # type: ignore[index]
    with pytest.raises(QQHandlerEventRejected, match="plain_text_required"):
        service.handle_private_event(rich)

    clock.advance(days=1, seconds=1)
    with pytest.raises(
        QQHandlerAuthorizationDenied, match="private_artifact_unavailable|private_locator_inactive"
    ):
        service.handle_private_event(
            c2c_event(
                content=f"WF-PULL {CASE_ID} 1",
                message_id="expired-artifact",
                timestamp=clock(),
            )
        )
