from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "development" / "qq-sandbox-intake-and-ack.md"
DEV = ROOT / "scripts" / "dev.py"


def test_qq_runbook_covers_operator_gate_stop_disable_retention_and_rollback() -> None:
    guide = RUNBOOK.read_text(encoding="utf-8")

    for required in (
        "qq-sandbox-offline-acceptance",
        "qq-sandbox-intake-ack",
        "--confirm-live-qq",
        "qq-sandbox-pair-group",
        "--confirm-live-qq-pairing",
        "--readiness-only",
        "--verify-live-event-dedup",
        "gateway_ready=true",
        "pairing_challenge_expired",
        "qq-sandbox-acceptance-verify",
        "Ctrl+C",
        "Remove-Item Env:WEFLOW_QQ_CLIENT_SECRET",
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID",
        "qq.group_at.read,qq.passive_ack.execute",
        "24 hours",
        "NEEDS_RECONCILIATION",
        "customer_receipt_verified=false",
        "production_ready=false",
        "AppID",
        "AppSecret",
        "group_openid",
        "Rollback",
    ):
        assert required in guide
    assert "????????" not in guide
    assert "已受理，工单编号：{case_id}。当前仅确认已进入处理流程，不代表问题已解决。" in guide
    assert "https://bot.q.qq.com/wiki/develop/api-v2/" in guide


def test_qq_runbook_does_not_embed_a_real_credential_or_group_value() -> None:
    guide = RUNBOOK.read_text(encoding="utf-8")

    assert "process-only-secret" not in guide
    assert "qq-group-sandbox" not in guide
    assert "offline-fake-secret" not in guide
    assert "Authorization: QQBot ey" not in guide


def test_pairing_command_source_has_a_readable_gateway_ready_instruction() -> None:
    source = DEV.read_text(encoding="utf-8")

    assert "????????" not in source
    assert "\\u5728\\u552f\\u4e00\\u6d4b\\u8bd5\\u7fa4\\u53d1\\u9001" in source
