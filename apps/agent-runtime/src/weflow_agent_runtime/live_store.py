"""Append-only temporary evidence store for bounded live-model attempts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from weflow_contracts.evaluation import canonical_sha256
from weflow_contracts.live import (
    MODEL_INVOCATION_OBSERVATION_SCHEMA_ID,
    validate_live_candidate_binding,
    validate_model_invocation_intent,
    validate_model_invocation_observation,
    validate_response_draft_artifact,
)

JsonObject = dict[str, Any]


class LiveStoreError(RuntimeError):
    """A redacted immutable-store failure."""


def stable_identifier(prefix: str, material: object) -> str:
    encoded = json.dumps(
        {"prefix": prefix, "material": material},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:32]}"


@dataclass(frozen=True)
class LiveAttemptIdentities:
    evaluation_session_id: str
    evaluation_task_id: str
    attempt_index: int

    @property
    def attempt_id(self) -> str:
        return stable_identifier(
            "live-attempt",
            {
                "evaluation_session_id": self.evaluation_session_id,
                "evaluation_task_id": self.evaluation_task_id,
                "attempt_index": self.attempt_index,
            },
        )

    def logical_turn_id(self, turn_index: int) -> str:
        return stable_identifier(
            "live-turn", {"attempt_id": self.attempt_id, "turn_index": turn_index}
        )

    def invocation_id(self, turn_index: int, invocation_sequence: int = 1) -> str:
        return stable_identifier(
            "model-invocation",
            {
                "logical_turn_id": self.logical_turn_id(turn_index),
                "invocation_sequence": invocation_sequence,
            },
        )


class LiveEvaluationStore:
    """SQLite journal containing only safe, schema-bounded live metadata."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_sessions (
                    evaluation_session_id TEXT PRIMARY KEY,
                    suite_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    config_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS live_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    evaluation_session_id TEXT NOT NULL,
                    evaluation_task_id TEXT NOT NULL,
                    attempt_index INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('open', 'closed')),
                    terminal_outcome TEXT,
                    reason_code TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(evaluation_session_id, evaluation_task_id, attempt_index),
                    FOREIGN KEY(evaluation_session_id)
                      REFERENCES live_sessions(evaluation_session_id)
                );
                CREATE TABLE IF NOT EXISTS live_turns (
                    logical_turn_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    normalized_action_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(attempt_id, turn_index),
                    FOREIGN KEY(attempt_id) REFERENCES live_attempts(attempt_id)
                );
                CREATE TABLE IF NOT EXISTS model_invocation_intents (
                    invocation_id TEXT PRIMARY KEY,
                    logical_turn_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(logical_turn_id, invocation_id),
                    FOREIGN KEY(logical_turn_id) REFERENCES live_turns(logical_turn_id)
                );
                CREATE TABLE IF NOT EXISTS model_invocation_observations (
                    observation_id TEXT PRIMARY KEY,
                    invocation_id TEXT NOT NULL UNIQUE,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(invocation_id)
                      REFERENCES model_invocation_intents(invocation_id)
                );
                CREATE TABLE IF NOT EXISTS response_draft_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    producer_invocation_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(attempt_id, producer_invocation_id),
                    FOREIGN KEY(attempt_id) REFERENCES live_attempts(attempt_id),
                    FOREIGN KEY(producer_invocation_id)
                      REFERENCES model_invocation_intents(invocation_id)
                );
                CREATE TABLE IF NOT EXISTS live_candidate_bindings (
                    binding_sha256 TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(attempt_id) REFERENCES live_attempts(attempt_id),
                    FOREIGN KEY(artifact_id) REFERENCES response_draft_artifacts(artifact_id)
                );
                CREATE TABLE IF NOT EXISTS live_budget_events (
                    budget_event_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    invocation_id TEXT,
                    event_kind TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(attempt_id) REFERENCES live_attempts(attempt_id)
                );
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _serialized(payload: Mapping[str, Any]) -> tuple[str, str]:
        serialized = json.dumps(
            dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _insert_immutable(
        self,
        table: str,
        identity_field: str,
        identity: str,
        values: Mapping[str, Any],
    ) -> None:
        connection = self._connect()
        try:
            columns = tuple(values)
            existing = connection.execute(
                f"SELECT * FROM {table} WHERE {identity_field} = ?", (identity,)
            ).fetchone()
            if existing is not None:
                if any(existing[column] != values[column] for column in columns):
                    raise LiveStoreError("live_store_immutable_conflict")
                return
            placeholders = ", ".join("?" for _ in columns)
            connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values[column] for column in columns),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise LiveStoreError("live_store_integrity_error") from error
        finally:
            connection.close()

    def append_session(
        self,
        *,
        evaluation_session_id: str,
        suite_id: str,
        tenant_id: str,
        config_sha256: str,
        created_at: str,
    ) -> None:
        self._insert_immutable(
            "live_sessions",
            "evaluation_session_id",
            evaluation_session_id,
            {
                "evaluation_session_id": evaluation_session_id,
                "suite_id": suite_id,
                "tenant_id": tenant_id,
                "config_sha256": config_sha256,
                "created_at": created_at,
            },
        )

    def append_attempt(
        self,
        identities: LiveAttemptIdentities,
        *,
        created_at: str,
    ) -> str:
        attempt_id = identities.attempt_id
        connection = self._connect()
        try:
            existing = connection.execute(
                "SELECT * FROM live_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
        finally:
            connection.close()
        if existing is not None:
            immutable = {
                "evaluation_session_id": identities.evaluation_session_id,
                "evaluation_task_id": identities.evaluation_task_id,
                "attempt_index": identities.attempt_index,
                "created_at": created_at,
            }
            if any(existing[field] != value for field, value in immutable.items()):
                raise LiveStoreError("live_store_immutable_conflict")
            return attempt_id
        self._insert_immutable(
            "live_attempts",
            "attempt_id",
            attempt_id,
            {
                "attempt_id": attempt_id,
                "evaluation_session_id": identities.evaluation_session_id,
                "evaluation_task_id": identities.evaluation_task_id,
                "attempt_index": identities.attempt_index,
                "status": "open",
                "terminal_outcome": None,
                "reason_code": None,
                "created_at": created_at,
                "completed_at": None,
            },
        )
        return attempt_id

    def append_turn(
        self,
        identities: LiveAttemptIdentities,
        turn_index: int,
        *,
        created_at: str,
    ) -> str:
        logical_turn_id = identities.logical_turn_id(turn_index)
        connection = self._connect()
        try:
            existing = connection.execute(
                "SELECT * FROM live_turns WHERE logical_turn_id = ?", (logical_turn_id,)
            ).fetchone()
        finally:
            connection.close()
        if existing is not None:
            immutable = {
                "attempt_id": identities.attempt_id,
                "turn_index": turn_index,
                "created_at": created_at,
            }
            if any(existing[field] != value for field, value in immutable.items()):
                raise LiveStoreError("live_store_immutable_conflict")
            return logical_turn_id
        self._insert_immutable(
            "live_turns",
            "logical_turn_id",
            logical_turn_id,
            {
                "logical_turn_id": logical_turn_id,
                "attempt_id": identities.attempt_id,
                "turn_index": turn_index,
                "normalized_action_sha256": None,
                "created_at": created_at,
            },
        )
        return logical_turn_id

    def record_normalized_action(self, logical_turn_id: str, action_sha256: str) -> None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT normalized_action_sha256 FROM live_turns WHERE logical_turn_id = ?",
                (logical_turn_id,),
            ).fetchone()
            if row is None:
                raise LiveStoreError("live_turn_not_found")
            existing = row["normalized_action_sha256"]
            if existing not in (None, action_sha256):
                raise LiveStoreError("live_turn_action_conflict")
            if existing is None:
                connection.execute(
                    "UPDATE live_turns SET normalized_action_sha256 = ? WHERE logical_turn_id = ?",
                    (action_sha256, logical_turn_id),
                )
                connection.commit()
        finally:
            connection.close()

    def append_intent(self, payload: Mapping[str, Any]) -> None:
        validate_model_invocation_intent(payload)
        serialized, payload_hash = self._serialized(payload)
        self._insert_immutable(
            "model_invocation_intents",
            "invocation_id",
            str(payload["invocation_id"]),
            {
                "invocation_id": payload["invocation_id"],
                "logical_turn_id": payload["logical_turn_id"],
                "payload_sha256": payload_hash,
                "payload_json": serialized,
            },
        )

    def append_observation(self, payload: Mapping[str, Any]) -> None:
        validate_model_invocation_observation(payload)
        serialized, payload_hash = self._serialized(payload)
        self._insert_immutable(
            "model_invocation_observations",
            "observation_id",
            str(payload["observation_id"]),
            {
                "observation_id": payload["observation_id"],
                "invocation_id": payload["invocation_id"],
                "payload_sha256": payload_hash,
                "payload_json": serialized,
            },
        )

    def append_draft_artifact(self, payload: Mapping[str, Any]) -> None:
        validate_response_draft_artifact(payload)
        serialized, payload_hash = self._serialized(payload)
        self._insert_immutable(
            "response_draft_artifacts",
            "artifact_id",
            str(payload["artifact_id"]),
            {
                "artifact_id": payload["artifact_id"],
                "attempt_id": payload["attempt_id"],
                "producer_invocation_id": payload["producer_invocation_id"],
                "payload_sha256": payload_hash,
                "payload_json": serialized,
            },
        )

    def append_candidate_binding(self, payload: Mapping[str, Any]) -> None:
        validate_live_candidate_binding(payload)
        serialized, _ = self._serialized(payload)
        self._insert_immutable(
            "live_candidate_bindings",
            "binding_sha256",
            str(payload["binding_sha256"]),
            {
                "binding_sha256": payload["binding_sha256"],
                "attempt_id": payload["attempt_id"],
                "artifact_id": payload["draft_artifact_id"],
                "payload_json": serialized,
            },
        )

    def append_budget_event(
        self,
        *,
        attempt_id: str,
        event_kind: str,
        payload: Mapping[str, Any],
        created_at: str,
        invocation_id: str | None = None,
        event_id: str | None = None,
    ) -> str:
        if event_kind not in {
            "provider_reserved",
            "provider_settled",
            "action_consumed",
            "tool_consumed",
            "no_progress_consumed",
        }:
            raise LiveStoreError("live_budget_event_kind_invalid")
        if not payload or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            for value in payload.values()
        ):
            raise LiveStoreError("live_budget_event_payload_invalid")
        budget_event_id = event_id or stable_identifier(
            "budget-event",
            {
                "attempt_id": attempt_id,
                "event_kind": event_kind,
                "invocation_id": invocation_id,
                "payload": dict(payload),
            },
        )
        serialized, payload_hash = self._serialized(payload)
        self._insert_immutable(
            "live_budget_events",
            "budget_event_id",
            budget_event_id,
            {
                "budget_event_id": budget_event_id,
                "attempt_id": attempt_id,
                "invocation_id": invocation_id,
                "event_kind": event_kind,
                "payload_sha256": payload_hash,
                "payload_json": serialized,
                "created_at": created_at,
            },
        )
        return budget_event_id

    def close_attempt(
        self,
        attempt_id: str,
        *,
        terminal_outcome: str,
        reason_code: str,
        completed_at: str,
    ) -> None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT status, terminal_outcome, reason_code
                FROM live_attempts WHERE attempt_id = ?
                """,
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise LiveStoreError("live_attempt_not_found")
            if row["status"] == "closed":
                if row["terminal_outcome"] != terminal_outcome or row["reason_code"] != reason_code:
                    raise LiveStoreError("live_attempt_close_conflict")
                return
            connection.execute(
                """
                UPDATE live_attempts
                SET status = 'closed', terminal_outcome = ?, reason_code = ?, completed_at = ?
                WHERE attempt_id = ? AND status = 'open'
                """,
                (terminal_outcome, reason_code, completed_at, attempt_id),
            )
            connection.commit()
        finally:
            connection.close()

    def attempt_snapshot(self, attempt_id: str) -> JsonObject:
        connection = self._connect()
        try:
            attempt = connection.execute(
                "SELECT * FROM live_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if attempt is None:
                raise LiveStoreError("live_attempt_not_found")
            turns = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM live_turns WHERE attempt_id = ? ORDER BY turn_index",
                    (attempt_id,),
                ).fetchall()
            ]
            intents = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    """
                    SELECT intent.payload_json
                    FROM model_invocation_intents AS intent
                    JOIN live_turns AS turn
                      ON turn.logical_turn_id = intent.logical_turn_id
                    WHERE turn.attempt_id = ?
                    ORDER BY turn.turn_index, intent.rowid
                    """,
                    (attempt_id,),
                ).fetchall()
            ]
            draft_artifacts = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    "SELECT payload_json FROM response_draft_artifacts WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchall()
            ]
            candidate_bindings = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    "SELECT payload_json FROM live_candidate_bindings WHERE attempt_id = ?",
                    (attempt_id,),
                ).fetchall()
            ]
            observations = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    """
                    SELECT observation.payload_json
                    FROM model_invocation_observations AS observation
                    JOIN model_invocation_intents AS intent
                      ON intent.invocation_id = observation.invocation_id
                    JOIN live_turns AS turn ON turn.logical_turn_id = intent.logical_turn_id
                    WHERE turn.attempt_id = ? ORDER BY turn.turn_index
                    """,
                    (attempt_id,),
                ).fetchall()
            ]
            budget_events = [
                {
                    "budget_event_id": row["budget_event_id"],
                    "invocation_id": row["invocation_id"],
                    "event_kind": row["event_kind"],
                    "payload": json.loads(row["payload_json"]),
                    "created_at": row["created_at"],
                }
                for row in connection.execute(
                    "SELECT * FROM live_budget_events WHERE attempt_id = ? ORDER BY rowid",
                    (attempt_id,),
                ).fetchall()
            ]
            return {
                "attempt": dict(attempt),
                "turns": turns,
                "observations": observations,
                "intents": intents,
                "draft_artifacts": draft_artifacts,
                "candidate_bindings": candidate_bindings,
                "budget_events": budget_events,
            }
        finally:
            connection.close()

    def recover_attempt(
        self,
        attempt_id: str,
        *,
        observed_at: str,
        currency: str = "USD",
    ) -> JsonObject:
        """Close unknown intent-only calls and never issue a provider retry."""

        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT intent.payload_json AS intent_json,
                       observation.payload_json AS observation_json,
                       turn.normalized_action_sha256
                FROM live_turns AS turn
                JOIN model_invocation_intents AS intent
                  ON intent.logical_turn_id = turn.logical_turn_id
                LEFT JOIN model_invocation_observations AS observation
                  ON observation.invocation_id = intent.invocation_id
                WHERE turn.attempt_id = ? ORDER BY turn.turn_index
                """,
                (attempt_id,),
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            intent = json.loads(row["intent_json"])
            if row["observation_json"] is None:
                reservation = intent["reservation"]
                observation: JsonObject = {
                    "schema_id": MODEL_INVOCATION_OBSERVATION_SCHEMA_ID,
                    "schema_version": "v1",
                    "tenant_id": intent["tenant_id"],
                    "evaluation_session_id": intent["evaluation_session_id"],
                    "suite_id": intent["suite_id"],
                    "evaluation_task_id": intent["evaluation_task_id"],
                    "attempt_id": intent["attempt_id"],
                    "logical_turn_id": intent["logical_turn_id"],
                    "invocation_id": intent["invocation_id"],
                    "observation_id": stable_identifier(
                        "model-observation", {"invocation_id": intent["invocation_id"]}
                    ),
                    "status": "provider_outcome_unknown",
                    "request_reference_sha256": None,
                    "response_sha256": None,
                    "usage": {
                        "available": False,
                        "input_tokens": reservation["input_tokens"],
                        "output_tokens": reservation["output_tokens"],
                        "total_tokens": reservation["total_tokens"],
                    },
                    "provider_latency_ms": reservation["request_timeout_ms"],
                    "estimated_cost": reservation["estimated_cost"],
                    "currency": currency,
                    "failure_classification": "provider_outcome_unknown",
                    "observed_at": observed_at,
                    "observation_sha256": "",
                }
                observation["observation_sha256"] = canonical_sha256(
                    observation, without="observation_sha256"
                )
                self.append_observation(observation)
                self.close_attempt(
                    attempt_id,
                    terminal_outcome="provider_outcome_unknown",
                    reason_code="intent_without_observation",
                    completed_at=observed_at,
                )
                return {"recovery": "closed_unknown", "observation": observation}
        reusable = [
            json.loads(row["observation_json"])
            for row in rows
            if row["observation_json"] is not None and row["normalized_action_sha256"] is not None
        ]
        return {"recovery": "reuse_observed", "observations": reusable}


__all__ = [
    "LiveAttemptIdentities",
    "LiveEvaluationStore",
    "LiveStoreError",
    "stable_identifier",
]
