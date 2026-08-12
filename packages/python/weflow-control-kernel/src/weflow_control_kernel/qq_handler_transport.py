"""Narrow Stage 2 QQ transport fake with provider-visible idempotency state."""

from __future__ import annotations

from dataclasses import dataclass, field

from .qq_handler import (
    QQ_GROUP_NUDGE_TEMPLATE,
    QQHandlerTransportError,
    QQProviderOutcome,
)


@dataclass
class FakeQQHandlerTransport:
    configured_group_openid: str
    configured_user_openid: str
    notification_status: str = "accepted"
    passive_status: str = "accepted"
    reconcile_status: str = "absent"
    lose_notification_response: bool = False
    lose_passive_response: bool = False
    notification_calls: int = 0
    passive_c2c_calls: int = 0
    passive_group_calls: int = 0
    group_nudge_calls: int = 0
    reconcile_calls: int = 0
    notification_contents: list[str] = field(default_factory=list)
    passive_c2c_contents: list[str] = field(default_factory=list)
    passive_group_contents: list[str] = field(default_factory=list)
    effects: dict[tuple[str, str, str, int], str] = field(default_factory=dict)

    def _validate_user(self, user_openid: str) -> None:
        if user_openid != self.configured_user_openid:
            raise QQHandlerTransportError("qq_handler_c2c_destination_denied")

    def _validate_group(self, group_openid: str) -> None:
        if group_openid != self.configured_group_openid:
            raise QQHandlerTransportError("qq_handler_group_destination_denied")

    def notify_c2c(
        self, *, user_openid: str, content: str, idempotency_key: str
    ) -> QQProviderOutcome:
        del idempotency_key
        self._validate_user(user_openid)
        if "WF-PULL" not in content or "客户问题" in content or "草稿" in content:
            raise QQHandlerTransportError("qq_handler_notification_content_denied")
        self.notification_calls += 1
        self.notification_contents.append(content)
        if self.lose_notification_response:
            self.lose_notification_response = False
            raise QQHandlerTransportError("qq_handler_notification_outcome_unknown")
        return QQProviderOutcome(
            self.notification_status,
            f"qq_fake_notification_{self.notification_status}",
            "fake-notification-message" if self.notification_status == "accepted" else None,
            self.notification_status,
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
        if surface == "group":
            self._validate_group(destination)
        elif surface == "c2c":
            self._validate_user(destination)
        else:
            raise QQHandlerTransportError("qq_handler_passive_surface_denied")
        self.reconcile_calls += 1
        key = (surface, destination, source_message_id, msg_seq)
        if key in self.effects:
            return QQProviderOutcome(
                "present",
                "qq_fake_passive_present",
                self.effects[key],
                "present",
            )
        return QQProviderOutcome(
            self.reconcile_status,
            f"qq_fake_passive_{self.reconcile_status}",
            provider_status=self.reconcile_status,
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
        if not source_message_id or msg_seq not in {1, 2, 3, 4, 5}:
            raise QQHandlerTransportError("qq_handler_passive_source_denied")
        if not content or len(content) > 2_000:
            raise QQHandlerTransportError("qq_handler_passive_content_denied")
        key = (surface, destination, source_message_id, msg_seq)
        if key in self.effects:
            return QQProviderOutcome(
                "duplicate",
                "qq_fake_passive_duplicate",
                self.effects[key],
                "duplicate",
            )
        provider_message_id = f"fake-{surface}-{len(self.effects) + 1}"
        self.effects[key] = provider_message_id
        if self.lose_passive_response:
            self.lose_passive_response = False
            raise QQHandlerTransportError("qq_handler_passive_outcome_unknown")
        return QQProviderOutcome(
            self.passive_status,
            f"qq_fake_passive_{self.passive_status}",
            provider_message_id if self.passive_status == "accepted" else None,
            self.passive_status,
        )

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
        self._validate_user(user_openid)
        self.passive_c2c_calls += 1
        self.passive_c2c_contents.append(content)
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
        self._validate_group(group_openid)
        if msg_seq != 5:
            raise QQHandlerTransportError("qq_handler_final_sequence_denied")
        self.passive_group_calls += 1
        self.passive_group_contents.append(content)
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
        self._validate_group(group_openid)
        if content != QQ_GROUP_NUDGE_TEMPLATE or msg_seq != 2:
            raise QQHandlerTransportError("qq_handler_group_nudge_denied")
        self.group_nudge_calls += 1
        return self._passive(
            surface="group",
            destination=group_openid,
            source_message_id=source_message_id,
            msg_seq=msg_seq,
            content=content,
        )


__all__ = ["FakeQQHandlerTransport"]
