"""Deterministic QQ sandbox intake and fixed acknowledgement control boundary."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from weflow_contracts import (
    QQ_ACKNOWLEDGEMENT_COMPLETION_SCHEMA_ID,
    QQ_ACKNOWLEDGEMENT_INTENT_SCHEMA_ID,
    QQ_ACKNOWLEDGEMENT_OBSERVATION_SCHEMA_ID,
    QQ_GATEWAY_CURSOR_SCHEMA_ID,
    QQ_SANDBOX_INBOUND_EVENT_SCHEMA_ID,
    qq_gateway_cursor_sha256,
    stable_idempotency_key,
    validate_qq_acknowledgement_chain,
    validate_qq_gateway_cursor,
    validate_qq_sandbox_inbound_event,
)
from weflow_contracts.qq import canonical_sha256

from .ledger import IntakeResult, SQLiteCaseLedger

Clock = Callable[[], datetime]
JsonObject = dict[str, Any]

QQ_REQUIRED_CAPABILITIES = ("qq.group_at.read", "qq.passive_ack.execute")
QQ_ACK_TEMPLATE_ID = "qq.passive_ack.v1"
QQ_ACK_TEMPLATE = "已受理，工单编号：{case_id}。当前仅确认已进入处理流程，不代表问题已解决。"
QQ_PASSIVE_REPLY_WINDOW_SECONDS = 300
QQ_REPLY_LOCATOR_RETENTION_SECONDS = 86_400
QQ_ENVIRONMENT_KEYS = frozenset(
    {
        "WEFLOW_QQ_APP_ID",
        "WEFLOW_QQ_CLIENT_SECRET",
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID",
        "WEFLOW_QQ_TENANT_ID",
        "WEFLOW_QQ_IDENTITY_SALT",
        "WEFLOW_QQ_CAPABILITIES",
    }
)

_MESSAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_LEADING_MENTION = re.compile(r"^\s*(?:@机器人|<@!?[A-Za-z0-9._:-]+>)\s*")
_FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "tenant_id",
        "caller_tenant_id",
        "role",
        "caller_role",
        "destination",
        "group_override",
        "message_body",
        "access_token",
        "client_secret",
        "authorization",
    }
)


class QQSandboxError(ValueError):
    """A stable redacted QQ boundary failure."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class QQActivationDenied(QQSandboxError):
    """Raised before network construction when command activation is invalid."""


class QQEventRejected(QQSandboxError):
    """Raised before persistence for an unsupported or unsafe QQ event."""


class QQJournalError(QQSandboxError):
    """Raised when QQ durable evidence cannot be trusted."""


class QQTransportError(QQSandboxError):
    """A redacted transport failure; provider bodies are never attached."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise QQEventRejected("qq_event_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QQEventRejected("qq_event_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise QQEventRejected("qq_event_timestamp_invalid")
    return parsed.astimezone(UTC)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, material: Mapping[str, Any]) -> str:
    return f"{prefix}_{canonical_sha256(material)[:32]}"


def _contains_forbidden_authority(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_AUTHORITY_FIELDS:
                return True
            if _contains_forbidden_authority(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_authority(item) for item in value)
    return False


@dataclass(frozen=True)
class QQSandboxConfig:
    """Command-local QQ sandbox configuration; raw values never enter safe reports."""

    app_id: str
    client_secret: str
    group_openid: str
    tenant_id: str
    identity_salt: str
    capabilities: tuple[str, ...] = QQ_REQUIRED_CAPABILITIES
    environment: str = "sandbox"

    @classmethod
    def from_environment(
        cls,
        *,
        confirm_live: bool,
        environ: Mapping[str, str] | None = None,
        live_model_enabled: bool = False,
        other_external_write_enabled: bool = False,
    ) -> QQSandboxConfig:
        if not confirm_live:
            raise QQActivationDenied("explicit_confirmation_required")
        if live_model_enabled or other_external_write_enabled:
            raise QQActivationDenied("qq_capability_scope_denied")
        source = os.environ if environ is None else environ
        values = {
            key: source.get(key)
            for key in (
                "WEFLOW_QQ_APP_ID",
                "WEFLOW_QQ_CLIENT_SECRET",
                "WEFLOW_QQ_SANDBOX_GROUP_OPENID",
                "WEFLOW_QQ_TENANT_ID",
                "WEFLOW_QQ_IDENTITY_SALT",
            )
        }
        if any(not isinstance(value, str) or not value for value in values.values()):
            raise QQActivationDenied("qq_configuration_missing")
        capability_value = source.get("WEFLOW_QQ_CAPABILITIES")
        capabilities = (
            tuple(part.strip() for part in capability_value.split(","))
            if capability_value is not None
            else QQ_REQUIRED_CAPABILITIES
        )
        if capabilities != QQ_REQUIRED_CAPABILITIES:
            raise QQActivationDenied("qq_capability_scope_denied")
        return cls(
            app_id=str(values["WEFLOW_QQ_APP_ID"]),
            client_secret=str(values["WEFLOW_QQ_CLIENT_SECRET"]),
            group_openid=str(values["WEFLOW_QQ_SANDBOX_GROUP_OPENID"]),
            tenant_id=str(values["WEFLOW_QQ_TENANT_ID"]),
            identity_salt=str(values["WEFLOW_QQ_IDENTITY_SALT"]),
            capabilities=capabilities,
        )

    @property
    def app_id_hash(self) -> str:
        return _sha256_text(self.app_id)

    @property
    def group_openid_hash(self) -> str:
        return _sha256_text(self.group_openid)

    @property
    def capability_profile_hash(self) -> str:
        return _sha256_text("|".join(self.capabilities))

    def safe_readiness(self) -> JsonObject:
        return {
            "mode": "qq-sandbox-intake-and-ack",
            "environment": self.environment,
            "app_id_hash": self.app_id_hash,
            "group_openid_hash": self.group_openid_hash,
            "tenant_mapping_hash": _sha256_text(self.tenant_id),
            "capability_profile_hash": self.capability_profile_hash,
            "network_enabled": True,
            "model_enabled": False,
            "other_external_writes_enabled": False,
            "ready": True,
        }


def reject_qq_configuration_for_ordinary_command(environ: Mapping[str, str]) -> None:
    if any(key in environ for key in QQ_ENVIRONMENT_KEYS):
        raise QQActivationDenied("qq_configuration_forbidden_for_command")


def normalize_qq_group_at_event(
    raw_event: Mapping[str, Any],
    config: QQSandboxConfig,
    *,
    received_at: datetime | None = None,
    contract_root: Path | None = None,
) -> JsonObject:
    """Normalize one allowlisted QQ group mention and discard its readable content."""

    if _contains_forbidden_authority(raw_event):
        raise QQEventRejected("qq_event_authority_field_forbidden")
    if raw_event.get("t") != "GROUP_AT_MESSAGE_CREATE":
        raise QQEventRejected("qq_event_type_unsupported")
    sequence = raw_event.get("s")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise QQEventRejected("qq_gateway_sequence_invalid")
    data = raw_event.get("d")
    if not isinstance(data, Mapping):
        raise QQEventRejected("qq_event_shape_invalid")
    if data.get("group_openid") != config.group_openid:
        raise QQEventRejected("qq_group_not_allowlisted")
    attachments = data.get("attachments")
    if attachments not in (None, []):
        raise QQEventRejected("qq_attachment_unsupported")
    message_type = data.get("message_type", 0)
    if not isinstance(message_type, int) or isinstance(message_type, bool) or message_type != 0:
        raise QQEventRejected("qq_non_text_unsupported")
    if data.get("ark_data") not in (None, {}) or data.get("msg_elements") not in (
        None,
        [],
    ):
        raise QQEventRejected("qq_non_text_unsupported")
    source_message_id = data.get("id")
    if not isinstance(source_message_id, str) or not _MESSAGE_ID_PATTERN.fullmatch(
        source_message_id
    ):
        raise QQEventRejected("qq_message_identity_invalid")
    author = data.get("author")
    sender_openid = author.get("member_openid") if isinstance(author, Mapping) else None
    if not isinstance(sender_openid, str) or not sender_openid:
        raise QQEventRejected("qq_sender_identity_invalid")
    content = data.get("content")
    if not isinstance(content, str):
        raise QQEventRejected("qq_text_required")
    incident_text = _LEADING_MENTION.sub("", content, count=1).strip()
    if not incident_text:
        raise QQEventRejected("qq_text_required")
    if incident_text.startswith("WFPAIR-"):
        raise QQEventRejected("qq_pairing_control_message_reserved")
    occurred = _parse_timestamp(data.get("timestamp"))
    received = (received_at or _utc_now()).astimezone(UTC)
    if received < occurred:
        raise QQEventRejected("qq_event_timestamp_invalid")

    group_hash = config.group_openid_hash
    source_hash = _sha256_text(source_message_id)
    sender_hash = hmac.new(
        config.identity_salt.encode("utf-8"),
        f"{config.tenant_id}|{sender_openid}".encode(),
        hashlib.sha256,
    ).hexdigest()
    natural_key = canonical_sha256(
        {
            "app_id_hash": config.app_id_hash,
            "group_openid_hash": group_hash,
            "provider": "qq-sandbox",
            "source_message_id": source_message_id,
            "tenant_id": config.tenant_id,
        }
    )
    normalized = {
        "schema_id": QQ_SANDBOX_INBOUND_EVENT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": config.tenant_id,
        "provider": "qq-sandbox",
        "event_type": "GROUP_AT_MESSAGE_CREATE",
        "app_id_hash": config.app_id_hash,
        "group_openid_hash": group_hash,
        "source_message_id": source_message_id,
        "source_message_id_hash": source_hash,
        "sender_openid_hash": sender_hash,
        "conversation_id": f"qq-conversation:{group_hash}",
        "customer_id": f"qq-customer:{sender_hash}",
        "gateway_sequence": sequence,
        "occurred_at": _timestamp(occurred),
        "received_at": _timestamp(received),
        "correlation_id": f"qq-correlation:{natural_key}",
        "content_classification": "qq-private-hash",
        "content_sha256": _sha256_text(incident_text),
        "inbound_natural_key": natural_key,
    }
    validate_qq_sandbox_inbound_event(normalized, contract_root)
    return normalized


@dataclass(frozen=True)
class QQSendOutcome:
    status: str
    reason_code: str
    provider_message_id: str | None = None


class QQPassiveAcknowledgementTransport(Protocol):
    def reconcile(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        idempotency_key: str,
    ) -> QQSendOutcome: ...

    def send_fixed_acknowledgement(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        reply_msg_seq: int,
        idempotency_key: str,
        content: str,
    ) -> QQSendOutcome: ...


class SQLiteQQSandboxJournal:
    """Minimum QQ session/locator and append-only acknowledgement evidence journal."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Clock | None = None,
        contract_root: Path | None = None,
    ) -> None:
        self.path = Path(path)
        self._clock = clock or _utc_now
        self._contract_root = contract_root
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS qq_gateway_cursors (
                    tenant_id TEXT NOT NULL,
                    app_id_hash TEXT NOT NULL,
                    group_openid_hash TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, app_id_hash, group_openid_hash)
                );

                CREATE TABLE IF NOT EXISTS qq_acknowledgement_intents (
                    tenant_id TEXT NOT NULL,
                    natural_key TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, natural_key),
                    UNIQUE (tenant_id, idempotency_key),
                    UNIQUE (tenant_id, intent_id)
                );

                CREATE TABLE IF NOT EXISTS qq_acknowledgement_observations (
                    tenant_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    observation_sequence INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, observation_id),
                    UNIQUE (tenant_id, intent_id, observation_sequence)
                );

                CREATE TABLE IF NOT EXISTS qq_acknowledgement_completions (
                    tenant_id TEXT NOT NULL,
                    completion_id TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, completion_id),
                    UNIQUE (tenant_id, intent_id)
                );

                CREATE TABLE IF NOT EXISTS qq_reply_locators (
                    tenant_id TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    group_openid TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, intent_id)
                );

                CREATE TRIGGER IF NOT EXISTS qq_ack_intents_no_update
                BEFORE UPDATE ON qq_acknowledgement_intents
                BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_ack_intents_no_delete
                BEFORE DELETE ON qq_acknowledgement_intents
                BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_ack_observations_no_update
                BEFORE UPDATE ON qq_acknowledgement_observations
                BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_ack_observations_no_delete
                BEFORE DELETE ON qq_acknowledgement_observations
                BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_ack_completions_no_update
                BEFORE UPDATE ON qq_acknowledgement_completions
                BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_ack_completions_no_delete
                BEFORE DELETE ON qq_acknowledgement_completions
                BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
                """
            )
        finally:
            connection.close()

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)

    def get_cursor(self, config: QQSandboxConfig) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT record_json FROM qq_gateway_cursors
                WHERE tenant_id = ? AND app_id_hash = ? AND group_openid_hash = ?
                """,
                (config.tenant_id, config.app_id_hash, config.group_openid_hash),
            ).fetchone()
            if row is None:
                return None
            value = json.loads(str(row["record_json"]))
            validate_qq_gateway_cursor(value, self._contract_root)
            return value
        finally:
            connection.close()

    def record_cursor(
        self,
        config: QQSandboxConfig,
        *,
        sequence: int,
        status: str,
        session_id: str | None = None,
    ) -> JsonObject:
        current = self.get_cursor(config)
        provided_session_hash = _sha256_text(session_id) if session_id else None
        current_session_hash = current["session_id_hash"] if current is not None else None
        session_changed = (
            status == "identified"
            and provided_session_hash is not None
            and current is not None
            and provided_session_hash != current_session_hash
        )
        last_sequence = (
            sequence
            if session_changed
            else max(
                sequence,
                int(current["last_contiguous_sequence"]) if current is not None else 0,
            )
        )
        session_hash = provided_session_hash or current_session_hash
        cursor = {
            "schema_id": QQ_GATEWAY_CURSOR_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": config.tenant_id,
            "cursor_id": _stable_id(
                "qq_cursor",
                {
                    "app_id_hash": config.app_id_hash,
                    "group_openid_hash": config.group_openid_hash,
                    "tenant_id": config.tenant_id,
                },
            ),
            "app_id_hash": config.app_id_hash,
            "group_openid_hash": config.group_openid_hash,
            "session_id_hash": session_hash,
            "last_contiguous_sequence": last_sequence,
            "status": status,
            "updated_at": _timestamp(self._now()),
        }
        cursor["cursor_sha256"] = qq_gateway_cursor_sha256(cursor)
        validate_qq_gateway_cursor(cursor, self._contract_root)
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO qq_gateway_cursors (
                    tenant_id, app_id_hash, group_openid_hash, record_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, app_id_hash, group_openid_hash)
                DO UPDATE SET record_json = excluded.record_json
                """,
                (
                    config.tenant_id,
                    config.app_id_hash,
                    config.group_openid_hash,
                    json.dumps(cursor, sort_keys=True, separators=(",", ":")),
                ),
            )
            return cursor
        finally:
            connection.close()

    def create_acknowledgement_intent(
        self,
        config: QQSandboxConfig,
        inbound: Mapping[str, Any],
        intake: IntakeResult,
    ) -> JsonObject:
        if (
            inbound.get("tenant_id") != config.tenant_id
            or inbound.get("group_openid_hash") != config.group_openid_hash
        ):
            raise QQJournalError("qq_intent_identity_mismatch")
        created = self._now()
        deadline = _parse_timestamp(inbound["occurred_at"]) + timedelta(
            seconds=QQ_PASSIVE_REPLY_WINDOW_SECONDS
        )
        template_sha256 = _sha256_text(QQ_ACK_TEMPLATE.format(case_id=intake.case_id))
        natural_key = canonical_sha256(
            {
                "case_id": intake.case_id,
                "case_revision_id": intake.case_revision_id,
                "operation": QQ_ACK_TEMPLATE_ID,
                "tenant_id": config.tenant_id,
            }
        )
        intended_state_sha256 = canonical_sha256(
            {
                "group_openid_hash": config.group_openid_hash,
                "reply_msg_seq": 1,
                "source_message_id_hash": inbound["source_message_id_hash"],
                "template_sha256": template_sha256,
            }
        )
        idempotency_key = stable_idempotency_key(
            tenant_id=config.tenant_id,
            provider_id="qq-sandbox",
            operation="qq.passive_ack.execute",
            natural_key=natural_key,
            intended_state_hash=intended_state_sha256,
        )
        intent = {
            "schema_id": QQ_ACKNOWLEDGEMENT_INTENT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": config.tenant_id,
            "case_id": intake.case_id,
            "case_revision_id": intake.case_revision_id,
            "intent_id": _stable_id(
                "qq_ack_intent",
                {"idempotency_key": idempotency_key, "tenant_id": config.tenant_id},
            ),
            "effect_kind": "qq-sandbox-passive-acknowledgement",
            "operation": "qq.passive_ack.execute",
            "source_message_id": inbound["source_message_id"],
            "source_message_id_hash": inbound["source_message_id_hash"],
            "group_openid_hash": config.group_openid_hash,
            "conversation_id": inbound["conversation_id"],
            "template_id": QQ_ACK_TEMPLATE_ID,
            "template_sha256": template_sha256,
            "natural_key": natural_key,
            "intended_state_sha256": intended_state_sha256,
            "idempotency_key": idempotency_key,
            "reply_msg_seq": 1,
            "reply_deadline_at": _timestamp(deadline),
            "capability_profile_hash": config.capability_profile_hash,
            "correlation_id": inbound["correlation_id"],
            "created_at": _timestamp(created),
        }
        validate_qq_acknowledgement_chain(intent, [], [], self._contract_root)
        record_json = json.dumps(intent, sort_keys=True, separators=(",", ":"))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT record_json FROM qq_acknowledgement_intents
                WHERE tenant_id = ? AND natural_key = ?
                """,
                (config.tenant_id, natural_key),
            ).fetchone()
            if existing is not None:
                existing_value = json.loads(str(existing["record_json"]))
                if (
                    existing_value["idempotency_key"] != idempotency_key
                    or existing_value["case_id"] != intake.case_id
                    or existing_value["source_message_id_hash"] != inbound["source_message_id_hash"]
                ):
                    raise QQJournalError("qq_acknowledgement_intent_conflict")
                connection.commit()
                return existing_value
            connection.execute(
                """
                INSERT INTO qq_acknowledgement_intents (
                    tenant_id, natural_key, idempotency_key, intent_id, record_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    config.tenant_id,
                    natural_key,
                    idempotency_key,
                    intent["intent_id"],
                    record_json,
                ),
            )
            connection.execute(
                """
                INSERT INTO qq_reply_locators (
                    tenant_id, intent_id, group_openid, source_message_id,
                    expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    config.tenant_id,
                    intent["intent_id"],
                    config.group_openid,
                    inbound["source_message_id"],
                    _timestamp(created + timedelta(seconds=QQ_REPLY_LOCATOR_RETENTION_SECONDS)),
                    _timestamp(created),
                ),
            )
            connection.commit()
            return intent
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise QQJournalError("qq_journal_write_failed") from error
        finally:
            connection.close()

    def get_intent(self, tenant_id: str, intent_id: str) -> JsonObject:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT record_json FROM qq_acknowledgement_intents
                WHERE tenant_id = ? AND intent_id = ?
                """,
                (tenant_id, intent_id),
            ).fetchone()
            if row is None:
                raise QQJournalError("qq_acknowledgement_intent_not_found")
            return json.loads(str(row["record_json"]))
        finally:
            connection.close()

    def _records(self, table: str, tenant_id: str, intent_id: str) -> list[JsonObject]:
        connection = self._connect()
        try:
            order = (
                "observation_sequence ASC"
                if table == "qq_acknowledgement_observations"
                else "completion_id ASC"
            )
            rows = connection.execute(
                f"SELECT record_json FROM {table} "
                f"WHERE tenant_id = ? AND intent_id = ? ORDER BY {order}",
                (tenant_id, intent_id),
            ).fetchall()
            return [json.loads(str(row["record_json"])) for row in rows]
        finally:
            connection.close()

    def observations(self, tenant_id: str, intent_id: str) -> list[JsonObject]:
        return self._records("qq_acknowledgement_observations", tenant_id, intent_id)

    def completions(self, tenant_id: str, intent_id: str) -> list[JsonObject]:
        return self._records("qq_acknowledgement_completions", tenant_id, intent_id)

    def get_locator(self, tenant_id: str, intent_id: str) -> JsonObject:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT group_openid, source_message_id, expires_at
                FROM qq_reply_locators WHERE tenant_id = ? AND intent_id = ?
                """,
                (tenant_id, intent_id),
            ).fetchone()
            if row is None:
                raise QQJournalError("qq_reply_locator_not_found")
            return {
                "group_openid": str(row["group_openid"]),
                "source_message_id": str(row["source_message_id"]),
                "expires_at": str(row["expires_at"]),
            }
        finally:
            connection.close()

    def append_observation(
        self,
        intent: Mapping[str, Any],
        outcome: QQSendOutcome,
    ) -> JsonObject:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            sequence = (
                int(
                    connection.execute(
                        """
                    SELECT COUNT(*) FROM qq_acknowledgement_observations
                    WHERE tenant_id = ? AND intent_id = ?
                    """,
                        (intent["tenant_id"], intent["intent_id"]),
                    ).fetchone()[0]
                )
                + 1
            )
            provider_hash = (
                _sha256_text(outcome.provider_message_id)
                if outcome.provider_message_id is not None
                else None
            )
            outcome_hash = (
                canonical_sha256(
                    {
                        "provider_message_id_hash": provider_hash,
                        "reason_code": outcome.reason_code,
                        "status": outcome.status,
                    }
                )
                if outcome.status in {"accepted", "present", "duplicate"}
                else None
            )
            observation = {
                "schema_id": QQ_ACKNOWLEDGEMENT_OBSERVATION_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": intent["tenant_id"],
                "case_id": intent["case_id"],
                "case_revision_id": intent["case_revision_id"],
                "observation_id": _stable_id(
                    "qq_ack_observation",
                    {
                        "intent_id": intent["intent_id"],
                        "sequence": sequence,
                        "status": outcome.status,
                    },
                ),
                "intent_id": intent["intent_id"],
                "status": outcome.status,
                "provider_message_id_hash": provider_hash,
                "outcome_sha256": outcome_hash,
                "reason_code": outcome.reason_code,
                "recorded_at": _timestamp(self._now()),
            }
            chain = self.observations(str(intent["tenant_id"]), str(intent["intent_id"]))
            validate_qq_acknowledgement_chain(
                intent, [*chain, observation], [], self._contract_root
            )
            connection.execute(
                """
                INSERT INTO qq_acknowledgement_observations (
                    tenant_id, observation_id, intent_id, observation_sequence, record_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    intent["tenant_id"],
                    observation["observation_id"],
                    intent["intent_id"],
                    sequence,
                    json.dumps(observation, sort_keys=True, separators=(",", ":")),
                ),
            )
            connection.commit()
            return observation
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise QQJournalError("qq_journal_write_failed") from error
        finally:
            connection.close()

    def complete(
        self,
        intent: Mapping[str, Any],
        observation: Mapping[str, Any],
    ) -> JsonObject:
        existing = self.completions(str(intent["tenant_id"]), str(intent["intent_id"]))
        if existing:
            return existing[0]
        completion = {
            "schema_id": QQ_ACKNOWLEDGEMENT_COMPLETION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": intent["tenant_id"],
            "case_id": intent["case_id"],
            "case_revision_id": intent["case_revision_id"],
            "completion_id": _stable_id(
                "qq_ack_completion",
                {"intent_id": intent["intent_id"], "tenant_id": intent["tenant_id"]},
            ),
            "intent_id": intent["intent_id"],
            "observation_id": observation["observation_id"],
            "status": "provider_accepted_or_present",
            "provider_message_id_hash": observation["provider_message_id_hash"],
            "outcome_sha256": observation["outcome_sha256"],
            "completed_at": _timestamp(self._now()),
        }
        validate_qq_acknowledgement_chain(
            intent,
            self.observations(str(intent["tenant_id"]), str(intent["intent_id"])),
            [completion],
            self._contract_root,
        )
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO qq_acknowledgement_completions (
                    tenant_id, completion_id, intent_id, record_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    intent["tenant_id"],
                    completion["completion_id"],
                    intent["intent_id"],
                    json.dumps(completion, sort_keys=True, separators=(",", ":")),
                ),
            )
            return completion
        except sqlite3.IntegrityError:
            existing = self.completions(str(intent["tenant_id"]), str(intent["intent_id"]))
            if existing:
                return existing[0]
            raise QQJournalError("qq_journal_write_failed")
        finally:
            connection.close()

    def recoverable_intent_ids(self, tenant_id: str) -> list[str]:
        """Return incomplete intents whose latest observation permits bounded reconcile."""

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT intent_id FROM qq_acknowledgement_intents
                WHERE tenant_id = ?
                  AND intent_id NOT IN (
                      SELECT intent_id FROM qq_acknowledgement_completions
                      WHERE tenant_id = ?
                  )
                ORDER BY intent_id ASC
                """,
                (tenant_id, tenant_id),
            ).fetchall()
        finally:
            connection.close()
        recoverable: list[str] = []
        for row in rows:
            intent_id = str(row["intent_id"])
            intent = self.get_intent(tenant_id, intent_id)
            if self._now() >= _parse_timestamp(intent["reply_deadline_at"]):
                continue
            observations = self.observations(tenant_id, intent_id)
            if not observations or observations[-1]["status"] in {"absent", "unknown"}:
                recoverable.append(intent_id)
        return recoverable

    def safe_counts(self, tenant_id: str) -> JsonObject:
        connection = self._connect()
        try:
            return {
                "gateway_cursor_count": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM qq_gateway_cursors WHERE tenant_id = ?",
                        (tenant_id,),
                    ).fetchone()[0]
                ),
                "acknowledgement_intent_count": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM qq_acknowledgement_intents WHERE tenant_id = ?",
                        (tenant_id,),
                    ).fetchone()[0]
                ),
                "acknowledgement_observation_count": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM qq_acknowledgement_observations WHERE tenant_id = ?",
                        (tenant_id,),
                    ).fetchone()[0]
                ),
                "acknowledgement_completion_count": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM qq_acknowledgement_completions WHERE tenant_id = ?",
                        (tenant_id,),
                    ).fetchone()[0]
                ),
            }
        finally:
            connection.close()

    def purge_expired_locators(self, *, now: datetime | None = None) -> int:
        cutoff = _timestamp((now or self._now()).astimezone(UTC))
        connection = self._connect()
        try:
            cursor = connection.execute(
                "DELETE FROM qq_reply_locators WHERE expires_at <= ?", (cutoff,)
            )
            return int(cursor.rowcount)
        finally:
            connection.close()


class QQAcknowledgementController:
    def __init__(
        self,
        journal: SQLiteQQSandboxJournal,
        transport: QQPassiveAcknowledgementTransport,
        config: QQSandboxConfig,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.journal = journal
        self.transport = transport
        self.config = config
        self._clock = clock or _utc_now

    def _observe_and_maybe_complete(
        self,
        intent: Mapping[str, Any],
        outcome: QQSendOutcome,
    ) -> JsonObject:
        observation = self.journal.append_observation(intent, outcome)
        if outcome.status in {"accepted", "present", "duplicate"}:
            completion = self.journal.complete(intent, observation)
            return {
                "status": "completed",
                "intent_id": intent["intent_id"],
                "observation_id": observation["observation_id"],
                "completion_id": completion["completion_id"],
                "customer_receipt_verified": False,
                "case_completion": False,
            }
        return {
            "status": ("expired" if outcome.status == "expired" else "NEEDS_RECONCILIATION"),
            "intent_id": intent["intent_id"],
            "observation_id": observation["observation_id"],
            "customer_receipt_verified": False,
            "case_completion": False,
        }

    def process(self, intent_id: str, *, capability_active: bool = True) -> JsonObject:
        intent = self.journal.get_intent(self.config.tenant_id, intent_id)
        existing = self.journal.completions(self.config.tenant_id, intent_id)
        if existing:
            return {
                "status": "completed",
                "intent_id": intent_id,
                "completion_id": existing[0]["completion_id"],
                "customer_receipt_verified": False,
                "case_completion": False,
            }
        if (
            not capability_active
            or intent["capability_profile_hash"] != self.config.capability_profile_hash
            or intent["group_openid_hash"] != self.config.group_openid_hash
        ):
            return self._observe_and_maybe_complete(
                intent,
                QQSendOutcome("unauthorized", "qq_acknowledgement_unauthorized"),
            )
        if self._clock().astimezone(UTC) >= _parse_timestamp(intent["reply_deadline_at"]):
            return self._observe_and_maybe_complete(
                intent, QQSendOutcome("expired", "qq_passive_reply_deadline_expired")
            )
        locator = self.journal.get_locator(self.config.tenant_id, intent_id)
        if locator["group_openid"] != self.config.group_openid:
            return self._observe_and_maybe_complete(
                intent, QQSendOutcome("conflict", "qq_reply_locator_conflict")
            )
        try:
            outcome = self.transport.reconcile(
                group_openid=locator["group_openid"],
                source_message_id=locator["source_message_id"],
                reply_msg_seq=int(intent["reply_msg_seq"]),
                idempotency_key=str(intent["idempotency_key"]),
            )
        except QQTransportError:
            outcome = QQSendOutcome("unknown", "qq_provider_outcome_unknown")
        if outcome.status == "absent":
            try:
                outcome = self.transport.send_fixed_acknowledgement(
                    group_openid=locator["group_openid"],
                    source_message_id=locator["source_message_id"],
                    reply_msg_seq=int(intent["reply_msg_seq"]),
                    idempotency_key=str(intent["idempotency_key"]),
                    content=QQ_ACK_TEMPLATE.format(case_id=intent["case_id"]),
                )
            except QQTransportError:
                outcome = QQSendOutcome("unknown", "qq_provider_outcome_unknown")
        return self._observe_and_maybe_complete(intent, outcome)


@dataclass(frozen=True)
class QQIntakeAndIntentResult:
    intake: IntakeResult
    intent: JsonObject
    inbound: JsonObject


class QQSandboxIntakeService:
    def __init__(
        self,
        ledger: SQLiteCaseLedger,
        journal: SQLiteQQSandboxJournal,
        config: QQSandboxConfig,
        *,
        clock: Clock | None = None,
        contract_root: Path | None = None,
    ) -> None:
        self.ledger = ledger
        self.journal = journal
        self.config = config
        self._clock = clock or _utc_now
        self._contract_root = contract_root

    def accept(
        self,
        raw_event: Mapping[str, Any],
        *,
        session_id: str | None = None,
    ) -> QQIntakeAndIntentResult:
        inbound = normalize_qq_group_at_event(
            raw_event,
            self.config,
            received_at=self._clock(),
            contract_root=self._contract_root,
        )
        sequence = int(inbound["gateway_sequence"])
        cursor = self.journal.get_cursor(self.config)
        if (
            cursor is not None
            and sequence <= int(cursor["last_contiguous_sequence"])
            and not self.ledger.has_qq_receipt(inbound, effective_tenant_id=self.config.tenant_id)
        ):
            raise QQEventRejected("qq_gateway_sequence_out_of_order")
        if cursor is not None and sequence > int(cursor["last_contiguous_sequence"]) + 1:
            self.journal.record_cursor(
                self.config,
                sequence=int(cursor["last_contiguous_sequence"]),
                status="reconciliation_required",
                session_id=session_id,
            )
            raise QQEventRejected("qq_gateway_sequence_gap")
        intake = self.ledger.intake_qq(
            inbound,
            effective_tenant_id=self.config.tenant_id,
        )
        self.journal.record_cursor(
            self.config,
            sequence=sequence,
            status="identified",
            session_id=session_id,
        )
        intent = self.journal.create_acknowledgement_intent(self.config, inbound, intake)
        return QQIntakeAndIntentResult(intake=intake, intent=intent, inbound=inbound)
