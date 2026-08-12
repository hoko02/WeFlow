from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from weflow_control_kernel.qq_handler import (
    QQ_C2C_PASSIVE_REPLY_WINDOW_SECONDS,
    QQ_GROUP_PASSIVE_REPLY_WINDOW_SECONDS,
)

UNIT = Path(__file__).resolve().parent
if str(UNIT) not in sys.path:
    sys.path.insert(0, str(UNIT))

from test_qq_handler_workflow import CASE_ID, pair_handler  # noqa: E402


def test_private_and_group_passive_windows_match_provider_boundaries(
    tmp_path: Path,
) -> None:
    _, journal, clock, binding = pair_handler(tmp_path)
    journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-synthetic-1",
        source_message_id_hash="c" * 64,
        content="SYNTHETIC_ISSUE_API_503",
    )
    private_intent = journal.create_passive_intent(
        case_id=CASE_ID,
        binding=binding,
        source_message_id="synthetic-private-source",
        response_kind="pull",
        occurred_at=clock(),
        content_artifact_id=None,
        content_sha256="d" * 64,
    )
    group_intent = journal.create_passive_intent(
        case_id=CASE_ID,
        binding=binding,
        source_message_id="synthetic-group-source",
        response_kind="group-nudge",
        occurred_at=clock(),
        content_artifact_id=None,
        content_sha256="e" * 64,
    )
    private_deadline = datetime.fromisoformat(
        private_intent["reply_deadline_at"].replace("Z", "+00:00")
    )
    group_deadline = datetime.fromisoformat(
        group_intent["reply_deadline_at"].replace("Z", "+00:00")
    )
    assert int((private_deadline - clock()).total_seconds()) == 3_600
    assert QQ_C2C_PASSIVE_REPLY_WINDOW_SECONDS == 3_600
    assert int((group_deadline - clock()).total_seconds()) == 300
    assert QQ_GROUP_PASSIVE_REPLY_WINDOW_SECONDS == 300
