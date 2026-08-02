"""Deterministic offline Case ledger for synthetic IM intake."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from weflow_contracts import (
    BUSINESS_EVENT_SCHEMA_ID,
    CASE_PROJECTION_SCHEMA_ID,
    ContractValidationError,
    validate_case_projection,
    validate_generated_ledger_event,
    validate_inbound_message_event,
    validate_payload,
    validate_revision_chain,
    validate_tenant_reference,
)

from .workflow_journal_schema import (
    WorkflowJournalSchemaError,
    initialize_workflow_journal_schema,
    validate_workflow_journal_schema,
)
from .workflow_state import WorkflowTransitionError, validate_transition

CASE_SCHEMA_ID = "https://weflow.local/contracts/v1/case.schema.json"
CASE_REVISION_SCHEMA_ID = "https://weflow.local/contracts/v1/case-revision.schema.json"
INITIAL_CASE_STATE = "RECEIVED"
INITIAL_EVENT_TYPES = (
    "inbound.received.v1",
    "case.revision-created.v1",
    "case.state-transitioned.v1",
)
WORKFLOW_STATE_EVENT_TYPE = "workflow.state-transitioned.v1"
SNAPSHOT_SCHEMA_VERSION = "weflow-case-ledger-snapshot.v1"

Clock = Callable[[], datetime]
JsonObject = dict[str, Any]


class CaseLedgerError(ValueError):
    """A safe ledger error that never includes request, database, or filesystem values."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class IntakeRejected(CaseLedgerError):
    """An expected, payload-safe rejection of an inbound delivery."""


class LedgerIntegrityError(CaseLedgerError):
    """A source ledger consistency failure that must fail closed."""


class AppendOnlyViolation(CaseLedgerError):
    """An attempted mutation of immutable source records."""


@dataclass(frozen=True)
class FixedClock:
    """Inject a stable UTC clock for fixtures and repeated-run baselines."""

    value: datetime

    def __call__(self) -> datetime:
        return self.value


@dataclass(frozen=True)
class SyntheticActorRegistry:
    """Maps a local test actor identity to exactly one synthetic tenant."""

    actor_tenants: Mapping[str, str]

    def resolve(self, actor_id: str | None) -> str:
        if not isinstance(actor_id, str) or not actor_id:
            raise IntakeRejected("tenant_identity_mismatch")
        tenant_id = self.actor_tenants.get(actor_id)
        if not isinstance(tenant_id, str) or not tenant_id:
            raise IntakeRejected("tenant_identity_mismatch")
        return tenant_id

    @classmethod
    def default(cls) -> SyntheticActorRegistry:
        return cls(
            {
                "simulator-tenant-a": "tenant-alpha",
                "simulator-tenant-b": "tenant-bravo",
            }
        )


@dataclass(frozen=True)
class IntakeResult:
    """Safe references returned after an accepted or deduplicated inbound delivery."""

    disposition: str
    case_id: str
    case_revision_id: str
    event_ids: tuple[str, ...]

    def as_dict(self) -> JsonObject:
        return {
            "disposition": self.disposition,
            "case_id": self.case_id,
            "case_revision_id": self.case_revision_id,
            "event_ids": list(self.event_ids),
        }


class CaseLedger(Protocol):
    """Storage-neutral deterministic Case ledger boundary."""

    def intake(
        self,
        envelope: Mapping[str, Any],
        *,
        effective_tenant_id: str,
    ) -> IntakeResult: ...

    def get_case_projection(self, tenant_id: str, case_id: str) -> JsonObject | None: ...

    def list_case_revisions(self, tenant_id: str, case_id: str) -> list[JsonObject]: ...

    def list_case_events(self, tenant_id: str, case_id: str) -> list[JsonObject]: ...

    def export_snapshot(self, tenant_id: str) -> JsonObject: ...


def default_case_store_path(root: Path) -> Path:
    """Return the ignored local runtime store path for offline mode."""

    return root / ".weflow" / "case-ledger.sqlite3"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_identifier(prefix: str, material: object) -> str:
    digest = _sha256({"prefix": prefix, "material": material})
    return f"{prefix}_{digest[:32]}"


def _row_dict(row: sqlite3.Row) -> JsonObject:
    return {key: row[key] for key in row.keys()}


class SQLiteCaseLedger:
    """SQLite implementation of the local source-of-truth Case ledger."""

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
        self.rebuild_projection()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS inbound_receipts (
                    tenant_id TEXT NOT NULL,
                    delivery_key TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    conversation_sequence INTEGER NOT NULL,
                    case_id TEXT NOT NULL,
                    case_revision_id TEXT NOT NULL,
                    event_ids_json TEXT NOT NULL,
                    accepted_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, delivery_key)
                );

                CREATE TABLE IF NOT EXISTS conversation_cursors (
                    tenant_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    last_sequence INTEGER NOT NULL,
                    PRIMARY KEY (tenant_id, channel, conversation_id)
                );

                CREATE TABLE IF NOT EXISTS cases (
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, case_id)
                );

                CREATE TABLE IF NOT EXISTS case_revisions (
                    tenant_id TEXT NOT NULL,
                    case_revision_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    previous_case_revision_id TEXT,
                    created_at TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    source_event_fingerprint TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, case_revision_id),
                    UNIQUE (tenant_id, case_id, revision)
                );

                CREATE TABLE IF NOT EXISTS business_events (
                    tenant_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    case_revision_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    causation_id TEXT,
                    case_event_index INTEGER NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    workflow_id TEXT,
                    workflow_checkpoint_id TEXT,
                    PRIMARY KEY (tenant_id, event_id),
                    UNIQUE (tenant_id, case_id, case_event_index)
                );

                CREATE TABLE IF NOT EXISTS case_projection (
                    tenant_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    latest_case_revision_id TEXT NOT NULL,
                    latest_revision INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    event_count INTEGER NOT NULL,
                    correlation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, case_id)
                );

                CREATE TRIGGER IF NOT EXISTS inbound_receipts_no_update
                BEFORE UPDATE ON inbound_receipts
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;

                CREATE TRIGGER IF NOT EXISTS inbound_receipts_no_delete
                BEFORE DELETE ON inbound_receipts
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;

                CREATE TRIGGER IF NOT EXISTS cases_no_update
                BEFORE UPDATE ON cases
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;

                CREATE TRIGGER IF NOT EXISTS cases_no_delete
                BEFORE DELETE ON cases
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;

                CREATE TRIGGER IF NOT EXISTS case_revisions_no_update
                BEFORE UPDATE ON case_revisions
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;

                CREATE TRIGGER IF NOT EXISTS case_revisions_no_delete
                BEFORE DELETE ON case_revisions
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;

                CREATE TRIGGER IF NOT EXISTS business_events_no_update
                BEFORE UPDATE ON business_events
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;

                CREATE TRIGGER IF NOT EXISTS business_events_no_delete
                BEFORE DELETE ON business_events
                BEGIN
                    SELECT RAISE(ABORT, 'append_only_violation');
                END;
                """
            )
            try:
                initialize_workflow_journal_schema(connection)
            except WorkflowJournalSchemaError as error:
                raise LedgerIntegrityError(error.args[0]) from error
        finally:
            connection.close()

    def _now(self) -> str:
        return _timestamp(self._clock())

    def _validate_inbound(
        self,
        envelope: Mapping[str, Any],
        effective_tenant_id: str,
    ) -> JsonObject:
        payload = dict(envelope)
        try:
            validate_inbound_message_event(payload, self._contract_root)
        except ContractValidationError as error:
            raise IntakeRejected("invalid_inbound_event") from error
        if payload.get("tenant_id") != effective_tenant_id:
            raise IntakeRejected("tenant_identity_mismatch")
        return payload

    @staticmethod
    def _delivery_key(tenant_id: str, envelope: Mapping[str, Any]) -> str:
        return ":".join(
            (
                tenant_id,
                str(envelope["channel"]),
                str(envelope["channel_event_id"]),
            )
        )

    @staticmethod
    def _fingerprint(tenant_id: str, envelope: Mapping[str, Any]) -> str:
        material = {
            key: value for key, value in envelope.items() if key not in {"received_at", "tenant_id"}
        }
        material["effective_tenant_id"] = tenant_id
        return _sha256(material)

    @staticmethod
    def _case_id(tenant_id: str, delivery_key: str) -> str:
        return _stable_identifier(
            "case",
            {
                "version": "v1",
                "tenant_id": tenant_id,
                "delivery_key": delivery_key,
            },
        )

    @staticmethod
    def _revision_id(case_id: str) -> str:
        return _stable_identifier(
            "case_revision",
            {
                "version": "v1",
                "case_id": case_id,
                "revision": 1,
            },
        )

    @staticmethod
    def _event_id(case_id: str, event_type: str, event_index: int) -> str:
        return _stable_identifier(
            "event",
            {
                "version": "v1",
                "case_id": case_id,
                "event_type": event_type,
                "event_index": event_index,
            },
        )

    def intake(
        self,
        envelope: Mapping[str, Any],
        *,
        effective_tenant_id: str,
    ) -> IntakeResult:
        """Atomically accept or deduplicate a normalized synthetic delivery."""

        payload = self._validate_inbound(envelope, effective_tenant_id)
        tenant_id = effective_tenant_id
        delivery_key = self._delivery_key(tenant_id, payload)
        fingerprint = self._fingerprint(tenant_id, payload)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                """
                SELECT fingerprint, case_id, case_revision_id, event_ids_json
                FROM inbound_receipts
                WHERE tenant_id = ? AND delivery_key = ?
                """,
                (tenant_id, delivery_key),
            ).fetchone()
            if receipt is not None:
                if str(receipt["fingerprint"]) != fingerprint:
                    raise IntakeRejected("inbound_event_conflict")
                event_ids = json.loads(str(receipt["event_ids_json"]))
                if not isinstance(event_ids, list) or not all(
                    isinstance(event_id, str) for event_id in event_ids
                ):
                    raise LedgerIntegrityError("ledger_invalid")
                connection.commit()
                return IntakeResult(
                    disposition="deduplicated",
                    case_id=str(receipt["case_id"]),
                    case_revision_id=str(receipt["case_revision_id"]),
                    event_ids=tuple(event_ids),
                )

            cursor = connection.execute(
                """
                SELECT last_sequence
                FROM conversation_cursors
                WHERE tenant_id = ? AND channel = ? AND conversation_id = ?
                """,
                (tenant_id, payload["channel"], payload["conversation_id"]),
            ).fetchone()
            expected_sequence = 1 if cursor is None else int(cursor["last_sequence"]) + 1
            if payload["conversation_sequence"] != expected_sequence:
                raise IntakeRejected("inbound_out_of_order")

            created_at = self._now()
            case_id = self._case_id(tenant_id, delivery_key)
            revision_id = self._revision_id(case_id)
            case = {
                "schema_id": CASE_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": tenant_id,
                "case_id": case_id,
                "created_at": created_at,
                "source_event_id": payload["channel_event_id"],
                "correlation_id": payload["correlation_id"],
                "channel": payload["channel"],
                "conversation_id": payload["conversation_id"],
                "customer_id": payload["customer_id"],
            }
            revision = {
                "schema_id": CASE_REVISION_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": tenant_id,
                "case_id": case_id,
                "case_revision_id": revision_id,
                "revision": 1,
                "previous_case_revision_id": None,
                "created_at": created_at,
                "reason": "initial-capture",
                "source_event_id": payload["channel_event_id"],
                "source_event_fingerprint": fingerprint,
            }
            validate_payload(case, self._contract_root)
            validate_payload(revision, self._contract_root)

            events = self._initial_events(
                tenant_id=tenant_id,
                case_id=case_id,
                revision_id=revision_id,
                delivery_key=delivery_key,
                fingerprint=fingerprint,
                payload=payload,
                created_at=created_at,
            )
            for event, _ in events:
                validate_generated_ledger_event(event, self._contract_root)
            connection.execute(
                """
                INSERT INTO cases (
                    tenant_id, case_id, created_at, source_event_id, correlation_id,
                    channel, conversation_id, customer_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case["tenant_id"],
                    case["case_id"],
                    case["created_at"],
                    case["source_event_id"],
                    case["correlation_id"],
                    case["channel"],
                    case["conversation_id"],
                    case["customer_id"],
                ),
            )
            connection.execute(
                """
                INSERT INTO case_revisions (
                    tenant_id, case_revision_id, case_id, revision,
                    previous_case_revision_id, created_at, reason, source_event_id,
                    source_event_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision["tenant_id"],
                    revision["case_revision_id"],
                    revision["case_id"],
                    revision["revision"],
                    revision["previous_case_revision_id"],
                    revision["created_at"],
                    revision["reason"],
                    revision["source_event_id"],
                    revision["source_event_fingerprint"],
                ),
            )
            for event, metadata in events:
                connection.execute(
                    """
                    INSERT INTO business_events (
                        tenant_id, event_id, case_id, case_revision_id, event_type,
                        occurred_at, received_at, correlation_id, causation_id,
                        case_event_index, payload_sha256, metadata_json, workflow_id,
                        workflow_checkpoint_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["tenant_id"],
                        event["event_id"],
                        event["case_id"],
                        event["case_revision_id"],
                        event["event_type"],
                        event["occurred_at"],
                        event["received_at"],
                        event["correlation_id"],
                        event["causation_id"],
                        event["case_event_index"],
                        event["payload_sha256"],
                        _canonical_json(metadata),
                        None,
                        None,
                    ),
                )

            event_ids = [str(event["event_id"]) for event, _ in events]
            connection.execute(
                """
                INSERT INTO inbound_receipts (
                    tenant_id, delivery_key, fingerprint, channel, conversation_id,
                    conversation_sequence, case_id, case_revision_id, event_ids_json,
                    accepted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    delivery_key,
                    fingerprint,
                    payload["channel"],
                    payload["conversation_id"],
                    payload["conversation_sequence"],
                    case_id,
                    revision_id,
                    _canonical_json(event_ids),
                    created_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO conversation_cursors (
                    tenant_id, channel, conversation_id, last_sequence
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, channel, conversation_id)
                DO UPDATE SET last_sequence = excluded.last_sequence
                """,
                (
                    tenant_id,
                    payload["channel"],
                    payload["conversation_id"],
                    payload["conversation_sequence"],
                ),
            )
            projection = self._projection_from_records(
                case,
                revision,
                [event for event, _ in events],
            )
            connection.execute(
                """
                INSERT INTO case_projection (
                    tenant_id, case_id, latest_case_revision_id, latest_revision, state,
                    source_event_id, event_count, correlation_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["tenant_id"],
                    projection["case_id"],
                    projection["latest_case_revision_id"],
                    projection["latest_revision"],
                    projection["state"],
                    projection["source_event_id"],
                    projection["event_count"],
                    projection["correlation_id"],
                    projection["created_at"],
                    projection["updated_at"],
                ),
            )
            connection.commit()
            return IntakeResult(
                disposition="accepted",
                case_id=case_id,
                case_revision_id=revision_id,
                event_ids=tuple(event_ids),
            )
        except CaseLedgerError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            if "append_only_violation" in str(error):
                raise AppendOnlyViolation("append_only_violation") from error
            raise LedgerIntegrityError("ledger_write_failed") from error
        finally:
            connection.close()

    def _initial_events(
        self,
        *,
        tenant_id: str,
        case_id: str,
        revision_id: str,
        delivery_key: str,
        fingerprint: str,
        payload: Mapping[str, Any],
        created_at: str,
    ) -> list[tuple[JsonObject, JsonObject]]:
        definitions: list[tuple[str, str, str, str | None, JsonObject]] = [
            (
                INITIAL_EVENT_TYPES[0],
                str(payload["occurred_at"]),
                str(payload["received_at"]),
                None,
                {
                    "delivery_key": delivery_key,
                    "inbound_fingerprint": fingerprint,
                },
            ),
            (
                INITIAL_EVENT_TYPES[1],
                created_at,
                created_at,
                self._event_id(case_id, INITIAL_EVENT_TYPES[0], 1),
                {
                    "previous_case_revision_id": None,
                    "revision": 1,
                },
            ),
            (
                INITIAL_EVENT_TYPES[2],
                created_at,
                created_at,
                self._event_id(case_id, INITIAL_EVENT_TYPES[1], 2),
                {
                    "from_state": None,
                    "to_state": INITIAL_CASE_STATE,
                },
            ),
        ]
        events: list[tuple[JsonObject, JsonObject]] = []
        for index, (event_type, occurred_at, received_at, causation_id, metadata) in enumerate(
            definitions,
            start=1,
        ):
            events.append(
                (
                    {
                        "schema_id": BUSINESS_EVENT_SCHEMA_ID,
                        "schema_version": "v1",
                        "tenant_id": tenant_id,
                        "event_id": self._event_id(case_id, event_type, index),
                        "case_id": case_id,
                        "case_revision_id": revision_id,
                        "event_type": event_type,
                        "occurred_at": occurred_at,
                        "received_at": received_at,
                        "correlation_id": payload["correlation_id"],
                        "causation_id": causation_id,
                        "case_event_index": index,
                        "payload_sha256": _sha256(metadata),
                    },
                    metadata,
                )
            )
        return events

    def _append_workflow_state_event(
        self,
        *,
        tenant_id: str,
        case_id: str,
        case_revision_id: str,
        workflow_id: str,
        checkpoint_id: str,
        transition_kind: str,
        from_state: str,
        to_state: str,
        resume_state: str | None,
        correlation_id: str,
        occurred_at: str,
    ) -> str:
        """Internal-only port for an allowlisted workflow-originated Case event.

        The public ledger interface deliberately has no arbitrary event/state mutation
        method. Durable workflow code calls this underscored port only after it has
        recorded an immutable checkpoint that proves the transition.
        """

        try:
            validate_transition(
                from_state,
                transition_kind,
                to_state,
                resume_state=resume_state,
            )
        except WorkflowTransitionError as error:
            raise CaseLedgerError(error.reason_code) from error
        if not all(
            isinstance(value, str) and value
            for value in (
                tenant_id,
                case_id,
                case_revision_id,
                workflow_id,
                checkpoint_id,
                correlation_id,
                occurred_at,
            )
        ):
            raise CaseLedgerError("workflow_event_invalid")

        metadata = {
            "from_state": from_state,
            "resume_state": resume_state,
            "to_state": to_state,
            "transition_kind": transition_kind,
        }
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            projection = connection.execute(
                """
                SELECT state, correlation_id
                FROM case_projection
                WHERE tenant_id = ? AND case_id = ?
                """,
                (tenant_id, case_id),
            ).fetchone()
            revision = connection.execute(
                """
                SELECT 1
                FROM case_revisions
                WHERE tenant_id = ? AND case_id = ? AND case_revision_id = ?
                """,
                (tenant_id, case_id, case_revision_id),
            ).fetchone()
            if (
                projection is None
                or revision is None
                or projection["correlation_id"] != correlation_id
            ):
                raise LedgerIntegrityError("ledger_invalid")

            existing = connection.execute(
                """
                SELECT event_id, event_type, payload_sha256, metadata_json
                FROM business_events
                WHERE tenant_id = ? AND case_id = ? AND workflow_id = ?
                  AND workflow_checkpoint_id = ?
                """,
                (tenant_id, case_id, workflow_id, checkpoint_id),
            ).fetchone()
            if existing is not None:
                try:
                    existing_metadata = json.loads(str(existing["metadata_json"]))
                except json.JSONDecodeError as error:
                    raise LedgerIntegrityError("ledger_invalid") from error
                if (
                    existing["event_type"] == WORKFLOW_STATE_EVENT_TYPE
                    and existing_metadata == metadata
                    and existing["payload_sha256"] == _sha256(metadata)
                ):
                    connection.commit()
                    return str(existing["event_id"])
                raise LedgerIntegrityError("workflow_event_conflict")

            if projection["state"] != from_state:
                raise LedgerIntegrityError("workflow_event_predecessor_mismatch")
            event_index = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(case_event_index), 0) + 1
                    FROM business_events
                    WHERE tenant_id = ? AND case_id = ?
                    """,
                    (tenant_id, case_id),
                ).fetchone()[0]
            )
            event = {
                "schema_id": BUSINESS_EVENT_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": tenant_id,
                "event_id": self._event_id(case_id, WORKFLOW_STATE_EVENT_TYPE, event_index),
                "case_id": case_id,
                "case_revision_id": case_revision_id,
                "event_type": WORKFLOW_STATE_EVENT_TYPE,
                "occurred_at": occurred_at,
                "received_at": occurred_at,
                "correlation_id": correlation_id,
                "causation_id": checkpoint_id,
                "case_event_index": event_index,
                "payload_sha256": _sha256(metadata),
                "workflow_id": workflow_id,
                "workflow_checkpoint_id": checkpoint_id,
            }
            validate_generated_ledger_event(event, self._contract_root)
            connection.execute(
                """
                INSERT INTO business_events (
                    tenant_id, event_id, case_id, case_revision_id, event_type,
                    occurred_at, received_at, correlation_id, causation_id,
                    case_event_index, payload_sha256, metadata_json, workflow_id,
                    workflow_checkpoint_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["tenant_id"],
                    event["event_id"],
                    event["case_id"],
                    event["case_revision_id"],
                    event["event_type"],
                    event["occurred_at"],
                    event["received_at"],
                    event["correlation_id"],
                    event["causation_id"],
                    event["case_event_index"],
                    event["payload_sha256"],
                    _canonical_json(metadata),
                    event["workflow_id"],
                    event["workflow_checkpoint_id"],
                ),
            )
            connection.execute(
                """
                UPDATE case_projection
                SET state = ?, event_count = ?, updated_at = ?
                WHERE tenant_id = ? AND case_id = ?
                """,
                (to_state, event_index, occurred_at, tenant_id, case_id),
            )
            connection.commit()
            return str(event["event_id"])
        except CaseLedgerError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            if "append_only_violation" in str(error):
                raise AppendOnlyViolation("append_only_violation") from error
            raise LedgerIntegrityError("ledger_write_failed") from error
        finally:
            connection.close()

    def _projection_from_records(
        self,
        case: Mapping[str, Any],
        revision: Mapping[str, Any],
        events: list[Mapping[str, Any]],
        metadata: list[Mapping[str, Any]] | None = None,
    ) -> JsonObject:
        if len(events) < len(INITIAL_EVENT_TYPES) or [
            event["event_type"] for event in events[: len(INITIAL_EVENT_TYPES)]
        ] != list(INITIAL_EVENT_TYPES):
            raise LedgerIntegrityError("ledger_invalid")
        if metadata is not None and len(metadata) != len(events):
            raise LedgerIntegrityError("ledger_invalid")
        state = INITIAL_CASE_STATE
        if metadata is not None:
            for event, event_metadata in zip(
                events[len(INITIAL_EVENT_TYPES) :],
                metadata[len(INITIAL_EVENT_TYPES) :],
                strict=True,
            ):
                if (
                    event["event_type"] != WORKFLOW_STATE_EVENT_TYPE
                    or not isinstance(event.get("workflow_id"), str)
                    or not isinstance(event.get("workflow_checkpoint_id"), str)
                    or set(event_metadata)
                    != {"from_state", "resume_state", "to_state", "transition_kind"}
                    or event_metadata.get("from_state") != state
                ):
                    raise LedgerIntegrityError("ledger_invalid")
                try:
                    validate_transition(
                        state,
                        str(event_metadata["transition_kind"]),
                        str(event_metadata["to_state"]),
                        resume_state=event_metadata.get("resume_state"),
                    )
                except WorkflowTransitionError as error:
                    raise LedgerIntegrityError("ledger_invalid") from error
                state = str(event_metadata["to_state"])
        return {
            "schema_id": CASE_PROJECTION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": case["tenant_id"],
            "case_id": case["case_id"],
            "latest_case_revision_id": revision["case_revision_id"],
            "latest_revision": revision["revision"],
            "state": state,
            "source_event_id": case["source_event_id"],
            "event_count": len(events),
            "correlation_id": case["correlation_id"],
            "created_at": case["created_at"],
            "updated_at": events[-1]["occurred_at"],
        }

    def get_case_projection(self, tenant_id: str, case_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT tenant_id, case_id, latest_case_revision_id, latest_revision, state,
                       source_event_id, event_count, correlation_id, created_at, updated_at
                FROM case_projection
                WHERE tenant_id = ? AND case_id = ?
                """,
                (tenant_id, case_id),
            ).fetchone()
            if row is None:
                return None
            projection = {
                "schema_id": CASE_PROJECTION_SCHEMA_ID,
                "schema_version": "v1",
                **_row_dict(row),
            }
            validate_case_projection(projection, self._contract_root)
            return projection
        finally:
            connection.close()

    def list_case_revisions(self, tenant_id: str, case_id: str) -> list[JsonObject]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT tenant_id, case_id, case_revision_id, revision,
                       previous_case_revision_id, created_at, reason, source_event_id,
                       source_event_fingerprint
                FROM case_revisions
                WHERE tenant_id = ? AND case_id = ?
                ORDER BY revision ASC
                """,
                (tenant_id, case_id),
            ).fetchall()
            revisions = [
                {
                    "schema_id": CASE_REVISION_SCHEMA_ID,
                    "schema_version": "v1",
                    **_row_dict(row),
                }
                for row in rows
            ]
            if revisions:
                validate_revision_chain(revisions)
            return revisions
        finally:
            connection.close()

    def list_case_events(self, tenant_id: str, case_id: str) -> list[JsonObject]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT tenant_id, event_id, case_id, case_revision_id, event_type,
                       occurred_at, received_at, correlation_id, causation_id,
                       case_event_index, payload_sha256, workflow_id, workflow_checkpoint_id
                FROM business_events
                WHERE tenant_id = ? AND case_id = ?
                ORDER BY case_event_index ASC
                """,
                (tenant_id, case_id),
            ).fetchall()
            events = []
            for row in rows:
                data = _row_dict(row)
                if data.get("workflow_id") is None:
                    data.pop("workflow_id")
                if data.get("workflow_checkpoint_id") is None:
                    data.pop("workflow_checkpoint_id")
                events.append(
                    {
                        "schema_id": BUSINESS_EVENT_SCHEMA_ID,
                        "schema_version": "v1",
                        **data,
                    }
                )
            for event in events:
                validate_generated_ledger_event(event, self._contract_root)
            return events
        finally:
            connection.close()

    def rebuild_projection(self) -> None:
        """Validate source records and rebuild only the mutable Case read model."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                validate_workflow_journal_schema(connection)
            except WorkflowJournalSchemaError as error:
                raise LedgerIntegrityError(error.args[0]) from error
            connection.execute("DELETE FROM case_projection")
            case_rows = connection.execute(
                """
                SELECT tenant_id, case_id, created_at, source_event_id, correlation_id,
                       channel, conversation_id, customer_id
                FROM cases
                ORDER BY tenant_id ASC, case_id ASC
                """
            ).fetchall()
            for row in case_rows:
                self._rebuild_case_projection(connection, _row_dict(row))
            self._validate_cursors(connection)
            connection.commit()
        except (CaseLedgerError, ContractValidationError):
            connection.rollback()
            raise LedgerIntegrityError("ledger_invalid")
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise LedgerIntegrityError("ledger_invalid") from error
        finally:
            connection.close()

    def _rebuild_case_projection(
        self,
        connection: sqlite3.Connection,
        case_row: JsonObject,
    ) -> None:
        tenant_id = str(case_row["tenant_id"])
        case_id = str(case_row["case_id"])
        case = {
            "schema_id": CASE_SCHEMA_ID,
            "schema_version": "v1",
            **case_row,
        }
        validate_payload(case, self._contract_root)
        revisions = self._query_revisions(connection, tenant_id, case_id)
        if len(revisions) != 1:
            raise LedgerIntegrityError("ledger_invalid")
        validate_revision_chain(revisions)
        revision = revisions[0]
        if (
            revision["revision"] != 1
            or revision["previous_case_revision_id"] is not None
            or revision["source_event_id"] != case["source_event_id"]
        ):
            raise LedgerIntegrityError("ledger_invalid")

        events, metadata = self._query_events_with_metadata(connection, tenant_id, case_id)
        for index, event in enumerate(events, start=1):
            validate_generated_ledger_event(event, self._contract_root)
            if event["case_event_index"] != index:
                raise LedgerIntegrityError("ledger_invalid")
        if len(events) < len(INITIAL_EVENT_TYPES) or [
            event["event_type"] for event in events[: len(INITIAL_EVENT_TYPES)]
        ] != list(INITIAL_EVENT_TYPES):
            raise LedgerIntegrityError("ledger_invalid")
        validate_tenant_reference(case, revision, *events)

        receipt_rows = connection.execute(
            """
            SELECT delivery_key, fingerprint, case_revision_id, event_ids_json
            FROM inbound_receipts
            WHERE tenant_id = ? AND case_id = ?
            """,
            (tenant_id, case_id),
        ).fetchall()
        if len(receipt_rows) != 1:
            raise LedgerIntegrityError("ledger_invalid")
        receipt = _row_dict(receipt_rows[0])
        if receipt["case_revision_id"] != revision["case_revision_id"]:
            raise LedgerIntegrityError("ledger_invalid")
        try:
            receipt_event_ids = json.loads(str(receipt["event_ids_json"]))
        except json.JSONDecodeError as error:
            raise LedgerIntegrityError("ledger_invalid") from error
        expected_event_ids = [event["event_id"] for event in events[: len(INITIAL_EVENT_TYPES)]]
        if receipt_event_ids != expected_event_ids:
            raise LedgerIntegrityError("ledger_invalid")

        expected_metadata = [
            {
                "delivery_key": receipt["delivery_key"],
                "inbound_fingerprint": receipt["fingerprint"],
            },
            {
                "previous_case_revision_id": None,
                "revision": 1,
            },
            {
                "from_state": None,
                "to_state": INITIAL_CASE_STATE,
            },
        ]
        for event, event_metadata, expected in zip(
            events[: len(INITIAL_EVENT_TYPES)],
            metadata[: len(INITIAL_EVENT_TYPES)],
            expected_metadata,
            strict=True,
        ):
            if event_metadata != expected or _sha256(event_metadata) != event["payload_sha256"]:
                raise LedgerIntegrityError("ledger_invalid")

        for event, event_metadata in zip(
            events[len(INITIAL_EVENT_TYPES) :],
            metadata[len(INITIAL_EVENT_TYPES) :],
            strict=True,
        ):
            if _sha256(event_metadata) != event["payload_sha256"]:
                raise LedgerIntegrityError("ledger_invalid")
        projection = self._projection_from_records(case, revision, events, metadata)
        validate_case_projection(projection, self._contract_root)
        connection.execute(
            """
            INSERT INTO case_projection (
                tenant_id, case_id, latest_case_revision_id, latest_revision, state,
                source_event_id, event_count, correlation_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                projection["tenant_id"],
                projection["case_id"],
                projection["latest_case_revision_id"],
                projection["latest_revision"],
                projection["state"],
                projection["source_event_id"],
                projection["event_count"],
                projection["correlation_id"],
                projection["created_at"],
                projection["updated_at"],
            ),
        )

    def _query_revisions(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        case_id: str,
    ) -> list[JsonObject]:
        rows = connection.execute(
            """
            SELECT tenant_id, case_id, case_revision_id, revision,
                   previous_case_revision_id, created_at, reason, source_event_id,
                   source_event_fingerprint
            FROM case_revisions
            WHERE tenant_id = ? AND case_id = ?
            ORDER BY revision ASC
            """,
            (tenant_id, case_id),
        ).fetchall()
        return [
            {
                "schema_id": CASE_REVISION_SCHEMA_ID,
                "schema_version": "v1",
                **_row_dict(row),
            }
            for row in rows
        ]

    def _query_events_with_metadata(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        case_id: str,
    ) -> tuple[list[JsonObject], list[JsonObject]]:
        rows = connection.execute(
            """
            SELECT tenant_id, event_id, case_id, case_revision_id, event_type,
                   occurred_at, received_at, correlation_id, causation_id,
                   case_event_index, payload_sha256, metadata_json, workflow_id,
                   workflow_checkpoint_id
            FROM business_events
            WHERE tenant_id = ? AND case_id = ?
            ORDER BY case_event_index ASC
            """,
            (tenant_id, case_id),
        ).fetchall()
        events: list[JsonObject] = []
        metadata: list[JsonObject] = []
        for row in rows:
            data = _row_dict(row)
            metadata_value = json.loads(str(data.pop("metadata_json")))
            if not isinstance(metadata_value, dict):
                raise LedgerIntegrityError("ledger_invalid")
            if data.get("workflow_id") is None:
                data.pop("workflow_id")
            if data.get("workflow_checkpoint_id") is None:
                data.pop("workflow_checkpoint_id")
            events.append(
                {
                    "schema_id": BUSINESS_EVENT_SCHEMA_ID,
                    "schema_version": "v1",
                    **data,
                }
            )
            metadata.append(metadata_value)
        return events, metadata

    def _validate_cursors(self, connection: sqlite3.Connection) -> None:
        receipt_rows = connection.execute(
            """
            SELECT tenant_id, channel, conversation_id, conversation_sequence
            FROM inbound_receipts
            ORDER BY tenant_id ASC, channel ASC, conversation_id ASC,
                     conversation_sequence ASC
            """
        ).fetchall()
        expected: dict[tuple[str, str, str], int] = {}
        for row in receipt_rows:
            key = (
                str(row["tenant_id"]),
                str(row["channel"]),
                str(row["conversation_id"]),
            )
            sequence = int(row["conversation_sequence"])
            prior = expected.get(key, 0)
            if sequence != prior + 1:
                raise LedgerIntegrityError("ledger_invalid")
            expected[key] = sequence
        cursor_rows = connection.execute(
            """
            SELECT tenant_id, channel, conversation_id, last_sequence
            FROM conversation_cursors
            """
        ).fetchall()
        actual = {
            (
                str(row["tenant_id"]),
                str(row["channel"]),
                str(row["conversation_id"]),
            ): int(row["last_sequence"])
            for row in cursor_rows
        }
        if actual != expected:
            raise LedgerIntegrityError("ledger_invalid")

    def export_snapshot(self, tenant_id: str) -> JsonObject:
        """Export one tenant's source records in a canonical content-addressed envelope."""

        connection = self._connect()
        try:
            data = {
                "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
                "tenant_id": tenant_id,
                "inbound_receipts": self._snapshot_rows(
                    connection,
                    "inbound_receipts",
                    tenant_id,
                    "delivery_key ASC",
                ),
                "conversation_cursors": self._snapshot_rows(
                    connection,
                    "conversation_cursors",
                    tenant_id,
                    "channel ASC, conversation_id ASC",
                ),
                "cases": self._snapshot_rows(connection, "cases", tenant_id, "case_id ASC"),
                "case_revisions": self._snapshot_rows(
                    connection,
                    "case_revisions",
                    tenant_id,
                    "case_id ASC, revision ASC",
                ),
                "business_events": self._snapshot_rows(
                    connection,
                    "business_events",
                    tenant_id,
                    "case_id ASC, case_event_index ASC",
                ),
            }
            return {
                **data,
                "content_sha256": _sha256(data),
            }
        finally:
            connection.close()

    @staticmethod
    def _snapshot_rows(
        connection: sqlite3.Connection,
        table: str,
        tenant_id: str,
        order_by: str,
    ) -> list[JsonObject]:
        columns = "*"
        if table == "business_events":
            columns = (
                "tenant_id, event_id, case_id, case_revision_id, event_type, occurred_at, "
                "received_at, correlation_id, causation_id, case_event_index, payload_sha256, "
                "metadata_json"
            )
        predicate = "tenant_id = ?"
        if table == "business_events":
            # The Change 1 ledger snapshot remains a legacy intake-only artifact.
            # Change 2 state events are regenerated from its linked workflow journal.
            predicate += " AND workflow_id IS NULL"
        rows = connection.execute(
            f"SELECT {columns} FROM {table} WHERE {predicate} ORDER BY {order_by}",
            (tenant_id,),
        ).fetchall()
        return [_row_dict(row) for row in rows]

    @classmethod
    def restore_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        path: str | Path,
        *,
        clock: Clock | None = None,
        contract_root: Path | None = None,
    ) -> SQLiteCaseLedger:
        """Restore a verified tenant snapshot into a fresh local SQLite store."""

        target = Path(path)
        if target.exists():
            raise LedgerIntegrityError("snapshot_restore_requires_fresh_store")
        payload = dict(snapshot)
        digest = payload.pop("content_sha256", None)
        if not isinstance(digest, str) or digest != _sha256(payload):
            raise LedgerIntegrityError("snapshot_hash_mismatch")
        if payload.get("snapshot_schema_version") != SNAPSHOT_SCHEMA_VERSION:
            raise LedgerIntegrityError("snapshot_invalid")
        tenant_id = payload.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise LedgerIntegrityError("snapshot_invalid")

        table_columns = {
            "inbound_receipts": (
                "tenant_id",
                "delivery_key",
                "fingerprint",
                "channel",
                "conversation_id",
                "conversation_sequence",
                "case_id",
                "case_revision_id",
                "event_ids_json",
                "accepted_at",
            ),
            "conversation_cursors": (
                "tenant_id",
                "channel",
                "conversation_id",
                "last_sequence",
            ),
            "cases": (
                "tenant_id",
                "case_id",
                "created_at",
                "source_event_id",
                "correlation_id",
                "channel",
                "conversation_id",
                "customer_id",
            ),
            "case_revisions": (
                "tenant_id",
                "case_revision_id",
                "case_id",
                "revision",
                "previous_case_revision_id",
                "created_at",
                "reason",
                "source_event_id",
                "source_event_fingerprint",
            ),
            "business_events": (
                "tenant_id",
                "event_id",
                "case_id",
                "case_revision_id",
                "event_type",
                "occurred_at",
                "received_at",
                "correlation_id",
                "causation_id",
                "case_event_index",
                "payload_sha256",
                "metadata_json",
            ),
        }
        expected_keys = {"snapshot_schema_version", "tenant_id", *table_columns}
        if set(payload) != expected_keys:
            raise LedgerIntegrityError("snapshot_invalid")
        for table, columns in table_columns.items():
            records = payload[table]
            if not isinstance(records, list):
                raise LedgerIntegrityError("snapshot_invalid")
            for record in records:
                if not isinstance(record, Mapping) or set(record) != set(columns):
                    raise LedgerIntegrityError("snapshot_invalid")
                if record.get("tenant_id") != tenant_id:
                    raise LedgerIntegrityError("snapshot_tenant_mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.restore-{uuid.uuid4().hex}.sqlite3")
        try:
            restored = cls(temporary, clock=clock, contract_root=contract_root)
            connection = restored._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                for table, columns in table_columns.items():
                    placeholders = ", ".join("?" for _ in columns)
                    column_names = ", ".join(columns)
                    statement = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
                    for record in payload[table]:
                        connection.execute(statement, tuple(record[column] for column in columns))
                connection.commit()
            except sqlite3.DatabaseError as error:
                connection.rollback()
                raise LedgerIntegrityError("snapshot_invalid") from error
            finally:
                connection.close()
            restored.rebuild_projection()
            os.replace(temporary, target)
            return cls(target, clock=clock, contract_root=contract_root)
        except CaseLedgerError:
            temporary.unlink(missing_ok=True)
            raise
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise LedgerIntegrityError("snapshot_restore_failed") from error

    def source_counts(self, tenant_id: str) -> JsonObject:
        """Return safe source-record counts for local acceptance evidence."""

        connection = self._connect()
        try:
            counts = {}
            for table in (
                "inbound_receipts",
                "cases",
                "case_revisions",
                "business_events",
                "case_projection",
            ):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id = ?",
                    (tenant_id,),
                ).fetchone()[0]
                counts[table] = int(count)
            return counts
        finally:
            connection.close()
