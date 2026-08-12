from __future__ import annotations

import sys
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import QQHandlerEventRejected, parse_group_approval

SECURITY = Path(__file__).resolve().parent
UNIT = Path(__file__).resolve().parents[1] / "unit"
for directory in (SECURITY, UNIT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from test_qq_handler_security import _draft_twice  # noqa: E402
from test_qq_handler_workflow import group_event  # noqa: E402


def test_public_parser_still_requires_a_mention_marker() -> None:
    request_id = "qqhar_" + "1" * 32
    with pytest.raises(QQHandlerEventRejected, match="mention_required"):
        parse_group_approval(f"WF-APPROVE {request_id} {'a' * 12} 3")


def test_verified_group_at_event_may_omit_provider_normalized_mention(
    tmp_path: Path,
) -> None:
    service, clock, _, metadata_text, _ = _draft_twice(tmp_path)

    response = service.handle_group_approval(
        group_event(
            content=f"WF-APPROVE {metadata_text}",
            message_id="approval-provider-omitted-mention",
            timestamp=clock(),
        )
    )

    assert response.decision["decision"] == "approved"


def test_ordinary_event_type_cannot_claim_provider_omitted_mention(
    tmp_path: Path,
) -> None:
    service, clock, _, metadata_text, _ = _draft_twice(tmp_path)
    event = group_event(
        content=f"WF-APPROVE {metadata_text}",
        message_id="approval-wrong-event-type",
        timestamp=clock(),
    )
    event["t"] = "MESSAGE_CREATE"

    with pytest.raises(QQHandlerEventRejected, match="event_type_unsupported"):
        service.handle_group_approval(event)
