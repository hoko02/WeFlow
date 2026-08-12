from __future__ import annotations

import sys
from pathlib import Path

from weflow_control_kernel.qq_handler import QQ_GROUP_NUDGE_TEMPLATE
from weflow_control_kernel.qq_handler_transport import FakeQQHandlerTransport

UNIT = Path(__file__).resolve().parent
if str(UNIT) not in sys.path:
    sys.path.insert(0, str(UNIT))

from test_qq_handler_workflow import CASE_ID, pair_handler  # noqa: E402


def test_group_nudge_is_durable_bounded_and_not_a_final_delivery(tmp_path: Path) -> None:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    issue = journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-synthetic-1",
        source_message_id_hash="a" * 64,
        content="SYNTHETIC_ISSUE_API_503",
    )
    transport = FakeQQHandlerTransport(cfg.group_openid, "user-raw-1")
    intent = journal.create_group_nudge_intent(
        case_id=CASE_ID,
        binding=binding,
        source_message_id="synthetic-intake-source",
        occurred_at=clock(),
    )

    first = journal.execute_passive_reply(
        intent,
        binding=binding,
        content=QQ_GROUP_NUDGE_TEMPLATE,
        transport=transport,
    )
    second = journal.execute_passive_reply(
        intent,
        binding=binding,
        content=QQ_GROUP_NUDGE_TEMPLATE,
        transport=transport,
    )

    assert intent["response_kind"] == "group-nudge"
    assert intent["reply_msg_seq"] == 2
    assert first == second
    assert transport.group_nudge_calls == 1
    assert transport.passive_group_calls == 0
    assert journal.case_projection(CASE_ID)["status"] == "READY"
    assert journal.artifact_content(issue["artifact_id"]) == "SYNTHETIC_ISSUE_API_503"
