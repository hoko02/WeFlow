"""Bounded live runner for one QQ handler approval-and-delivery sandbox flow."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weflow_control_kernel.ledger import IntakeRejected, SQLiteCaseLedger
from weflow_control_kernel.qq_handler import (
    QQ_GROUP_NUDGE_TEMPLATE,
    QQ_HANDLER_CHALLENGE_TTL_SECONDS,
    QQHandlerAuthorizationDenied,
    QQHandlerConfig,
    QQHandlerEventRejected,
    QQHandlerStateConflict,
    QQHandlerTransportError,
    SQLiteQQHandlerJournal,
    begin_handler_pairing,
    normalize_handler_pairing_event,
)
from weflow_control_kernel.qq_handler_service import QQHandlerWorkflowService
from weflow_control_kernel.qq_sandbox import (
    QQEventRejected,
    QQSandboxConfig,
    normalize_qq_group_at_event,
)

from .qq_adapter import (
    QQ_GROUP_INTENT,
    BoundedQQHTTPClient,
    RealQQGatewayTransport,
    RealQQTokenTransport,
    RealQQWebSocketTransport,
)
from .qq_handler_adapter import RealQQHandlerTransport

JsonObject = dict[str, Any]
PAIRING_CONFIRMATION = "CONFIRM-DUAL-QQ-HANDLER"
RECEIVE_TIMEOUT_SECONDS = 60.0
_MESSAGE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_MENTION = re.compile(r"^\s*(?:@机器人|<@!?[A-Za-z0-9._:-]+>)\s*")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise QQHandlerEventRejected("handler_live_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QQHandlerEventRejected("handler_live_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise QQHandlerEventRejected("handler_live_timestamp_invalid")
    return parsed.astimezone(UTC)


def normalize_live_customer_intake(
    raw_event: Mapping[str, Any], *, config: QQHandlerConfig
) -> JsonObject:
    """Minimize one allowlisted group event before it reaches the restricted store."""

    if raw_event.get("t") != "GROUP_AT_MESSAGE_CREATE":
        raise QQHandlerEventRejected("handler_intake_event_type_unsupported")
    data = raw_event.get("d")
    if not isinstance(data, Mapping) or data.get("group_openid") != config.group_openid:
        raise QQHandlerEventRejected("handler_intake_foreign_group")
    if any(
        data.get(field) not in (None, [], {})
        for field in ("attachments", "ark_data", "msg_elements")
    ):
        raise QQHandlerEventRejected("handler_intake_plain_text_required")
    message_id = data.get("id")
    content = data.get("content")
    author = data.get("author")
    if not isinstance(message_id, str) or not _MESSAGE_ID.fullmatch(message_id):
        raise QQHandlerEventRejected("handler_intake_message_id_invalid")
    if not isinstance(content, str) or not isinstance(author, Mapping):
        raise QQHandlerEventRejected("handler_intake_plain_text_required")
    if not isinstance(author.get("member_openid"), str):
        raise QQHandlerEventRejected("handler_intake_author_unavailable")
    minimized_content = _MENTION.sub("", content, count=1).strip()
    if not minimized_content or minimized_content.startswith("WF-APPROVE "):
        raise QQHandlerEventRejected("handler_intake_command_not_issue")
    occurred_at = _timestamp(data.get("timestamp"))
    if occurred_at > datetime.now(UTC):
        raise QQHandlerEventRejected("handler_intake_timestamp_invalid")
    case_material = f"{config.tenant_id}\0{message_id}"
    return {
        "case_id": f"case_{_hash(case_material)[:32]}",
        "case_revision_id": f"qqrev_{_hash(case_material + ':revision')[:32]}",
        "source_message_id": message_id,
        "source_message_id_hash": _hash(message_id),
        "occurred_at": occurred_at,
        "content": minimized_content,
    }


def accept_live_stage1_intake(
    raw_event: Mapping[str, Any],
    *,
    config: QQHandlerConfig,
    ledger: SQLiteCaseLedger,
) -> JsonObject:
    """Accept the same event into the Stage 1 Case ledger without enabling its QQ write."""

    minimized = normalize_live_customer_intake(raw_event, config=config)
    stage1_config = QQSandboxConfig(
        app_id=config.app_id,
        client_secret=config.client_secret,
        group_openid=config.group_openid,
        tenant_id=config.tenant_id,
        identity_salt=config.identity_salt,
    )
    inbound = normalize_qq_group_at_event(
        raw_event,
        stage1_config,
        received_at=datetime.now(UTC),
        contract_root=config.repository_root,
    )
    accepted = ledger.intake_qq(inbound, effective_tenant_id=config.tenant_id)
    if inbound["source_message_id_hash"] != minimized["source_message_id_hash"]:
        raise QQHandlerStateConflict("handler_stage1_source_mismatch")
    minimized.update(
        {
            "case_id": accepted.case_id,
            "case_revision_id": accepted.case_revision_id,
            "stage1_intake_disposition": accepted.disposition,
        }
    )
    return minimized


class _LiveGateway:
    def __init__(self, config: QQHandlerConfig) -> None:
        self.config = config
        self.client = BoundedQQHTTPClient()
        self.connection: Any | None = None
        self.access_token: str | None = None
        self._latest_sequence: int | None = None
        self._heartbeat_seconds = 30.0
        self.session_id: str | None = None
        self.ready_sequence: int | None = None

    async def open(self) -> None:
        token = RealQQTokenTransport(self.client).fetch(
            app_id=self.config.app_id, client_secret=self.config.client_secret
        )
        endpoint = RealQQGatewayTransport(self.client).fetch(access_token=token.value)
        self.connection = await RealQQWebSocketTransport().connect(
            endpoint=endpoint.url, open_timeout_seconds=10.0
        )
        hello = dict(await asyncio.wait_for(self.connection.receive(), 10.0))
        data = hello.get("d")
        interval = data.get("heartbeat_interval") if isinstance(data, Mapping) else None
        if hello.get("op") != 10 or not isinstance(interval, int):
            raise QQHandlerTransportError("qq_handler_gateway_hello_invalid")
        if interval < 1_000 or interval > 120_000:
            raise QQHandlerTransportError("qq_handler_gateway_heartbeat_invalid")
        self._heartbeat_seconds = interval / 1000
        self.access_token = token.value
        await self.connection.send(
            {
                "op": 2,
                "d": {
                    "token": f"QQBot {token.value}",
                    "intents": QQ_GROUP_INTENT,
                    "shard": [0, 1],
                    "properties": {
                        "$os": "weflow",
                        "$browser": "weflow-stage2",
                        "$device": "weflow-stage2",
                    },
                },
            }
        )

    async def wait_until_ready(self) -> None:
        if self.connection is None:
            raise QQHandlerTransportError("qq_handler_gateway_not_open")
        while self.session_id is None:
            try:
                frame = dict(
                    await asyncio.wait_for(
                        self.connection.receive(),
                        min(RECEIVE_TIMEOUT_SECONDS, self._heartbeat_seconds),
                    )
                )
            except TimeoutError:
                await self.connection.send({"op": 1, "d": self._latest_sequence})
                continue
            opcode = frame.get("op")
            sequence = frame.get("s")
            if isinstance(sequence, int) and not isinstance(sequence, bool):
                if self._latest_sequence is not None and sequence <= self._latest_sequence:
                    raise QQHandlerTransportError("qq_handler_gateway_sequence_out_of_order")
                self._latest_sequence = sequence
            if opcode == 7:
                raise QQHandlerTransportError("qq_handler_gateway_reconnect_required")
            if opcode == 9:
                raise QQHandlerTransportError("qq_handler_gateway_session_invalid")
            if opcode != 0:
                continue
            if frame.get("t") != "READY":
                raise QQHandlerTransportError("qq_handler_gateway_ready_invalid")
            data = frame.get("d")
            session_id = data.get("session_id") if isinstance(data, Mapping) else None
            if not isinstance(session_id, str) or not session_id or self._latest_sequence is None:
                raise QQHandlerTransportError("qq_handler_gateway_ready_invalid")
            self.session_id = session_id
            self.ready_sequence = self._latest_sequence

    async def next_event(self) -> JsonObject:
        if self.connection is None:
            raise QQHandlerTransportError("qq_handler_gateway_not_open")
        while True:
            try:
                frame = dict(
                    await asyncio.wait_for(
                        self.connection.receive(),
                        min(RECEIVE_TIMEOUT_SECONDS, self._heartbeat_seconds),
                    )
                )
            except TimeoutError:
                await self.connection.send({"op": 1, "d": self._latest_sequence})
                continue
            opcode = frame.get("op")
            sequence = frame.get("s")
            if isinstance(sequence, int) and not isinstance(sequence, bool):
                if self._latest_sequence is not None and sequence <= self._latest_sequence:
                    raise QQHandlerTransportError("qq_handler_gateway_sequence_out_of_order")
                self._latest_sequence = sequence
            if opcode == 7:
                raise QQHandlerTransportError("qq_handler_gateway_reconnect_required")
            if opcode == 9:
                raise QQHandlerTransportError("qq_handler_gateway_session_invalid")
            if opcode != 0:
                continue
            if frame.get("t") == "READY":
                data = frame.get("d")
                session_id = data.get("session_id") if isinstance(data, Mapping) else None
                if not isinstance(session_id, str) or not session_id:
                    raise QQHandlerTransportError("qq_handler_gateway_ready_invalid")
                self.session_id = session_id
                self.ready_sequence = self._latest_sequence
                continue
            if frame.get("t") == "RESUMED":
                continue
            if frame.get("t") not in {"GROUP_AT_MESSAGE_CREATE", "C2C_MESSAGE_CREATE"}:
                continue
            return frame

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None


def build_c2c_probe_observation(
    raw_event: Mapping[str, Any],
    *,
    config: QQHandlerConfig,
    challenge: Any,
) -> JsonObject:
    """Return only presence and matcher facts; never return identity or message text."""

    data = raw_event.get("d")
    author = data.get("author") if isinstance(data, Mapping) else None
    content = data.get("content") if isinstance(data, Mapping) else None
    normalized = " ".join(content.strip().split()) if isinstance(content, str) else None
    report: JsonObject = {
        "report_type": "weflow-qq-handler-c2c-probe.v1",
        "gateway_ready": True,
        "c2c_event_received": raw_event.get("t") == "C2C_MESSAGE_CREATE",
        "has_gateway_sequence": isinstance(raw_event.get("s"), int),
        "has_message_id": isinstance(data, Mapping) and isinstance(data.get("id"), str),
        "has_timestamp": isinstance(data, Mapping) and isinstance(data.get("timestamp"), str),
        "has_user_openid": isinstance(author, Mapping)
        and isinstance(author.get("user_openid"), str)
        and bool(author.get("user_openid")),
        "content_exact_probe": normalized == challenge.plaintext,
        "pairing_matcher": "rejected",
        "raw_identity_present": False,
        "raw_content_present": False,
        "provider_event_persisted": False,
        "network_contacted": True,
        "external_write_attempted": False,
        "case_mutation": False,
        "model_invocation": False,
        "production_ready": False,
    }
    try:
        normalize_handler_pairing_event(
            raw_event,
            config=config,
            challenge=challenge,
            now=datetime.now(UTC),
        )
    except QQHandlerEventRejected as error:
        report["reason_code"] = error.reason_code
    else:
        report["pairing_matcher"] = "accepted"
        report["reason_code"] = "c2c_probe_exact_event_accepted"
    return report


async def probe_live_c2c(
    *,
    config: QQHandlerConfig,
    display: Callable[[JsonObject], None],
) -> JsonObject:
    """Observe one bounded C2C event without creating a binding, Case, or write."""

    session = begin_handler_pairing(config, contract_root=config.repository_root)
    display(
        {
            "report_type": "weflow-qq-handler-c2c-probe-challenge.v1",
            "deadline_seconds": QQ_HANDLER_CHALLENGE_TTL_SECONDS,
            "instruction": f"由开发体验用户私聊机器人发送：{session.c2c.plaintext}",
            "persisted": False,
        }
    )
    gateway = _LiveGateway(config)
    await gateway.open()
    display(
        {
            "report_type": "weflow-qq-handler-c2c-probe-ready.v1",
            "gateway_ready": True,
            "network_contacted": True,
            "external_write_attempted": False,
        }
    )
    try:
        async with asyncio.timeout(QQ_HANDLER_CHALLENGE_TTL_SECONDS):
            while True:
                event = await gateway.next_event()
                if event.get("t") != "C2C_MESSAGE_CREATE":
                    continue
                return build_c2c_probe_observation(
                    event,
                    config=config,
                    challenge=session.c2c,
                )
    except TimeoutError:
        return {
            "report_type": "weflow-qq-handler-c2c-probe.v1",
            "gateway_ready": True,
            "c2c_event_received": False,
            "pairing_matcher": "not_observed",
            "reason_code": "c2c_probe_deadline_expired",
            "raw_identity_present": False,
            "raw_content_present": False,
            "provider_event_persisted": False,
            "network_contacted": True,
            "external_write_attempted": False,
            "case_mutation": False,
            "model_invocation": False,
            "production_ready": False,
        }
    except (OSError, RuntimeError) as error:
        return {
            "report_type": "weflow-qq-handler-c2c-probe.v1",
            "gateway_ready": True,
            "c2c_event_received": False,
            "pairing_matcher": "not_observed",
            "reason_code": getattr(error, "reason_code", "c2c_probe_transport_failed"),
            "raw_identity_present": False,
            "raw_content_present": False,
            "provider_event_persisted": False,
            "network_contacted": True,
            "external_write_attempted": False,
            "case_mutation": False,
            "model_invocation": False,
            "production_ready": False,
        }
    finally:
        await gateway.close()


def build_group_approval_probe_observation(
    raw_event: Mapping[str, Any],
    *,
    config: QQHandlerConfig,
    binding: Mapping[str, Any],
    journal: SQLiteQQHandlerJournal,
) -> JsonObject:
    """Return only safe group-approval matcher facts without mutation or writes."""

    data = raw_event.get("d")
    author = data.get("author") if isinstance(data, Mapping) else None
    report: JsonObject = {
        "report_type": "weflow-qq-handler-group-approval-probe.v1",
        "gateway_ready": True,
        "group_event_received": raw_event.get("t") == "GROUP_AT_MESSAGE_CREATE",
        "has_gateway_sequence": isinstance(raw_event.get("s"), int),
        "has_message_id": isinstance(data, Mapping) and isinstance(data.get("id"), str),
        "has_timestamp": isinstance(data, Mapping) and isinstance(data.get("timestamp"), str),
        "has_group_openid": isinstance(data, Mapping) and isinstance(data.get("group_openid"), str),
        "has_member_openid": isinstance(author, Mapping)
        and isinstance(author.get("member_openid"), str)
        and bool(author.get("member_openid")),
        "paired_group_match": False,
        "bound_member_match": False,
        "current_request_match": False,
        "request_unexpired": False,
        "approval_matcher": "rejected",
        "raw_identity_present": False,
        "raw_content_present": False,
        "provider_event_persisted": False,
        "network_contacted": True,
        "external_write_attempted": False,
        "case_mutation": False,
        "model_invocation": False,
        "production_ready": False,
    }
    service = QQHandlerWorkflowService(config=config, binding=binding, journal=journal)
    try:
        command, event = service._group_event(raw_event)
    except (QQHandlerAuthorizationDenied, QQHandlerEventRejected) as error:
        report["reason_code"] = error.reason_code
        return report
    report["paired_group_match"] = True
    report["bound_member_match"] = event["member_openid"] == journal.private_locator(
        str(binding["handler_binding_id"]), "group-member"
    )
    with journal._connect() as connection:
        request_row = connection.execute(
            "SELECT record_json FROM qq_handler_approval_requests WHERE approval_request_id=?",
            (command.approval_request_id,),
        ).fetchone()
    if request_row:
        request = json.loads(request_row[0])
        case = journal.case_projection(str(request["case_id"]))
        report["request_unexpired"] = _timestamp(
            request["expires_at"]
        ) > journal._clock().astimezone(UTC)
        report["current_request_match"] = bool(
            case["current_approval_request_id"] == request["approval_request_id"]
            and case["current_candidate_revision_id"] == request["candidate_revision_id"]
            and request["workflow_version"] == command.expected_version
            and request["candidate_hash_prefix"] == command.candidate_hash_prefix
            and request["candidate_sha256"].startswith(command.candidate_hash_prefix)
            and report["request_unexpired"]
        )
    if not report["bound_member_match"]:
        report["reason_code"] = "group_approval_probe_foreign_member"
    elif not report["current_request_match"]:
        report["reason_code"] = "group_approval_probe_request_mismatch"
    else:
        report["approval_matcher"] = "accepted"
        report["reason_code"] = "group_approval_probe_exact_event_accepted"
    return report


async def probe_live_group_approval(
    *,
    config: QQHandlerConfig,
    binding: Mapping[str, Any],
    journal: SQLiteQQHandlerJournal,
    display: Callable[[JsonObject], None],
) -> JsonObject:
    """Observe one group approval event without recording a decision or write."""

    gateway = _LiveGateway(config)
    await gateway.open()
    display(
        {
            "report_type": "weflow-qq-handler-group-approval-probe-ready.v1",
            "gateway_ready": True,
            "deadline_seconds": QQ_HANDLER_CHALLENGE_TTL_SECONDS,
            "instruction": "在已配对群真实@机器人并发送当前的 WF-APPROVE 元数据。",
            "network_contacted": True,
            "external_write_attempted": False,
        }
    )
    try:
        async with asyncio.timeout(QQ_HANDLER_CHALLENGE_TTL_SECONDS):
            while True:
                event = await gateway.next_event()
                if event.get("t") != "GROUP_AT_MESSAGE_CREATE":
                    continue
                return build_group_approval_probe_observation(
                    event,
                    config=config,
                    binding=binding,
                    journal=journal,
                )
    except TimeoutError:
        return {
            "report_type": "weflow-qq-handler-group-approval-probe.v1",
            "gateway_ready": True,
            "group_event_received": False,
            "approval_matcher": "not_observed",
            "reason_code": "group_approval_probe_deadline_expired",
            "raw_identity_present": False,
            "raw_content_present": False,
            "provider_event_persisted": False,
            "network_contacted": True,
            "external_write_attempted": False,
            "case_mutation": False,
            "model_invocation": False,
            "production_ready": False,
        }
    finally:
        await gateway.close()


async def pair_live_handler(
    *,
    config: QQHandlerConfig,
    journal: SQLiteQQHandlerJournal,
    display: Callable[[JsonObject], None],
    confirm: Callable[[], str],
) -> JsonObject:
    existing = journal.active_binding_for_config(config)
    if existing is not None:
        return journal.build_acceptance_report(
            config=config,
            binding=existing,
            mode="qq-sandbox-live",
            recovery_state="reconciled",
        )
    session = begin_handler_pairing(config, contract_root=config.repository_root)
    journal.record_pairing_session(session)
    display(
        {
            "report_type": "weflow-qq-handler-pairing-challenge-display.v1",
            "pairing_session_id": session.session_id,
            "deadline_seconds": 300,
            "group_instruction": f"在已配对群中真实@机器人并发送：{session.group.plaintext}",
            "c2c_instruction": f"由同一处理人私聊机器人发送：{session.c2c.plaintext}",
            "persisted": False,
        }
    )
    gateway = _LiveGateway(config)
    observed: set[str] = set()
    rejected = 0
    await gateway.open()
    try:
        while observed != {"group", "c2c"}:
            event = await gateway.next_event()
            for challenge in (session.group, session.c2c):
                surface = str(challenge.record["surface"])
                if surface in observed:
                    continue
                try:
                    observation = normalize_handler_pairing_event(
                        event,
                        config=config,
                        challenge=challenge,
                        now=datetime.now(UTC),
                    )
                except QQHandlerEventRejected:
                    continue
                journal.record_pairing_observation(challenge, observation)
                observed.add(surface)
                display(
                    {
                        "report_type": "weflow-qq-handler-pairing-observation.v1",
                        "surface": surface,
                        "observed": True,
                        "raw_identity_present": False,
                    }
                )
                break
            else:
                rejected += 1
    finally:
        await gateway.close()
    binding = journal.confirm_handler_binding(
        config=config,
        pairing_session_id=session.session_id,
        operator_confirmation=confirm().strip(),
    )
    return journal.build_acceptance_report(
        config=config,
        binding=binding,
        mode="qq-sandbox-live",
        rejected_event_count=rejected,
        network_contacted=True,
    )


async def run_live_handler_case(
    *,
    config: QQHandlerConfig,
    binding: Mapping[str, Any],
    journal: SQLiteQQHandlerJournal,
) -> JsonObject:
    service = QQHandlerWorkflowService(config=config, binding=binding, journal=journal)
    gateway = _LiveGateway(config)
    rejected = 0
    duplicates = 0
    commands: list[str] = []
    notification_status = "not_attempted"
    recovery_state = "not_required"
    external_write_attempted = False
    intake: JsonObject | None = None
    stage1_ledger = SQLiteCaseLedger(config.store_path, contract_root=config.repository_root)
    await gateway.open()
    try:
        assert gateway.access_token is not None
        transport = RealQQHandlerTransport(
            gateway.client,
            access_token=gateway.access_token,
            group_openid=config.group_openid,
            user_openid=journal.private_locator(binding["handler_binding_id"], "c2c-user"),
        )
        while intake is None:
            event = await gateway.next_event()
            try:
                intake = accept_live_stage1_intake(event, config=config, ledger=stage1_ledger)
            except (IntakeRejected, QQEventRejected, QQHandlerEventRejected):
                rejected += 1
        journal.create_issue_artifact(
            binding=binding,
            case_id=intake["case_id"],
            case_revision_id=intake["case_revision_id"],
            source_message_id_hash=intake["source_message_id_hash"],
            content=intake["content"],
        )
        notification = journal.execute_notification(
            journal.create_notification_intent(intake["case_id"], binding),
            binding=binding,
            transport=transport,
        )
        external_write_attempted = True
        notification_status = str(notification["status"])
        if notification_status in {"unknown", "timed_out", "disconnected"}:
            recovery_state = "ambiguous_no_retry"
        if notification_status != "accepted":
            nudge_intent = journal.create_group_nudge_intent(
                case_id=intake["case_id"],
                binding=binding,
                source_message_id=intake["source_message_id"],
                occurred_at=intake["occurred_at"],
            )
            journal.execute_passive_reply(
                nudge_intent,
                binding=binding,
                content=QQ_GROUP_NUDGE_TEMPLATE,
                transport=transport,
            )
        while True:
            event = await gateway.next_event()
            if event.get("t") == "C2C_MESSAGE_CREATE":
                try:
                    response = service.handle_private_event(event)
                    result = service.execute_private_response(response, transport=transport)
                    external_write_attempted = True
                    commands.append(str(response.command["command"]))
                    duplicates += int(response.duplicate)
                    if result["status"] == "expired_window":
                        recovery_state = "expired_no_fallback"
                except (
                    QQHandlerAuthorizationDenied,
                    QQHandlerEventRejected,
                    QQHandlerStateConflict,
                ):
                    rejected += 1
                continue
            try:
                approval = service.handle_group_approval(event)
                final = service.execute_final_response(approval, transport=transport)
                external_write_attempted = True
            except (
                QQHandlerAuthorizationDenied,
                QQHandlerEventRejected,
                QQHandlerStateConflict,
            ):
                rejected += 1
                continue
            if final["status"] in {"unknown", "timed_out", "disconnected"}:
                recovery_state = "ambiguous_no_retry"
            elif final["status"] == "expired_window":
                recovery_state = "expired_no_fallback"
            return journal.build_acceptance_report(
                config=config,
                binding=binding,
                mode="qq-sandbox-live",
                case_id=str(intake["case_id"]),
                notification_status=notification_status,
                private_workflow_verified=(
                    "pull" in commands and "accept" in commands and commands.count("draft") >= 2
                ),
                group_approval_verified=True,
                final_provider_accepted=bool(final["provider_accepted"]),
                recovery_state=recovery_state,
                duplicate_event_count=duplicates,
                rejected_event_count=rejected,
                artifact_deletion_verified=(
                    journal.deleted_artifact_count(str(intake["case_id"])) >= 2
                ),
                network_contacted=True,
                external_write_attempted=external_write_attempted,
            )
    finally:
        await gateway.close()


def build_handler_journal(config: QQHandlerConfig) -> SQLiteQQHandlerJournal:
    return SQLiteQQHandlerJournal(config.store_path, contract_root=Path(config.repository_root))


__all__ = [
    "PAIRING_CONFIRMATION",
    "accept_live_stage1_intake",
    "build_c2c_probe_observation",
    "build_group_approval_probe_observation",
    "build_handler_journal",
    "normalize_live_customer_intake",
    "pair_live_handler",
    "probe_live_c2c",
    "probe_live_group_approval",
    "run_live_handler_case",
]
