"""Deterministic, privacy-bounded QQ handler approval and delivery workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from weflow_contracts import (
    QQ_CUSTOMER_ISSUE_ARTIFACT_SCHEMA_ID,
    QQ_HANDLER_ACCEPTANCE_REPORT_SCHEMA_ID,
    QQ_HANDLER_APPROVAL_DECISION_SCHEMA_ID,
    QQ_HANDLER_APPROVAL_REQUEST_SCHEMA_ID,
    QQ_HANDLER_BINDING_SCHEMA_ID,
    QQ_HANDLER_CANDIDATE_REVISION_SCHEMA_ID,
    QQ_HANDLER_NOTIFICATION_INTENT_SCHEMA_ID,
    QQ_HANDLER_NOTIFICATION_RESULT_SCHEMA_ID,
    QQ_HANDLER_PAIRING_CHALLENGE_SCHEMA_ID,
    QQ_HANDLER_PASSIVE_REPLY_INTENT_SCHEMA_ID,
    QQ_HANDLER_PASSIVE_REPLY_RESULT_SCHEMA_ID,
    QQ_HANDLER_PRIVATE_LOCATOR_SCHEMA_ID,
    QQ_HANDLER_RESPONSE_ARTIFACT_SCHEMA_ID,
    canonical_sha256,
    qq_handler_acceptance_report_sha256,
    stable_idempotency_key,
    validate_qq_customer_issue_artifact,
    validate_qq_handler_acceptance_report,
    validate_qq_handler_approval_chain,
    validate_qq_handler_binding,
    validate_qq_handler_candidate_revision,
    validate_qq_handler_notification_chain,
    validate_qq_handler_pairing_challenge,
    validate_qq_handler_passive_reply_chain,
    validate_qq_handler_private_locator,
    validate_qq_handler_response_artifact,
)

JsonObject = dict[str, Any]
Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]

QQ_HANDLER_REQUIRED_CAPABILITIES = (
    "qq.group_at.read",
    "qq.c2c.read",
    "qq.c2c.notification.execute",
    "qq.c2c.passive_reply.execute",
    "qq.handler_approval.decide",
    "qq.final_reply.execute",
)
QQ_HANDLER_CHALLENGE_TTL_SECONDS = 300
QQ_HANDLER_BINDING_TTL_SECONDS = 86_400
QQ_HANDLER_ARTIFACT_TTL_SECONDS = 86_400
QQ_C2C_PASSIVE_REPLY_WINDOW_SECONDS = 3_600
QQ_GROUP_PASSIVE_REPLY_WINDOW_SECONDS = 300
QQ_HANDLER_REVOCATION_CONFIRMATION = "CONFIRM-LOCAL-QQ-HANDLER-REVOCATION"
QQ_NOTIFICATION_TEMPLATE = (
    "工单 {case_reference} 待处理。请私聊发送 WF-PULL {case_reference} {version}。"
)
QQ_GROUP_NUDGE_TEMPLATE = "处理人请查看与机器人的私聊任务通知；群内不展示工单或草稿内容。"
QQ_RESPONSE_MSG_SEQ = {
    "pull": 1,
    "accept": 2,
    "draft-preview": 3,
    "reject": 4,
    "group-nudge": 2,
    "final": 5,
}

_MESSAGE_ID_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MENTION = re.compile(r"^\s*(?:@机器人|<@!?[A-Za-z0-9._:-]+>)\s*")
_CASE_ID = re.compile(r"^case_[a-f0-9]{24,64}$")
_REQUEST_ID = re.compile(r"^qqhar_[a-f0-9]{32}$")
_HASH_PREFIX = re.compile(r"^[a-f0-9]{12,64}$")
_HANDLER_BINDING_ID = re.compile(r"^qqhbind_[a-f0-9]{32}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(access[_ -]?token|client[_ -]?secret|password|api[_ -]?key)\s*[:=]\s*([^\s,;]+)"
)
_PROHIBITED_CANDIDATE = re.compile(
    r"(?i)(?:\bBEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY\b|\b(?:client_secret|access_token)\s*[:=])"
)
_REJECTION_REASON = re.compile(r"^[a-z0-9._-]{1,64}$")


class QQHandlerError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class QQHandlerActivationDenied(QQHandlerError):
    pass


class QQHandlerEventRejected(QQHandlerError):
    pass


class QQHandlerAuthorizationDenied(QQHandlerError):
    pass


class QQHandlerStateConflict(QQHandlerError):
    pass


class QQHandlerTransportError(QQHandlerError):
    pass


class _ClosingSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


def _now() -> datetime:
    return datetime.now(UTC)


def _ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: object, reason: str = "qq_handler_timestamp_invalid") -> datetime:
    if not isinstance(value, str):
        raise QQHandlerEventRejected(reason)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QQHandlerEventRejected(reason) from error
    if parsed.tzinfo is None:
        raise QQHandlerEventRejected(reason)
    return parsed.astimezone(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _salted_hash(salt: str, surface: str, value: str) -> str:
    return _hash(f"weflow-qq-handler-v1\0{salt}\0{surface}\0{value}")


def is_safe_provider_message_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 256
        and _MESSAGE_ID_CONTROL.search(value) is None
    )


def _id(prefix: str, material: Mapping[str, Any]) -> str:
    return f"{prefix}_{canonical_sha256(material)[:32]}"


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_private_content(value: str, *, candidate: bool) -> str:
    """Normalize and redact one process-memory private artifact deterministically."""

    if not isinstance(value, str):
        raise QQHandlerEventRejected("private_content_type_invalid")
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    if _CONTROL.search(normalized):
        raise QQHandlerEventRejected("private_content_control_character")
    normalized = "\n".join(" ".join(line.split()) for line in normalized.split("\n"))
    normalized = "\n".join(line for line in normalized.split("\n") if line).strip()
    if candidate and _PROHIBITED_CANDIDATE.search(normalized):
        raise QQHandlerEventRejected("candidate_prohibited_content")
    normalized = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", normalized)
    scalar_count = len(normalized)
    if scalar_count < 1:
        raise QQHandlerEventRejected("private_content_empty")
    if scalar_count > 1_200:
        raise QQHandlerEventRejected("private_content_oversized")
    return normalized


@dataclass(frozen=True)
class QQHandlerConfig:
    app_id: str
    client_secret: str
    tenant_id: str
    stage1_pairing_id: str
    group_openid: str
    identity_salt: str
    store_path: Path
    repository_root: Path
    capabilities: tuple[str, ...] = QQ_HANDLER_REQUIRED_CAPABILITIES
    environment: str = "sandbox"

    @classmethod
    def from_environment(
        cls,
        *,
        confirm_live_qq: bool,
        store_path: str | Path,
        repository_root: str | Path,
        group_openid: str,
        environ: Mapping[str, str] | None = None,
    ) -> QQHandlerConfig:
        if not confirm_live_qq:
            raise QQHandlerActivationDenied("handler_explicit_confirmation_required")
        source = os.environ if environ is None else environ
        required_names = (
            "WEFLOW_QQ_APP_ID",
            "WEFLOW_QQ_CLIENT_SECRET",
            "WEFLOW_QQ_TENANT_ID",
            "WEFLOW_QQ_SANDBOX_PAIRING_ID",
            "WEFLOW_QQ_IDENTITY_SALT",
        )
        required = {name: source.get(name, "").strip() for name in required_names}
        if any(not value for value in required.values()) or not group_openid:
            raise QQHandlerActivationDenied("handler_configuration_missing")
        if not re.fullmatch(r"qqpair_[a-f0-9]{32}", required["WEFLOW_QQ_SANDBOX_PAIRING_ID"]):
            raise QQHandlerActivationDenied("handler_stage1_pairing_invalid")
        if len(required["WEFLOW_QQ_IDENTITY_SALT"].encode("utf-8")) < 32:
            raise QQHandlerActivationDenied("handler_identity_salt_too_short")
        capability_text = source.get("WEFLOW_QQ_CAPABILITIES", "")
        capabilities = tuple(part.strip() for part in capability_text.split(",") if part.strip())
        if capabilities != QQ_HANDLER_REQUIRED_CAPABILITIES:
            raise QQHandlerActivationDenied("handler_capability_scope_denied")
        forbidden = (
            "WEFLOW_LIVE_MODEL_API_KEY",
            "WEFLOW_PROVIDER_API_KEY",
            "WEFLOW_PROVIDER_ALLOW_LIVE",
            "WEFLOW_EXTERNAL_WRITE_ENABLED",
            "WEFLOW_MULTI_AGENT_ENABLED",
            "WEFLOW_QQ_MAIL_ENABLED",
            "WEFLOW_QQ_ATTACHMENT_ENABLED",
        )
        if any(source.get(name) for name in forbidden):
            raise QQHandlerActivationDenied("handler_unrelated_authority_denied")
        if source.get("WEFLOW_PROVIDER_MODE", "replay").strip().lower() != "replay":
            raise QQHandlerActivationDenied("handler_model_authority_denied")
        root = Path(repository_root).resolve()
        store = Path(store_path)
        store = store.resolve() if store.is_absolute() else (root / store).resolve()
        try:
            store.relative_to(root)
        except ValueError as error:
            raise QQHandlerActivationDenied("handler_store_outside_repository") from error
        if store.name != "qq-sandbox.sqlite3" or store.parent.name != ".weflow":
            raise QQHandlerActivationDenied("handler_store_not_bounded")
        return cls(
            app_id=required["WEFLOW_QQ_APP_ID"],
            client_secret=required["WEFLOW_QQ_CLIENT_SECRET"],
            tenant_id=required["WEFLOW_QQ_TENANT_ID"],
            stage1_pairing_id=required["WEFLOW_QQ_SANDBOX_PAIRING_ID"],
            group_openid=group_openid,
            identity_salt=required["WEFLOW_QQ_IDENTITY_SALT"],
            store_path=store,
            repository_root=root,
            capabilities=capabilities,
        )

    @property
    def app_id_hash(self) -> str:
        return _hash(self.app_id)

    @property
    def tenant_id_hash(self) -> str:
        return _hash(self.tenant_id)

    @property
    def group_openid_hash(self) -> str:
        return _hash(self.group_openid)

    @property
    def capability_profile_hash(self) -> str:
        return _hash("|".join(self.capabilities))

    def safe_readiness(self, *, handler_binding_id: str | None = None) -> JsonObject:
        return {
            "mode": "qq-sandbox-handler-approval",
            "environment": self.environment,
            "app_id_hash": self.app_id_hash,
            "tenant_id_hash": self.tenant_id_hash,
            "group_openid_hash": self.group_openid_hash,
            "stage1_pairing_id": self.stage1_pairing_id,
            "handler_binding_id": handler_binding_id,
            "capability_profile_hash": self.capability_profile_hash,
            "network_enabled": False,
            "external_write_enabled": False,
            "case_mutation_enabled": False,
            "model_enabled": False,
            "production_ready": False,
            "ready": True,
        }


def reject_handler_configuration_for_other_commands(environ: Mapping[str, str]) -> None:
    handler_caps = ",".join(QQ_HANDLER_REQUIRED_CAPABILITIES)
    if (
        environ.get("WEFLOW_QQ_HANDLER_ACTIVE")
        or environ.get("WEFLOW_QQ_HANDLER_BINDING_ID")
        or environ.get("WEFLOW_QQ_CAPABILITIES") == handler_caps
    ):
        raise QQHandlerActivationDenied("handler_configuration_forbidden_for_command")


@dataclass(frozen=True)
class QQHandlerPairingChallenge:
    plaintext: str
    record: JsonObject


@dataclass(frozen=True)
class QQHandlerPairingSession:
    session_id: str
    group: QQHandlerPairingChallenge
    c2c: QQHandlerPairingChallenge


def begin_handler_pairing(
    config: QQHandlerConfig,
    *,
    clock: Clock = _now,
    token_factory: TokenFactory | None = None,
    contract_root: Path | None = None,
) -> QQHandlerPairingSession:
    factory = token_factory or (lambda: secrets.token_urlsafe(24))
    group_token = factory()
    c2c_token = factory()
    if min(len(group_token.encode()), len(c2c_token.encode())) < 22 or group_token == c2c_token:
        raise QQHandlerActivationDenied("handler_challenge_entropy_insufficient")
    created = clock().astimezone(UTC)
    session_id = _id(
        "qqhps",
        {
            "app": config.app_id_hash,
            "tenant": config.tenant_id_hash,
            "group": config.group_openid_hash,
            "created": _ts(created),
            "entropy": _hash(group_token + c2c_token),
        },
    )

    def challenge(surface: str, token: str) -> QQHandlerPairingChallenge:
        plaintext = f"WFH-{surface.upper()}-{token}"
        digest = _hash(plaintext)
        record = {
            "schema_id": QQ_HANDLER_PAIRING_CHALLENGE_SCHEMA_ID,
            "schema_version": "v1",
            "challenge_id": _id(
                "qqhc", {"session": session_id, "surface": surface, "digest": digest}
            ),
            "pairing_session_id": session_id,
            "surface": surface,
            "challenge_sha256": digest,
            "app_id_hash": config.app_id_hash,
            "tenant_id": config.tenant_id,
            "tenant_id_hash": config.tenant_id_hash,
            "group_openid_hash": config.group_openid_hash,
            "capability_profile_hash": config.capability_profile_hash,
            "observed_identity_hash": None,
            "source_message_id_hash": None,
            "created_at": _ts(created),
            "deadline_at": _ts(created + timedelta(seconds=QQ_HANDLER_CHALLENGE_TTL_SECONDS)),
            "status": "PENDING",
        }
        validate_qq_handler_pairing_challenge(record, contract_root)
        return QQHandlerPairingChallenge(plaintext, record)

    return QQHandlerPairingSession(
        session_id=session_id,
        group=challenge("group", group_token),
        c2c=challenge("c2c", c2c_token),
    )


@dataclass(frozen=True)
class QQHandlerPairingObservation:
    surface: str
    identity: str
    identity_hash: str
    source_message_id: str
    source_message_id_hash: str
    group_openid: str
    group_openid_hash: str
    occurred_at: str
    gateway_sequence: int


def normalize_handler_pairing_event(
    raw_event: Mapping[str, Any],
    *,
    config: QQHandlerConfig,
    challenge: QQHandlerPairingChallenge,
    now: datetime,
) -> QQHandlerPairingObservation:
    expected_type = (
        "GROUP_AT_MESSAGE_CREATE"
        if challenge.record["surface"] == "group"
        else "C2C_MESSAGE_CREATE"
    )
    if raw_event.get("t") != expected_type:
        raise QQHandlerEventRejected("handler_pairing_event_type_unsupported")
    sequence = raw_event.get("s")
    data = raw_event.get("d")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise QQHandlerEventRejected("handler_pairing_sequence_invalid")
    if not isinstance(data, Mapping):
        raise QQHandlerEventRejected("handler_pairing_event_shape_invalid")
    if any(
        data.get(field) not in (None, [], {})
        for field in ("attachments", "ark_data", "msg_elements")
    ):
        raise QQHandlerEventRejected("handler_pairing_plain_text_required")
    message_id = data.get("id")
    content = data.get("content")
    author = data.get("author")
    if not is_safe_provider_message_id(message_id):
        raise QQHandlerEventRejected("handler_pairing_message_identity_invalid")
    if not isinstance(content, str) or not isinstance(author, Mapping):
        raise QQHandlerEventRejected("handler_pairing_plain_text_required")
    occurred = _parse(data.get("timestamp"))
    current = now.astimezone(UTC)
    if occurred > current or current > _parse(challenge.record["deadline_at"]):
        raise QQHandlerEventRejected("handler_pairing_challenge_expired")
    normalized = " ".join(content.strip().split())
    if challenge.record["surface"] == "group":
        normalized = " ".join(_MENTION.sub("", content, count=1).strip().split())
        group_openid = data.get("group_openid")
        identity = author.get("member_openid")
        surface_salt = "group-member"
        if group_openid != config.group_openid:
            raise QQHandlerEventRejected("handler_pairing_foreign_group")
    else:
        group_openid = config.group_openid
        identity = author.get("user_openid")
        surface_salt = "c2c-user"
    if normalized != challenge.plaintext:
        raise QQHandlerEventRejected("handler_pairing_challenge_mismatch")
    if not isinstance(identity, str) or not identity:
        raise QQHandlerEventRejected("handler_pairing_identity_invalid")
    return QQHandlerPairingObservation(
        surface=str(challenge.record["surface"]),
        identity=identity,
        identity_hash=_salted_hash(config.identity_salt, surface_salt, identity),
        source_message_id=message_id,
        source_message_id_hash=_hash(message_id),
        group_openid=str(group_openid),
        group_openid_hash=_hash(str(group_openid)),
        occurred_at=_ts(occurred),
        gateway_sequence=sequence,
    )


@dataclass(frozen=True)
class QQPrivateCommand:
    command: str
    case_id: str
    expected_version: int
    body: str | None = None


def parse_private_command(content: str) -> QQPrivateCommand:
    normalized = (
        unicodedata.normalize("NFKC", content).replace("\r\n", "\n").replace("\r", "\n").strip()
    )
    head, separator, body = normalized.partition("\n")
    parts = head.split()
    if not parts or parts[0] not in {"WF-PULL", "WF-ACCEPT", "WF-DRAFT", "WF-REJECT"}:
        raise QQHandlerEventRejected("private_command_unknown_or_malformed")
    command = parts[0].removeprefix("WF-").lower()
    expected_parts = 4 if command == "reject" else 3
    if len(parts) != expected_parts:
        raise QQHandlerEventRejected("private_command_unknown_or_malformed")
    if not _CASE_ID.fullmatch(parts[1]):
        raise QQHandlerEventRejected("private_command_case_invalid")
    try:
        version = int(parts[2])
    except ValueError as error:
        raise QQHandlerEventRejected("private_command_version_invalid") from error
    if version < 1:
        raise QQHandlerEventRejected("private_command_version_invalid")
    if command == "draft":
        if not separator:
            raise QQHandlerEventRejected("private_command_draft_missing")
        return QQPrivateCommand(command, parts[1], version, body)
    if command == "reject":
        if separator or not _REJECTION_REASON.fullmatch(parts[3]):
            raise QQHandlerEventRejected("private_command_rejection_reason_invalid")
        return QQPrivateCommand(command, parts[1], version, parts[3])
    if separator:
        raise QQHandlerEventRejected("private_command_extra_content")
    return QQPrivateCommand(command, parts[1], version)


@dataclass(frozen=True)
class QQGroupApprovalCommand:
    approval_request_id: str
    candidate_hash_prefix: str
    expected_version: int


def parse_group_approval(content: str) -> QQGroupApprovalCommand:
    normalized = unicodedata.normalize("NFKC", content)
    without_mention = _MENTION.sub("", normalized, count=1)
    if without_mention == normalized:
        raise QQHandlerEventRejected("group_approval_mention_required")
    parts = without_mention.strip().split()
    if len(parts) != 4 or parts[0] != "WF-APPROVE":
        raise QQHandlerEventRejected("group_approval_unknown_or_malformed")
    if not _REQUEST_ID.fullmatch(parts[1]) or not _HASH_PREFIX.fullmatch(parts[2]):
        raise QQHandlerEventRejected("group_approval_metadata_invalid")
    try:
        version = int(parts[3])
    except ValueError as error:
        raise QQHandlerEventRejected("group_approval_version_invalid") from error
    if version < 1:
        raise QQHandlerEventRejected("group_approval_version_invalid")
    return QQGroupApprovalCommand(parts[1], parts[2], version)


@dataclass(frozen=True)
class QQProviderOutcome:
    status: str
    reason_code: str
    provider_message_id: str | None = None
    provider_status: str | None = None


class QQHandlerTransport(Protocol):
    def notify_c2c(
        self, *, user_openid: str, content: str, idempotency_key: str
    ) -> QQProviderOutcome: ...

    def passive_c2c_reply(
        self,
        *,
        user_openid: str,
        source_message_id: str,
        msg_seq: int,
        content: str,
        idempotency_key: str,
    ) -> QQProviderOutcome: ...

    def passive_group_reply(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        msg_seq: int,
        content: str,
        idempotency_key: str,
    ) -> QQProviderOutcome: ...

    def group_nudge(
        self,
        *,
        group_openid: str,
        source_message_id: str,
        msg_seq: int,
        content: str,
        idempotency_key: str,
    ) -> QQProviderOutcome: ...

    def reconcile_passive(
        self,
        *,
        surface: str,
        destination: str,
        source_message_id: str,
        msg_seq: int,
        idempotency_key: str,
    ) -> QQProviderOutcome: ...


class SQLiteQQHandlerJournal:
    """One local restricted store with append-only public facts and private payload tables."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Clock = _now,
        contract_root: Path | None = None,
    ) -> None:
        self.path = Path(path)
        self._clock = clock
        self._contract_root = contract_root
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        try:
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path, isolation_level=None, timeout=5, factory=_ClosingSQLiteConnection
        )
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS qq_handler_pairing_sessions(
                    pairing_session_id TEXT PRIMARY KEY, app_id_hash TEXT NOT NULL,
                    tenant_id_hash TEXT NOT NULL, group_openid_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_pairing_challenges(
                    challenge_id TEXT PRIMARY KEY, pairing_session_id TEXT NOT NULL,
                    surface TEXT NOT NULL, challenge_sha256 TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL, UNIQUE(pairing_session_id, surface)
                );
                CREATE TABLE IF NOT EXISTS qq_handler_pairing_observations(
                    observation_id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL UNIQUE,
                    pairing_session_id TEXT NOT NULL, surface TEXT NOT NULL,
                    identity_hash TEXT NOT NULL, source_message_id_hash TEXT NOT NULL,
                    group_openid_hash TEXT NOT NULL, observed_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_pending_locators(
                    challenge_id TEXT PRIMARY KEY, pairing_session_id TEXT NOT NULL,
                    surface TEXT NOT NULL, provider_identity TEXT NOT NULL,
                    group_openid TEXT NOT NULL, source_message_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_bindings(
                    handler_binding_id TEXT PRIMARY KEY, pairing_session_id TEXT NOT NULL UNIQUE,
                    app_id_hash TEXT NOT NULL, tenant_id_hash TEXT NOT NULL,
                    group_openid_hash TEXT NOT NULL, status TEXT NOT NULL,
                    expires_at TEXT NOT NULL, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_private_locators(
                    locator_id TEXT PRIMARY KEY, handler_binding_id TEXT NOT NULL,
                    locator_kind TEXT NOT NULL, provider_locator TEXT NOT NULL,
                    locator_sha256 TEXT NOT NULL, expires_at TEXT NOT NULL,
                    status TEXT NOT NULL, UNIQUE(handler_binding_id, locator_kind)
                );
                CREATE TABLE IF NOT EXISTS qq_handler_events(
                    event_id TEXT PRIMARY KEY, aggregate_id TEXT NOT NULL,
                    event_kind TEXT NOT NULL, expected_prior_version INTEGER,
                    resulting_version INTEGER, correlation_id TEXT NOT NULL,
                    causation_id TEXT NOT NULL, reason_code TEXT NOT NULL,
                    metadata_json TEXT NOT NULL, recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_artifacts(
                    artifact_id TEXT PRIMARY KEY, artifact_kind TEXT NOT NULL,
                    tenant_id TEXT NOT NULL, case_id TEXT NOT NULL,
                    case_revision_id TEXT NOT NULL, content_sha256 TEXT NOT NULL,
                    expires_at TEXT NOT NULL, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_artifact_content(
                    artifact_id TEXT PRIMARY KEY, content TEXT NOT NULL,
                    reachable INTEGER NOT NULL CHECK(reachable IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS qq_handler_artifact_lifecycle(
                    event_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL,
                    status TEXT NOT NULL, reason_code TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_cases(
                    case_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    case_revision_id TEXT NOT NULL, handler_binding_id TEXT NOT NULL,
                    issue_artifact_id TEXT NOT NULL, group_openid_hash TEXT NOT NULL,
                    workflow_version INTEGER NOT NULL, status TEXT NOT NULL,
                    current_candidate_revision_id TEXT,
                    current_approval_request_id TEXT
                );
                CREATE TABLE IF NOT EXISTS qq_handler_candidate_revisions(
                    candidate_revision_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
                    candidate_artifact_id TEXT NOT NULL, status TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_approval_requests(
                    approval_request_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
                    candidate_revision_id TEXT NOT NULL, expires_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_approval_decisions(
                    approval_decision_id TEXT PRIMARY KEY, approval_request_id TEXT NOT NULL UNIQUE,
                    case_id TEXT NOT NULL, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_commands(
                    source_message_id_hash TEXT PRIMARY KEY, command_id TEXT NOT NULL,
                    case_id TEXT, classification TEXT NOT NULL, result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_event_cursors(
                    surface TEXT NOT NULL, handler_binding_id TEXT NOT NULL,
                    last_sequence INTEGER NOT NULL, last_source_message_id_hash TEXT NOT NULL,
                    PRIMARY KEY(surface, handler_binding_id)
                );
                CREATE TABLE IF NOT EXISTS qq_handler_notification_intents(
                    intent_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE,
                    case_id TEXT NOT NULL, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_notification_attempts(
                    intent_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    started_at TEXT NOT NULL, result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS qq_handler_passive_intents(
                    intent_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE,
                    case_id TEXT NOT NULL, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_handler_passive_results(
                    intent_id TEXT PRIMARY KEY, result_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS qq_handler_event_no_update
                    BEFORE UPDATE ON qq_handler_events
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_handler_event_no_delete
                    BEFORE DELETE ON qq_handler_events
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_handler_binding_no_update
                    BEFORE UPDATE ON qq_handler_bindings
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_handler_binding_no_delete
                    BEFORE DELETE ON qq_handler_bindings
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_handler_artifact_no_update
                    BEFORE UPDATE ON qq_handler_artifacts
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_handler_artifact_no_delete
                    BEFORE DELETE ON qq_handler_artifacts
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                """
            )

    def _event(
        self,
        c: sqlite3.Connection,
        *,
        aggregate_id: str,
        event_kind: str,
        prior_version: int | None,
        resulting_version: int | None,
        correlation_id: str,
        causation_id: str,
        reason_code: str,
        metadata: Mapping[str, Any],
    ) -> str:
        recorded = _ts(self._clock())
        safe_metadata = dict(metadata)
        forbidden = {
            "member_openid",
            "user_openid",
            "group_openid",
            "content",
            "issue",
            "candidate",
            "preview",
            "transcript",
            "raw_event",
            "provider_response",
        }
        if forbidden.intersection(key.lower() for key in safe_metadata):
            raise QQHandlerStateConflict("unsafe_event_metadata")
        event_id = _id(
            "qqhe",
            {
                "aggregate": aggregate_id,
                "kind": event_kind,
                "prior": prior_version,
                "result": resulting_version,
                "correlation": correlation_id,
                "causation": causation_id,
                "reason": reason_code,
                "metadata": safe_metadata,
                "recorded": recorded,
            },
        )
        c.execute(
            "INSERT OR IGNORE INTO qq_handler_events VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                aggregate_id,
                event_kind,
                prior_version,
                resulting_version,
                correlation_id,
                causation_id,
                reason_code,
                _json(safe_metadata),
                recorded,
            ),
        )
        return event_id

    def record_pairing_session(self, session: QQHandlerPairingSession) -> None:
        for challenge in (session.group, session.c2c):
            validate_qq_handler_pairing_challenge(challenge.record, self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT INTO qq_handler_pairing_sessions VALUES(?,?,?,?,?)",
                (
                    session.session_id,
                    session.group.record["app_id_hash"],
                    session.group.record["tenant_id_hash"],
                    session.group.record["group_openid_hash"],
                    session.group.record["created_at"],
                ),
            )
            for challenge in (session.group, session.c2c):
                c.execute(
                    "INSERT INTO qq_handler_pairing_challenges VALUES(?,?,?,?,?)",
                    (
                        challenge.record["challenge_id"],
                        session.session_id,
                        challenge.record["surface"],
                        challenge.record["challenge_sha256"],
                        _json(challenge.record),
                    ),
                )
            self._event(
                c,
                aggregate_id=session.session_id,
                event_kind="HANDLER_PAIRING_STARTED",
                prior_version=None,
                resulting_version=None,
                correlation_id=session.session_id,
                causation_id=session.session_id,
                reason_code="dual_challenge_created",
                metadata={"challenge_count": 2},
            )
            c.execute("COMMIT")

    def record_pairing_observation(
        self,
        challenge: QQHandlerPairingChallenge,
        observation: QQHandlerPairingObservation,
    ) -> JsonObject:
        if observation.surface != challenge.record["surface"]:
            raise QQHandlerStateConflict("handler_pairing_surface_mismatch")
        observed = dict(challenge.record)
        observed.update(
            {
                "observed_identity_hash": observation.identity_hash,
                "source_message_id_hash": observation.source_message_id_hash,
                "status": "OBSERVED",
            }
        )
        validate_qq_handler_pairing_challenge(observed, self._contract_root)
        observation_id = _id(
            "qqho",
            {
                "challenge": challenge.record["challenge_id"],
                "identity": observation.identity_hash,
                "source": observation.source_message_id_hash,
            },
        )
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            known = c.execute(
                "SELECT record_json FROM qq_handler_pairing_observations WHERE challenge_id=?",
                (challenge.record["challenge_id"],),
            ).fetchone()
            if known:
                prior = json.loads(known[0])
                c.execute("COMMIT")
                if prior == observed:
                    return prior
                raise QQHandlerStateConflict("handler_pairing_challenge_replayed")
            session = c.execute(
                "SELECT app_id_hash, tenant_id_hash, group_openid_hash "
                "FROM qq_handler_pairing_sessions "
                "WHERE pairing_session_id=?",
                (challenge.record["pairing_session_id"],),
            ).fetchone()
            if not session:
                c.execute("ROLLBACK")
                raise QQHandlerStateConflict("handler_pairing_session_missing")
            if tuple(session) != (
                challenge.record["app_id_hash"],
                challenge.record["tenant_id_hash"],
                observation.group_openid_hash,
            ):
                c.execute("ROLLBACK")
                raise QQHandlerStateConflict("handler_pairing_session_mismatch")
            c.execute(
                "INSERT INTO qq_handler_pairing_observations VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    observation_id,
                    challenge.record["challenge_id"],
                    challenge.record["pairing_session_id"],
                    observation.surface,
                    observation.identity_hash,
                    observation.source_message_id_hash,
                    observation.group_openid_hash,
                    observation.occurred_at,
                    _json(observed),
                ),
            )
            c.execute(
                "INSERT INTO qq_handler_pending_locators VALUES(?,?,?,?,?,?,?)",
                (
                    challenge.record["challenge_id"],
                    challenge.record["pairing_session_id"],
                    observation.surface,
                    observation.identity,
                    observation.group_openid,
                    observation.source_message_id,
                    challenge.record["deadline_at"],
                ),
            )
            self._event(
                c,
                aggregate_id=str(challenge.record["pairing_session_id"]),
                event_kind=f"HANDLER_{observation.surface.upper()}_CHALLENGE_OBSERVED",
                prior_version=None,
                resulting_version=None,
                correlation_id=str(challenge.record["pairing_session_id"]),
                causation_id=observation.source_message_id_hash,
                reason_code="exact_challenge_observed",
                metadata={
                    "challenge_id": challenge.record["challenge_id"],
                    "identity_hash": observation.identity_hash,
                    "source_message_id_hash": observation.source_message_id_hash,
                },
            )
            c.execute("COMMIT")
        return observed

    def confirm_handler_binding(
        self,
        *,
        config: QQHandlerConfig,
        pairing_session_id: str,
        operator_confirmation: str,
        provider_cross_surface_identity_hash: str | None = None,
    ) -> JsonObject:
        if operator_confirmation != "CONFIRM-DUAL-QQ-HANDLER":
            raise QQHandlerAuthorizationDenied("handler_local_confirmation_required")
        now = self._clock().astimezone(UTC)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT record_json FROM qq_handler_bindings WHERE pairing_session_id=?",
                (pairing_session_id,),
            ).fetchone()
            if existing:
                c.execute("COMMIT")
                return json.loads(existing[0])
            session = c.execute(
                "SELECT * FROM qq_handler_pairing_sessions WHERE pairing_session_id=?",
                (pairing_session_id,),
            ).fetchone()
            observations = c.execute(
                "SELECT * FROM qq_handler_pairing_observations WHERE pairing_session_id=? "
                "ORDER BY surface",
                (pairing_session_id,),
            ).fetchall()
            if (
                not session
                or len(observations) != 2
                or {row["surface"] for row in observations} != {"group", "c2c"}
            ):
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_dual_challenge_incomplete")
            if tuple(
                session[key] for key in ("app_id_hash", "tenant_id_hash", "group_openid_hash")
            ) != (
                config.app_id_hash,
                config.tenant_id_hash,
                config.group_openid_hash,
            ):
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_pairing_configuration_mismatch")
            pending = c.execute(
                "SELECT * FROM qq_handler_pending_locators WHERE pairing_session_id=? "
                "ORDER BY surface",
                (pairing_session_id,),
            ).fetchall()
            if len(pending) != 2 or any(_parse(row["expires_at"]) < now for row in pending):
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_pairing_expired_or_missing")
            active = c.execute(
                "SELECT b.handler_binding_id FROM qq_handler_bindings b WHERE b.app_id_hash=? "
                "AND b.tenant_id_hash=? AND b.group_openid_hash=? AND b.status='ACTIVE' "
                "AND b.expires_at>? AND NOT EXISTS (SELECT 1 FROM qq_handler_events e "
                "WHERE e.aggregate_id=b.handler_binding_id "
                "AND e.event_kind='HANDLER_BINDING_REVOKED')",
                (config.app_id_hash, config.tenant_id_hash, config.group_openid_hash, _ts(now)),
            ).fetchone()
            if active:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_unauthorized_rebinding")
            by_surface = {row["surface"]: row for row in observations}
            private_by_surface = {row["surface"]: row for row in pending}
            binding_id = _id(
                "qqhbind",
                {
                    "session": pairing_session_id,
                    "group_member": by_surface["group"]["identity_hash"],
                    "c2c_user": by_surface["c2c"]["identity_hash"],
                    "confirmed": _ts(now),
                },
            )
            group_locator_id = _id("qqloc", {"binding": binding_id, "kind": "group-member"})
            c2c_locator_id = _id("qqloc", {"binding": binding_id, "kind": "c2c-user"})
            expires = now + timedelta(seconds=QQ_HANDLER_BINDING_TTL_SECONDS)
            assurance = (
                "provider_cross_surface_verified"
                if provider_cross_surface_identity_hash
                else "operator_confirmed_dual_challenge"
            )
            binding = {
                "schema_id": QQ_HANDLER_BINDING_SCHEMA_ID,
                "schema_version": "v1",
                "handler_binding_id": binding_id,
                "pairing_session_id": pairing_session_id,
                "stage1_pairing_id": config.stage1_pairing_id,
                "group_challenge_id": by_surface["group"]["challenge_id"],
                "c2c_challenge_id": by_surface["c2c"]["challenge_id"],
                "tenant_id": config.tenant_id,
                "tenant_id_hash": config.tenant_id_hash,
                "app_id_hash": config.app_id_hash,
                "group_openid_hash": config.group_openid_hash,
                "group_member_identity_hash": by_surface["group"]["identity_hash"],
                "c2c_user_identity_hash": by_surface["c2c"]["identity_hash"],
                "group_locator_id": group_locator_id,
                "c2c_locator_id": c2c_locator_id,
                "assurance_level": assurance,
                "cross_surface_identity_hash": provider_cross_surface_identity_hash,
                "operator_confirmation_hash": _hash(operator_confirmation),
                "capability_profile_hash": config.capability_profile_hash,
                "status": "ACTIVE",
                "confirmed_at": _ts(now),
                "expires_at": _ts(expires),
            }
            validate_qq_handler_binding(binding, self._contract_root)
            c.execute(
                "INSERT INTO qq_handler_bindings VALUES(?,?,?,?,?,?,?,?)",
                (
                    binding_id,
                    pairing_session_id,
                    config.app_id_hash,
                    config.tenant_id_hash,
                    config.group_openid_hash,
                    "ACTIVE",
                    binding["expires_at"],
                    _json(binding),
                ),
            )
            locator_rows = (
                (
                    group_locator_id,
                    "group-member",
                    private_by_surface["group"]["provider_identity"],
                    by_surface["group"]["identity_hash"],
                ),
                (
                    c2c_locator_id,
                    "c2c-user",
                    private_by_surface["c2c"]["provider_identity"],
                    by_surface["c2c"]["identity_hash"],
                ),
            )
            for locator_id, kind, raw_value, value_hash in locator_rows:
                locator = {
                    "schema_id": QQ_HANDLER_PRIVATE_LOCATOR_SCHEMA_ID,
                    "schema_version": "v1",
                    "locator_id": locator_id,
                    "handler_binding_id": binding_id,
                    "tenant_id": config.tenant_id,
                    "locator_kind": kind,
                    "locator_sha256": value_hash,
                    "created_at": _ts(now),
                    "expires_at": _ts(expires),
                    "status": "ACTIVE",
                }
                validate_qq_handler_private_locator(locator, self._contract_root)
                c.execute(
                    "INSERT INTO qq_handler_private_locators VALUES(?,?,?,?,?,?,?)",
                    (locator_id, binding_id, kind, raw_value, value_hash, _ts(expires), "ACTIVE"),
                )
            self._event(
                c,
                aggregate_id=binding_id,
                event_kind="HANDLER_BINDING_ACTIVATED",
                prior_version=None,
                resulting_version=None,
                correlation_id=pairing_session_id,
                causation_id=_hash(operator_confirmation),
                reason_code="operator_confirmed_dual_challenge",
                metadata={
                    "group_member_identity_hash": binding["group_member_identity_hash"],
                    "c2c_user_identity_hash": binding["c2c_user_identity_hash"],
                    "assurance_level": assurance,
                },
            )
            c.execute(
                "DELETE FROM qq_handler_pending_locators WHERE pairing_session_id=?",
                (pairing_session_id,),
            )
            c.execute("COMMIT")
        return binding

    def revoke_handler_binding(
        self,
        *,
        config: QQHandlerConfig,
        handler_binding_id: str,
        operator_confirmation: str,
    ) -> JsonObject:
        if not _HANDLER_BINDING_ID.fullmatch(handler_binding_id):
            raise QQHandlerAuthorizationDenied("handler_binding_id_invalid")
        if operator_confirmation != QQ_HANDLER_REVOCATION_CONFIRMATION:
            raise QQHandlerAuthorizationDenied("handler_local_revocation_confirmation_required")
        now = self._clock().astimezone(UTC)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT record_json, expires_at, status FROM qq_handler_bindings "
                "WHERE handler_binding_id=?",
                (handler_binding_id,),
            ).fetchone()
            if not row:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_binding_inactive")
            binding = json.loads(row["record_json"])
            validate_qq_handler_binding(binding, self._contract_root)
            if (
                binding["app_id_hash"],
                binding["tenant_id_hash"],
                binding["group_openid_hash"],
            ) != (
                config.app_id_hash,
                config.tenant_id_hash,
                config.group_openid_hash,
            ):
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_revocation_scope_mismatch")
            revoked = c.execute(
                "SELECT event_id FROM qq_handler_events WHERE aggregate_id=? "
                "AND event_kind='HANDLER_BINDING_REVOKED' ORDER BY recorded_at LIMIT 1",
                (handler_binding_id,),
            ).fetchone()
            if revoked:
                c.execute("COMMIT")
                return {
                    "report_type": "weflow-qq-handler-binding-revocation.v1",
                    "handler_binding_id": handler_binding_id,
                    "revocation_event_id": revoked["event_id"],
                    "revoked": True,
                    "already_revoked": True,
                    "locator_deactivation_count": 0,
                    "reason_code": "handler_binding_already_revoked",
                    "network_contacted": False,
                    "qq_write_attempted": False,
                    "external_write_attempted": False,
                    "case_mutation": False,
                    "model_invocation": False,
                    "production_ready": False,
                }
            if row["status"] != "ACTIVE" or _parse(row["expires_at"]) <= now:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_binding_inactive")
            locator_count = c.execute(
                "UPDATE qq_handler_private_locators SET provider_locator='',status='REVOKED' "
                "WHERE handler_binding_id=? AND status='ACTIVE'",
                (handler_binding_id,),
            ).rowcount
            event_id = self._event(
                c,
                aggregate_id=handler_binding_id,
                event_kind="HANDLER_BINDING_REVOKED",
                prior_version=None,
                resulting_version=None,
                correlation_id=config.stage1_pairing_id,
                causation_id=_hash(f"{handler_binding_id}:{operator_confirmation}"),
                reason_code="handler_binding_revoked_by_local_operator",
                metadata={
                    "app_id_hash": config.app_id_hash,
                    "tenant_id_hash": config.tenant_id_hash,
                    "group_openid_hash": config.group_openid_hash,
                    "locator_deactivation_count": locator_count,
                },
            )
            c.execute("COMMIT")
        return {
            "report_type": "weflow-qq-handler-binding-revocation.v1",
            "handler_binding_id": handler_binding_id,
            "revocation_event_id": event_id,
            "revoked": True,
            "already_revoked": False,
            "locator_deactivation_count": locator_count,
            "reason_code": "handler_binding_revoked_by_local_operator",
            "network_contacted": False,
            "qq_write_attempted": False,
            "external_write_attempted": False,
            "case_mutation": False,
            "model_invocation": False,
            "production_ready": False,
        }

    def active_binding(self, handler_binding_id: str) -> JsonObject:
        with self._connect() as c:
            row = c.execute(
                "SELECT b.record_json, b.expires_at, b.status, "
                "EXISTS(SELECT 1 FROM qq_handler_events e WHERE "
                "e.aggregate_id=b.handler_binding_id "
                "AND e.event_kind='HANDLER_BINDING_REVOKED') AS revoked "
                "FROM qq_handler_bindings b WHERE b.handler_binding_id=?",
                (handler_binding_id,),
            ).fetchone()
        if (
            not row
            or row["status"] != "ACTIVE"
            or bool(row["revoked"])
            or _parse(row["expires_at"]) <= self._clock().astimezone(UTC)
        ):
            raise QQHandlerAuthorizationDenied("handler_binding_inactive")
        binding = json.loads(row["record_json"])
        validate_qq_handler_binding(binding, self._contract_root)
        return binding

    def active_binding_for_config(self, config: QQHandlerConfig) -> JsonObject | None:
        """Resolve an already-confirmed binding without exposing provider locators."""
        with self._connect() as c:
            rows = c.execute(
                "SELECT b.handler_binding_id, b.record_json FROM qq_handler_bindings b "
                "WHERE b.app_id_hash=? AND b.tenant_id_hash=? AND b.group_openid_hash=? "
                "AND b.status='ACTIVE' AND b.expires_at>? "
                "AND NOT EXISTS (SELECT 1 FROM qq_handler_events e "
                "WHERE e.aggregate_id=b.handler_binding_id "
                "AND e.event_kind='HANDLER_BINDING_REVOKED')",
                (
                    config.app_id_hash,
                    config.tenant_id_hash,
                    config.group_openid_hash,
                    _ts(self._clock().astimezone(UTC)),
                ),
            ).fetchall()
        matches = []
        for row in rows:
            binding = json.loads(row["record_json"])
            validate_qq_handler_binding(binding, self._contract_root)
            if binding["stage1_pairing_id"] == config.stage1_pairing_id:
                matches.append(str(row["handler_binding_id"]))
        if not matches:
            return None
        if len(matches) != 1:
            raise QQHandlerStateConflict("handler_binding_scope_ambiguous")
        return self.active_binding(matches[0])

    def private_locator(self, handler_binding_id: str, kind: str) -> str:
        with self._connect() as c:
            row = c.execute(
                "SELECT provider_locator, expires_at, status FROM qq_handler_private_locators "
                "WHERE handler_binding_id=? AND locator_kind=?",
                (handler_binding_id, kind),
            ).fetchone()
        if (
            not row
            or row["status"] != "ACTIVE"
            or _parse(row["expires_at"]) <= self._clock().astimezone(UTC)
        ):
            raise QQHandlerAuthorizationDenied("handler_private_locator_inactive")
        return str(row["provider_locator"])

    def create_issue_artifact(
        self,
        *,
        binding: Mapping[str, Any],
        case_id: str,
        case_revision_id: str,
        source_message_id_hash: str,
        content: str,
    ) -> JsonObject:
        normalized = normalize_private_content(content, candidate=False)
        content_hash = _hash(normalized)
        created = self._clock().astimezone(UTC)
        artifact_id = _id(
            "qqa",
            {
                "kind": "issue",
                "tenant": binding["tenant_id"],
                "case": case_id,
                "revision": case_revision_id,
                "content": content_hash,
            },
        )
        record = {
            "schema_id": QQ_CUSTOMER_ISSUE_ARTIFACT_SCHEMA_ID,
            "schema_version": "v1",
            "artifact_id": artifact_id,
            "artifact_kind": "qq_customer_issue",
            "tenant_id": binding["tenant_id"],
            "case_id": case_id,
            "case_revision_id": case_revision_id,
            "handler_binding_id": binding["handler_binding_id"],
            "source_message_id_hash": source_message_id_hash,
            "content_sha256": content_hash,
            "normalized_length": len(normalized),
            "classification": "restricted-qq-handler",
            "redaction_policy_id": "qq-handler-redaction.v1",
            "workflow_version": 1,
            "created_at": _ts(created),
            "expires_at": _ts(created + timedelta(seconds=QQ_HANDLER_ARTIFACT_TTL_SECONDS)),
            "deletion_status": "ACTIVE",
            "deleted_at": None,
        }
        validate_qq_customer_issue_artifact(record, self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing_case = c.execute(
                "SELECT issue_artifact_id, case_revision_id FROM qq_handler_cases WHERE case_id=?",
                (case_id,),
            ).fetchone()
            if existing_case:
                existing = c.execute(
                    "SELECT record_json FROM qq_handler_artifacts WHERE artifact_id=?",
                    (existing_case["issue_artifact_id"],),
                ).fetchone()
                c.execute("COMMIT")
                if (
                    existing
                    and json.loads(existing[0])["content_sha256"] == content_hash
                    and existing_case["case_revision_id"] == case_revision_id
                ):
                    return json.loads(existing[0])
                raise QQHandlerStateConflict("case_issue_artifact_conflict")
            c.execute(
                "INSERT INTO qq_handler_artifacts VALUES(?,?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    record["artifact_kind"],
                    record["tenant_id"],
                    case_id,
                    case_revision_id,
                    content_hash,
                    record["expires_at"],
                    _json(record),
                ),
            )
            c.execute(
                "INSERT INTO qq_handler_artifact_content VALUES(?,?,1)",
                (artifact_id, normalized),
            )
            c.execute(
                "INSERT INTO qq_handler_cases VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    case_id,
                    record["tenant_id"],
                    case_revision_id,
                    binding["handler_binding_id"],
                    artifact_id,
                    binding["group_openid_hash"],
                    1,
                    "READY",
                    None,
                    None,
                ),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind="QQ_CUSTOMER_ISSUE_ARTIFACT_CREATED",
                prior_version=0,
                resulting_version=1,
                correlation_id=case_id,
                causation_id=source_message_id_hash,
                reason_code="accepted_stage1_intake_selected",
                metadata={
                    "artifact_id": artifact_id,
                    "content_sha256": content_hash,
                    "normalized_length": len(normalized),
                    "classification": record["classification"],
                },
            )
            c.execute("COMMIT")
        return record

    def artifact_content(self, artifact_id: str) -> str:
        now = self._clock().astimezone(UTC)
        with self._connect() as c:
            row = c.execute(
                "SELECT a.expires_at, p.content, p.reachable FROM qq_handler_artifacts a "
                "JOIN qq_handler_artifact_content p ON p.artifact_id=a.artifact_id "
                "WHERE a.artifact_id=?",
                (artifact_id,),
            ).fetchone()
        if row and _parse(row["expires_at"]) <= now:
            self.delete_expired_artifacts()
            raise QQHandlerAuthorizationDenied("private_artifact_unavailable")
        if not row or not row["reachable"]:
            raise QQHandlerAuthorizationDenied("private_artifact_unavailable")
        return str(row["content"])

    def delete_expired_artifacts(self) -> list[JsonObject]:
        """Remove expired restricted bodies while preserving content-free evidence."""

        now = _ts(self._clock())
        with self._connect() as c:
            case_rows = c.execute(
                "SELECT DISTINCT a.case_id FROM qq_handler_artifacts a "
                "JOIN qq_handler_artifact_content p ON p.artifact_id=a.artifact_id "
                "WHERE a.expires_at<=?",
                (now,),
            ).fetchall()
        deleted: list[JsonObject] = []
        for row in case_rows:
            deleted.extend(
                self.delete_artifacts(str(row["case_id"]), reason_code="artifact_retention_expired")
            )
        return deleted

    def _schedule_artifact_deletion(
        self, c: sqlite3.Connection, artifact_id: str, reason_code: str
    ) -> None:
        c.execute(
            "UPDATE qq_handler_artifact_content SET reachable=0 WHERE artifact_id=?",
            (artifact_id,),
        )
        recorded = _ts(self._clock())
        lifecycle_id = _id(
            "qqhal",
            {
                "artifact": artifact_id,
                "status": "DELETION_SCHEDULED",
                "reason": reason_code,
                "at": recorded,
            },
        )
        c.execute(
            "INSERT OR IGNORE INTO qq_handler_artifact_lifecycle VALUES(?,?,?,?,?)",
            (lifecycle_id, artifact_id, "DELETION_SCHEDULED", reason_code, recorded),
        )

    def delete_artifacts(self, case_id: str, *, reason_code: str) -> list[JsonObject]:
        deleted: list[JsonObject] = []
        now = self._clock().astimezone(UTC)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            rows = c.execute(
                "SELECT a.artifact_id, a.content_sha256, a.artifact_kind, a.record_json "
                "FROM qq_handler_artifacts a WHERE a.case_id=?",
                (case_id,),
            ).fetchall()
            for row in rows:
                c.execute(
                    "DELETE FROM qq_handler_artifact_content WHERE artifact_id=?",
                    (row["artifact_id"],),
                )
                recorded = _ts(now)
                event_id = _id(
                    "qqhal", {"artifact": row["artifact_id"], "status": "DELETED", "at": recorded}
                )
                c.execute(
                    "INSERT OR IGNORE INTO qq_handler_artifact_lifecycle VALUES(?,?,?,?,?)",
                    (event_id, row["artifact_id"], "DELETED", reason_code, recorded),
                )
                evidence = {
                    "artifact_id": row["artifact_id"],
                    "content_sha256": row["content_sha256"],
                    "artifact_kind": row["artifact_kind"],
                    "classification": json.loads(row["record_json"])["classification"],
                    "deleted_at": recorded,
                }
                deleted.append(evidence)
                self._event(
                    c,
                    aggregate_id=case_id,
                    event_kind="QQ_PRIVATE_ARTIFACT_DELETED",
                    prior_version=None,
                    resulting_version=None,
                    correlation_id=case_id,
                    causation_id=reason_code,
                    reason_code=reason_code,
                    metadata=evidence,
                )
            c.execute("COMMIT")
        return deleted

    def case_projection(self, case_id: str) -> JsonObject:
        with self._connect() as c:
            row = c.execute("SELECT * FROM qq_handler_cases WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise QQHandlerAuthorizationDenied("handler_case_unavailable")
        return dict(row)

    def observe_event_order(
        self,
        *,
        surface: str,
        handler_binding_id: str,
        sequence: int,
        source_message_id_hash: str,
    ) -> bool:
        """Record a session-local sequence high-water; exact source replay is idempotent."""

        if surface not in {"c2c", "group"} or sequence < 1:
            raise QQHandlerEventRejected("handler_event_cursor_invalid")
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT last_sequence, last_source_message_id_hash "
                "FROM qq_handler_event_cursors WHERE surface=? AND handler_binding_id=?",
                (surface, handler_binding_id),
            ).fetchone()
            if row and row["last_source_message_id_hash"] == source_message_id_hash:
                c.execute("COMMIT")
                return False
            high_water = max(int(row["last_sequence"]), sequence) if row else sequence
            c.execute(
                "INSERT INTO qq_handler_event_cursors VALUES(?,?,?,?) "
                "ON CONFLICT(surface,handler_binding_id) DO UPDATE SET "
                "last_sequence=excluded.last_sequence, "
                "last_source_message_id_hash=excluded.last_source_message_id_hash",
                (surface, handler_binding_id, high_water, source_message_id_hash),
            )
            c.execute("COMMIT")
        return True

    def record_command_once(
        self,
        *,
        source_message_id_hash: str,
        command_id: str,
        case_id: str | None,
        classification: str,
        result: Mapping[str, Any],
    ) -> tuple[bool, JsonObject]:
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT result_json FROM qq_handler_commands WHERE source_message_id_hash=?",
                (source_message_id_hash,),
            ).fetchone()
            if existing:
                c.execute("COMMIT")
                return False, json.loads(existing[0])
            c.execute(
                "INSERT INTO qq_handler_commands VALUES(?,?,?,?,?)",
                (source_message_id_hash, command_id, case_id, classification, _json(result)),
            )
            c.execute("COMMIT")
        return True, dict(result)

    def create_candidate_and_request(
        self,
        *,
        binding: Mapping[str, Any],
        case_id: str,
        expected_version: int,
        candidate_text: str,
        source_message_id_hash: str,
        predecessor_invalidator: Callable[[sqlite3.Connection, sqlite3.Row], None] | None = None,
        candidate_finalizer: Callable[
            [
                sqlite3.Connection,
                Mapping[str, Any],
                Mapping[str, Any],
                Mapping[str, Any],
            ],
            None,
        ]
        | None = None,
    ) -> tuple[JsonObject, JsonObject, JsonObject]:
        normalized = normalize_private_content(candidate_text, candidate=True)
        candidate_hash = _hash(normalized)
        now = self._clock().astimezone(UTC)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            case = c.execute(
                "SELECT * FROM qq_handler_cases WHERE case_id=?", (case_id,)
            ).fetchone()
            if not case:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_case_unavailable")
            self._authorize_case_row(case, binding=binding, expected_version=expected_version)
            issue = c.execute(
                "SELECT record_json FROM qq_handler_artifacts WHERE artifact_id=?",
                (case["issue_artifact_id"],),
            ).fetchone()
            if not issue:
                c.execute("ROLLBACK")
                raise QQHandlerStateConflict("issue_artifact_missing")
            issue_record = json.loads(issue[0])
            if _parse(issue_record["expires_at"]) <= now:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("issue_artifact_expired")
            prior_candidate_id = case["current_candidate_revision_id"]
            prior_request_id = case["current_approval_request_id"]
            if predecessor_invalidator is not None:
                predecessor_invalidator(c, case)
            if prior_candidate_id:
                prior = c.execute(
                    "SELECT candidate_artifact_id FROM qq_handler_candidate_revisions "
                    "WHERE candidate_revision_id=?",
                    (prior_candidate_id,),
                ).fetchone()
                if prior:
                    self._schedule_artifact_deletion(
                        c, prior["candidate_artifact_id"], "candidate_superseded"
                    )
                self._event(
                    c,
                    aggregate_id=case_id,
                    event_kind="QQ_HANDLER_CANDIDATE_INVALIDATED",
                    prior_version=expected_version,
                    resulting_version=expected_version,
                    correlation_id=case_id,
                    causation_id=source_message_id_hash,
                    reason_code="candidate_replacement",
                    metadata={
                        "candidate_revision_id": prior_candidate_id,
                        "approval_request_id": prior_request_id,
                    },
                )
            new_version = expected_version + 1
            artifact_id = _id(
                "qqa",
                {
                    "kind": "response",
                    "case": case_id,
                    "version": new_version,
                    "content": candidate_hash,
                },
            )
            artifact = {
                "schema_id": QQ_HANDLER_RESPONSE_ARTIFACT_SCHEMA_ID,
                "schema_version": "v1",
                "artifact_id": artifact_id,
                "artifact_kind": "qq_handler_response",
                "tenant_id": case["tenant_id"],
                "case_id": case_id,
                "case_revision_id": case["case_revision_id"],
                "handler_binding_id": case["handler_binding_id"],
                "issue_artifact_id": case["issue_artifact_id"],
                "issue_content_sha256": issue_record["content_sha256"],
                "content_sha256": candidate_hash,
                "normalized_length": len(normalized),
                "classification": "restricted-qq-handler",
                "redaction_policy_id": "qq-handler-redaction.v1",
                "policy_decision_id": "qq-handler-deterministic-policy.v1",
                "workflow_version": new_version,
                "created_at": _ts(now),
                "expires_at": _ts(now + timedelta(seconds=QQ_HANDLER_ARTIFACT_TTL_SECONDS)),
                "deletion_status": "ACTIVE",
                "deleted_at": None,
            }
            validate_qq_handler_response_artifact(artifact, self._contract_root)
            revision_id = _id(
                "qqhcr", {"case": case_id, "version": new_version, "artifact": artifact_id}
            )
            revision = {
                "schema_id": QQ_HANDLER_CANDIDATE_REVISION_SCHEMA_ID,
                "schema_version": "v1",
                "candidate_revision_id": revision_id,
                "tenant_id": case["tenant_id"],
                "case_id": case_id,
                "case_revision_id": case["case_revision_id"],
                "handler_binding_id": case["handler_binding_id"],
                "issue_artifact_id": case["issue_artifact_id"],
                "candidate_artifact_id": artifact_id,
                "candidate_sha256": candidate_hash,
                "normalized_length": len(normalized),
                "policy_decision_id": artifact["policy_decision_id"],
                "workflow_version": new_version,
                "predecessor_candidate_revision_id": prior_candidate_id,
                "status": "CURRENT",
                "created_at": _ts(now),
            }
            validate_qq_handler_candidate_revision(revision, self._contract_root)
            request_id = _id(
                "qqhar",
                {
                    "case": case_id,
                    "version": new_version,
                    "revision": revision_id,
                    "candidate": candidate_hash,
                },
            )
            request = {
                "schema_id": QQ_HANDLER_APPROVAL_REQUEST_SCHEMA_ID,
                "schema_version": "v1",
                "approval_request_id": request_id,
                "tenant_id": case["tenant_id"],
                "case_id": case_id,
                "case_revision_id": case["case_revision_id"],
                "handler_binding_id": case["handler_binding_id"],
                "issue_artifact_id": case["issue_artifact_id"],
                "issue_content_sha256": issue_record["content_sha256"],
                "candidate_revision_id": revision_id,
                "candidate_artifact_id": artifact_id,
                "candidate_sha256": candidate_hash,
                "candidate_hash_prefix": candidate_hash[:12],
                "policy_decision_id": artifact["policy_decision_id"],
                "workflow_version": new_version,
                "status": "PENDING",
                "created_at": _ts(now),
                "expires_at": _ts(now + timedelta(minutes=10)),
            }
            validate_qq_handler_approval_chain(request, [], self._contract_root)
            c.execute(
                "INSERT INTO qq_handler_artifacts VALUES(?,?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    artifact["artifact_kind"],
                    artifact["tenant_id"],
                    case_id,
                    artifact["case_revision_id"],
                    candidate_hash,
                    artifact["expires_at"],
                    _json(artifact),
                ),
            )
            c.execute(
                "INSERT INTO qq_handler_artifact_content VALUES(?,?,1)", (artifact_id, normalized)
            )
            c.execute(
                "INSERT INTO qq_handler_candidate_revisions VALUES(?,?,?,?,?)",
                (revision_id, case_id, artifact_id, "CURRENT", _json(revision)),
            )
            c.execute(
                "INSERT INTO qq_handler_approval_requests VALUES(?,?,?,?,?)",
                (request_id, case_id, revision_id, request["expires_at"], _json(request)),
            )
            c.execute(
                "UPDATE qq_handler_cases SET workflow_version=?, status='DRAFTED', "
                "current_candidate_revision_id=?, current_approval_request_id=? WHERE case_id=?",
                (new_version, revision_id, request_id, case_id),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind="QQ_HANDLER_CANDIDATE_CREATED",
                prior_version=expected_version,
                resulting_version=new_version,
                correlation_id=case_id,
                causation_id=source_message_id_hash,
                reason_code="deterministic_candidate_verified",
                metadata={
                    "candidate_artifact_id": artifact_id,
                    "candidate_revision_id": revision_id,
                    "candidate_sha256": candidate_hash,
                    "normalized_length": len(normalized),
                    "approval_request_id": request_id,
                },
            )
            if candidate_finalizer is not None:
                candidate_finalizer(c, artifact, revision, request)
            c.execute("COMMIT")
        return artifact, revision, request

    def _authorize_case_row(
        self, case: sqlite3.Row, *, binding: Mapping[str, Any], expected_version: int
    ) -> None:
        if (
            case["tenant_id"] != binding["tenant_id"]
            or case["handler_binding_id"] != binding["handler_binding_id"]
        ):
            raise QQHandlerAuthorizationDenied("handler_case_binding_mismatch")
        if case["group_openid_hash"] != binding["group_openid_hash"]:
            raise QQHandlerAuthorizationDenied("handler_case_group_mismatch")
        if case["workflow_version"] != expected_version:
            raise QQHandlerAuthorizationDenied("handler_workflow_version_stale")
        if case["status"] in {"REJECTED", "FINAL_ACCEPTED", "TERMINAL"}:
            raise QQHandlerAuthorizationDenied("handler_case_terminal")

    def transition_simple_command(
        self,
        *,
        binding: Mapping[str, Any],
        case_id: str,
        expected_version: int,
        command: str,
        source_message_id_hash: str,
        rejection_reason_code: str | None = None,
    ) -> JsonObject:
        if command not in {"pull", "accept", "reject"}:
            raise QQHandlerStateConflict("handler_simple_command_invalid")
        if command == "reject":
            if not rejection_reason_code or not _REJECTION_REASON.fullmatch(rejection_reason_code):
                raise QQHandlerStateConflict("handler_rejection_reason_invalid")
        elif rejection_reason_code is not None:
            raise QQHandlerStateConflict("handler_rejection_reason_unexpected")
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            case = c.execute(
                "SELECT * FROM qq_handler_cases WHERE case_id=?", (case_id,)
            ).fetchone()
            if not case:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("handler_case_unavailable")
            self._authorize_case_row(case, binding=binding, expected_version=expected_version)
            new_version = expected_version if command == "pull" else expected_version + 1
            status = case["status"]
            if command == "accept":
                status = "ACCEPTED"
            elif command == "reject":
                status = "REJECTED"
                for artifact_id in c.execute(
                    "SELECT artifact_id FROM qq_handler_artifacts WHERE case_id=?", (case_id,)
                ).fetchall():
                    self._schedule_artifact_deletion(c, artifact_id[0], "handler_rejected")
            c.execute(
                "UPDATE qq_handler_cases SET workflow_version=?, status=? WHERE case_id=?",
                (new_version, status, case_id),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind=f"QQ_HANDLER_{command.upper()}",
                prior_version=expected_version,
                resulting_version=new_version,
                correlation_id=case_id,
                causation_id=source_message_id_hash,
                reason_code=f"private_{command}_accepted",
                metadata={
                    "handler_binding_id": binding["handler_binding_id"],
                    "rejection_reason_code": rejection_reason_code,
                },
            )
            c.execute("COMMIT")
        return self.case_projection(case_id)

    def approve_request(
        self,
        *,
        binding: Mapping[str, Any],
        command: QQGroupApprovalCommand,
        member_openid: str,
        group_openid: str,
        source_message_id: str,
        occurred_at: datetime,
        identity_salt: str,
    ) -> JsonObject:
        if group_openid != self._binding_group_from_stage1(binding):
            raise QQHandlerAuthorizationDenied("group_approval_foreign_group")
        author_hash = _salted_hash(identity_salt, "group-member", member_openid)
        if author_hash != binding["group_member_identity_hash"]:
            raise QQHandlerAuthorizationDenied("group_approval_foreign_member")
        now = self._clock().astimezone(UTC)
        if occurred_at.astimezone(UTC) > now:
            raise QQHandlerEventRejected("group_approval_timestamp_invalid")
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            request_row = c.execute(
                "SELECT record_json FROM qq_handler_approval_requests WHERE approval_request_id=?",
                (command.approval_request_id,),
            ).fetchone()
            if not request_row:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("group_approval_request_unavailable")
            request = json.loads(request_row[0])
            case = c.execute(
                "SELECT * FROM qq_handler_cases WHERE case_id=?", (request["case_id"],)
            ).fetchone()
            if not case:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("group_approval_case_unavailable")
            self._authorize_case_row(
                case, binding=binding, expected_version=command.expected_version
            )
            if (
                case["current_approval_request_id"] != request["approval_request_id"]
                or case["current_candidate_revision_id"] != request["candidate_revision_id"]
                or request["workflow_version"] != command.expected_version
                or _parse(request["expires_at"]) <= now
            ):
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("group_approval_stale")
            if command.candidate_hash_prefix != request["candidate_hash_prefix"] or not request[
                "candidate_sha256"
            ].startswith(command.candidate_hash_prefix):
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("group_approval_hash_mismatch_or_ambiguous")
            existing = c.execute(
                "SELECT record_json FROM qq_handler_approval_decisions WHERE approval_request_id=?",
                (request["approval_request_id"],),
            ).fetchone()
            if existing:
                c.execute("COMMIT")
                return json.loads(existing[0])
            decision_id = _id(
                "qqhad",
                {
                    "request": request["approval_request_id"],
                    "author": author_hash,
                    "source": _hash(source_message_id),
                },
            )
            decision = {
                "schema_id": QQ_HANDLER_APPROVAL_DECISION_SCHEMA_ID,
                "schema_version": "v1",
                "approval_decision_id": decision_id,
                "approval_request_id": request["approval_request_id"],
                "tenant_id": request["tenant_id"],
                "case_id": request["case_id"],
                "case_revision_id": request["case_revision_id"],
                "handler_binding_id": request["handler_binding_id"],
                "candidate_revision_id": request["candidate_revision_id"],
                "candidate_sha256": request["candidate_sha256"],
                "workflow_version": request["workflow_version"],
                "decision": "approved",
                "author_identity_hash": author_hash,
                "group_openid_hash": binding["group_openid_hash"],
                "source_message_id": source_message_id,
                "source_message_id_hash": _hash(source_message_id),
                "reason_code": "exact_metadata_approved",
                "decided_at": _ts(now),
                "expires_at": request["expires_at"],
            }
            validate_qq_handler_approval_chain(request, [decision], self._contract_root)
            c.execute(
                "INSERT INTO qq_handler_approval_decisions VALUES(?,?,?,?)",
                (decision_id, request["approval_request_id"], request["case_id"], _json(decision)),
            )
            c.execute(
                "UPDATE qq_handler_cases SET status='APPROVED' WHERE case_id=?",
                (request["case_id"],),
            )
            self._event(
                c,
                aggregate_id=request["case_id"],
                event_kind="QQ_HANDLER_GROUP_APPROVAL_DECIDED",
                prior_version=request["workflow_version"],
                resulting_version=request["workflow_version"],
                correlation_id=request["case_id"],
                causation_id=_hash(source_message_id),
                reason_code="exact_metadata_approved",
                metadata={
                    "approval_request_id": request["approval_request_id"],
                    "approval_decision_id": decision_id,
                    "candidate_sha256": request["candidate_sha256"],
                    "author_identity_hash": author_hash,
                },
            )
            c.execute("COMMIT")
        return decision

    def private_group_locator(self, handler_binding_id: str) -> str:
        with self._connect() as c:
            row = c.execute(
                "SELECT p.group_openid FROM qq_handler_pending_locators p "
                "JOIN qq_handler_bindings b ON b.pairing_session_id=p.pairing_session_id "
                "WHERE b.handler_binding_id=? LIMIT 1",
                (handler_binding_id,),
            ).fetchone()
        # Pending values are deleted after confirmation, so use Stage 1's already bounded locator.
        if row:
            return str(row[0])
        raise QQHandlerAuthorizationDenied("group_execution_locator_unavailable")

    def create_notification_intent(self, case_id: str, binding: Mapping[str, Any]) -> JsonObject:
        case = self.case_projection(case_id)
        self._assert_projection_binding(case, binding)
        natural_key = canonical_sha256(
            {
                "case": case_id,
                "binding": binding["handler_binding_id"],
                "kind": "handler-notification",
            }
        )
        intent_id = _id("qqhni", {"natural_key": natural_key})
        created = self._clock().astimezone(UTC)
        intent = {
            "schema_id": QQ_HANDLER_NOTIFICATION_INTENT_SCHEMA_ID,
            "schema_version": "v1",
            "intent_id": intent_id,
            "operation": "qq.c2c.notification.execute",
            "tenant_id": case["tenant_id"],
            "case_id": case_id,
            "case_revision_id": case["case_revision_id"],
            "handler_binding_id": binding["handler_binding_id"],
            "private_locator_id": binding["c2c_locator_id"],
            "workflow_version": case["workflow_version"],
            "template_id": "qq.handler.notification.v1",
            "case_reference": case_id,
            "natural_key": natural_key,
            "idempotency_key": stable_idempotency_key(
                tenant_id=case["tenant_id"],
                provider_id="qq-sandbox",
                operation="qq.c2c.notification.execute",
                natural_key=natural_key,
                intended_state_hash=_hash(
                    QQ_NOTIFICATION_TEMPLATE.format(
                        case_reference=case_id, version=case["workflow_version"]
                    )
                ),
            ),
            "capability_profile_hash": binding["capability_profile_hash"],
            "created_at": _ts(created),
        }
        validate_qq_handler_notification_chain(intent, [], self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT record_json FROM qq_handler_notification_intents WHERE natural_key=?",
                (natural_key,),
            ).fetchone()
            if existing:
                c.execute("COMMIT")
                return json.loads(existing[0])
            c.execute(
                "INSERT INTO qq_handler_notification_intents VALUES(?,?,?,?)",
                (intent_id, natural_key, case_id, _json(intent)),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind="QQ_HANDLER_NOTIFICATION_INTENT_CREATED",
                prior_version=case["workflow_version"],
                resulting_version=case["workflow_version"],
                correlation_id=case_id,
                causation_id=intent_id,
                reason_code="minimal_notification_intent",
                metadata={"intent_id": intent_id, "natural_key": natural_key},
            )
            c.execute("COMMIT")
        return intent

    def execute_notification(
        self,
        intent: Mapping[str, Any],
        *,
        binding: Mapping[str, Any],
        transport: QQHandlerTransport,
    ) -> JsonObject:
        validate_qq_handler_notification_chain(intent, [], self._contract_root)
        user_openid = self.private_locator(binding["handler_binding_id"], "c2c-user")
        content = QQ_NOTIFICATION_TEMPLATE.format(
            case_reference=intent["case_reference"], version=intent["workflow_version"]
        )
        if "WF-PULL" not in content or any(
            word in content.lower() for word in ("issue", "draft", "preview")
        ):
            raise QQHandlerStateConflict("notification_template_not_minimal")
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            attempt = c.execute(
                "SELECT status, result_json FROM qq_handler_notification_attempts "
                "WHERE intent_id=?",
                (intent["intent_id"],),
            ).fetchone()
            if attempt:
                if attempt["result_json"]:
                    c.execute("COMMIT")
                    return json.loads(attempt["result_json"])
                recovered = self._notification_result(
                    intent, "unknown", "ambiguous_started_attempt"
                )
                c.execute(
                    "UPDATE qq_handler_notification_attempts "
                    "SET status='UNKNOWN', result_json=? WHERE intent_id=?",
                    (_json(recovered), intent["intent_id"]),
                )
                self._event(
                    c,
                    aggregate_id=str(intent["case_id"]),
                    event_kind="QQ_HANDLER_NOTIFICATION_OUTCOME",
                    prior_version=int(intent["workflow_version"]),
                    resulting_version=int(intent["workflow_version"]),
                    correlation_id=str(intent["case_id"]),
                    causation_id=str(intent["intent_id"]),
                    reason_code="ambiguous_started_attempt",
                    metadata={
                        "intent_id": intent["intent_id"],
                        "status": "unknown",
                        "provider_accepted": False,
                    },
                )
                c.execute("COMMIT")
                return recovered
            c.execute(
                "INSERT INTO qq_handler_notification_attempts VALUES(?,?,?,NULL)",
                (intent["intent_id"], "STARTED", _ts(self._clock())),
            )
            c.execute("COMMIT")
        try:
            outcome = transport.notify_c2c(
                user_openid=user_openid,
                content=content,
                idempotency_key=str(intent["idempotency_key"]),
            )
        except (QQHandlerTransportError, TimeoutError, ConnectionError):
            outcome = QQProviderOutcome("unknown", "notification_transport_ambiguous")
        allowed = {"accepted", "rejected", "rate_limited", "timed_out", "disconnected", "unknown"}
        status = outcome.status if outcome.status in allowed else "unknown"
        result = self._notification_result(
            intent, status, outcome.reason_code, outcome.provider_status
        )
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "UPDATE qq_handler_notification_attempts SET status=?, result_json=? "
                "WHERE intent_id=? AND result_json IS NULL",
                (status.upper(), _json(result), intent["intent_id"]),
            )
            self._event(
                c,
                aggregate_id=str(intent["case_id"]),
                event_kind="QQ_HANDLER_NOTIFICATION_OUTCOME",
                prior_version=int(intent["workflow_version"]),
                resulting_version=int(intent["workflow_version"]),
                correlation_id=str(intent["case_id"]),
                causation_id=str(intent["intent_id"]),
                reason_code=str(result["reason_code"]),
                metadata={
                    "intent_id": intent["intent_id"],
                    "status": status,
                    "provider_accepted": result["provider_accepted"],
                },
            )
            c.execute("COMMIT")
        return result

    def _notification_result(
        self,
        intent: Mapping[str, Any],
        status: str,
        reason_code: str,
        provider_status: str | None = None,
    ) -> JsonObject:
        result = {
            "schema_id": QQ_HANDLER_NOTIFICATION_RESULT_SCHEMA_ID,
            "schema_version": "v1",
            "result_id": _id("qqhnr", {"intent": intent["intent_id"], "status": status}),
            "intent_id": intent["intent_id"],
            "tenant_id": intent["tenant_id"],
            "attempt_count": 1,
            "status": status,
            "provider_accepted": status == "accepted",
            "delivered": False,
            "reason_code": reason_code,
            "provider_status_hash": _hash(provider_status) if provider_status else None,
            "recorded_at": _ts(self._clock()),
        }
        validate_qq_handler_notification_chain(intent, [result], self._contract_root)
        return result

    def create_passive_intent(
        self,
        *,
        case_id: str,
        binding: Mapping[str, Any],
        source_message_id: str,
        response_kind: str,
        occurred_at: datetime,
        content_artifact_id: str | None,
        content_sha256: str,
        approval_decision_id: str | None = None,
    ) -> JsonObject:
        case = self.case_projection(case_id)
        self._assert_projection_binding(case, binding)
        if response_kind not in QQ_RESPONSE_MSG_SEQ:
            raise QQHandlerStateConflict("passive_response_kind_invalid")
        surface = "group" if response_kind in {"group-nudge", "final"} else "c2c"
        operation = (
            "qq.final_reply.execute" if surface == "group" else "qq.c2c.passive_reply.execute"
        )
        msg_seq = QQ_RESPONSE_MSG_SEQ[response_kind]
        reply_window_seconds = (
            QQ_GROUP_PASSIVE_REPLY_WINDOW_SECONDS
            if surface == "group"
            else QQ_C2C_PASSIVE_REPLY_WINDOW_SECONDS
        )
        deadline = occurred_at.astimezone(UTC) + timedelta(seconds=reply_window_seconds)
        natural_key = canonical_sha256(
            {
                "source": source_message_id,
                "msg_seq": msg_seq,
                "case": case_id,
                "binding": binding["handler_binding_id"],
                "version": case["workflow_version"],
                "response_kind": response_kind,
            }
        )
        intent = {
            "schema_id": QQ_HANDLER_PASSIVE_REPLY_INTENT_SCHEMA_ID,
            "schema_version": "v1",
            "intent_id": _id("qqhpi", {"natural_key": natural_key}),
            "operation": operation,
            "surface": surface,
            "response_kind": response_kind,
            "tenant_id": case["tenant_id"],
            "case_id": case_id,
            "case_revision_id": case["case_revision_id"],
            "handler_binding_id": binding["handler_binding_id"],
            "workflow_version": case["workflow_version"],
            "source_message_id": source_message_id,
            "source_message_id_hash": _hash(source_message_id),
            "reply_msg_seq": msg_seq,
            "content_artifact_id": content_artifact_id,
            "content_sha256": content_sha256,
            "natural_key": natural_key,
            "idempotency_key": stable_idempotency_key(
                tenant_id=case["tenant_id"],
                provider_id="qq-sandbox",
                operation=operation,
                natural_key=natural_key,
                intended_state_hash=content_sha256,
            ),
            "reply_deadline_at": _ts(deadline),
            "approval_decision_id": approval_decision_id,
            "created_at": _ts(self._clock()),
        }
        validate_qq_handler_passive_reply_chain(intent, [], self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT record_json FROM qq_handler_passive_intents WHERE natural_key=?",
                (natural_key,),
            ).fetchone()
            if existing:
                c.execute("COMMIT")
                return json.loads(existing[0])
            c.execute(
                "INSERT INTO qq_handler_passive_intents VALUES(?,?,?,?)",
                (intent["intent_id"], natural_key, case_id, _json(intent)),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind=(
                    "QQ_HANDLER_GROUP_NUDGE_INTENT_CREATED"
                    if response_kind == "group-nudge"
                    else "QQ_HANDLER_FINAL_DELIVERY_INTENT_CREATED"
                    if response_kind == "final"
                    else "QQ_HANDLER_PRIVATE_REPLY_INTENT_CREATED"
                ),
                prior_version=case["workflow_version"],
                resulting_version=case["workflow_version"],
                correlation_id=case_id,
                causation_id=_hash(source_message_id),
                reason_code="passive_reply_intent_created",
                metadata={
                    "intent_id": intent["intent_id"],
                    "response_kind": response_kind,
                    "source_message_id_hash": intent["source_message_id_hash"],
                    "reply_msg_seq": msg_seq,
                    "content_sha256": content_sha256,
                },
            )
            c.execute("COMMIT")
        return intent

    def execute_passive_reply(
        self,
        intent: Mapping[str, Any],
        *,
        binding: Mapping[str, Any],
        content: str,
        transport: QQHandlerTransport,
    ) -> JsonObject:
        validate_qq_handler_passive_reply_chain(intent, [], self._contract_root)
        if _hash(content) != intent["content_sha256"]:
            raise QQHandlerAuthorizationDenied("passive_reply_content_hash_mismatch")
        if _parse(intent["reply_deadline_at"]) <= self._clock().astimezone(UTC):
            return self._record_passive_result(intent, "expired_window", "passive_window_expired")
        with self._connect() as c:
            existing = c.execute(
                "SELECT result_json FROM qq_handler_passive_results WHERE intent_id=?",
                (intent["intent_id"],),
            ).fetchone()
        if existing:
            return json.loads(existing[0])
        if intent["surface"] == "group":
            destination = self._binding_group_from_stage1(binding)
        else:
            destination = self.private_locator(binding["handler_binding_id"], "c2c-user")
        reconciled = transport.reconcile_passive(
            surface=str(intent["surface"]),
            destination=destination,
            source_message_id=str(intent["source_message_id"]),
            msg_seq=int(intent["reply_msg_seq"]),
            idempotency_key=str(intent["idempotency_key"]),
        )
        if reconciled.status in {"accepted", "duplicate", "present"}:
            return self._record_passive_result(
                intent, "duplicate", "passive_effect_reconciled", reconciled.provider_status
            )
        try:
            if intent["response_kind"] == "group-nudge":
                outcome = transport.group_nudge(
                    group_openid=destination,
                    source_message_id=str(intent["source_message_id"]),
                    msg_seq=int(intent["reply_msg_seq"]),
                    content=content,
                    idempotency_key=str(intent["idempotency_key"]),
                )
            elif intent["surface"] == "group":
                outcome = transport.passive_group_reply(
                    group_openid=destination,
                    source_message_id=str(intent["source_message_id"]),
                    msg_seq=int(intent["reply_msg_seq"]),
                    content=content,
                    idempotency_key=str(intent["idempotency_key"]),
                )
            else:
                outcome = transport.passive_c2c_reply(
                    user_openid=destination,
                    source_message_id=str(intent["source_message_id"]),
                    msg_seq=int(intent["reply_msg_seq"]),
                    content=content,
                    idempotency_key=str(intent["idempotency_key"]),
                )
        except (QQHandlerTransportError, TimeoutError, ConnectionError):
            outcome = QQProviderOutcome("unknown", "passive_transport_ambiguous")
        allowed = {
            "accepted",
            "duplicate",
            "rejected",
            "rate_limited",
            "expired_window",
            "timed_out",
            "disconnected",
            "unknown",
        }
        status = outcome.status if outcome.status in allowed else "unknown"
        return self._record_passive_result(
            intent, status, outcome.reason_code, outcome.provider_status
        )

    def _record_passive_result(
        self,
        intent: Mapping[str, Any],
        status: str,
        reason_code: str,
        provider_status: str | None = None,
    ) -> JsonObject:
        result = {
            "schema_id": QQ_HANDLER_PASSIVE_REPLY_RESULT_SCHEMA_ID,
            "schema_version": "v1",
            "result_id": _id("qqhpr", {"intent": intent["intent_id"], "status": status}),
            "intent_id": intent["intent_id"],
            "tenant_id": intent["tenant_id"],
            "status": status,
            "provider_accepted": status in {"accepted", "duplicate"},
            "customer_receipt_verified": False,
            "issue_resolution": False,
            "case_completion": False,
            "reason_code": reason_code,
            "provider_status_hash": _hash(provider_status) if provider_status else None,
            "recorded_at": _ts(self._clock()),
        }
        validate_qq_handler_passive_reply_chain(intent, [result], self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT OR IGNORE INTO qq_handler_passive_results VALUES(?,?)",
                (intent["intent_id"], _json(result)),
            )
            self._event(
                c,
                aggregate_id=str(intent["case_id"]),
                event_kind=(
                    "QQ_HANDLER_GROUP_NUDGE_RESULT"
                    if intent["response_kind"] == "group-nudge"
                    else "QQ_HANDLER_FINAL_DELIVERY_RESULT"
                    if intent["response_kind"] == "final"
                    else "QQ_HANDLER_PRIVATE_REPLY_RESULT"
                ),
                prior_version=int(intent["workflow_version"]),
                resulting_version=int(intent["workflow_version"]),
                correlation_id=str(intent["case_id"]),
                causation_id=str(intent["intent_id"]),
                reason_code=reason_code,
                metadata={
                    "intent_id": intent["intent_id"],
                    "status": status,
                    "provider_accepted": result["provider_accepted"],
                },
            )
            if intent["response_kind"] == "final" and result["provider_accepted"]:
                c.execute(
                    "UPDATE qq_handler_cases SET status='FINAL_ACCEPTED' WHERE case_id=?",
                    (intent["case_id"],),
                )
            c.execute("COMMIT")
            stored = c.execute(
                "SELECT result_json FROM qq_handler_passive_results WHERE intent_id=?",
                (intent["intent_id"],),
            ).fetchone()
        stored_result = json.loads(stored[0]) if stored else result
        if intent["response_kind"] == "final" and stored_result["provider_accepted"]:
            self.delete_artifacts(
                str(intent["case_id"]), reason_code="final_provider_acceptance_terminal"
            )
        return stored_result

    def create_group_nudge_intent(
        self,
        *,
        case_id: str,
        binding: Mapping[str, Any],
        source_message_id: str,
        occurred_at: datetime,
    ) -> JsonObject:
        """Create one content-free, passive group fallback bound to the intake event."""

        return self.create_passive_intent(
            case_id=case_id,
            binding=binding,
            source_message_id=source_message_id,
            response_kind="group-nudge",
            occurred_at=occurred_at,
            content_artifact_id=None,
            content_sha256=_hash(QQ_GROUP_NUDGE_TEMPLATE),
        )

    def final_delivery_intent(
        self, decision: Mapping[str, Any], *, binding: Mapping[str, Any]
    ) -> tuple[JsonObject, str]:
        with self._connect() as c:
            request_row = c.execute(
                "SELECT record_json FROM qq_handler_approval_requests WHERE approval_request_id=?",
                (decision["approval_request_id"],),
            ).fetchone()
            stored_decision = c.execute(
                "SELECT record_json FROM qq_handler_approval_decisions "
                "WHERE approval_decision_id=?",
                (decision["approval_decision_id"],),
            ).fetchone()
        if (
            not request_row
            or not stored_decision
            or json.loads(stored_decision[0]) != dict(decision)
        ):
            raise QQHandlerAuthorizationDenied("final_decision_not_durable")
        request = json.loads(request_row[0])
        validate_qq_handler_approval_chain(request, [decision], self._contract_root)
        case = self.case_projection(str(decision["case_id"]))
        self._assert_projection_binding(case, binding)
        if (
            case["status"] != "APPROVED"
            or case["current_approval_request_id"] != decision["approval_request_id"]
            or case["workflow_version"] != decision["workflow_version"]
            or _parse(decision["expires_at"]) <= self._clock().astimezone(UTC)
        ):
            raise QQHandlerAuthorizationDenied("final_decision_stale")
        content = self.artifact_content(request["candidate_artifact_id"])
        intent = self.create_passive_intent(
            case_id=str(decision["case_id"]),
            binding=binding,
            source_message_id=str(decision["source_message_id"]),
            response_kind="final",
            occurred_at=_parse(decision["decided_at"]),
            content_artifact_id=str(request["candidate_artifact_id"]),
            content_sha256=str(decision["candidate_sha256"]),
            approval_decision_id=str(decision["approval_decision_id"]),
        )
        return intent, content

    def _assert_projection_binding(
        self, case: Mapping[str, Any], binding: Mapping[str, Any]
    ) -> None:
        if (
            case["tenant_id"] != binding["tenant_id"]
            or case["handler_binding_id"] != binding["handler_binding_id"]
            or case["group_openid_hash"] != binding["group_openid_hash"]
        ):
            raise QQHandlerAuthorizationDenied("handler_case_binding_mismatch")

    def _binding_group_from_stage1(self, binding: Mapping[str, Any]) -> str:
        # The Stage 1 resolver stores the raw group in qq_pairing_locators; it never enters reports.
        with self._connect() as c:
            row = c.execute(
                "SELECT group_openid, expires_at, status FROM qq_pairing_locators "
                "WHERE pairing_id=?",
                (binding["stage1_pairing_id"],),
            ).fetchone()
        if (
            not row
            or row["status"] != "COMPLETED"
            or _parse(row["expires_at"]) <= self._clock().astimezone(UTC)
        ):
            raise QQHandlerAuthorizationDenied("stage1_group_locator_inactive")
        if _hash(str(row["group_openid"])) != binding["group_openid_hash"]:
            raise QQHandlerAuthorizationDenied("stage1_group_locator_mismatch")
        return str(row["group_openid"])

    def safe_counts(self) -> JsonObject:
        with self._connect() as c:
            return {
                "binding_count": c.execute("SELECT COUNT(*) FROM qq_handler_bindings").fetchone()[
                    0
                ],
                "notification_attempt_count": c.execute(
                    "SELECT COUNT(*) FROM qq_handler_notification_attempts"
                ).fetchone()[0],
                "private_command_count": c.execute(
                    "SELECT COUNT(*) FROM qq_handler_commands"
                ).fetchone()[0],
                "approval_decision_count": c.execute(
                    "SELECT COUNT(*) FROM qq_handler_approval_decisions"
                ).fetchone()[0],
                "passive_result_count": c.execute(
                    "SELECT COUNT(*) FROM qq_handler_passive_results"
                ).fetchone()[0],
                "deletion_count": c.execute(
                    "SELECT COUNT(*) FROM qq_handler_artifact_lifecycle WHERE status='DELETED'"
                ).fetchone()[0],
            }

    def notification_attempt_count(self, case_id: str, handler_binding_id: str) -> int:
        """Count only attempts belonging to one acceptance Case and binding."""
        with self._connect() as c:
            rows = c.execute(
                "SELECT i.record_json FROM qq_handler_notification_intents i "
                "JOIN qq_handler_notification_attempts a ON a.intent_id=i.intent_id "
                "WHERE i.case_id=?",
                (case_id,),
            ).fetchall()
        return sum(
            1
            for row in rows
            if json.loads(row["record_json"]).get("handler_binding_id") == handler_binding_id
        )

    def deleted_artifact_count(self, case_id: str) -> int:
        """Count distinct deleted artifacts for one acceptance Case."""
        with self._connect() as c:
            return int(
                c.execute(
                    "SELECT COUNT(DISTINCT l.artifact_id) "
                    "FROM qq_handler_artifact_lifecycle l "
                    "JOIN qq_handler_artifacts a ON a.artifact_id=l.artifact_id "
                    "WHERE a.case_id=? AND l.status='DELETED'",
                    (case_id,),
                ).fetchone()[0]
            )

    def build_acceptance_report(
        self,
        *,
        config: QQHandlerConfig,
        binding: Mapping[str, Any] | None,
        mode: str,
        case_id: str | None = None,
        notification_status: str = "not_attempted",
        private_workflow_verified: bool = False,
        group_approval_verified: bool = False,
        final_provider_accepted: bool = False,
        recovery_state: str = "not_required",
        duplicate_event_count: int = 0,
        rejected_event_count: int = 0,
        artifact_deletion_verified: bool = False,
        network_contacted: bool = False,
        external_write_attempted: bool = False,
    ) -> JsonObject:
        notification_attempt_count = (
            self.notification_attempt_count(case_id, str(binding["handler_binding_id"]))
            if case_id is not None and binding is not None
            else 0
        )
        report = {
            "schema_id": QQ_HANDLER_ACCEPTANCE_REPORT_SCHEMA_ID,
            "schema_version": "v1",
            "report_type": "weflow-qq-handler-acceptance.v1",
            "report_id": _id(
                "qqharp",
                {
                    "mode": mode,
                    "app": config.app_id_hash,
                    "binding": binding["handler_binding_id"] if binding else None,
                    "case": case_id,
                    "notification_attempt_count": notification_attempt_count,
                    "final_provider_accepted": final_provider_accepted,
                },
            ),
            "report_sha256": "0" * 64,
            "mode": mode,
            "app_id_hash": config.app_id_hash,
            "tenant_id_hash": config.tenant_id_hash,
            "group_openid_hash": config.group_openid_hash,
            "handler_binding_id": binding["handler_binding_id"] if binding else None,
            "assurance_level": binding["assurance_level"] if binding else None,
            "dual_surface_binding_verified": binding is not None,
            "notification_status": notification_status,
            "notification_attempt_count": notification_attempt_count,
            "private_workflow_verified": private_workflow_verified,
            "group_approval_verified": group_approval_verified,
            "final_provider_accepted": final_provider_accepted,
            "recovery_state": recovery_state,
            "duplicate_event_count": duplicate_event_count,
            "rejected_event_count": rejected_event_count,
            "artifact_deletion_verified": artifact_deletion_verified,
            "network_contacted": network_contacted,
            "external_write_attempted": external_write_attempted,
            "model_invocation": False,
            "customer_receipt_verified": False,
            "issue_resolution": False,
            "case_completion": False,
            "production_ready": False,
        }
        report["report_sha256"] = qq_handler_acceptance_report_sha256(report)
        validate_qq_handler_acceptance_report(report, self._contract_root)
        return report


__all__ = [
    "QQ_GROUP_NUDGE_TEMPLATE",
    "QQ_HANDLER_REQUIRED_CAPABILITIES",
    "QQ_HANDLER_CHALLENGE_TTL_SECONDS",
    "QQ_NOTIFICATION_TEMPLATE",
    "QQHandlerActivationDenied",
    "QQ_HANDLER_REVOCATION_CONFIRMATION",
    "QQHandlerAuthorizationDenied",
    "QQHandlerConfig",
    "QQHandlerError",
    "QQHandlerEventRejected",
    "QQHandlerPairingChallenge",
    "QQHandlerPairingObservation",
    "QQHandlerPairingSession",
    "QQHandlerStateConflict",
    "QQHandlerTransport",
    "QQHandlerTransportError",
    "QQPrivateCommand",
    "QQGroupApprovalCommand",
    "QQProviderOutcome",
    "SQLiteQQHandlerJournal",
    "begin_handler_pairing",
    "normalize_handler_pairing_event",
    "is_safe_provider_message_id",
    "normalize_private_content",
    "parse_group_approval",
    "parse_private_command",
    "reject_handler_configuration_for_other_commands",
]
