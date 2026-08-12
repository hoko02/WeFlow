from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQAcknowledgementController,
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


def stack(tmp_path: Path):
    now = datetime.now(UTC).replace(microsecond=0)
    clock = FixedClock(now)
    path = tmp_path / "qq.sqlite3"
    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=ROOT)
    service = QQSandboxIntakeService(
        ledger, journal, config(), clock=clock, contract_root=ROOT
    )
    accepted = service.accept(
        {
            "op": 0,
            "s": 1,
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "fake-message",
                "group_openid": "fake-group",
                "author": {"member_openid": "fake-member"},
                "message_type": 0,
                "content": "广告系统出现了API 503错误",
                "timestamp": now.isoformat().replace("+00:00", "Z"),
            },
        }
    )
    return now, ledger, journal, accepted


def runner(
    *,
    ledger: SQLiteCaseLedger,
    journal: SQLiteQQSandboxJournal,
    passive: FakeQQPassiveAcknowledgementTransport,
    websocket: FakeQQWebSocketTransport,
) -> QQGatewayRunner:
    return QQGatewayRunner(
        config=config(),
        token_transport=FakeQQTokenTransport(),
        gateway_transport=FakeQQGatewayTransport(),
        websocket_transport=websocket,
        ledger=ledger,
        journal=journal,
        passive_transport_factory=lambda _: passive,
        contract_root=ROOT,
    )


def test_restart_recovers_stop_after_intent_without_new_gateway_event(tmp_path: Path) -> None:
    _, ledger, journal, accepted = stack(tmp_path)
    websocket = FakeQQWebSocketTransport([])
    passive = FakeQQPassiveAcknowledgementTransport("fake-group")

    assert journal.recoverable_intent_ids("fake-tenant") == [accepted.intent["intent_id"]]
    report = asyncio.run(
        runner(ledger=ledger, journal=journal, passive=passive, websocket=websocket).run_one()
    ).report

    assert report["accepted"] is True
    assert report["intake_disposition"] == "recovered_pending_intent"
    assert report["gateway_event_observed_this_run"] is False
    assert report["recovery_attempted"] is True
    assert passive.send_calls == 1
    assert websocket.connections == []
    assert journal.recoverable_intent_ids("fake-tenant") == []


def test_lost_response_restart_reconciles_provider_presence_without_second_send(
    tmp_path: Path,
) -> None:
    now, ledger, journal, accepted = stack(tmp_path)
    passive = FakeQQPassiveAcknowledgementTransport("fake-group", lose_first_response=True)
    first = QQAcknowledgementController(
        journal, passive, config(), clock=FixedClock(now)
    ).process(str(accepted.intent["intent_id"]))
    assert first["status"] == "NEEDS_RECONCILIATION"
    assert passive.send_calls == 1

    websocket = FakeQQWebSocketTransport([])
    recovered = asyncio.run(
        runner(ledger=ledger, journal=journal, passive=passive, websocket=websocket).run_one()
    ).report

    assert recovered["accepted"] is True
    assert recovered["acknowledgement_status"] == "completed"
    assert passive.send_calls == 1
    assert websocket.connections == []


def test_expired_or_unauthorized_observation_is_not_auto_retried(tmp_path: Path) -> None:
    now, _, journal, accepted = stack(tmp_path)
    passive = FakeQQPassiveAcknowledgementTransport("fake-group")
    expired = QQAcknowledgementController(
        journal,
        passive,
        config(),
        clock=FixedClock(now + timedelta(minutes=6)),
    ).process(str(accepted.intent["intent_id"]))

    assert expired["status"] == "expired"
    assert passive.reconcile_calls == passive.send_calls == 0
    assert journal.recoverable_intent_ids("fake-tenant") == []
