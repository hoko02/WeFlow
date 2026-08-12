from __future__ import annotations

import sys
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler_transport import FakeQQHandlerTransport

RECOVERY = Path(__file__).resolve().parent
if str(RECOVERY) not in sys.path:
    sys.path.insert(0, str(RECOVERY))

from test_qq_handler_recovery import approved_case  # noqa: E402


def bound_transport(cfg, journal, binding, *, passive_status: str = "accepted"):
    return FakeQQHandlerTransport(
        cfg.group_openid,
        journal.private_locator(binding["handler_binding_id"], "c2c-user"),
        passive_status=passive_status,
    )


def test_expired_final_window_never_falls_back_to_active_group_send(tmp_path: Path) -> None:
    cfg, journal, clock, binding, issue, service, approval = approved_case(tmp_path)
    clock.advance(hours=2)
    transport = bound_transport(cfg, journal, binding)

    first = service.execute_final_response(approval, transport=transport)
    second = service.execute_final_response(approval, transport=transport)

    assert first["status"] == "expired_window"
    assert first["provider_accepted"] is False
    assert second == first
    assert transport.passive_group_calls == 0
    assert transport.group_nudge_calls == 0
    assert journal.artifact_content(issue["artifact_id"])


@pytest.mark.parametrize("status", ["timed_out", "disconnected", "unknown"])
def test_ambiguous_final_classes_persist_without_second_attempt(
    tmp_path: Path, status: str
) -> None:
    cfg, journal, _, binding, _, service, approval = approved_case(tmp_path)
    transport = bound_transport(cfg, journal, binding, passive_status=status)

    first = service.execute_final_response(approval, transport=transport)
    second = service.execute_final_response(approval, transport=transport)

    assert first["status"] == status
    assert first["provider_accepted"] is False
    assert second == first
    assert transport.passive_group_calls == 1
