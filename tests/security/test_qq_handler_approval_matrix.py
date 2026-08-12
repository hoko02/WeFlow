from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import (
    QQGroupApprovalCommand,
    QQHandlerAuthorizationDenied,
    QQHandlerEventRejected,
    parse_group_approval,
)

SECURITY = Path(__file__).resolve().parent
UNIT = Path(__file__).resolve().parents[1] / "unit"
for directory in (SECURITY, UNIT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from test_qq_handler_security import _draft_twice  # noqa: E402
from test_qq_handler_workflow import group_event  # noqa: E402


def test_group_approval_rejects_plaintext_preview_and_ambiguous_hash_shapes() -> None:
    request_id = "qqhar_" + "1" * 32
    with pytest.raises(QQHandlerEventRejected, match="unknown_or_malformed"):
        parse_group_approval(
            f"@机器人 WF-APPROVE {request_id} {'a' * 12} 3 SYNTHETIC_CANDIDATE"
        )
    with pytest.raises(QQHandlerEventRejected, match="unknown_or_malformed"):
        parse_group_approval(f"@机器人 WF-PREVIEW {request_id} {'a' * 12} 3")
    with pytest.raises(QQHandlerEventRejected, match="metadata_invalid"):
        parse_group_approval(f"@机器人 WF-APPROVE {request_id} {'a' * 11} 3")


def test_group_approval_rejects_wrong_or_extended_prefix_foreign_group_and_version(
    tmp_path: Path,
) -> None:
    service, clock, _, metadata_text, version = _draft_twice(tmp_path)
    request_id, prefix, _ = metadata_text.split()
    for suffix, candidate_prefix in (
        ("wrong", "0" * len(prefix)),
        ("extended", prefix + "0"),
    ):
        with pytest.raises(
            QQHandlerAuthorizationDenied, match="hash_mismatch_or_ambiguous"
        ):
            service.handle_group_approval(
                group_event(
                    content=(
                        f"@机器人 WF-APPROVE {request_id} {candidate_prefix} {version}"
                    ),
                    message_id=f"approve-{suffix}",
                    timestamp=clock(),
                )
            )

    foreign = group_event(
        content=f"@机器人 WF-APPROVE {metadata_text}",
        message_id="approve-foreign-group",
        timestamp=clock(),
    )
    foreign["d"]["group_openid"] = "foreign-group"  # type: ignore[index]
    with pytest.raises(QQHandlerAuthorizationDenied, match="foreign_group"):
        service.handle_group_approval(foreign)

    with pytest.raises(QQHandlerAuthorizationDenied, match="version"):
        service.handle_group_approval(
            group_event(
                content=f"@机器人 WF-APPROVE {request_id} {prefix} {version + 1}",
                message_id="approve-wrong-version",
                timestamp=clock(),
            )
        )


def test_approval_request_cannot_be_rebound_to_another_handler(tmp_path: Path) -> None:
    service, clock, _, metadata_text, version = _draft_twice(tmp_path)
    request_id, prefix, _ = metadata_text.split()
    foreign_binding = copy.deepcopy(service.binding)
    foreign_binding["handler_binding_id"] = "qqhbind_" + "f" * 32
    bound_group_member = service.journal.private_locator(
        service.binding["handler_binding_id"], "group-member"
    )

    with pytest.raises(QQHandlerAuthorizationDenied):
        service.journal.approve_request(
            binding=foreign_binding,
            command=QQGroupApprovalCommand(request_id, prefix, version),
            member_openid=bound_group_member,
            group_openid=service.config.group_openid,
            source_message_id="approve-rebound",
            occurred_at=clock(),
            identity_salt=service.config.identity_salt,
        )
