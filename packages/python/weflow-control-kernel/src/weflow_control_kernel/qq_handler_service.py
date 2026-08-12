"""Closed QQ C2C/group command controller for the Stage 2 handler workflow."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from weflow_contracts import (
    QQ_HANDLER_COMMAND_SCHEMA_ID,
    validate_qq_handler_command,
)

from .qq_handler import (
    QQGroupApprovalCommand,
    QQHandlerAuthorizationDenied,
    QQHandlerConfig,
    QQHandlerEventRejected,
    QQHandlerTransport,
    SQLiteQQHandlerJournal,
    _hash,
    _id,
    _parse,
    _ts,
    is_safe_provider_message_id,
    parse_group_approval,
    parse_private_command,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class QQPrivateWorkflowResponse:
    duplicate: bool
    command: JsonObject
    passive_intent: JsonObject
    content: str


@dataclass(frozen=True)
class QQGroupApprovalResponse:
    decision: JsonObject
    final_intent: JsonObject
    content: str


class QQHandlerWorkflowService:
    def __init__(
        self,
        *,
        config: QQHandlerConfig,
        binding: Mapping[str, Any],
        journal: SQLiteQQHandlerJournal,
    ) -> None:
        self.config = config
        self.binding = dict(binding)
        self.journal = journal
        active = journal.active_binding(str(binding["handler_binding_id"]))
        if active != self.binding:
            raise QQHandlerAuthorizationDenied("handler_binding_record_mismatch")
        if (
            active["app_id_hash"] != config.app_id_hash
            or active["tenant_id_hash"] != config.tenant_id_hash
            or active["group_openid_hash"] != config.group_openid_hash
            or active["capability_profile_hash"] != config.capability_profile_hash
        ):
            raise QQHandlerAuthorizationDenied("handler_binding_configuration_mismatch")

    def _private_event(self, raw_event: Mapping[str, Any]) -> JsonObject:
        if raw_event.get("t") != "C2C_MESSAGE_CREATE":
            raise QQHandlerEventRejected("private_event_type_unsupported")
        sequence = raw_event.get("s")
        data = raw_event.get("d")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise QQHandlerEventRejected("private_event_sequence_invalid")
        if not isinstance(data, Mapping):
            raise QQHandlerEventRejected("private_event_shape_invalid")
        if any(
            data.get(field) not in (None, [], {})
            for field in ("attachments", "ark_data", "msg_elements")
        ):
            raise QQHandlerEventRejected("private_event_plain_text_required")
        author = data.get("author")
        message_id = data.get("id")
        content = data.get("content")
        if not isinstance(author, Mapping) or not isinstance(author.get("user_openid"), str):
            raise QQHandlerAuthorizationDenied("private_event_author_unavailable")
        expected_user = self.journal.private_locator(self.binding["handler_binding_id"], "c2c-user")
        if author["user_openid"] != expected_user:
            raise QQHandlerAuthorizationDenied("private_event_foreign_user")
        if not is_safe_provider_message_id(message_id):
            raise QQHandlerEventRejected("private_event_message_id_invalid")
        if not isinstance(content, str):
            raise QQHandlerEventRejected("private_event_plain_text_required")
        occurred = _parse(data.get("timestamp"), "private_event_timestamp_invalid")
        if occurred > self.journal._clock().astimezone(UTC):
            raise QQHandlerEventRejected("private_event_timestamp_invalid")
        return {
            "message_id": message_id,
            "message_id_hash": _hash(message_id),
            "content": content,
            "occurred_at": occurred,
            "gateway_sequence": sequence,
            "author_identity_hash": self.binding["c2c_user_identity_hash"],
        }

    def _stored_command(self, source_message_id_hash: str) -> JsonObject | None:
        with self.journal._connect() as c:
            row = c.execute(
                "SELECT result_json FROM qq_handler_commands WHERE source_message_id_hash=?",
                (source_message_id_hash,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _content_for_metadata(self, metadata: Mapping[str, Any]) -> str:
        kind = metadata["response_kind"]
        case_id = metadata["case_id"]
        version = metadata["workflow_version"]
        if kind == "pull":
            issue = self.journal.artifact_content(metadata["content_artifact_id"])
            return (
                f"工单 {case_id}\n当前状态：{metadata['case_status']}\n客户问题（仅私聊）：{issue}"
            )
        if kind == "accept":
            return (
                f"工单 {case_id} 已接受，当前版本 {version}。\n"
                f"请用 WF-DRAFT {case_id} {version} 换行提交草稿。"
            )
        if kind == "draft-preview":
            candidate = self.journal.artifact_content(metadata["content_artifact_id"])
            return (
                f"草稿预览（仅私聊）：{candidate}\n"
                "群审批元数据（不得附带草稿正文）："
                f"WF-APPROVE {metadata['approval_request_id']} "
                f"{metadata['candidate_hash_prefix']} {version}"
            )
        if kind == "reject":
            return f"工单 {case_id} 已拒绝；受限内容已进入删除流程。"
        raise QQHandlerEventRejected("private_response_kind_invalid")

    def handle_private_event(self, raw_event: Mapping[str, Any]) -> QQPrivateWorkflowResponse:
        event = self._private_event(raw_event)
        self.journal.observe_event_order(
            surface="c2c",
            handler_binding_id=str(self.binding["handler_binding_id"]),
            sequence=int(event["gateway_sequence"]),
            source_message_id_hash=str(event["message_id_hash"]),
        )
        stored = self._stored_command(event["message_id_hash"])
        if stored:
            content = self._content_for_metadata(stored)
            return QQPrivateWorkflowResponse(
                duplicate=True,
                command=stored["command"],
                passive_intent=stored["passive_intent"],
                content=content,
            )
        private = parse_private_command(event["content"])
        case = self.journal.case_projection(private.case_id)
        if (
            case["tenant_id"] != self.binding["tenant_id"]
            or case["handler_binding_id"] != self.binding["handler_binding_id"]
            or case["case_revision_id"] == ""
        ):
            raise QQHandlerAuthorizationDenied("private_command_case_binding_mismatch")
        # Every private command is gated by the retained issue artifact before mutation.
        self.journal.artifact_content(case["issue_artifact_id"])

        artifact: JsonObject | None = None
        request: JsonObject | None = None
        if private.command == "draft":
            assert private.body is not None
            artifact, _, request = self.journal.create_candidate_and_request(
                binding=self.binding,
                case_id=private.case_id,
                expected_version=private.expected_version,
                candidate_text=private.body,
                source_message_id_hash=event["message_id_hash"],
            )
            projection = self.journal.case_projection(private.case_id)
            response_kind = "draft-preview"
            content_artifact_id = artifact["artifact_id"]
            artifact["content_sha256"]
        else:
            projection = self.journal.transition_simple_command(
                binding=self.binding,
                case_id=private.case_id,
                expected_version=private.expected_version,
                command=private.command,
                source_message_id_hash=event["message_id_hash"],
                rejection_reason_code=(
                    private.body if private.command == "reject" else None
                ),
            )
            response_kind = private.command
            if private.command == "pull":
                content_artifact_id = projection["issue_artifact_id"]
                _hash(self.journal.artifact_content(projection["issue_artifact_id"]))
            else:
                content_artifact_id = None

        command_record = {
            "schema_id": QQ_HANDLER_COMMAND_SCHEMA_ID,
            "schema_version": "v1",
            "command_id": _id(
                "qqhcmd",
                {
                    "source": event["message_id_hash"],
                    "command": private.command,
                    "case": private.case_id,
                },
            ),
            "surface": "c2c",
            "command": private.command,
            "tenant_id": projection["tenant_id"],
            "case_id": private.case_id,
            "case_revision_id": projection["case_revision_id"],
            "handler_binding_id": self.binding["handler_binding_id"],
            "author_identity_hash": event["author_identity_hash"],
            "source_message_id": event["message_id"],
            "source_message_id_hash": event["message_id_hash"],
            "expected_version": private.expected_version,
            "candidate_artifact_id": artifact["artifact_id"] if artifact else None,
            "approval_request_id": None,
            "candidate_hash_prefix": None,
            "rejection_reason_code": (
                private.body if private.command == "reject" else None
            ),
            "received_at": _ts(event["occurred_at"]),
        }
        validate_qq_handler_command(command_record, self.config.repository_root)
        metadata: JsonObject = {
            "case_id": private.case_id,
            "case_status": projection["status"],
            "workflow_version": projection["workflow_version"],
            "response_kind": response_kind,
            "content_artifact_id": content_artifact_id,
            "command": command_record,
        }
        if request:
            metadata.update(
                {
                    "approval_request_id": request["approval_request_id"],
                    "candidate_hash_prefix": request["candidate_hash_prefix"],
                }
            )
        content = self._content_for_metadata(metadata)
        passive_intent = self.journal.create_passive_intent(
            case_id=private.case_id,
            binding=self.binding,
            source_message_id=event["message_id"],
            response_kind=response_kind,
            occurred_at=event["occurred_at"],
            content_artifact_id=content_artifact_id,
            content_sha256=_hash(content),
        )
        metadata["passive_intent"] = passive_intent
        created, persisted = self.journal.record_command_once(
            source_message_id_hash=event["message_id_hash"],
            command_id=command_record["command_id"],
            case_id=private.case_id,
            classification=f"private_{private.command}",
            result=metadata,
        )
        return QQPrivateWorkflowResponse(
            duplicate=not created,
            command=persisted["command"],
            passive_intent=persisted["passive_intent"],
            content=self._content_for_metadata(persisted),
        )

    def execute_private_response(
        self,
        response: QQPrivateWorkflowResponse,
        *,
        transport: QQHandlerTransport,
    ) -> JsonObject:
        return self.journal.execute_passive_reply(
            response.passive_intent,
            binding=self.binding,
            content=response.content,
            transport=transport,
        )

    def _group_event(
        self, raw_event: Mapping[str, Any]
    ) -> tuple[QQGroupApprovalCommand, JsonObject]:
        if raw_event.get("t") != "GROUP_AT_MESSAGE_CREATE":
            raise QQHandlerEventRejected("group_approval_event_type_unsupported")
        sequence = raw_event.get("s")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise QQHandlerEventRejected("group_approval_sequence_invalid")
        data = raw_event.get("d")
        if not isinstance(data, Mapping):
            raise QQHandlerEventRejected("group_approval_event_shape_invalid")
        author = data.get("author")
        if not isinstance(author, Mapping) or not isinstance(author.get("member_openid"), str):
            raise QQHandlerAuthorizationDenied("group_approval_author_unavailable")
        group_openid = data.get("group_openid")
        message_id = data.get("id")
        content = data.get("content")
        if group_openid != self.config.group_openid:
            raise QQHandlerAuthorizationDenied("group_approval_foreign_group")
        if not is_safe_provider_message_id(message_id):
            raise QQHandlerEventRejected("group_approval_message_id_invalid")
        if not isinstance(content, str):
            raise QQHandlerEventRejected("group_approval_plain_text_required")
        occurred = _parse(data.get("timestamp"), "group_approval_timestamp_invalid")
        try:
            command = parse_group_approval(content)
        except QQHandlerEventRejected as error:
            if error.reason_code != "group_approval_mention_required":
                raise
            # QQ proves the real mention through GROUP_AT_MESSAGE_CREATE but may
            # omit its display token from the provider-normalized content.
            command = parse_group_approval(f"<@!provider-event> {content}")
        return command, {
            "member_openid": author["member_openid"],
            "group_openid": group_openid,
            "message_id": message_id,
            "gateway_sequence": sequence,
            "occurred_at": occurred,
        }

    def handle_group_approval(self, raw_event: Mapping[str, Any]) -> QQGroupApprovalResponse:
        command, event = self._group_event(raw_event)
        self.journal.observe_event_order(
            surface="group",
            handler_binding_id=str(self.binding["handler_binding_id"]),
            sequence=int(event["gateway_sequence"]),
            source_message_id_hash=_hash(str(event["message_id"])),
        )
        decision = self.journal.approve_request(
            binding=self.binding,
            command=command,
            member_openid=event["member_openid"],
            group_openid=event["group_openid"],
            source_message_id=event["message_id"],
            occurred_at=event["occurred_at"],
            identity_salt=self.config.identity_salt,
        )
        final_intent, content = self.journal.final_delivery_intent(decision, binding=self.binding)
        return QQGroupApprovalResponse(decision, final_intent, content)

    def execute_final_response(
        self,
        response: QQGroupApprovalResponse,
        *,
        transport: QQHandlerTransport,
    ) -> JsonObject:
        return self.journal.execute_passive_reply(
            response.final_intent,
            binding=self.binding,
            content=response.content,
            transport=transport,
        )


__all__ = [
    "QQGroupApprovalResponse",
    "QQHandlerWorkflowService",
    "QQPrivateWorkflowResponse",
]
