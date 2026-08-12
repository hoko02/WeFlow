from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQJournalError,
    QQSandboxConfig,
    QQSandboxIntakeService,
    SQLiteQQSandboxJournal,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 10, 0, 0, 1, tzinfo=UTC)


def test_qq_journal_discards_transcript_and_secret_then_purges_reply_locator(
    tmp_path: Path,
) -> None:
    path = tmp_path / "qq.sqlite3"
    clock = FixedClock(NOW)
    config = QQSandboxConfig(
        app_id="qq-app-sandbox",
        client_secret="not-a-real-secret",
        group_openid="qq-group-sandbox",
        tenant_id="tenant-alpha",
        identity_salt="identity-salt-never-persisted",
    )
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=ROOT)
    service = QQSandboxIntakeService(
        SQLiteCaseLedger(path, clock=clock, contract_root=ROOT),
        journal,
        config,
        clock=clock,
        contract_root=ROOT,
    )
    accepted = service.accept(
        {
            "op": 0,
            "s": 1,
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "qq-message-opaque",
                "group_openid": "qq-group-sandbox",
                "author": {
                    "member_openid": "qq-member-private",
                    "username": "客户显示名",
                },
                "content": "广告系统出现了API 503错误",
                "timestamp": "2026-08-10T00:00:00Z",
            },
        },
        session_id="session-private",
    )

    stored = path.read_bytes()
    for forbidden in (
        "广告系统出现了API 503错误",
        "客户显示名",
        "qq-member-private",
        "not-a-real-secret",
        "identity-salt-never-persisted",
        "session-private",
    ):
        assert forbidden.encode("utf-8") not in stored

    assert journal.purge_expired_locators(now=NOW + timedelta(days=1, seconds=1)) == 1
    with pytest.raises(QQJournalError, match="qq_reply_locator_not_found"):
        journal.get_locator("tenant-alpha", str(accepted.intent["intent_id"]))
    assert journal.safe_counts("tenant-alpha") == {
        "gateway_cursor_count": 1,
        "acknowledgement_intent_count": 1,
        "acknowledgement_observation_count": 0,
        "acknowledgement_completion_count": 0,
    }
