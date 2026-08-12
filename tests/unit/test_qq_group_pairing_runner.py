import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weflow_control_kernel.qq_pairing import (
    QQGroupPairingConfig,
    QQGroupPairingController,
    SQLiteQQPairingJournal,
    create_pairing_challenge,
)
from weflow_control_kernel.qq_sandbox import QQTransportError
from weflow_control_kernel.qq_transport import (
    FakeQQGatewayTransport,
    FakeQQTokenTransport,
    FakeQQWebSocketTransport,
)
from weflow_control_worker.qq_pairing_runner import QQGroupPairingRunner

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 10, tzinfo=UTC)


def test_fake_pairing_runner_observes_one_event_without_write_runtime(tmp_path: Path) -> None:
    config = QQGroupPairingConfig(
        "app", "secret", "tenant", tmp_path / ".weflow/qq-sandbox.sqlite3", tmp_path
    )
    journal = SQLiteQQPairingJournal(config.store_path, clock=lambda: NOW, contract_root=ROOT)
    challenge = create_pairing_challenge(
        config,
        clock=lambda: NOW,
        token_factory=lambda: "abcdefghijklmnopqrstuvwx",
        contract_root=ROOT,
    )
    controller = QQGroupPairingController(config, journal, challenge, clock=lambda: NOW)
    websocket = FakeQQWebSocketTransport(
        [
            {"op": 10, "d": {"heartbeat_interval": 30000}},
            {"op": 0, "s": 1, "t": "READY", "d": {"session_id": "session"}},
            {
                "op": 0,
                "s": 2,
                "t": "GROUP_AT_MESSAGE_CREATE",
                "d": {
                    "id": "message",
                    "group_openid": "group",
                    "author": {"member_openid": "member"},
                    "content": "@机器人 " + challenge.plaintext,
                    "timestamp": "2026-08-10T00:00:00Z",
                },
            },
        ]
    )
    runner = QQGroupPairingRunner(
        config=config,
        controller=controller,
        token_transport=FakeQQTokenTransport(),
        gateway_transport=FakeQQGatewayTransport(),
        websocket_transport=websocket,
        contract_root=ROOT,
    )
    announced: list[str] = []

    def announce(challenge_text: str) -> None:
        assert websocket.connections[0].sent[0]["op"] == 2
        announced.append(challenge_text)

    report = asyncio.run(runner.run_one(on_listening=announce))
    assert report["accepted"] is True and report["qq_write_attempted"] is False
    assert announced == [challenge.plaintext]
    assert websocket.connections[0].sent[0]["op"] == 2
    assert all(frame["op"] in {1, 2, 6} for frame in websocket.connections[0].sent)


def test_fake_transports_cannot_publish_live_pairing_evidence(tmp_path: Path) -> None:
    config = QQGroupPairingConfig(
        "app", "secret", "tenant", tmp_path / ".weflow/qq-sandbox.sqlite3", tmp_path
    )
    challenge = create_pairing_challenge(
        config, clock=lambda: NOW, token_factory=lambda: "abcdefghijklmnopqrstuvwx"
    )
    controller = QQGroupPairingController(
        config,
        SQLiteQQPairingJournal(config.store_path, clock=lambda: NOW),
        challenge,
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match="pairing_live_evidence_requires_real_adapters"):
        QQGroupPairingRunner(
            config=config,
            controller=controller,
            token_transport=FakeQQTokenTransport(),
            gateway_transport=FakeQQGatewayTransport(),
            websocket_transport=FakeQQWebSocketTransport([]),
            contract_root=ROOT,
            evidence_mode="live",
        )


class _UnknownTokenTransport(FakeQQTokenTransport):
    def fetch(self, *, app_id: str, client_secret: str):
        del app_id, client_secret
        raise QQTransportError("qq_provider_outcome_unknown")


class _UnknownGatewayTransport(FakeQQGatewayTransport):
    def fetch(self, *, access_token: str):
        del access_token
        raise QQTransportError("qq_provider_outcome_unknown")


@pytest.mark.parametrize(
    ("token_transport", "gateway_transport", "expected_reason"),
    (
        (
            _UnknownTokenTransport(),
            FakeQQGatewayTransport(),
            "pairing_token_transport_unreachable",
        ),
        (
            FakeQQTokenTransport(),
            _UnknownGatewayTransport(),
            "pairing_gateway_transport_unreachable",
        ),
    ),
)
def test_pairing_runner_reports_the_failed_http_stage_before_challenge_display(
    tmp_path: Path,
    token_transport: FakeQQTokenTransport,
    gateway_transport: FakeQQGatewayTransport,
    expected_reason: str,
) -> None:
    config = QQGroupPairingConfig(
        "app", "secret", "tenant", tmp_path / ".weflow/qq-sandbox.sqlite3", tmp_path
    )
    challenge = create_pairing_challenge(
        config, clock=lambda: NOW, token_factory=lambda: "abcdefghijklmnopqrstuvwx"
    )
    controller = QQGroupPairingController(
        config,
        SQLiteQQPairingJournal(config.store_path, clock=lambda: NOW),
        challenge,
        clock=lambda: NOW,
    )
    runner = QQGroupPairingRunner(
        config=config,
        controller=controller,
        token_transport=token_transport,
        gateway_transport=gateway_transport,
        websocket_transport=FakeQQWebSocketTransport([]),
        contract_root=ROOT,
    )
    announced: list[str] = []
    with pytest.raises(QQTransportError, match=expected_reason):
        asyncio.run(runner.run_one(on_listening=announced.append))
    assert announced == []


def test_pairing_runner_expires_before_network_and_appends_terminal_lifecycle(
    tmp_path: Path,
) -> None:
    config = QQGroupPairingConfig(
        "app", "secret", "tenant", tmp_path / ".weflow/qq-sandbox.sqlite3", tmp_path
    )
    journal = SQLiteQQPairingJournal(config.store_path, clock=lambda: NOW + timedelta(seconds=301))
    challenge = create_pairing_challenge(
        config, clock=lambda: NOW, token_factory=lambda: "abcdefghijklmnopqrstuvwx"
    )
    controller = QQGroupPairingController(
        config, journal, challenge, clock=lambda: NOW + timedelta(seconds=301)
    )
    token_transport = FakeQQTokenTransport()
    runner = QQGroupPairingRunner(
        config=config,
        controller=controller,
        token_transport=token_transport,
        gateway_transport=FakeQQGatewayTransport(),
        websocket_transport=FakeQQWebSocketTransport([]),
        contract_root=ROOT,
    )
    announced: list[str] = []
    with pytest.raises(QQTransportError, match="pairing_challenge_expired"):
        asyncio.run(runner.run_one(on_listening=announced.append))
    assert token_transport.calls == 0
    assert announced == []
    with sqlite3.connect(journal.path) as connection:
        row = connection.execute(
            "SELECT status,reason_code FROM qq_pairing_lifecycle "
            "WHERE challenge_id=? ORDER BY rowid DESC LIMIT 1",
            (challenge.record["challenge_id"],),
        ).fetchone()
    assert row == ("EXPIRED", "pairing_challenge_expired")
