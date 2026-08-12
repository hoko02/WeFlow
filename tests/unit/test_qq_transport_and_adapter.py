from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from weflow_control_kernel.ledger import SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQ_ACK_TEMPLATE,
    QQSandboxConfig,
    QQTransportError,
    SQLiteQQSandboxJournal,
)
from weflow_control_kernel.qq_transport import (
    FakeQQGatewayTransport,
    FakeQQPassiveAcknowledgementTransport,
    FakeQQTokenTransport,
    FakeQQWebSocketTransport,
)
from weflow_control_worker.qq_adapter import (
    RealQQGatewayTransport,
    RealQQPassiveAcknowledgementTransport,
    RealQQTokenTransport,
    RealQQWebSocketConnection,
    _HTTPResult,
)
from weflow_control_worker.qq_runner import QQGatewayRunner

ROOT = Path(__file__).resolve().parents[2]


def config() -> QQSandboxConfig:
    return QQSandboxConfig(
        app_id="qq-app-sandbox",
        client_secret="not-a-real-secret",
        group_openid="qq-group-sandbox",
        tenant_id="tenant-alpha",
        identity_salt="process-only-salt",
    )


class StubHTTPClient:
    def __init__(self, results: list[_HTTPResult]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> _HTTPResult:
        self.calls.append(
            {"method": method, "url": url, "headers": headers or {}, "payload": payload}
        )
        return self.results.pop(0)


def test_real_token_gateway_and_fixed_send_use_current_qq_shapes() -> None:
    client = StubHTTPClient(
        [
            _HTTPResult(200, {"access_token": "not-a-real-secret", "expires_in": "7200"}),
            _HTTPResult(200, {"url": "wss://api.sgroup.qq.com/websocket/"}),
            _HTTPResult(200, {"id": "qq-provider-message", "timestamp": "safe"}),
        ]
    )
    token = RealQQTokenTransport(client).fetch(
        app_id="qq-app-sandbox", client_secret="not-a-real-secret"
    )
    gateway = RealQQGatewayTransport(client).fetch(access_token=token.value)
    passive = RealQQPassiveAcknowledgementTransport(client, config(), token.value)
    outcome = passive.send_fixed_acknowledgement(
        group_openid="qq-group-sandbox",
        source_message_id="qq-source-message",
        reply_msg_seq=1,
        idempotency_key="server-owned",
        content=QQ_ACK_TEMPLATE.format(case_id="case-safe"),
    )

    assert gateway.url == "wss://api.sgroup.qq.com/websocket/"
    assert outcome.status == "accepted"
    assert client.calls[0]["payload"] == {
        "appId": "qq-app-sandbox",
        "clientSecret": "not-a-real-secret",
    }
    assert client.calls[1]["headers"] == {"Authorization": "QQBot not-a-real-secret"}
    assert client.calls[2]["headers"] == {"Authorization": "QQBot not-a-real-secret"}
    assert client.calls[2]["payload"] == {
        "msg_type": 0,
        "content": QQ_ACK_TEMPLATE.format(case_id="case-safe"),
        "msg_id": "qq-source-message",
        "msg_seq": 1,
    }


def test_real_send_maps_official_duplicate_and_denies_arbitrary_write() -> None:
    client = StubHTTPClient([_HTTPResult(400, {"code": 40054005, "message": "not logged"})])
    passive = RealQQPassiveAcknowledgementTransport(client, config(), "not-a-real-secret")
    duplicate = passive.send_fixed_acknowledgement(
        group_openid="qq-group-sandbox",
        source_message_id="qq-source-message",
        reply_msg_seq=1,
        idempotency_key="server-owned",
        content=QQ_ACK_TEMPLATE.format(case_id="case-safe"),
    )
    assert duplicate.status == "duplicate"
    assert duplicate.reason_code == "qq_provider_message_deduplicated"
    assert "not logged" not in str(duplicate)

    for kwargs in (
        {"group_openid": "foreign-group"},
        {"reply_msg_seq": 2},
        {"content": "这是任意回复或最终答复"},
    ):
        request = {
            "group_openid": "qq-group-sandbox",
            "source_message_id": "qq-source-message",
            "reply_msg_seq": 1,
            "idempotency_key": "server-owned",
            "content": QQ_ACK_TEMPLATE.format(case_id="case-safe"),
            **kwargs,
        }
        with pytest.raises(QQTransportError):
            passive.send_fixed_acknowledgement(**request)
    assert len(client.calls) == 1


class RawWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.frames: list[object] = [{"op": 11}]

    async def recv(self) -> object:
        return self.frames.pop(0)

    async def send(self, value: str) -> None:
        self.sent.append(value)

    async def close(self) -> None:
        return None


def test_real_websocket_wrapper_rejects_unrestricted_non_json_frame() -> None:
    socket = RawWebSocket()
    socket.frames = ["not-json"]
    with pytest.raises(QQTransportError, match="qq_websocket_frame_invalid"):
        asyncio.run(RealQQWebSocketConnection(socket).receive())


def test_deterministic_transports_and_runner_need_no_network_or_credentials(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    event_time = now.isoformat().replace("+00:00", "Z")
    frames = [
        {"op": 10, "d": {"heartbeat_interval": 45_000}},
        {
            "op": 0,
            "s": 1,
            "t": "READY",
            "d": {"session_id": "memory-only-session"},
        },
        {
            "op": 0,
            "s": 2,
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "qq-source-message",
                "group_openid": "qq-group-sandbox",
                "author": {"member_openid": "qq-member-customer"},
                "content": "广告系统出现了API 503错误",
                "timestamp": event_time,
            },
        },
    ]
    path = tmp_path / "qq.sqlite3"
    token = FakeQQTokenTransport()
    gateway = FakeQQGatewayTransport()
    websocket = FakeQQWebSocketTransport(frames)
    passive = FakeQQPassiveAcknowledgementTransport("qq-group-sandbox")
    runner = QQGatewayRunner(
        config=config(),
        token_transport=token,
        gateway_transport=gateway,
        websocket_transport=websocket,
        ledger=SQLiteCaseLedger(path, contract_root=ROOT),
        journal=SQLiteQQSandboxJournal(path, contract_root=ROOT),
        passive_transport_factory=lambda _: passive,
        contract_root=ROOT,
        verify_event_dedup=True,
    )
    result = asyncio.run(runner.run_one()).report

    assert result["accepted"] is True
    assert result["fake_transport_verified"] is True
    assert result["qq_sandbox_live_verified"] is False
    assert result["customer_receipt_verified"] is False
    assert result["same_event_deduplication_verified"] is True
    assert result["duplicate_event_count"] == 1
    assert result["same_case_reused"] is True
    assert result["same_acknowledgement_intent_reused"] is True
    assert result["second_qq_write_attempted"] is False
    assert result["second_logical_acknowledgement"] is False
    assert result["case_count_delta"] == 1
    assert result["acknowledgement_intent_count_delta"] == 1
    assert result["acknowledgement_observation_count_delta"] == 1
    assert result["acknowledgement_completion_count_delta"] == 1
    assert token.calls == gateway.calls == passive.send_calls == 1
    assert websocket.connections[0].sent[0]["op"] == 2
    assert websocket.connections[0].sent[0]["d"]["intents"] == 1 << 25
    assert "memory-only-session" not in str(result)
    assert "广告系统" not in str(result)
