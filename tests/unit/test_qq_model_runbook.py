from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "development" / "qq-bounded-live-model-workflow.md"


def test_stage3_runbook_covers_closed_setup_protocol_and_verification() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "qq-sandbox-live-model-workflow",
        "qq-sandbox-live-model-workflow-verify",
        "--readiness-only",
        "--offline-fake",
        "--confirm-live-qq",
        "--confirm-live-model",
        "WF-PULL <case_id> 1",
        "WF-ACCEPT <case_id> 1",
        "WF-ASSIST <case_id> 2",
        "WF-DRAFT <case_id> <current_version>",
        "WF-APPROVE <approval_request_id> <candidate_hash_prefix> <expected_version>",
    ):
        assert required in text


def test_stage3_runbook_documents_exact_capabilities_privacy_and_layered_outcomes() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "qq.group_at.read",
        "qq.passive_ack.execute",
        "qq.c2c.read",
        "qq.c2c.notification.execute",
        "qq.c2c.passive_reply.execute",
        "qq.handler_approval.decide",
        "qq.final_reply.execute",
        "model.proposal.invoke",
        "fixture.crm.read",
        "fixture.monitoring.read",
        "fixture.knowledge.read",
        "provider_outcome_unknown",
        "最多保留 24 小时",
        "customer_receipt_verified=false",
        "production_ready=false",
        "ZeroFreeBSTR",
        "不要删除 `.weflow/qq-sandbox.sqlite3`",
    ):
        assert required in text
    assert "Authorization: Bearer" not in text
    assert "sk-" not in text
