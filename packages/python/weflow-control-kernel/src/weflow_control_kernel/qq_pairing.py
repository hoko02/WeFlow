"""Read-only, command-local secure first QQ sandbox group pairing boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from weflow_contracts.qq import canonical_sha256
from weflow_contracts.qq_pairing import (
    QQ_GROUP_PAIRING_ACCEPTANCE_REPORT_SCHEMA_ID,
    QQ_GROUP_PAIRING_CHALLENGE_SCHEMA_ID,
    QQ_GROUP_PAIRING_COMPLETION_SCHEMA_ID,
    qq_group_pairing_report_sha256,
    validate_qq_group_pairing_acceptance_report,
    validate_qq_group_pairing_challenge,
    validate_qq_group_pairing_completion,
)

JsonObject = dict[str, Any]
Clock = Callable[[], datetime]
TokenFactory = Callable[[], str]

QQ_PAIRING_CAPABILITIES = ("qq.group_pair.read",)
QQ_PAIRING_CHALLENGE_PREFIX = "WFPAIR-"
QQ_PAIRING_DEADLINE_SECONDS = 300
QQ_PAIRING_LOCATOR_TTL_SECONDS = 86_400
QQ_PAIRING_ENVIRONMENT_KEYS = frozenset(
    {
        "WEFLOW_QQ_APP_ID",
        "WEFLOW_QQ_CLIENT_SECRET",
        "WEFLOW_QQ_TENANT_ID",
        "WEFLOW_QQ_CAPABILITIES",
        "WEFLOW_QQ_PAIRING_ACTIVE",
    }
)
_FORBIDDEN_PAIRING_KEYS = frozenset(
    {
        "WEFLOW_QQ_SANDBOX_GROUP_OPENID",
        "WEFLOW_QQ_SANDBOX_PAIRING_ID",
        "WEFLOW_QQ_IDENTITY_SALT",
        "WEFLOW_LIVE_MODEL_API_KEY",
        "WEFLOW_MULTI_AGENT_ENABLED",
    }
)
_MESSAGE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_MENTION = re.compile(r"^\s*(?:@机器人|<@!?[A-Za-z0-9._:-]+>)\s*")


class QQPairingError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class QQPairingActivationDenied(QQPairingError):
    pass


class QQPairingEventRejected(QQPairingError):
    pass


class QQPairingJournalError(QQPairingError):
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


def _parse(value: object) -> datetime:
    if not isinstance(value, str):
        raise QQPairingEventRejected("pairing_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QQPairingEventRejected("pairing_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise QQPairingEventRejected("pairing_timestamp_invalid")
    return parsed.astimezone(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _id(prefix: str, value: Mapping[str, Any]) -> str:
    return f"{prefix}_{canonical_sha256(value)[:32]}"


@dataclass(frozen=True)
class QQGroupPairingConfig:
    app_id: str
    client_secret: str
    tenant_id: str
    store_path: Path
    repository_root: Path
    capabilities: tuple[str, ...] = QQ_PAIRING_CAPABILITIES
    environment: str = "sandbox"

    @classmethod
    def from_environment(
        cls,
        *,
        confirm_live_pairing: bool,
        store_path: str | Path,
        repository_root: str | Path,
        environ: Mapping[str, str] | None = None,
        model_enabled: bool = False,
        external_write_enabled: bool = False,
        multi_agent_enabled: bool = False,
    ) -> QQGroupPairingConfig:
        if not confirm_live_pairing:
            raise QQPairingActivationDenied("pairing_explicit_confirmation_required")
        source = os.environ if environ is None else environ
        if (
            model_enabled
            or external_write_enabled
            or multi_agent_enabled
            or any(source.get(key) for key in _FORBIDDEN_PAIRING_KEYS)
        ):
            raise QQPairingActivationDenied("pairing_scope_denied")
        required = {
            key: source.get(key)
            for key in ("WEFLOW_QQ_APP_ID", "WEFLOW_QQ_CLIENT_SECRET", "WEFLOW_QQ_TENANT_ID")
        }
        if any(not isinstance(value, str) or not value.strip() for value in required.values()):
            raise QQPairingActivationDenied("pairing_configuration_missing")
        capability_text = source.get("WEFLOW_QQ_CAPABILITIES", "qq.group_pair.read")
        capabilities = tuple(part.strip() for part in capability_text.split(","))
        if capabilities != QQ_PAIRING_CAPABILITIES:
            raise QQPairingActivationDenied("pairing_capability_scope_denied")
        root = Path(repository_root).resolve()
        store = (
            (root / store_path).resolve()
            if not Path(store_path).is_absolute()
            else Path(store_path).resolve()
        )
        try:
            store.relative_to(root)
        except ValueError as error:
            raise QQPairingActivationDenied("pairing_store_outside_repository") from error
        if store.name != "qq-sandbox.sqlite3" or store.parent.name != ".weflow":
            raise QQPairingActivationDenied("pairing_store_not_bounded")
        return cls(
            str(required["WEFLOW_QQ_APP_ID"]),
            str(required["WEFLOW_QQ_CLIENT_SECRET"]),
            str(required["WEFLOW_QQ_TENANT_ID"]),
            store,
            root,
            capabilities,
        )

    @property
    def app_id_hash(self) -> str:
        return _hash(self.app_id)

    @property
    def tenant_id_hash(self) -> str:
        return _hash(self.tenant_id)

    @property
    def capability_profile_hash(self) -> str:
        return _hash("|".join(self.capabilities))

    def safe_readiness(self) -> JsonObject:
        return {
            "mode": "qq-sandbox-pair-group",
            "environment": self.environment,
            "app_id_hash": self.app_id_hash,
            "tenant_id_hash": self.tenant_id_hash,
            "capability_profile_hash": self.capability_profile_hash,
            "read_only": True,
            "qq_write_enabled": False,
            "case_enabled": False,
            "workflow_enabled": False,
            "model_enabled": False,
            "ready": True,
        }


def reject_pairing_configuration_for_ordinary_command(environ: Mapping[str, str]) -> None:
    if (
        environ.get("WEFLOW_QQ_PAIRING_ACTIVE")
        or environ.get("WEFLOW_QQ_SANDBOX_PAIRING_ID")
        or environ.get("WEFLOW_QQ_CAPABILITIES") == "qq.group_pair.read"
    ):
        raise QQPairingActivationDenied("pairing_configuration_forbidden_for_command")


@dataclass(frozen=True)
class QQPairingChallenge:
    plaintext: str
    record: JsonObject


def create_pairing_challenge(
    config: QQGroupPairingConfig,
    *,
    clock: Clock = _now,
    token_factory: TokenFactory | None = None,
    contract_root: Path | None = None,
) -> QQPairingChallenge:
    token = (token_factory or (lambda: secrets.token_urlsafe(24)))()
    if len(token.encode()) < 22:
        raise QQPairingActivationDenied("pairing_challenge_entropy_insufficient")
    plaintext = f"{QQ_PAIRING_CHALLENGE_PREFIX}{token}"
    created = clock().astimezone(UTC)
    digest = _hash(plaintext)
    record = {
        "schema_id": QQ_GROUP_PAIRING_CHALLENGE_SCHEMA_ID,
        "schema_version": "v1",
        "challenge_id": _id(
            "qqpc",
            {
                "app": config.app_id_hash,
                "tenant": config.tenant_id_hash,
                "digest": digest,
                "created": _ts(created),
            },
        ),
        "challenge_sha256": digest,
        "app_id_hash": config.app_id_hash,
        "tenant_id": config.tenant_id,
        "tenant_id_hash": config.tenant_id_hash,
        "capability_profile_hash": config.capability_profile_hash,
        "created_at": _ts(created),
        "deadline_at": _ts(created + timedelta(seconds=QQ_PAIRING_DEADLINE_SECONDS)),
        "status": "PENDING",
    }
    validate_qq_group_pairing_challenge(record, contract_root)
    return QQPairingChallenge(plaintext, record)


def normalize_pairing_event(
    raw_event: Mapping[str, Any], *, expected_plaintext: str, now: datetime, deadline_at: str
) -> JsonObject:
    if raw_event.get("t") != "GROUP_AT_MESSAGE_CREATE":
        raise QQPairingEventRejected("pairing_event_type_unsupported")
    sequence = raw_event.get("s")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise QQPairingEventRejected("pairing_sequence_invalid")
    data = raw_event.get("d")
    if not isinstance(data, Mapping):
        raise QQPairingEventRejected("pairing_event_shape_invalid")
    if (
        data.get("attachments") not in (None, [])
        or data.get("ark_data") not in (None, {})
        or data.get("msg_elements") not in (None, [])
    ):
        raise QQPairingEventRejected("pairing_plain_text_required")
    if data.get("message_type", 0) != 0:
        raise QQPairingEventRejected("pairing_plain_text_required")
    group = data.get("group_openid")
    message = data.get("id")
    author = data.get("author")
    member = author.get("member_openid") if isinstance(author, Mapping) else None
    if not isinstance(group, str) or not group:
        raise QQPairingEventRejected("pairing_group_identity_invalid")
    if not isinstance(message, str) or not _MESSAGE_ID.fullmatch(message):
        raise QQPairingEventRejected("pairing_message_identity_invalid")
    if not isinstance(member, str) or not member:
        raise QQPairingEventRejected("pairing_member_identity_invalid")
    content = data.get("content")
    if not isinstance(content, str):
        raise QQPairingEventRejected("pairing_plain_text_required")
    normalized = " ".join(_MENTION.sub("", content, count=1).strip().split())
    if normalized != expected_plaintext:
        raise QQPairingEventRejected("pairing_challenge_mismatch")
    if now.astimezone(UTC) > _parse(deadline_at):
        raise QQPairingEventRejected("pairing_challenge_expired")
    occurred = _parse(data.get("timestamp"))
    if occurred > now.astimezone(UTC):
        raise QQPairingEventRejected("pairing_timestamp_invalid")
    return {
        "group_openid": group,
        "group_openid_hash": _hash(group),
        "source_message_id_hash": _hash(message),
        "gateway_sequence": sequence,
        "occurred_at": _ts(occurred),
    }


class SQLiteQQPairingJournal:
    def __init__(
        self, path: str | Path, *, clock: Clock = _now, contract_root: Path | None = None
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
                CREATE TABLE IF NOT EXISTS qq_pairing_challenges(
                    challenge_id TEXT PRIMARY KEY, app_id_hash TEXT NOT NULL,
                    tenant_id_hash TEXT NOT NULL, challenge_sha256 TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_pairing_lifecycle(
                    event_id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL, pairing_id TEXT,
                    status TEXT NOT NULL, reason_code TEXT NOT NULL, recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_pairing_completions(
                    completion_id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL UNIQUE,
                    pairing_id TEXT NOT NULL, app_id_hash TEXT NOT NULL,
                    tenant_id_hash TEXT NOT NULL, group_openid_hash TEXT NOT NULL,
                    source_message_id_hash TEXT NOT NULL, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_pairing_locators(
                    pairing_id TEXT PRIMARY KEY, app_id_hash TEXT NOT NULL,
                    tenant_id TEXT NOT NULL, tenant_id_hash TEXT NOT NULL,
                    group_openid TEXT NOT NULL, group_openid_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_pairing_cursors(
                    app_id_hash TEXT NOT NULL, tenant_id_hash TEXT NOT NULL,
                    session_id_hash TEXT NOT NULL, sequence INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(app_id_hash, tenant_id_hash, session_id_hash)
                );
                CREATE TRIGGER IF NOT EXISTS qq_pair_challenge_no_update
                BEFORE UPDATE ON qq_pairing_challenges
                BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_pair_challenge_no_delete
                BEFORE DELETE ON qq_pairing_challenges
                BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_pair_lifecycle_no_update
                BEFORE UPDATE ON qq_pairing_lifecycle
                BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_pair_lifecycle_no_delete
                BEFORE DELETE ON qq_pairing_lifecycle
                BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_pair_completion_no_update
                BEFORE UPDATE ON qq_pairing_completions
                BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_pair_completion_no_delete
                BEFORE DELETE ON qq_pairing_completions
                BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                """
            )

    def _lifecycle(
        self,
        c: sqlite3.Connection,
        challenge_id: str,
        status: str,
        reason: str,
        pairing_id: str | None = None,
    ) -> None:
        recorded = _ts(self._clock())
        event_id = _id(
            "qqple",
            {
                "challenge": challenge_id,
                "pairing": pairing_id,
                "status": status,
                "reason": reason,
                "at": recorded,
            },
        )
        c.execute(
            "INSERT OR IGNORE INTO qq_pairing_lifecycle VALUES(?,?,?,?,?,?)",
            (event_id, challenge_id, pairing_id, status, reason, recorded),
        )

    def record_challenge(self, record: Mapping[str, Any]) -> None:
        validate_qq_group_pairing_challenge(record, self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            rows = c.execute(
                "SELECT challenge_id FROM qq_pairing_challenges WHERE app_id_hash=? "
                "AND tenant_id_hash=?",
                (record["app_id_hash"], record["tenant_id_hash"]),
            ).fetchall()
            for row in rows:
                status = c.execute(
                    "SELECT status FROM qq_pairing_lifecycle WHERE challenge_id=? "
                    "ORDER BY rowid DESC LIMIT 1",
                    (row[0],),
                ).fetchone()
                if status and status[0] == "PENDING":
                    self._lifecycle(c, row[0], "CANCELLED", "pairing_restart_new_challenge")
            c.execute(
                "INSERT INTO qq_pairing_challenges VALUES(?,?,?,?,?)",
                (
                    record["challenge_id"],
                    record["app_id_hash"],
                    record["tenant_id_hash"],
                    record["challenge_sha256"],
                    json.dumps(dict(record), sort_keys=True, separators=(",", ":")),
                ),
            )
            self._lifecycle(c, str(record["challenge_id"]), "PENDING", "pairing_challenge_created")
            c.execute("COMMIT")

    def complete(
        self,
        challenge: Mapping[str, Any],
        observed: Mapping[str, Any],
        *,
        session_id: str | None = None,
    ) -> JsonObject:
        now = self._clock().astimezone(UTC)
        group_hash = str(observed["group_openid_hash"])
        source_hash = str(observed["source_message_id_hash"])
        pairing_id = _id(
            "qqpair",
            {
                "challenge": challenge["challenge_sha256"],
                "app": challenge["app_id_hash"],
                "tenant": challenge["tenant_id_hash"],
                "group": group_hash,
                "source": source_hash,
            },
        )
        completion = {
            "schema_id": QQ_GROUP_PAIRING_COMPLETION_SCHEMA_ID,
            "schema_version": "v1",
            "completion_id": _id(
                "qqpcmp", {"pairing": pairing_id, "challenge": challenge["challenge_id"]}
            ),
            "challenge_id": challenge["challenge_id"],
            "pairing_id": pairing_id,
            "tenant_id": challenge["tenant_id"],
            "tenant_id_hash": challenge["tenant_id_hash"],
            "app_id_hash": challenge["app_id_hash"],
            "group_openid_hash": group_hash,
            "source_message_id_hash": source_hash,
            "session_id_hash": _hash(session_id) if session_id else None,
            "gateway_sequence": observed["gateway_sequence"],
            "status": "COMPLETED",
            "reason_code": "pairing_exact_challenge_completed",
            "completed_at": _ts(now),
            "expires_at": _ts(now + timedelta(seconds=QQ_PAIRING_LOCATOR_TTL_SECONDS)),
        }
        validate_qq_group_pairing_completion(completion, self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT record_json FROM qq_pairing_completions WHERE challenge_id=?",
                (challenge["challenge_id"],),
            ).fetchone()
            if existing:
                prior = json.loads(existing[0])
                c.execute("COMMIT")
                if (
                    prior["group_openid_hash"] == group_hash
                    and prior["source_message_id_hash"] == source_hash
                ):
                    return prior
                with self._connect() as conflict:
                    self._lifecycle(
                        conflict,
                        str(challenge["challenge_id"]),
                        "CONFLICT",
                        "pairing_different_group_conflict",
                        str(prior["pairing_id"]),
                    )
                raise QQPairingJournalError("pairing_different_group_conflict")
            current = c.execute(
                "SELECT pairing_id FROM qq_pairing_locators WHERE app_id_hash=? "
                "AND tenant_id_hash=? AND status='COMPLETED' AND expires_at>?",
                (challenge["app_id_hash"], challenge["tenant_id_hash"], _ts(now)),
            ).fetchone()
            if current and current[0] != pairing_id:
                self._lifecycle(
                    c,
                    str(challenge["challenge_id"]),
                    "CONFLICT",
                    "pairing_current_binding_conflict",
                )
                c.execute("COMMIT")
                raise QQPairingJournalError("pairing_current_binding_conflict")
            c.execute(
                "INSERT INTO qq_pairing_completions VALUES(?,?,?,?,?,?,?,?)",
                (
                    completion["completion_id"],
                    completion["challenge_id"],
                    pairing_id,
                    completion["app_id_hash"],
                    completion["tenant_id_hash"],
                    group_hash,
                    source_hash,
                    json.dumps(completion, sort_keys=True, separators=(",", ":")),
                ),
            )
            c.execute(
                "INSERT INTO qq_pairing_locators VALUES(?,?,?,?,?,?,?,?)",
                (
                    pairing_id,
                    completion["app_id_hash"],
                    completion["tenant_id"],
                    completion["tenant_id_hash"],
                    observed["group_openid"],
                    group_hash,
                    completion["expires_at"],
                    "COMPLETED",
                ),
            )
            self._lifecycle(
                c,
                str(challenge["challenge_id"]),
                "COMPLETED",
                "pairing_exact_challenge_completed",
                pairing_id,
            )
            c.execute("COMMIT")
        return completion

    def expire_challenge(self, challenge_id: str) -> None:
        """Append one safe terminal event when a pending challenge reaches its deadline."""
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT status FROM qq_pairing_lifecycle WHERE challenge_id=? "
                "ORDER BY rowid DESC LIMIT 1",
                (challenge_id,),
            ).fetchone()
            if row is None:
                c.execute("ROLLBACK")
                raise QQPairingJournalError("pairing_challenge_missing")
            if row[0] == "EXPIRED":
                c.execute("COMMIT")
                return
            if row[0] != "PENDING":
                c.execute("ROLLBACK")
                raise QQPairingJournalError("pairing_challenge_not_pending")
            self._lifecycle(c, challenge_id, "EXPIRED", "pairing_challenge_expired")
            c.execute("COMMIT")

    def resolve(self, pairing_id: str, *, app_id_hash: str) -> JsonObject:
        self.purge_expired()
        try:
            with self._connect() as c:
                row = c.execute(
                    "SELECT * FROM qq_pairing_locators WHERE pairing_id=?", (pairing_id,)
                ).fetchone()
        except sqlite3.DatabaseError as error:
            raise QQPairingJournalError("pairing_locator_unreadable") from error
        if row is None:
            raise QQPairingJournalError("pairing_locator_missing")
        if row["app_id_hash"] != app_id_hash:
            raise QQPairingJournalError("pairing_application_mismatch")
        if row["status"] != "COMPLETED":
            raise QQPairingJournalError("pairing_locator_not_current")
        return {
            "pairing_id": pairing_id,
            "tenant_id": row["tenant_id"],
            "tenant_id_hash": row["tenant_id_hash"],
            "group_openid": row["group_openid"],
            "group_openid_hash": row["group_openid_hash"],
            "app_id_hash": row["app_id_hash"],
            "expires_at": row["expires_at"],
        }

    def revoke(self, pairing_id: str) -> None:
        with self._connect() as c:
            row = c.execute(
                "SELECT challenge_id FROM qq_pairing_completions WHERE pairing_id=?", (pairing_id,)
            ).fetchone()
            changed = c.execute(
                "UPDATE qq_pairing_locators SET status='REVOKED' "
                "WHERE pairing_id=? AND status='COMPLETED'",
                (pairing_id,),
            ).rowcount
            if not changed or row is None:
                raise QQPairingJournalError("pairing_locator_not_current")
            self._lifecycle(c, row[0], "REVOKED", "pairing_locally_revoked", pairing_id)

    def purge_expired(self) -> int:
        cutoff = _ts(self._clock())
        with self._connect() as c:
            rows = c.execute(
                "SELECT pairing_id FROM qq_pairing_locators WHERE expires_at<=? "
                "AND status='COMPLETED'",
                (cutoff,),
            ).fetchall()
            for row in rows:
                c.execute(
                    "UPDATE qq_pairing_locators SET group_openid='',status='EXPIRED' "
                    "WHERE pairing_id=?",
                    (row[0],),
                )
            return len(rows)

    def record_sequence(self, config: QQGroupPairingConfig, session_id: str, sequence: int) -> None:
        key = (config.app_id_hash, config.tenant_id_hash, _hash(session_id))
        now = _ts(self._clock())
        with self._connect() as c:
            row = c.execute(
                "SELECT sequence FROM qq_pairing_cursors WHERE app_id_hash=? "
                "AND tenant_id_hash=? AND session_id_hash=?",
                key,
            ).fetchone()
            if row and sequence > row[0] + 1:
                raise QQPairingJournalError("pairing_sequence_gap")
            if row and sequence < row[0]:
                raise QQPairingJournalError("pairing_sequence_out_of_order")
            c.execute(
                "INSERT INTO qq_pairing_cursors VALUES(?,?,?,?,?) "
                "ON CONFLICT(app_id_hash,tenant_id_hash,session_id_hash) "
                "DO UPDATE SET sequence=excluded.sequence,updated_at=excluded.updated_at",
                (*key, sequence, now),
            )

    def safe_counts(self) -> JsonObject:
        with self._connect() as c:
            return {
                "challenge_count": c.execute(
                    "SELECT COUNT(*) FROM qq_pairing_challenges"
                ).fetchone()[0],
                "completion_count": c.execute(
                    "SELECT COUNT(*) FROM qq_pairing_completions"
                ).fetchone()[0],
                "current_locator_count": c.execute(
                    "SELECT COUNT(*) FROM qq_pairing_locators WHERE status='COMPLETED'"
                ).fetchone()[0],
            }


class QQGroupPairingController:
    def __init__(
        self,
        config: QQGroupPairingConfig,
        journal: SQLiteQQPairingJournal,
        challenge: QQPairingChallenge,
        *,
        clock: Clock = _now,
    ) -> None:
        self.config = config
        self.journal = journal
        self.challenge = challenge
        self.clock = clock
        self.journal.record_challenge(challenge.record)

    def accept(self, raw_event: Mapping[str, Any], *, session_id: str | None = None) -> JsonObject:
        observed = normalize_pairing_event(
            raw_event,
            expected_plaintext=self.challenge.plaintext,
            now=self.clock(),
            deadline_at=str(self.challenge.record["deadline_at"]),
        )
        if session_id:
            self.journal.record_sequence(self.config, session_id, int(observed["gateway_sequence"]))
        return self.journal.complete(self.challenge.record, observed, session_id=session_id)

    def remaining_deadline_seconds(self) -> float:
        deadline = _parse(self.challenge.record["deadline_at"])
        return (deadline - self.clock().astimezone(UTC)).total_seconds()

    def expire(self) -> None:
        self.journal.expire_challenge(str(self.challenge.record["challenge_id"]))


def build_pairing_report(
    completion: Mapping[str, Any] | None,
    *,
    mode: str,
    observed: int,
    rejected: int,
    duplicates: int = 0,
    reason_code: str = "pairing_not_completed",
    contract_root: Path | None = None,
) -> JsonObject:
    completed = completion is not None and completion.get("status") == "COMPLETED"
    material: JsonObject = {
        "schema_id": QQ_GROUP_PAIRING_ACCEPTANCE_REPORT_SCHEMA_ID,
        "schema_version": "v1",
        "report_id": _id(
            "qqpr",
            {
                "mode": mode,
                "pairing": completion.get("pairing_id") if completion else None,
                "observed": observed,
                "rejected": rejected,
            },
        ),
        "mode": mode,
        "accepted": completed,
        "fake_pairing_verified": mode == "offline-fake" and completed,
        "qq_group_pairing_live_verified": mode == "qq-sandbox-live" and completed,
        "pairing_id": completion.get("pairing_id") if completion else None,
        "app_id_hash": completion.get("app_id_hash") if completion else None,
        "group_openid_hash": completion.get("group_openid_hash") if completion else None,
        "tenant_id_hash": completion.get("tenant_id_hash") if completion else None,
        "completion_status": completion.get("status", "NOT_COMPLETED")
        if completion
        else "NOT_COMPLETED",
        "reason_code": completion.get("reason_code", reason_code) if completion else reason_code,
        "observed_event_count": observed,
        "rejected_event_count": rejected,
        "duplicate_event_count": duplicates,
        "case_creation": False,
        "workflow_activation": False,
        "qq_write_attempted": False,
        "acknowledgement_sent": False,
        "model_invocation": False,
        "handler_binding": False,
        "customer_receipt_verified": False,
        "issue_resolution": False,
        "case_completion": False,
        "production_ready": False,
        "stage1_verified": False,
        "network_required": mode == "qq-sandbox-live",
        "credentials_required": mode == "qq-sandbox-live",
        "privacy": {
            "challenge_plaintext_persisted": False,
            "raw_group_in_report": False,
            "member_identity_persisted": False,
            "provider_event_persisted": False,
            "credential_persisted": False,
        },
    }
    material["report_sha256"] = qq_group_pairing_report_sha256(material)
    validate_qq_group_pairing_acceptance_report(material, contract_root)
    return material


def verify_pairing_report(
    report: Mapping[str, Any], *, expected_mode: str, contract_root: Path | None = None
) -> None:
    forbidden = {
        "group_openid",
        "member_openid",
        "client_secret",
        "access_token",
        "challenge_plaintext",
        "raw_event",
        "message_id",
    }

    def walk(value: object) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).lower() in forbidden:
                    raise QQPairingError("pairing_report_unsafe_key")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and value.startswith(QQ_PAIRING_CHALLENGE_PREFIX):
            raise QQPairingError("pairing_report_challenge_leak")

    walk(report)
    validate_qq_group_pairing_acceptance_report(report, contract_root)
    if report.get("mode") != expected_mode:
        raise QQPairingError("pairing_report_mode_mismatch")


def resolve_stage1_pairing_environment(
    environ: Mapping[str, str],
    *,
    store_path: str | Path,
    clock: Clock | None = None,
) -> dict[str, str]:
    """Resolve exactly one direct or safe-pairing selector before Stage 1 construction."""
    values = dict(environ)
    direct = values.get("WEFLOW_QQ_SANDBOX_GROUP_OPENID")
    pairing_id = values.get("WEFLOW_QQ_SANDBOX_PAIRING_ID")
    if direct and pairing_id:
        raise QQPairingActivationDenied("qq_selector_modes_conflict")
    if not pairing_id:
        return values
    if values.get("WEFLOW_QQ_TENANT_ID"):
        raise QQPairingActivationDenied("pairing_tenant_override_forbidden")
    app_id = values.get("WEFLOW_QQ_APP_ID")
    if not app_id:
        raise QQPairingActivationDenied("qq_configuration_missing")
    effective_clock = clock if clock is not None else _now
    binding = SQLiteQQPairingJournal(store_path, clock=effective_clock).resolve(
        pairing_id, app_id_hash=_hash(app_id)
    )
    values["WEFLOW_QQ_SANDBOX_GROUP_OPENID"] = str(binding["group_openid"])
    values["WEFLOW_QQ_TENANT_ID"] = str(binding["tenant_id"])
    return values


__all__ = [
    name
    for name in globals()
    if name.startswith("QQ")
    or name.startswith("build_pairing")
    or name.startswith("create_pairing")
    or name.startswith("normalize_pairing")
    or name.startswith("reject_pairing")
    or name.startswith("verify_pairing")
]
