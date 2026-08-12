"""Real QQ sandbox transports, importable only by the dedicated live command."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from weflow_control_kernel.qq_sandbox import (
    QQ_ACK_TEMPLATE,
    QQSandboxConfig,
    QQSendOutcome,
    QQTransportError,
)
from weflow_control_kernel.qq_transport import QQAccessToken, QQGatewayEndpoint

QQ_OPENAPI_ORIGIN = "https://api.bot.qq.com"
QQ_TOKEN_URL = f"{QQ_OPENAPI_ORIGIN}/app/getAppAccessToken"
QQ_GROUP_INTENT = 1 << 25
MAX_HTTP_RESPONSE_BYTES = 65_536
MAX_WEBSOCKET_MESSAGE_BYTES = 65_536
_ALLOWED_HOST = "api.bot.qq.com"
_SOURCE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_CASE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_ACK_PREFIX, _ACK_SUFFIX = QQ_ACK_TEMPLATE.split("{case_id}")


@dataclass(frozen=True)
class _HTTPResult:
    status: int
    payload: Mapping[str, Any] | None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: object, **__: object) -> None:
        return None


class BoundedQQHTTPClient:
    """HTTPS-only, host-bound JSON client that never exposes raw response bodies."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise QQTransportError("qq_http_timeout_invalid")
        self.timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context())
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> _HTTPResult:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != _ALLOWED_HOST:
            raise QQTransportError("qq_http_destination_denied")
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=body, headers=request_headers, method=method
        )
        try:
            response = self._opener.open(request, timeout=self.timeout_seconds)
            status = int(response.status)
            raw = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            status = int(error.code)
            raw = error.read(MAX_HTTP_RESPONSE_BYTES + 1)
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise QQTransportError("qq_provider_outcome_unknown") from error
        if len(raw) > MAX_HTTP_RESPONSE_BYTES:
            raise QQTransportError("qq_provider_response_too_large")
        try:
            decoded = json.loads(raw) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _HTTPResult(status, None)
        return _HTTPResult(status, decoded if isinstance(decoded, Mapping) else None)


class RealQQTokenTransport:
    def __init__(self, client: BoundedQQHTTPClient) -> None:
        self._client = client

    def fetch(self, *, app_id: str, client_secret: str) -> QQAccessToken:
        if not app_id or not client_secret:
            raise QQTransportError("qq_token_configuration_missing")
        result = self._client.request(
            "POST",
            QQ_TOKEN_URL,
            payload={"appId": app_id, "clientSecret": client_secret},
        )
        if result.status != 200 or result.payload is None:
            raise QQTransportError("qq_token_request_denied")
        value = result.payload.get("access_token")
        expires_raw = result.payload.get("expires_in")
        try:
            expires = int(expires_raw)
        except (TypeError, ValueError) as error:
            raise QQTransportError("qq_token_response_invalid") from error
        if not isinstance(value, str) or not value or expires <= 60 or expires > 7200:
            raise QQTransportError("qq_token_response_invalid")
        return QQAccessToken(value, expires)


class RealQQGatewayTransport:
    def __init__(self, client: BoundedQQHTTPClient) -> None:
        self._client = client

    def fetch(self, *, access_token: str) -> QQGatewayEndpoint:
        if not access_token:
            raise QQTransportError("qq_gateway_token_missing")
        result = self._client.request(
            "GET",
            f"{QQ_OPENAPI_ORIGIN}/gateway",
            headers={"Authorization": f"QQBot {access_token}"},
        )
        endpoint = result.payload.get("url") if result.payload is not None else None
        if result.status != 200 or not isinstance(endpoint, str):
            raise QQTransportError("qq_gateway_response_invalid")
        parsed = urllib.parse.urlparse(endpoint)
        if (
            parsed.scheme != "wss"
            or not parsed.hostname
            or not parsed.hostname.lower().endswith(".qq.com")
        ):
            raise QQTransportError("qq_gateway_destination_denied")
        return QQGatewayEndpoint(endpoint)


class RealQQWebSocketConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def receive(self) -> Mapping[str, Any]:
        try:
            raw = await self._connection.recv()
        except Exception as error:
            raise QQTransportError("qq_websocket_disconnected") from error
        if isinstance(raw, str):
            encoded = raw.encode("utf-8")
        elif isinstance(raw, bytes):
            encoded = raw
        else:
            raise QQTransportError("qq_websocket_frame_invalid")
        if len(encoded) > MAX_WEBSOCKET_MESSAGE_BYTES:
            raise QQTransportError("qq_websocket_frame_too_large")
        try:
            decoded = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QQTransportError("qq_websocket_frame_invalid") from error
        if not isinstance(decoded, Mapping):
            raise QQTransportError("qq_websocket_frame_invalid")
        return decoded

    async def send(self, payload: Mapping[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > MAX_WEBSOCKET_MESSAGE_BYTES:
            raise QQTransportError("qq_websocket_frame_too_large")
        try:
            await self._connection.send(serialized)
        except Exception as error:
            raise QQTransportError("qq_websocket_disconnected") from error

    async def close(self) -> None:
        try:
            await self._connection.close()
        except Exception as error:
            raise QQTransportError("qq_websocket_close_failed") from error


class RealQQWebSocketTransport:
    async def connect(
        self, *, endpoint: str, open_timeout_seconds: float
    ) -> RealQQWebSocketConnection:
        parsed = urllib.parse.urlparse(endpoint)
        if (
            parsed.scheme != "wss"
            or not parsed.hostname
            or not parsed.hostname.lower().endswith(".qq.com")
        ):
            raise QQTransportError("qq_gateway_destination_denied")
        try:
            from websockets.asyncio.client import connect

            connection = await connect(
                endpoint,
                open_timeout=open_timeout_seconds,
                close_timeout=5,
                ping_interval=None,
                max_size=MAX_WEBSOCKET_MESSAGE_BYTES,
                max_queue=4,
            )
        except Exception as error:
            raise QQTransportError("qq_websocket_connect_failed") from error
        return RealQQWebSocketConnection(connection)


class RealQQPassiveAcknowledgementTransport:
    """The only real-write adapter: one configured group and one fixed text shape."""

    def __init__(
        self, client: BoundedQQHTTPClient, config: QQSandboxConfig, access_token: str
    ) -> None:
        if not access_token:
            raise QQTransportError("qq_passive_token_missing")
        self._client = client
        self._config = config
        self._access_token = access_token
        self._accepted: dict[tuple[str, str, int], str] = {}

    def _validate(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        content: str | None = None,
    ) -> None:
        if group_openid != self._config.group_openid:
            raise QQTransportError("qq_passive_destination_denied")
        if not _SOURCE_ID.fullmatch(source_message_id):
            raise QQTransportError("qq_passive_source_denied")
        if reply_msg_seq != 1:
            raise QQTransportError("qq_passive_sequence_denied")
        if content is not None:
            if not content.startswith(_ACK_PREFIX) or not content.endswith(_ACK_SUFFIX):
                raise QQTransportError("qq_passive_content_denied")
            case_id = content[len(_ACK_PREFIX) : len(content) - len(_ACK_SUFFIX)]
            if not _CASE_ID.fullmatch(case_id) or content != QQ_ACK_TEMPLATE.format(
                case_id=case_id
            ):
                raise QQTransportError("qq_passive_content_denied")

    def reconcile(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        idempotency_key: str,
    ) -> QQSendOutcome:
        del idempotency_key
        self._validate(
            group_openid=group_openid,
            source_message_id=source_message_id,
            reply_msg_seq=reply_msg_seq,
        )
        provider_id = self._accepted.get(
            (group_openid, source_message_id, reply_msg_seq)
        )
        if provider_id is not None:
            return QQSendOutcome("present", "qq_local_send_observation_present", provider_id)
        return QQSendOutcome("absent", "qq_local_send_observation_absent")

    def send_fixed_acknowledgement(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        idempotency_key: str,
        content: str,
    ) -> QQSendOutcome:
        del idempotency_key
        self._validate(
            group_openid=group_openid,
            source_message_id=source_message_id,
            reply_msg_seq=reply_msg_seq,
            content=content,
        )
        group_path = urllib.parse.quote(group_openid, safe="")
        result = self._client.request(
            "POST",
            f"{QQ_OPENAPI_ORIGIN}/v2/groups/{group_path}/messages",
            headers={"Authorization": f"QQBot {self._access_token}"},
            payload={
                "msg_type": 0,
                "content": content,
                "msg_id": source_message_id,
                "msg_seq": reply_msg_seq,
            },
        )
        provider_id = result.payload.get("id") if result.payload is not None else None
        if 200 <= result.status < 300 and isinstance(provider_id, str) and provider_id:
            if len(provider_id) > 512:
                return QQSendOutcome("unknown", "qq_provider_response_invalid")
            self._accepted[(group_openid, source_message_id, reply_msg_seq)] = provider_id
            return QQSendOutcome("accepted", "qq_provider_accepted", provider_id)
        code = result.payload.get("code") if result.payload is not None else None
        try:
            provider_code = int(code)
        except (TypeError, ValueError):
            provider_code = None
        if provider_code == 40054005:
            duplicate_id = f"dedup-{source_message_id}-{reply_msg_seq}"
            self._accepted[(group_openid, source_message_id, reply_msg_seq)] = duplicate_id
            return QQSendOutcome("duplicate", "qq_provider_message_deduplicated", duplicate_id)
        if provider_code in {304103, 40034005, 40034128}:
            return QQSendOutcome("expired", "qq_passive_reply_deadline_expired")
        if result.status in {401, 403} or provider_code in {
            40034024,
            40034101,
            40034105,
            40054002,
            40054003,
            40054016,
        }:
            return QQSendOutcome("unauthorized", "qq_provider_capability_denied")
        if result.status == 429 or result.status >= 500 or result.payload is None:
            return QQSendOutcome("unknown", "qq_provider_outcome_unknown")
        return QQSendOutcome("conflict", "qq_provider_request_conflict")
