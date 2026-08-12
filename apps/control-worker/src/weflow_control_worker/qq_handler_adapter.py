"""Real QQ Stage 2 transport, importable only by the dedicated live command."""

from __future__ import annotations

import re
import urllib.parse

from weflow_control_kernel.qq_handler import (
    QQ_GROUP_NUDGE_TEMPLATE,
    QQ_NOTIFICATION_TEMPLATE,
    QQHandlerTransportError,
    QQProviderOutcome,
    is_safe_provider_message_id,
)

from .qq_adapter import QQ_OPENAPI_ORIGIN, BoundedQQHTTPClient, _HTTPResult

_NOTIFICATION = re.compile(
    r"工单 (case_[a-f0-9]{24,64}) 待处理。请私聊发送 "
    r"WF-PULL \1 ([1-9][0-9]*)。"
)


class RealQQHandlerTransport:
    """Capability-shaped transport bound to one group and one C2C handler."""

    def __init__(
        self,
        client: BoundedQQHTTPClient,
        *,
        access_token: str,
        group_openid: str,
        user_openid: str,
    ) -> None:
        if not access_token or not group_openid or not user_openid:
            raise QQHandlerTransportError("qq_handler_transport_configuration_missing")
        self._client = client
        self._access_token = access_token
        self._group_openid = group_openid
        self._user_openid = user_openid
        self._accepted: dict[tuple[str, str, str, int], str] = {}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"QQBot {self._access_token}"}

    @staticmethod
    def _provider_outcome(result: _HTTPResult) -> QQProviderOutcome:
        provider_id = result.payload.get("id") if result.payload is not None else None
        if 200 <= result.status < 300 and isinstance(provider_id, str) and provider_id:
            if len(provider_id) > 512:
                return QQProviderOutcome("unknown", "qq_provider_response_invalid")
            return QQProviderOutcome(
                "accepted", "qq_provider_accepted", provider_id, "accepted"
            )
        code = result.payload.get("code") if result.payload is not None else None
        try:
            provider_code = int(code)
        except (TypeError, ValueError):
            provider_code = None
        if provider_code == 40054005:
            return QQProviderOutcome("duplicate", "qq_provider_message_deduplicated")
        if provider_code in {304103, 40034005, 40034128}:
            return QQProviderOutcome("expired_window", "qq_passive_reply_deadline_expired")
        if result.status == 429:
            return QQProviderOutcome("rate_limited", "qq_provider_rate_limited")
        if result.status in {401, 403} or provider_code in {
            40034024,
            40034101,
            40034105,
            40054002,
            40054003,
            40054016,
        }:
            return QQProviderOutcome("rejected", "qq_provider_capability_denied")
        if result.status >= 500 or result.payload is None:
            return QQProviderOutcome("unknown", "qq_provider_outcome_unknown")
        return QQProviderOutcome("rejected", "qq_provider_request_rejected")

    def _validate_user(self, user_openid: str) -> None:
        if user_openid != self._user_openid:
            raise QQHandlerTransportError("qq_handler_c2c_destination_denied")

    def _validate_group(self, group_openid: str) -> None:
        if group_openid != self._group_openid:
            raise QQHandlerTransportError("qq_handler_group_destination_denied")

    def notify_c2c(
        self, *, user_openid: str, content: str, idempotency_key: str
    ) -> QQProviderOutcome:
        del idempotency_key
        self._validate_user(user_openid)
        match = _NOTIFICATION.fullmatch(content)
        if match is None or content != QQ_NOTIFICATION_TEMPLATE.format(
            case_reference=match.group(1), version=int(match.group(2))
        ):
            raise QQHandlerTransportError("qq_handler_notification_content_denied")
        user_path = urllib.parse.quote(user_openid, safe="")
        return self._provider_outcome(
            self._client.request(
                "POST",
                f"{QQ_OPENAPI_ORIGIN}/v2/users/{user_path}/messages",
                headers=self._headers(),
                payload={"msg_type": 0, "content": content},
            )
        )

    def reconcile_passive(
        self,
        *,
        surface: str,
        destination: str,
        source_message_id: str,
        msg_seq: int,
        idempotency_key: str,
    ) -> QQProviderOutcome:
        del idempotency_key
        if surface == "c2c":
            self._validate_user(destination)
        elif surface == "group":
            self._validate_group(destination)
        else:
            raise QQHandlerTransportError("qq_handler_passive_surface_denied")
        provider_id = self._accepted.get((surface, destination, source_message_id, msg_seq))
        if provider_id is None:
            return QQProviderOutcome("absent", "qq_local_send_observation_absent")
        return QQProviderOutcome(
            "present", "qq_local_send_observation_present", provider_id, "present"
        )

    def _passive(
        self,
        *,
        surface: str,
        destination: str,
        source_message_id: str,
        msg_seq: int,
        content: str,
    ) -> QQProviderOutcome:
        if not is_safe_provider_message_id(source_message_id):
            raise QQHandlerTransportError("qq_handler_passive_source_denied")
        if not content or len(content) > 2_000:
            raise QQHandlerTransportError("qq_handler_passive_content_denied")
        if surface == "c2c":
            self._validate_user(destination)
            if msg_seq not in {1, 2, 3, 4}:
                raise QQHandlerTransportError("qq_handler_c2c_sequence_denied")
            path = f"/v2/users/{urllib.parse.quote(destination, safe='')}/messages"
        elif surface == "group":
            self._validate_group(destination)
            if msg_seq not in {2, 5}:
                raise QQHandlerTransportError("qq_handler_group_sequence_denied")
            path = f"/v2/groups/{urllib.parse.quote(destination, safe='')}/messages"
        else:
            raise QQHandlerTransportError("qq_handler_passive_surface_denied")
        outcome = self._provider_outcome(
            self._client.request(
                "POST",
                f"{QQ_OPENAPI_ORIGIN}{path}",
                headers=self._headers(),
                payload={
                    "msg_type": 0,
                    "content": content,
                    "msg_id": source_message_id,
                    "msg_seq": msg_seq,
                },
            )
        )
        if outcome.status in {"accepted", "duplicate"}:
            provider_id = outcome.provider_message_id or f"dedup-{source_message_id}-{msg_seq}"
            self._accepted[(surface, destination, source_message_id, msg_seq)] = provider_id
        return outcome

    def passive_c2c_reply(
        self,
        *,
        user_openid: str,
        source_message_id: str,
        msg_seq: int,
        content: str,
        idempotency_key: str,
    ) -> QQProviderOutcome:
        del idempotency_key
        return self._passive(
            surface="c2c",
            destination=user_openid,
            source_message_id=source_message_id,
            msg_seq=msg_seq,
            content=content,
        )

    def passive_group_reply(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        msg_seq: int,
        content: str,
        idempotency_key: str,
    ) -> QQProviderOutcome:
        del idempotency_key
        if msg_seq != 5:
            raise QQHandlerTransportError("qq_handler_final_sequence_denied")
        return self._passive(
            surface="group",
            destination=group_openid,
            source_message_id=source_message_id,
            msg_seq=msg_seq,
            content=content,
        )

    def group_nudge(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        msg_seq: int,
        content: str,
        idempotency_key: str,
    ) -> QQProviderOutcome:
        del idempotency_key
        if content != QQ_GROUP_NUDGE_TEMPLATE or msg_seq != 2:
            raise QQHandlerTransportError("qq_handler_group_nudge_denied")
        return self._passive(
            surface="group",
            destination=group_openid,
            source_message_id=source_message_id,
            msg_seq=msg_seq,
            content=content,
        )


__all__ = ["RealQQHandlerTransport"]
