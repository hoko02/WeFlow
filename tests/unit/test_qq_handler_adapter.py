from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from weflow_control_kernel.qq_handler import (
    QQ_GROUP_NUDGE_TEMPLATE,
    QQ_NOTIFICATION_TEMPLATE,
    QQHandlerTransportError,
)
from weflow_control_worker.qq_handler_adapter import RealQQHandlerTransport


@dataclass
class FakeHTTPResult:
    status: int = 200
    payload: dict[str, Any] = field(default_factory=lambda: {"id": "provider-message-1"})


@dataclass
class RecordingClient:
    result: FakeHTTPResult = field(default_factory=FakeHTTPResult)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> FakeHTTPResult:
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "payload": payload}
        )
        return self.result


def transport(client: RecordingClient) -> RealQQHandlerTransport:
    return RealQQHandlerTransport(
        client,  # type: ignore[arg-type]
        access_token="not-a-real-secret",
        group_openid="bound-group",
        user_openid="bound-user",
    )


def test_real_handler_adapter_has_no_arbitrary_recipient_or_notification_body() -> None:
    client = RecordingClient()
    adapter = transport(client)

    with pytest.raises(QQHandlerTransportError, match="destination_denied"):
        adapter.notify_c2c(
            user_openid="foreign-user",
            content=QQ_NOTIFICATION_TEMPLATE.format(
                case_reference="case_111111111111111111111111", version=1
            ),
            idempotency_key="ignored",
        )
    with pytest.raises(QQHandlerTransportError, match="content_denied"):
        adapter.notify_c2c(
            user_openid="bound-user",
            content="SYNTHETIC_PRIVATE_CONTENT",
            idempotency_key="ignored",
        )

    assert client.calls == []


def test_real_handler_adapter_uses_only_bounded_qq_endpoints_and_passive_shapes() -> None:
    client = RecordingClient()
    adapter = transport(client)
    case_id = "case_111111111111111111111111"

    notification = adapter.notify_c2c(
        user_openid="bound-user",
        content=QQ_NOTIFICATION_TEMPLATE.format(case_reference=case_id, version=1),
        idempotency_key="ignored",
    )
    c2c = adapter.passive_c2c_reply(
        user_openid="bound-user",
        source_message_id="synthetic/C2C+opaque=message==",
        msg_seq=1,
        content="SYNTHETIC_PRIVATE_REPLY",
        idempotency_key="ignored",
    )
    nudge = adapter.group_nudge(
        group_openid="bound-group",
        source_message_id="intake-source",
        msg_seq=2,
        content=QQ_GROUP_NUDGE_TEMPLATE,
        idempotency_key="ignored",
    )
    final = adapter.passive_group_reply(
        group_openid="bound-group",
        source_message_id="approval-source",
        msg_seq=5,
        content="SYNTHETIC_APPROVED_RESPONSE",
        idempotency_key="ignored",
    )

    assert {notification.status, c2c.status, nudge.status, final.status} == {"accepted"}
    assert [call["url"] for call in client.calls] == [
        "https://api.bot.qq.com/v2/users/bound-user/messages",
        "https://api.bot.qq.com/v2/users/bound-user/messages",
        "https://api.bot.qq.com/v2/groups/bound-group/messages",
        "https://api.bot.qq.com/v2/groups/bound-group/messages",
    ]
    assert client.calls[0]["payload"] == {
        "msg_type": 0,
        "content": QQ_NOTIFICATION_TEMPLATE.format(case_reference=case_id, version=1),
    }
    assert client.calls[2]["payload"]["msg_seq"] == 2
    assert client.calls[1]["payload"]["msg_id"] == "synthetic/C2C+opaque=message=="
    assert client.calls[3]["payload"]["msg_seq"] == 5


def test_real_handler_adapter_classifies_rate_limit_and_expired_window() -> None:
    client = RecordingClient(FakeHTTPResult(status=429, payload={"code": 0}))
    adapter = transport(client)
    rate_limited = adapter.notify_c2c(
        user_openid="bound-user",
        content=QQ_NOTIFICATION_TEMPLATE.format(
            case_reference="case_111111111111111111111111", version=1
        ),
        idempotency_key="ignored",
    )
    assert rate_limited.status == "rate_limited"

    client.result = FakeHTTPResult(status=400, payload={"code": 304103})
    expired = adapter.passive_c2c_reply(
        user_openid="bound-user",
        source_message_id="private-source",
        msg_seq=1,
        content="SYNTHETIC_PRIVATE_REPLY",
        idempotency_key="ignored",
    )
    assert expired.status == "expired_window"
