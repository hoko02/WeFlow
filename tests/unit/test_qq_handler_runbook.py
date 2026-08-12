from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "development" / "qq-sandbox-handler-approval-and-delivery.md"


def test_handler_runbook_covers_dual_pairing_and_closed_private_protocol() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "qq-sandbox-handler-approval",
        "--readiness-only",
        "--pair-handler",
        "CONFIRM-DUAL-QQ-HANDLER",
        "WFH-GROUP-...",
        "WFH-C2C-...",
        "WF-PULL <case_id> 1",
        "WF-ACCEPT <case_id> 1",
        "WF-DRAFT <case_id> 2",
        "WF-REJECT <case_id> <expected_version> not_my_scope",
        "WF-APPROVE <approval_request_id> <candidate_hash_prefix> <expected_version>",
    ):
        assert required in text


def test_handler_runbook_warns_about_windows_at_most_once_and_privacy() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "五分钟",
        "只有一个 transport attempt",
        "不会改用主动群发",
        "不保存群/C2C transcript",
        "最多 24 小时",
        "customer receipt",
        "production readiness",
        "Ctrl+C",
        "不要删除本地 journal",
    ):
        assert required in text


def test_handler_runbook_has_exact_capabilities_and_safe_cleanup() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for capability in (
        "qq.group_at.read",
        "qq.c2c.read",
        "qq.c2c.notification.execute",
        "qq.c2c.passive_reply.execute",
        "qq.handler_approval.decide",
        "qq.final_reply.execute",
    ):
        assert capability in text
    assert "Remove-Item Env:WEFLOW_QQ_CLIENT_SECRET" in text
    assert "ZeroFreeBSTR" in text
    assert "qq-sandbox-handler-verify" in text
