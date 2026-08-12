from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQEventRejected,
    QQSandboxConfig,
    QQSandboxIntakeService,
    SQLiteQQSandboxJournal,
)
from weflow_control_kernel.qq_transport import (
    FakeQQGatewayTransport,
    FakeQQPassiveAcknowledgementTransport,
    FakeQQTokenTransport,
    FakeQQWebSocketTransport,
)
from weflow_control_worker.qq_runner import QQGatewayRunner

ROOT = Path(__file__).resolve().parents[2]


def config() -> QQSandboxConfig:
    return QQSandboxConfig(
        "fake-app", "not-a-real-secret", "fake-group", "fake-tenant", "fake-salt"
    )


def event(message_id: str, sequence: int, timestamp: str) -> dict[str, object]:
    return {
        "op": 0,
        "s": sequence,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": message_id,
            "group_openid": "fake-group",
            "author": {"member_openid": "fake-member"},
            "message_type": 0,
            "content": "广告系统出现了API 503错误",
            "timestamp": timestamp,
        },
    }


def test_new_gateway_session_resets_cursor_but_business_dedup_stays_stable(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    clock = FixedClock(now)
    timestamp = now.isoformat().replace("+00:00", "Z")
    path = tmp_path / "qq.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=ROOT)
    service = QQSandboxIntakeService(
        ledger, journal, config(), clock=clock, contract_root=ROOT
    )

    journal.record_cursor(config(), sequence=1, status="identified", session_id="session-a")
    first = service.accept(event("message-a", 2, timestamp), session_id="session-a")
    assert first.intake.disposition == "accepted"

    journal.record_cursor(config(), sequence=1, status="identified", session_id="session-b")
    assert journal.get_cursor(config())["last_contiguous_sequence"] == 1
    duplicate = service.accept(event("message-a", 2, timestamp), session_id="session-b")
    assert duplicate.intake.disposition == "deduplicated"

    journal.record_cursor(config(), sequence=1, status="identified", session_id="session-c")
    second = service.accept(event("message-b", 2, timestamp), session_id="session-c")
    assert second.intake.disposition == "accepted"
    assert second.intake.case_id != first.intake.case_id
    assert ledger.source_counts("fake-tenant")["cases"] == 2
    assert journal.safe_counts("fake-tenant")["acknowledgement_intent_count"] == 2


def test_same_session_out_of_order_new_message_is_rejected_before_case(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    clock = FixedClock(now)
    timestamp = now.isoformat().replace("+00:00", "Z")
    path = tmp_path / "out-of-order.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=ROOT)
    service = QQSandboxIntakeService(
        ledger, journal, config(), clock=clock, contract_root=ROOT
    )
    service.accept(event("message-a", 42, timestamp), session_id="session-a")

    with pytest.raises(QQEventRejected, match="qq_gateway_sequence_out_of_order"):
        service.accept(event("message-b", 41, timestamp), session_id="session-a")
    assert ledger.source_counts("fake-tenant")["cases"] == 1


def test_runner_accepts_second_case_after_process_restart_and_new_ready_session(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    path = tmp_path / "runner.sqlite3"
    ledger = SQLiteCaseLedger(path, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, contract_root=ROOT)

    def run(message_id: str, session_id: str) -> dict[str, object]:
        websocket = FakeQQWebSocketTransport(
            [
                {"op": 10, "d": {"heartbeat_interval": 45_000}},
                {"op": 0, "s": 1, "t": "READY", "d": {"session_id": session_id}},
                event(message_id, 2, now),
            ]
        )
        passive = FakeQQPassiveAcknowledgementTransport("fake-group")
        return asyncio.run(
            QQGatewayRunner(
                config=config(),
                token_transport=FakeQQTokenTransport(),
                gateway_transport=FakeQQGatewayTransport(),
                websocket_transport=websocket,
                ledger=ledger,
                journal=journal,
                passive_transport_factory=lambda _: passive,
                contract_root=ROOT,
            ).run_one()
        ).report

    assert run("message-a", "session-a")["accepted"] is True
    assert run("message-b", "session-b")["accepted"] is True
    assert ledger.source_counts("fake-tenant")["cases"] == 2
