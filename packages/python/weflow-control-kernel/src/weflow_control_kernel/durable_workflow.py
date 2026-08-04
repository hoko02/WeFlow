"""Offline deterministic driver, journal, and fixture-local effect protocol for Change 2."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from weflow_contracts import (
    AGENT_ACTION_SCHEMA_ID,
    CONTEXT_MANIFEST_SCHEMA_ID,
    OUTBOUND_DELIVERY_COMPLETION_SCHEMA_ID,
    OUTBOUND_DELIVERY_INTENT_SCHEMA_ID,
    OUTBOUND_DELIVERY_OBSERVATION_SCHEMA_ID,
    RESPONSE_CANDIDATE_SCHEMA_ID,
    SIDE_EFFECT_COMPLETION_SCHEMA_ID,
    SIDE_EFFECT_INTENT_SCHEMA_ID,
    SIDE_EFFECT_OBSERVATION_SCHEMA_ID,
    SYNTHETIC_SLA_POLICY_SCHEMA_ID,
    TOOL_REQUEST_SCHEMA_ID,
    TOOL_RESULT_SCHEMA_ID,
    VERIFIER_OUTCOME_SCHEMA_ID,
    WORKFLOW_CHECKPOINT_SCHEMA_ID,
    WORKFLOW_COMMAND_SCHEMA_ID,
    WORKFLOW_PROJECTION_SCHEMA_ID,
    ContractValidationError,
    stable_idempotency_key,
    validate_agent_action,
    validate_approval_decision,
    validate_approval_request,
    validate_authorization_binding,
    validate_capability_grant,
    validate_change4_authorization_profile,
    validate_checkpoint_sequence,
    validate_context_manifest,
    validate_hash_bound_approval,
    validate_outbound_delivery_chain,
    validate_outbound_delivery_completion,
    validate_outbound_delivery_intent,
    validate_outbound_delivery_observation,
    validate_policy_decision,
    validate_response_candidate,
    validate_side_effect_chain,
    validate_side_effect_intents,
    validate_synthetic_sla_policy,
    validate_tool_request,
    validate_tool_result,
    validate_verifier_outcome,
    validate_workflow_checkpoint,
    validate_workflow_command,
    validate_workflow_command_version,
    validate_workflow_projection,
)

from .ledger import CaseLedgerError, SQLiteCaseLedger
from .policy import (
    API_503_DELIVERY_RESOURCE_ID,
    API_503_POLICY_FIXTURE_ID,
    FIXTURE_APPROVER_ROLE,
    FIXTURE_CONTROLLER_ROLE,
    api_503_policy_fixture,
    bind_fixture_authorization,
    build_approval_decision,
    build_approval_request,
    evaluate_fixture_policy,
    issue_fixture_grant,
)
from .workflow_journal_schema import (
    WORKFLOW_SOURCE_TABLES,
    WorkflowJournalSchemaError,
    validate_workflow_journal_schema,
)
from .workflow_state import (
    APPROVAL_GRANTED,
    AUTHORIZATION_DENIED,
    AWAITING_APPROVAL,
    CANCEL,
    CANCELLED,
    DELIVERING,
    DELIVERY_COMPLETE,
    DELIVERY_RECORDED,
    INVESTIGATING,
    INVESTIGATION_STARTED,
    NEEDS_RECONCILIATION,
    PAUSE,
    PAUSED,
    POLICY_APPROVAL_ACTIVATED,
    RECEIVED,
    RECONCILIATION_COMPLETE,
    RECONCILIATION_REQUIRED,
    RESPONSE_CANDIDATE_VERIFIED,
    RESPONSE_READY,
    RESUME,
    SLA_EXPIRED,
    TICKET_HANDOFF_COMPLETE,
    TICKET_READY,
    WAITING_FOR_OPERATOR,
    WORKFLOW_DEFINITION_VERSION,
    WorkflowTransitionError,
    is_terminal,
    run_status,
    validate_transition,
)

JsonObject = dict[str, Any]
Clock = Callable[[], datetime]

WORKFLOW_SNAPSHOT_SCHEMA_VERSION = "weflow-durable-workflow-snapshot.v1"
INVESTIGATION_TOOL_REQUESTS_TABLE = "investigation_tool_" + "re" + "quests"
LOCAL_TICKET_EFFECT_KIND = "fixture-local-ticket"
LOCAL_TICKET_PROVIDER_ID = "fixture-local-ticket"
FIND_OR_CREATE = "find-or-create"
WORKFLOW_HANDOFF = "workflow-handoff"


class WorkflowError(CaseLedgerError):
    """A safe workflow error that never includes fixture or database values."""


class WorkflowNotFound(WorkflowError):
    """A tenant-scoped absence; callers must not distinguish a foreign workflow."""


class WorkflowInterrupted(WorkflowError):
    """A deterministic injected worker interruption after a durable boundary."""


@dataclass
class FixtureClock:
    """A manually advanced UTC clock used by repeatable workflow and SLA fixtures."""

    value: datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            self.value = self.value.replace(tzinfo=UTC)
        else:
            self.value = self.value.astimezone(UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        if seconds < 0:
            raise ValueError("fixture_clock_cannot_move_backwards")
        self.value += timedelta(seconds=seconds)


@dataclass(frozen=True)
class FaultProfile:
    """Named deterministic fault controls; they never synthesize an outcome."""

    interrupt_after: frozenset[str] = frozenset()
    reconciliation_timeout: bool = False

    _POINTS = frozenset(
        {
            "activation",
            "checkpoint",
            "intent",
            "reconcile",
            "execute",
            "lost-response",
            "observation",
            "completion",
            "agent-action",
            "tool-result",
            "candidate",
            "verifier",
            "policy",
            "approval-request",
            "approval-decision",
            "delivery-intent",
            "delivery-execute",
            "delivery-lost-response",
            "delivery-observation",
            "delivery-completion",
            "delivery-transition",
        }
    )

    @classmethod
    def after(cls, *points: str) -> FaultProfile:
        normalized = frozenset(points)
        if not normalized <= cls._POINTS:
            raise ValueError("unsupported_fault_profile")
        return cls(interrupt_after=normalized)

    @classmethod
    def named(cls, name: str) -> FaultProfile:
        if name == "reconciliation-timeout":
            return cls(reconciliation_timeout=True)
        return cls.after(name)


@dataclass(frozen=True)
class WorkflowCommandResult:
    disposition: str
    projection: JsonObject


@dataclass(frozen=True)
class TicketOutcome:
    status: str
    ticket_id: str | None
    version: int | None
    outcome_sha256: str | None
    reason_code: str | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    delivery_id: str | None
    version: int | None
    content_sha256: str | None
    reason_code: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_identifier(prefix: str, material: object) -> str:
    return f"{prefix}_{_sha256({'prefix': prefix, 'material': material})[:32]}"


def _row_dict(row: sqlite3.Row) -> JsonObject:
    return {key: row[key] for key in row.keys()}


class SQLiteDurableWorkflow:
    """One driver-neutral durable workflow implementation over the local Case ledger."""

    def __init__(
        self,
        ledger: SQLiteCaseLedger,
        *,
        clock: Clock | None = None,
        contract_root: Path | None = None,
    ) -> None:
        self.ledger = ledger
        self._clock = clock or _utc_now
        self._contract_root = contract_root or ledger._contract_root
        self.rebuild_workflow_projection()

    def _connect(self) -> sqlite3.Connection:
        return self.ledger._connect()

    def _now(self) -> str:
        return _timestamp(self._clock())

    @staticmethod
    def workflow_id(
        tenant_id: str,
        case_id: str,
        case_revision_id: str,
        workflow_definition_version: str = WORKFLOW_DEFINITION_VERSION,
    ) -> str:
        return _stable_identifier(
            "workflow",
            {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "case_revision_id": case_revision_id,
                "workflow_definition_version": workflow_definition_version,
            },
        )

    def default_sla_policy(self, tenant_id: str, *, created_at: str | None = None) -> JsonObject:
        policy = {
            "schema_id": SYNTHETIC_SLA_POLICY_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": tenant_id,
            "policy_id": "fixture-sla-default",
            "policy_version": "v1",
            "deadline_seconds": 3600,
            "created_at": created_at or self._now(),
        }
        validate_synthetic_sla_policy(policy, self._contract_root)
        return policy

    def activate_case(
        self,
        tenant_id: str,
        case_id: str,
        case_revision_id: str,
        *,
        sla_policy: Mapping[str, Any] | None = None,
    ) -> tuple[str, bool]:
        """Append one activation/run or return the existing stable workflow identity."""

        projection = self.ledger.get_case_projection(tenant_id, case_id)
        revisions = self.ledger.list_case_revisions(tenant_id, case_id)
        events = self.ledger.list_case_events(tenant_id, case_id)
        if (
            projection is None
            or len(revisions) != 1
            or not events
            or revisions[0]["case_revision_id"] != case_revision_id
        ):
            raise WorkflowNotFound("workflow_not_found")
        if projection["state"] != RECEIVED:
            existing = self._activation_for_case(tenant_id, case_id, case_revision_id)
            if existing is None:
                raise WorkflowError("workflow_activation_predecessor_invalid")
            return str(existing["workflow_id"]), False

        policy = dict(
            sla_policy or self.default_sla_policy(tenant_id, created_at=projection["created_at"])
        )
        try:
            validate_synthetic_sla_policy(policy, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("invalid_synthetic_sla_policy") from error
        if policy["tenant_id"] != tenant_id:
            raise WorkflowError("tenant_identity_mismatch")

        workflow_id = self.workflow_id(tenant_id, case_id, case_revision_id)
        activation_id = _stable_identifier("workflow_activation", {"workflow_id": workflow_id})
        deadline = _timestamp(
            _parse_timestamp(str(projection["created_at"]))
            + timedelta(seconds=int(policy["deadline_seconds"]))
        )
        created_at = self._now()
        source_event_id = str(events[-1]["event_id"])
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                validate_workflow_journal_schema(connection)
            except WorkflowJournalSchemaError as error:
                raise WorkflowError(error.args[0]) from error
            existing = connection.execute(
                """
                SELECT workflow_id, case_id, case_revision_id, workflow_definition_version
                FROM workflow_activations
                WHERE tenant_id = ? AND case_id = ? AND case_revision_id = ?
                  AND workflow_definition_version = ?
                """,
                (tenant_id, case_id, case_revision_id, WORKFLOW_DEFINITION_VERSION),
            ).fetchone()
            if existing is not None:
                if str(existing["workflow_id"]) != workflow_id:
                    raise WorkflowError("workflow_activation_conflict")
                connection.commit()
                return workflow_id, False
            connection.execute(
                """
                INSERT INTO workflow_activations (
                    tenant_id, workflow_id, activation_id, case_id, case_revision_id,
                    workflow_definition_version, source_event_id, correlation_id,
                    sla_policy_id, sla_policy_version, sla_deadline_seconds,
                    sla_deadline_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    workflow_id,
                    activation_id,
                    case_id,
                    case_revision_id,
                    WORKFLOW_DEFINITION_VERSION,
                    source_event_id,
                    projection["correlation_id"],
                    policy["policy_id"],
                    policy["policy_version"],
                    policy["deadline_seconds"],
                    deadline,
                    created_at,
                ),
            )
            self._insert_run(
                connection,
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                state=RECEIVED,
                reason_code="activated",
                created_at=created_at,
            )
            connection.commit()
            return workflow_id, True
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_activation_failed") from error
        finally:
            connection.close()

    def _activation_for_case(
        self,
        tenant_id: str,
        case_id: str,
        case_revision_id: str,
    ) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM workflow_activations
                WHERE tenant_id = ? AND case_id = ? AND case_revision_id = ?
                  AND workflow_definition_version = ?
                """,
                (tenant_id, case_id, case_revision_id, WORKFLOW_DEFINITION_VERSION),
            ).fetchone()
            return None if row is None else _row_dict(row)
        finally:
            connection.close()

    def _activation(self, tenant_id: str, workflow_id: str) -> JsonObject:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM workflow_activations WHERE tenant_id = ? AND workflow_id = ?",
                (tenant_id, workflow_id),
            ).fetchone()
            if row is None:
                raise WorkflowNotFound("workflow_not_found")
            return _row_dict(row)
        finally:
            connection.close()

    @staticmethod
    def _checkpoint_payload(row: Mapping[str, Any]) -> JsonObject:
        try:
            pending = json.loads(str(row["pending_intent_ids_json"]))
            completed = json.loads(str(row["completed_intent_ids_json"]))
        except json.JSONDecodeError as error:
            raise WorkflowError("workflow_journal_invalid") from error
        if not isinstance(pending, list) or not isinstance(completed, list):
            raise WorkflowError("workflow_journal_invalid")
        return {
            "schema_id": WORKFLOW_CHECKPOINT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": row["tenant_id"],
            "case_id": row["case_id"],
            "case_revision_id": row["case_revision_id"],
            "workflow_id": row["workflow_id"],
            "workflow_definition_version": row["workflow_definition_version"],
            "checkpoint_id": row["checkpoint_id"],
            "checkpoint_sequence": row["checkpoint_sequence"],
            "previous_checkpoint_id": row["previous_checkpoint_id"],
            "current_state": row["current_state"],
            "resume_state": row["resume_state"],
            "workflow_version": row["workflow_version"],
            "sla_deadline_at": row["sla_deadline_at"],
            "pending_intent_ids": pending,
            "completed_intent_ids": completed,
            "causation_event_id": row["causation_event_id"],
            "correlation_id": row["correlation_id"],
            "content_sha256": row["content_sha256"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _checkpoint_hash(payload: Mapping[str, Any]) -> str:
        material = {key: value for key, value in payload.items() if key != "content_sha256"}
        return _sha256(material)

    def _checkpoints(self, tenant_id: str, workflow_id: str) -> list[JsonObject]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM workflow_checkpoints
                WHERE tenant_id = ? AND workflow_id = ?
                ORDER BY checkpoint_sequence ASC
                """,
                (tenant_id, workflow_id),
            ).fetchall()
            records = []
            for row in rows:
                record = _row_dict(row)
                record["payload"] = self._checkpoint_payload(record)
                records.append(record)
            return records
        finally:
            connection.close()

    def _latest_checkpoint(self, tenant_id: str, workflow_id: str) -> JsonObject | None:
        checkpoints = self._checkpoints(tenant_id, workflow_id)
        return checkpoints[-1] if checkpoints else None

    def _insert_run(
        self,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        workflow_id: str,
        state: str,
        reason_code: str,
        created_at: str,
    ) -> None:
        sequence = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(run_sequence), 0) + 1
                FROM workflow_runs
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()[0]
        )
        run_id = _stable_identifier(
            "workflow_run",
            {"workflow_id": workflow_id, "run_sequence": sequence, "reason_code": reason_code},
        )
        connection.execute(
            """
            INSERT INTO workflow_runs (
                tenant_id, run_id, workflow_id, run_sequence, state, run_status,
                reason_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                run_id,
                workflow_id,
                sequence,
                state,
                run_status(state),
                reason_code,
                created_at,
            ),
        )

    def _ensure_checkpoint(
        self,
        activation: Mapping[str, Any],
        *,
        current_state: str,
        resume_state: str,
        pending_intent_ids: Sequence[str],
        completed_intent_ids: Sequence[str],
        causation_event_id: str | None,
        transition_kind: str | None,
    ) -> JsonObject:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        previous = self._latest_checkpoint(tenant_id, workflow_id)
        expected_pending = sorted(set(pending_intent_ids))
        expected_completed = sorted(set(completed_intent_ids))
        if set(expected_pending) & set(expected_completed):
            raise WorkflowError("workflow_checkpoint_effect_overlap")
        if previous is not None:
            previous_payload = previous["payload"]
            same = (
                previous_payload["current_state"] == current_state
                and previous_payload["resume_state"] == resume_state
                and previous_payload["pending_intent_ids"] == expected_pending
                and previous_payload["completed_intent_ids"] == expected_completed
                and previous_payload["causation_event_id"] == causation_event_id
                and previous["transition_kind"] == transition_kind
            )
            if same:
                return previous
            sequence = int(previous_payload["checkpoint_sequence"]) + 1
            workflow_version = int(previous_payload["workflow_version"]) + 1
            previous_checkpoint_id = str(previous_payload["checkpoint_id"])
        else:
            if current_state != RECEIVED or resume_state != RECEIVED or transition_kind is not None:
                raise WorkflowError("workflow_checkpoint_predecessor_invalid")
            sequence = 1
            workflow_version = 0
            previous_checkpoint_id = None
        checkpoint_id = _stable_identifier(
            "workflow_checkpoint",
            {"workflow_id": workflow_id, "checkpoint_sequence": sequence},
        )
        payload = {
            "schema_id": WORKFLOW_CHECKPOINT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": tenant_id,
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": workflow_id,
            "workflow_definition_version": activation["workflow_definition_version"],
            "checkpoint_id": checkpoint_id,
            "checkpoint_sequence": sequence,
            "previous_checkpoint_id": previous_checkpoint_id,
            "current_state": current_state,
            "resume_state": resume_state,
            "workflow_version": workflow_version,
            "sla_deadline_at": activation["sla_deadline_at"],
            "pending_intent_ids": expected_pending,
            "completed_intent_ids": expected_completed,
            "causation_event_id": causation_event_id,
            "correlation_id": activation["correlation_id"],
            "content_sha256": "",
            "created_at": self._now(),
        }
        payload["content_sha256"] = self._checkpoint_hash(payload)
        try:
            validate_workflow_checkpoint(payload, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("workflow_checkpoint_invalid") from error

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT checkpoint_id FROM workflow_checkpoints
                WHERE tenant_id = ? AND workflow_id = ? AND checkpoint_sequence = ?
                """,
                (tenant_id, workflow_id, sequence),
            ).fetchone()
            if current is not None:
                connection.commit()
                latest = self._latest_checkpoint(tenant_id, workflow_id)
                if latest is None:
                    raise WorkflowError("workflow_journal_invalid")
                return latest
            connection.execute(
                """
                INSERT INTO workflow_checkpoints (
                    tenant_id, checkpoint_id, workflow_id, case_id, case_revision_id,
                    workflow_definition_version, checkpoint_sequence, previous_checkpoint_id,
                    current_state, resume_state, workflow_version, sla_deadline_at,
                    pending_intent_ids_json, completed_intent_ids_json, causation_event_id,
                    correlation_id, content_sha256, transition_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["tenant_id"],
                    payload["checkpoint_id"],
                    payload["workflow_id"],
                    payload["case_id"],
                    payload["case_revision_id"],
                    payload["workflow_definition_version"],
                    payload["checkpoint_sequence"],
                    payload["previous_checkpoint_id"],
                    payload["current_state"],
                    payload["resume_state"],
                    payload["workflow_version"],
                    payload["sla_deadline_at"],
                    _canonical_json(payload["pending_intent_ids"]),
                    _canonical_json(payload["completed_intent_ids"]),
                    payload["causation_event_id"],
                    payload["correlation_id"],
                    payload["content_sha256"],
                    transition_kind,
                    payload["created_at"],
                ),
            )
            self._insert_run(
                connection,
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                state=current_state,
                reason_code=f"checkpoint:{transition_kind or 'progress'}",
                created_at=str(payload["created_at"]),
            )
            connection.commit()
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_checkpoint_failed") from error
        finally:
            connection.close()
        return {
            **payload,
            "transition_kind": transition_kind,
            "payload": payload,
        }

    @staticmethod
    def _intent_payload(row: Mapping[str, Any]) -> JsonObject:
        try:
            evidence_references = json.loads(str(row["evidence_references_json"]))
        except json.JSONDecodeError as error:
            raise WorkflowError("workflow_journal_invalid") from error
        if not isinstance(evidence_references, list):
            raise WorkflowError("workflow_journal_invalid")
        return {
            "schema_id": SIDE_EFFECT_INTENT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": row["tenant_id"],
            "case_id": row["case_id"],
            "case_revision_id": row["case_revision_id"],
            "workflow_id": row["workflow_id"],
            "checkpoint_id": row["checkpoint_id"],
            "intent_id": row["intent_id"],
            "effect_kind": row["effect_kind"],
            "operation": row["operation"],
            "natural_key": row["natural_key"],
            "intended_state_hash": row["intended_state_hash"],
            "idempotency_key": row["idempotency_key"],
            "evidence_references": evidence_references,
            "correlation_id": row["correlation_id"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _observation_payload(row: Mapping[str, Any]) -> JsonObject:
        return {
            "schema_id": SIDE_EFFECT_OBSERVATION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": row["tenant_id"],
            "case_id": row["case_id"],
            "case_revision_id": row["case_revision_id"],
            "workflow_id": row["workflow_id"],
            "checkpoint_id": row["checkpoint_id"],
            "observation_id": row["observation_id"],
            "intent_id": row["intent_id"],
            "status": row["status"],
            "observed_ticket_id": row["observed_ticket_id"],
            "observed_version": row["observed_version"],
            "outcome_sha256": row["outcome_sha256"],
            "reason_code": row["reason_code"],
            "recorded_at": row["recorded_at"],
        }

    @staticmethod
    def _completion_payload(row: Mapping[str, Any]) -> JsonObject:
        return {
            "schema_id": SIDE_EFFECT_COMPLETION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": row["tenant_id"],
            "case_id": row["case_id"],
            "case_revision_id": row["case_revision_id"],
            "workflow_id": row["workflow_id"],
            "checkpoint_id": row["checkpoint_id"],
            "completion_id": row["completion_id"],
            "intent_id": row["intent_id"],
            "observation_id": row["observation_id"],
            "observed_ticket_id": row["observed_ticket_id"],
            "observed_version": row["observed_version"],
            "result_sha256": row["result_sha256"],
            "completed_at": row["completed_at"],
        }

    def _workflow_intents(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        workflow_id: str,
    ) -> list[JsonObject]:
        rows = connection.execute(
            """
            SELECT * FROM side_effect_intents
            WHERE tenant_id = ? AND workflow_id = ?
            ORDER BY created_at ASC, intent_id ASC
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        records = []
        for row in rows:
            record = _row_dict(row)
            record["payload"] = self._intent_payload(record)
            records.append(record)
        return records

    def _intent_observations(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        intent_id: str,
    ) -> list[JsonObject]:
        rows = connection.execute(
            """
            SELECT * FROM side_effect_observations
            WHERE tenant_id = ? AND intent_id = ?
            ORDER BY recorded_at ASC, observation_id ASC
            """,
            (tenant_id, intent_id),
        ).fetchall()
        return [self._observation_payload(_row_dict(row)) for row in rows]

    def _intent_completions(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        intent_id: str,
    ) -> list[JsonObject]:
        rows = connection.execute(
            """
            SELECT * FROM side_effect_completions
            WHERE tenant_id = ? AND intent_id = ?
            ORDER BY completed_at ASC, completion_id ASC
            """,
            (tenant_id, intent_id),
        ).fetchall()
        return [self._completion_payload(_row_dict(row)) for row in rows]

    def _validate_workflow_source(
        self,
        connection: sqlite3.Connection,
        activation: Mapping[str, Any],
        checkpoints: Sequence[JsonObject],
    ) -> None:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        source_event = connection.execute(
            """
            SELECT 1 FROM business_events
            WHERE tenant_id = ? AND event_id = ? AND case_id = ? AND case_revision_id = ?
            """,
            (
                tenant_id,
                activation["source_event_id"],
                activation["case_id"],
                activation["case_revision_id"],
            ),
        ).fetchone()
        if source_event is None:
            raise WorkflowError("workflow_journal_invalid")
        runs = connection.execute(
            """
            SELECT run_sequence, state, run_status, reason_code
            FROM workflow_runs
            WHERE tenant_id = ? AND workflow_id = ?
            ORDER BY run_sequence ASC
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        if not runs or [int(row["run_sequence"]) for row in runs] != list(range(1, len(runs) + 1)):
            raise WorkflowError("workflow_journal_invalid")
        for row in runs:
            if str(row["run_status"]) != run_status(str(row["state"])):
                raise WorkflowError("workflow_journal_invalid")
        if not checkpoints:
            if str(runs[-1]["state"]) != RECEIVED:
                raise WorkflowError("workflow_journal_invalid")
            return

        payloads = [checkpoint["payload"] for checkpoint in checkpoints]
        try:
            validate_checkpoint_sequence(payloads, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("workflow_journal_invalid") from error
        if len(runs) != len(checkpoints) + 1:
            raise WorkflowError("workflow_journal_invalid")
        for index, checkpoint in enumerate(checkpoints):
            payload = checkpoint["payload"]
            if (
                payload["tenant_id"] != tenant_id
                or payload["case_id"] != activation["case_id"]
                or payload["case_revision_id"] != activation["case_revision_id"]
                or payload["workflow_id"] != workflow_id
                or payload["workflow_definition_version"]
                != activation["workflow_definition_version"]
                or payload["correlation_id"] != activation["correlation_id"]
                or payload["sla_deadline_at"] != activation["sla_deadline_at"]
                or payload["content_sha256"] != self._checkpoint_hash(payload)
                or str(runs[index + 1]["state"]) != payload["current_state"]
            ):
                raise WorkflowError("workflow_journal_invalid")
            if index == 0:
                if (
                    payload["current_state"] != RECEIVED
                    or payload["resume_state"] != RECEIVED
                    or payload["workflow_version"] != 0
                    or checkpoint["transition_kind"] is not None
                    or payload["causation_event_id"] != activation["source_event_id"]
                ):
                    raise WorkflowError("workflow_journal_invalid")
                continue
            previous = checkpoints[index - 1]["payload"]
            if payload["workflow_version"] != previous["workflow_version"] + 1:
                raise WorkflowError("workflow_journal_invalid")
            if payload["current_state"] == previous["current_state"]:
                if (
                    checkpoint["transition_kind"] is not None
                    or payload["resume_state"] != payload["current_state"]
                ):
                    raise WorkflowError("workflow_journal_invalid")
                continue
            if checkpoint["transition_kind"] is None:
                raise WorkflowError("workflow_journal_invalid")
            try:
                validate_transition(
                    str(previous["current_state"]),
                    str(checkpoint["transition_kind"]),
                    str(payload["current_state"]),
                    resume_state=str(payload["resume_state"]),
                    unresolved_effect=bool(previous["pending_intent_ids"]),
                )
            except WorkflowTransitionError as error:
                raise WorkflowError("workflow_journal_invalid") from error

        latest = payloads[-1]
        if str(runs[-1]["state"]) != latest["current_state"]:
            raise WorkflowError("workflow_journal_invalid")
        command_rows = connection.execute(
            """
            SELECT * FROM workflow_commands
            WHERE tenant_id = ? AND workflow_id = ?
            ORDER BY accepted_at ASC, command_id ASC
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        for command_row in command_rows:
            command_record = _row_dict(command_row)
            command_payload = {
                "schema_id": WORKFLOW_COMMAND_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": tenant_id,
                "case_id": activation["case_id"],
                "case_revision_id": activation["case_revision_id"],
                "workflow_id": workflow_id,
                "command_id": command_record["command_id"],
                "command_type": command_record["command_type"],
                "expected_workflow_version": command_record["expected_workflow_version"],
                "command_payload_sha256": command_record["command_payload_sha256"],
                "requested_at": command_record["requested_at"],
            }
            expected_payload_hash = _sha256(
                {
                    "case_id": activation["case_id"],
                    "command_type": command_record["command_type"],
                    "expected_workflow_version": command_record["expected_workflow_version"],
                }
            )
            expected_fingerprint = _sha256(
                {
                    "command_id": command_record["command_id"],
                    "command_type": command_record["command_type"],
                    "expected_workflow_version": command_record["expected_workflow_version"],
                    "command_payload_sha256": command_record["command_payload_sha256"],
                }
            )
            try:
                validate_workflow_command(command_payload, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("workflow_journal_invalid") from error
            if (
                command_record["command_payload_sha256"] != expected_payload_hash
                or command_record["command_fingerprint"] != expected_fingerprint
            ):
                raise WorkflowError("workflow_journal_invalid")
            applied = [
                checkpoint
                for checkpoint in checkpoints
                if checkpoint["payload"]["causation_event_id"]
                == f"command:{command_record['command_id']}"
            ]
            if len(applied) > 1:
                raise WorkflowError("workflow_journal_invalid")
        checkpoint_ids = {str(payload["checkpoint_id"]) for payload in payloads}
        intents = self._workflow_intents(connection, tenant_id, workflow_id)
        try:
            validate_side_effect_intents(
                [intent["payload"] for intent in intents], self._contract_root
            )
        except ContractValidationError as error:
            raise WorkflowError("workflow_journal_invalid") from error
        intent_ids = {str(intent["intent_id"]) for intent in intents}
        delivery_rows = connection.execute(
            """
            SELECT * FROM outbound_delivery_intents
            WHERE tenant_id = ? AND workflow_id = ?
            ORDER BY created_at ASC, intent_id ASC
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        delivery_completed_ids: set[str] = set()
        for delivery_row in delivery_rows:
            delivery_intent = self._change4_payload(_row_dict(delivery_row), "delivery-intent")
            try:
                validate_outbound_delivery_intent(delivery_intent, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            if (
                delivery_intent.get("case_id") != activation["case_id"]
                or delivery_intent.get("case_revision_id") != activation["case_revision_id"]
                or delivery_intent.get("workflow_id") != workflow_id
                or delivery_intent.get("checkpoint_id") not in checkpoint_ids
            ):
                raise WorkflowError("policy_journal_invalid")
            binding_row = connection.execute(
                """
                SELECT * FROM authorization_bindings
                WHERE tenant_id = ? AND authorization_binding_sha256 = ?
                """,
                (tenant_id, delivery_intent["authorization_binding_sha256"]),
            ).fetchone()
            if binding_row is None:
                raise WorkflowError("policy_journal_invalid")
            binding = self._change4_payload(_row_dict(binding_row), "binding")
            try:
                validate_authorization_binding(binding, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            observations = [
                self._change4_payload(_row_dict(row), "delivery-observation")
                for row in connection.execute(
                    """
                    SELECT * FROM outbound_delivery_observations
                    WHERE tenant_id = ? AND intent_id = ?
                    ORDER BY recorded_at ASC, observation_id ASC
                    """,
                    (tenant_id, delivery_intent["intent_id"]),
                ).fetchall()
            ]
            completions = [
                self._change4_payload(_row_dict(row), "delivery-completion")
                for row in connection.execute(
                    """
                    SELECT * FROM outbound_delivery_completions
                    WHERE tenant_id = ? AND intent_id = ?
                    ORDER BY completed_at ASC, completion_id ASC
                    """,
                    (tenant_id, delivery_intent["intent_id"]),
                ).fetchall()
            ]
            try:
                validate_outbound_delivery_chain(
                    delivery_intent, observations, completions, binding, self._contract_root
                )
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            intent_ids.add(str(delivery_intent["intent_id"]))
            if completions:
                delivery_completed_ids.add(str(delivery_intent["intent_id"]))
        if (set(latest["pending_intent_ids"]) | set(latest["completed_intent_ids"])) - intent_ids:
            raise WorkflowError("workflow_journal_invalid")
        completed_intents: set[str] = set()
        for intent in intents:
            payload = intent["payload"]
            if (
                payload["case_id"] != activation["case_id"]
                or payload["case_revision_id"] != activation["case_revision_id"]
                or payload["workflow_id"] != workflow_id
                or payload["checkpoint_id"] not in checkpoint_ids
                or payload["natural_key"]
                != f"{tenant_id}:{activation['case_id']}:{activation['case_revision_id']}"
            ):
                raise WorkflowError("workflow_journal_invalid")
            observations = self._intent_observations(
                connection, tenant_id, str(intent["intent_id"])
            )
            completions = self._intent_completions(connection, tenant_id, str(intent["intent_id"]))
            try:
                validate_side_effect_chain(payload, observations, completions, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("workflow_journal_invalid") from error
            if completions:
                completed_intents.add(str(intent["intent_id"]))
        completed_intents.update(delivery_completed_ids)
        if not set(latest["completed_intent_ids"]) <= completed_intents:
            raise WorkflowError("workflow_journal_invalid")
        if not set(latest["pending_intent_ids"]) <= intent_ids:
            raise WorkflowError("workflow_journal_invalid")
        if set(latest["pending_intent_ids"]) & set(latest["completed_intent_ids"]):
            raise WorkflowError("workflow_journal_invalid")
        self._validate_ticket_source(connection, tenant_id)

    def _validate_change4_source(
        self,
        connection: sqlite3.Connection,
        activation: Mapping[str, Any],
        checkpoints: Sequence[JsonObject],
    ) -> None:
        """Validate additive Change 4 facts without requiring an incomplete
        activation to progress."""

        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        checkpoint_ids = {str(item["payload"]["checkpoint_id"]) for item in checkpoints}
        states = {str(item["payload"]["current_state"]) for item in checkpoints}
        activation_rows = connection.execute(
            "SELECT * FROM policy_approval_activations WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchall()
        related_tables = (
            "capability_grants",
            "policy_decisions",
            "authorization_bindings",
            "approval_requests",
            "approval_decisions",
            "outbound_delivery_intents",
        )
        if not activation_rows:
            if states & {AWAITING_APPROVAL, DELIVERING, DELIVERY_RECORDED}:
                raise WorkflowError("policy_journal_invalid")
            for table in related_tables:
                if (
                    connection.execute(
                        f"SELECT 1 FROM {table} WHERE tenant_id = ? AND workflow_id = ?",
                        (tenant_id, workflow_id),
                    ).fetchone()
                    is not None
                ):
                    raise WorkflowError("policy_journal_invalid")
            return
        if len(activation_rows) != 1:
            raise WorkflowError("policy_journal_invalid")
        policy_activation = _row_dict(activation_rows[0])
        try:
            evidence = json.loads(str(policy_activation["evidence_hashes_json"]))
        except json.JSONDecodeError as error:
            raise WorkflowError("policy_journal_invalid") from error
        if (
            policy_activation["case_id"] != activation["case_id"]
            or policy_activation["case_revision_id"] != activation["case_revision_id"]
            or policy_activation["source_checkpoint_id"] not in checkpoint_ids
            or policy_activation["fixture_id"] != API_503_POLICY_FIXTURE_ID
            or policy_activation["delivery_resource_id"] != API_503_DELIVERY_RESOURCE_ID
            or policy_activation["data_classification"] != "synthetic"
            or not isinstance(evidence, list)
            or not evidence
        ):
            raise WorkflowError("policy_journal_invalid")
        grant_rows = connection.execute(
            "SELECT * FROM capability_grants WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchall()
        if len(grant_rows) > 1:
            raise WorkflowError("policy_journal_invalid")
        grant: JsonObject | None = None
        if grant_rows:
            grant = self._change4_payload(_row_dict(grant_rows[0]), "grant")
            try:
                validate_capability_grant(grant, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            if grant.get("tenant_id") != tenant_id or grant.get("grant_sha256") != _sha256(
                {key: value for key, value in grant.items() if key != "grant_sha256"}
            ):
                raise WorkflowError("policy_journal_invalid")
        decision_rows = connection.execute(
            """
            SELECT * FROM policy_decisions
            WHERE tenant_id = ? AND workflow_id = ?
            ORDER BY rowid ASC
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        if len(decision_rows) > 1:
            raise WorkflowError("policy_journal_invalid")
        decision: JsonObject | None = None
        if decision_rows:
            decision = self._change4_payload(_row_dict(decision_rows[0]), "policy")
            try:
                validate_policy_decision(decision, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            if (
                decision.get("tenant_id") != tenant_id
                or decision.get("workflow_id") != workflow_id
                or decision.get("checkpoint_id") != policy_activation["source_checkpoint_id"]
                or decision.get("policy_decision_sha256")
                != _sha256(
                    {
                        key: value
                        for key, value in decision.items()
                        if key != "policy_decision_sha256"
                    }
                )
            ):
                raise WorkflowError("policy_journal_invalid")
        binding_rows = connection.execute(
            "SELECT * FROM authorization_bindings WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchall()
        if len(binding_rows) > 1:
            raise WorkflowError("policy_journal_invalid")
        binding: JsonObject | None = None
        if binding_rows:
            binding = self._change4_payload(_row_dict(binding_rows[0]), "binding")
            try:
                validate_authorization_binding(binding, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            if (
                grant is None
                or decision is None
                or binding.get("workflow_id") != workflow_id
                or binding.get("grant_id") != grant.get("grant_id")
                or binding.get("policy_decision_id") != decision.get("policy_decision_id")
            ):
                raise WorkflowError("policy_journal_invalid")
        request_rows = connection.execute(
            "SELECT * FROM approval_requests WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchall()
        if len(request_rows) > 1:
            raise WorkflowError("policy_journal_invalid")
        request: JsonObject | None = None
        if request_rows:
            request = self._change4_payload(_row_dict(request_rows[0]), "approval-request")
            try:
                validate_approval_request(request, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            if binding is None or request.get("authorization_binding_sha256") != binding.get(
                "authorization_binding_sha256"
            ):
                raise WorkflowError("policy_journal_invalid")
        decision_approval_rows = connection.execute(
            """
            SELECT * FROM approval_decisions
            WHERE tenant_id = ? AND workflow_id = ?
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        if len(decision_approval_rows) > 1:
            raise WorkflowError("policy_journal_invalid")
        if decision_approval_rows:
            approval = self._change4_payload(
                _row_dict(decision_approval_rows[0]), "approval-decision"
            )
            try:
                validate_approval_decision(approval, self._contract_root)
            except ContractValidationError as error:
                raise WorkflowError("policy_journal_invalid") from error
            if (
                request is None
                or approval.get("approval_request_id") != request.get("approval_request_id")
                or approval.get("decision_sha256")
                != _sha256(
                    {key: value for key, value in approval.items() if key != "decision_sha256"}
                )
            ):
                raise WorkflowError("policy_journal_invalid")
        if states & {AWAITING_APPROVAL, DELIVERING, DELIVERY_RECORDED} and (
            grant is None or decision is None or binding is None or request is None
        ):
            raise WorkflowError("policy_journal_invalid")
        self._validate_fixture_delivery_source(connection, tenant_id)

    @staticmethod
    def _validate_fixture_delivery_source(connection: sqlite3.Connection, tenant_id: str) -> None:
        operation_rows = connection.execute(
            """
            SELECT * FROM fixture_delivery_operations WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchall()
        for operation in operation_rows:
            record = connection.execute(
                """
                SELECT * FROM fixture_delivery_records
                WHERE tenant_id = ? AND delivery_id = ? AND version = ?
                """,
                (tenant_id, operation["delivery_id"], operation["observed_version"]),
            ).fetchone()
            intent = connection.execute(
                """
                SELECT natural_key, candidate_hash FROM outbound_delivery_intents
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, operation["idempotency_key"]),
            ).fetchone()
            if (
                record is None
                or intent is None
                or record["natural_key"] != operation["natural_key"]
                or intent["natural_key"] != operation["natural_key"]
                or record["content_sha256"] != operation["content_sha256"]
                or intent["candidate_hash"] != operation["content_sha256"]
                or record["data_classification"] != "synthetic"
            ):
                raise WorkflowError("policy_journal_invalid")

    @staticmethod
    def _validate_ticket_source(connection: sqlite3.Connection, tenant_id: str) -> None:
        operation_rows = connection.execute(
            """
            SELECT tenant_id, idempotency_key, operation, natural_key, expected_version,
                   ticket_id, observed_version, outcome_sha256
            FROM fixture_ticket_operations
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        ).fetchall()
        for operation in operation_rows:
            revision = connection.execute(
                """
                SELECT natural_key, content_sha256, operation
                FROM fixture_ticket_revisions
                WHERE tenant_id = ? AND ticket_id = ? AND version = ?
                """,
                (tenant_id, operation["ticket_id"], operation["observed_version"]),
            ).fetchone()
            if revision is None or revision["natural_key"] != operation["natural_key"]:
                raise WorkflowError("workflow_journal_invalid")
            intent = connection.execute(
                """
                SELECT operation, natural_key
                FROM side_effect_intents
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, operation["idempotency_key"]),
            ).fetchone()
            if (
                intent is None
                or intent["operation"] != operation["operation"]
                or intent["natural_key"] != operation["natural_key"]
                or revision["operation"] != operation["operation"]
            ):
                raise WorkflowError("workflow_journal_invalid")
            if operation["operation"] == FIND_OR_CREATE:
                if operation["expected_version"] is not None or operation["observed_version"] != 1:
                    raise WorkflowError("workflow_journal_invalid")
            elif operation["operation"] == WORKFLOW_HANDOFF:
                if (
                    operation["expected_version"] is None
                    or operation["observed_version"] != operation["expected_version"] + 1
                ):
                    raise WorkflowError("workflow_journal_invalid")
            else:
                raise WorkflowError("workflow_journal_invalid")
            expected_outcome = _sha256(
                {
                    "ticket_id": operation["ticket_id"],
                    "version": operation["observed_version"],
                    "natural_key": operation["natural_key"],
                    "content_sha256": revision["content_sha256"],
                }
            )
            if expected_outcome != operation["outcome_sha256"]:
                raise WorkflowError("workflow_journal_invalid")

    def _validate_case_event_agreement(
        self,
        connection: sqlite3.Connection,
        activation: Mapping[str, Any],
        checkpoints: Sequence[JsonObject],
    ) -> None:
        """Require every durable transition to have one matching internal Case event.

        This check is deliberately separate from restart rebuild: a crash after a
        checkpoint is persisted but before the internal Case event is appended is
        recoverable. Callers use this stricter agreement check once recovery has
        completed or after a linked snapshot has replayed its Case events.
        """

        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        expected = [checkpoint for checkpoint in checkpoints if checkpoint["transition_kind"]]
        rows = connection.execute(
            """
            SELECT event_id, case_id, case_revision_id, event_type, occurred_at,
                   received_at, correlation_id, causation_id, case_event_index,
                   payload_sha256, metadata_json, workflow_checkpoint_id
            FROM business_events
            WHERE tenant_id = ? AND workflow_id = ?
            ORDER BY case_event_index ASC
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        if len(rows) != len(expected):
            raise WorkflowError("workflow_case_projection_mismatch")
        for index, (row, checkpoint) in enumerate(zip(rows, expected, strict=True)):
            if index == 0:
                previous_state = RECEIVED
            else:
                previous_state = expected[index - 1]["payload"]["current_state"]
            payload = checkpoint["payload"]
            try:
                metadata = json.loads(str(row["metadata_json"]))
            except json.JSONDecodeError as error:
                raise WorkflowError("workflow_case_projection_mismatch") from error
            expected_metadata = {
                "from_state": previous_state,
                "resume_state": payload["resume_state"],
                "to_state": payload["current_state"],
                "transition_kind": checkpoint["transition_kind"],
            }
            if (
                row["case_id"] != activation["case_id"]
                or row["case_revision_id"] != activation["case_revision_id"]
                or row["event_type"] != "workflow.state-transitioned.v1"
                or row["occurred_at"] != payload["created_at"]
                or row["received_at"] != payload["created_at"]
                or row["correlation_id"] != activation["correlation_id"]
                or row["causation_id"] != payload["checkpoint_id"]
                or row["workflow_checkpoint_id"] != payload["checkpoint_id"]
                or metadata != expected_metadata
                or row["payload_sha256"] != _sha256(expected_metadata)
            ):
                raise WorkflowError("workflow_case_projection_mismatch")

    def _validate_investigation_source(
        self,
        connection: sqlite3.Connection,
        activation: Mapping[str, Any],
        checkpoints: Sequence[JsonObject],
    ) -> None:
        """Validate immutable replay evidence before deriving a workflow projection."""

        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        rows = connection.execute(
            "SELECT * FROM investigation_activations WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchall()
        if len(rows) > 1:
            raise WorkflowError("investigation_journal_invalid")
        if not rows:
            return
        investigation = _row_dict(rows[0])
        manifest = self._investigation_manifest_payload(investigation)
        try:
            validate_context_manifest(manifest, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("investigation_journal_invalid") from error
        checkpoint_ids = {str(item["payload"]["checkpoint_id"]) for item in checkpoints}
        if (
            manifest["tenant_id"] != tenant_id
            or manifest["case_id"] != activation["case_id"]
            or manifest["case_revision_id"] != activation["case_revision_id"]
            or manifest["workflow_id"] != workflow_id
            or manifest["checkpoint_id"] not in checkpoint_ids
        ):
            raise WorkflowError("investigation_journal_invalid")
        for row in connection.execute(
            "SELECT * FROM agent_steps WHERE tenant_id = ? AND workflow_id = ? ORDER BY rowid ASC",
            (tenant_id, workflow_id),
        ).fetchall():
            record = _row_dict(row)
            action = {
                "schema_id": AGENT_ACTION_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": tenant_id,
                "case_id": activation["case_id"],
                "case_revision_id": activation["case_revision_id"],
                "workflow_id": workflow_id,
                "checkpoint_id": record["checkpoint_id"],
                "context_manifest_id": record["context_manifest_id"],
                "step_id": record["step_id"],
                "action_type": record["action_type"],
                "action_sha256": record["action_sha256"],
                "created_at": record["created_at"],
            }
            try:
                validate_agent_action(action, self._contract_root, context_manifest=manifest)
            except ContractValidationError as error:
                raise WorkflowError("investigation_journal_invalid") from error
        tool_rows = connection.execute(
            f"""
            SELECT request.*, result.tool_result_id, result.evidence_id, result.content_sha256,
                   result.redaction_classification, result.recorded_at
            FROM {INVESTIGATION_TOOL_REQUESTS_TABLE} AS request
            LEFT JOIN investigation_tool_results AS result
              ON result.tenant_id = request.tenant_id
             AND result.tool_request_id = request.tool_request_id
            WHERE request.tenant_id = ? AND request.workflow_id = ?
            ORDER BY request.rowid ASC
            """,
            (tenant_id, workflow_id),
        ).fetchall()
        for row in tool_rows:
            record = _row_dict(row)
            request = {
                "schema_id": TOOL_REQUEST_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": tenant_id,
                "case_id": activation["case_id"],
                "case_revision_id": activation["case_revision_id"],
                "workflow_id": workflow_id,
                "checkpoint_id": record["checkpoint_id"],
                "context_manifest_id": record["context_manifest_id"],
                "tool_request_id": record["tool_request_id"],
                "step_id": record["step_id"],
                "tool_name": record["tool_name"],
                "request_sha256": record["request_sha256"],
                "created_at": record["created_at"],
            }
            try:
                validate_tool_request(request, self._contract_root, context_manifest=manifest)
            except ContractValidationError as error:
                raise WorkflowError("investigation_journal_invalid") from error
            if record["tool_result_id"] is None:
                raise WorkflowError("investigation_journal_invalid")
            result = {
                "schema_id": TOOL_RESULT_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": tenant_id,
                "case_id": activation["case_id"],
                "case_revision_id": activation["case_revision_id"],
                "workflow_id": workflow_id,
                "checkpoint_id": record["checkpoint_id"],
                "context_manifest_id": record["context_manifest_id"],
                "tool_name": record["tool_name"],
                "tool_result_id": record["tool_result_id"],
                "tool_request_id": record["tool_request_id"],
                "evidence_id": record["evidence_id"],
                "content_sha256": record["content_sha256"],
                "redaction_classification": record["redaction_classification"],
                "recorded_at": record["recorded_at"],
            }
            try:
                validate_tool_result(result, self._contract_root, tool_request=request)
            except ContractValidationError as error:
                raise WorkflowError("investigation_journal_invalid") from error
        candidates: dict[str, JsonObject] = {}
        for row in connection.execute(
            "SELECT * FROM investigation_candidates WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchall():
            candidate = self._candidate_payload(activation, _row_dict(row))
            try:
                validate_response_candidate(
                    candidate, self._contract_root, context_manifest=manifest
                )
            except ContractValidationError as error:
                raise WorkflowError("investigation_journal_invalid") from error
            candidates[str(candidate["candidate_id"])] = candidate
        for row in connection.execute(
            "SELECT * FROM investigation_verifier_outcomes WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchall():
            outcome = self._verifier_outcome_payload(activation, _row_dict(row))
            candidate = candidates.get(str(outcome["candidate_id"]))
            if candidate is None:
                raise WorkflowError("investigation_journal_invalid")
            try:
                validate_verifier_outcome(outcome, self._contract_root, candidate=candidate)
            except ContractValidationError as error:
                raise WorkflowError("investigation_journal_invalid") from error

    def rebuild_workflow_projection(self) -> None:
        """Rebuild the workflow read model solely from immutable journal records."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                validate_workflow_journal_schema(connection)
            except WorkflowJournalSchemaError as error:
                raise WorkflowError(error.args[0]) from error
            connection.execute("DELETE FROM workflow_projection")
            activations = connection.execute(
                "SELECT * FROM workflow_activations ORDER BY tenant_id ASC, workflow_id ASC"
            ).fetchall()
            for activation_row in activations:
                activation = _row_dict(activation_row)
                checkpoint_rows = connection.execute(
                    """
                    SELECT * FROM workflow_checkpoints
                    WHERE tenant_id = ? AND workflow_id = ?
                    ORDER BY checkpoint_sequence ASC
                    """,
                    (activation["tenant_id"], activation["workflow_id"]),
                ).fetchall()
                checkpoints = []
                for checkpoint_row in checkpoint_rows:
                    record = _row_dict(checkpoint_row)
                    record["payload"] = self._checkpoint_payload(record)
                    checkpoints.append(record)
                self._validate_workflow_source(connection, activation, checkpoints)
                self._validate_investigation_source(connection, activation, checkpoints)
                self._validate_change4_source(connection, activation, checkpoints)
                if not checkpoints:
                    continue
                latest = checkpoints[-1]["payload"]
                projection = {
                    "schema_id": WORKFLOW_PROJECTION_SCHEMA_ID,
                    "schema_version": "v1",
                    "tenant_id": activation["tenant_id"],
                    "case_id": activation["case_id"],
                    "case_revision_id": activation["case_revision_id"],
                    "workflow_id": activation["workflow_id"],
                    "workflow_definition_version": activation["workflow_definition_version"],
                    "state": latest["current_state"],
                    "run_status": run_status(str(latest["current_state"])),
                    "workflow_version": latest["workflow_version"],
                    "latest_checkpoint_id": latest["checkpoint_id"],
                    "latest_checkpoint_sequence": latest["checkpoint_sequence"],
                    "sla_deadline_at": activation["sla_deadline_at"],
                    "correlation_id": activation["correlation_id"],
                    "created_at": activation["created_at"],
                    "updated_at": latest["created_at"],
                }
                try:
                    validate_workflow_projection(projection, self._contract_root)
                except ContractValidationError as error:
                    raise WorkflowError("workflow_journal_invalid") from error
                connection.execute(
                    """
                    INSERT INTO workflow_projection (
                        tenant_id, workflow_id, case_id, case_revision_id,
                        workflow_definition_version, state, run_status, workflow_version,
                        latest_checkpoint_id, latest_checkpoint_sequence, sla_deadline_at,
                        correlation_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        projection["tenant_id"],
                        projection["workflow_id"],
                        projection["case_id"],
                        projection["case_revision_id"],
                        projection["workflow_definition_version"],
                        projection["state"],
                        projection["run_status"],
                        projection["workflow_version"],
                        projection["latest_checkpoint_id"],
                        projection["latest_checkpoint_sequence"],
                        projection["sla_deadline_at"],
                        projection["correlation_id"],
                        projection["created_at"],
                        projection["updated_at"],
                    ),
                )
            connection.commit()
        except (WorkflowError, ContractValidationError):
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_journal_invalid") from error
        finally:
            connection.close()

    def get_workflow_projection(self, tenant_id: str, workflow_id: str) -> JsonObject | None:
        self.rebuild_workflow_projection()
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM workflow_projection WHERE tenant_id = ? AND workflow_id = ?",
                (tenant_id, workflow_id),
            ).fetchone()
            if row is None:
                return None
            projection = {
                "schema_id": WORKFLOW_PROJECTION_SCHEMA_ID,
                "schema_version": "v1",
                **_row_dict(row),
            }
            validate_workflow_projection(projection, self._contract_root)
            return projection
        finally:
            connection.close()

    def get_workflow_for_case(
        self,
        tenant_id: str,
        case_id: str,
        case_revision_id: str | None = None,
    ) -> JsonObject | None:
        self.rebuild_workflow_projection()
        connection = self._connect()
        try:
            query = """
                SELECT * FROM workflow_projection
                WHERE tenant_id = ? AND case_id = ?
            """
            arguments: tuple[object, ...] = (tenant_id, case_id)
            if case_revision_id is not None:
                query += " AND case_revision_id = ?"
                arguments = (*arguments, case_revision_id)
            row = connection.execute(query, arguments).fetchone()
            if row is None:
                return None
            return {
                "schema_id": WORKFLOW_PROJECTION_SCHEMA_ID,
                "schema_version": "v1",
                **_row_dict(row),
            }
        finally:
            connection.close()

    def list_workflow_checkpoints_for_case(
        self,
        tenant_id: str,
        case_id: str,
    ) -> list[JsonObject] | None:
        """Expose only canonical, tenant-scoped checkpoint records for local observation."""

        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            return None
        checkpoints = self._checkpoints(tenant_id, str(activation["workflow_id"]))
        return [dict(checkpoint["payload"]) for checkpoint in checkpoints]

    def source_counts(self, tenant_id: str) -> JsonObject:
        connection = self._connect()
        try:
            counts = {}
            for table in (*WORKFLOW_SOURCE_TABLES[1:], "workflow_projection"):
                counts[table] = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE tenant_id = ?", (tenant_id,)
                    ).fetchone()[0]
                )
            return counts
        finally:
            connection.close()

    def ticket_reconciliation_summary(self, tenant_id: str, workflow_id: str) -> JsonObject:
        """Return only synthetic natural-key/version evidence for acceptance reports."""

        connection = self._connect()
        try:
            activation = connection.execute(
                """
                SELECT case_id, case_revision_id
                FROM workflow_activations
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            if activation is None:
                raise WorkflowNotFound("workflow_not_found")
            natural_key = f"{tenant_id}:{activation['case_id']}:{activation['case_revision_id']}"
            ticket = self._latest_ticket(connection, tenant_id, natural_key)
            operations = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM fixture_ticket_operations
                    WHERE tenant_id = ? AND natural_key = ?
                    """,
                    (tenant_id, natural_key),
                ).fetchone()[0]
            )
            return {
                "natural_key": natural_key,
                "ticket_present": ticket is not None,
                "ticket_id": None if ticket is None else ticket["ticket_id"],
                "ticket_version": None if ticket is None else ticket["version"],
                "operation_count": operations,
            }
        finally:
            connection.close()

    @staticmethod
    def _investigation_manifest_payload(row: Mapping[str, Any]) -> JsonObject:
        try:
            evidence_references = json.loads(str(row["evidence_references_json"]))
        except json.JSONDecodeError as error:
            raise WorkflowError("investigation_journal_invalid") from error
        if not isinstance(evidence_references, list) or not all(
            isinstance(item, str) and item for item in evidence_references
        ):
            raise WorkflowError("investigation_journal_invalid")
        return {
            "schema_id": CONTEXT_MANIFEST_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": row["tenant_id"],
            "case_id": row["case_id"],
            "case_revision_id": row["case_revision_id"],
            "workflow_id": row["workflow_id"],
            "checkpoint_id": row["checkpoint_id"],
            "context_manifest_id": row["context_manifest_id"],
            "context_sha256": row["context_sha256"],
            "environment_snapshot_sha256": row["environment_snapshot_sha256"],
            "evidence_references": evidence_references,
            "action_budget": row["action_budget"],
            "tool_budget": row["tool_budget"],
            "no_progress_limit": row["no_progress_limit"],
            "created_at": row["created_at"],
        }

    def _investigation_activation(self, tenant_id: str, workflow_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM investigation_activations WHERE tenant_id = ? AND workflow_id = ?",
                (tenant_id, workflow_id),
            ).fetchone()
            if row is None:
                return None
            record = _row_dict(row)
            record["manifest"] = self._investigation_manifest_payload(record)
            return record
        finally:
            connection.close()

    def _require_investigation(
        self, tenant_id: str, case_id: str
    ) -> tuple[JsonObject, JsonObject, JsonObject]:
        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            raise WorkflowNotFound("workflow_not_found")
        investigation = self._investigation_activation(tenant_id, str(activation["workflow_id"]))
        if investigation is None:
            raise WorkflowError("investigation_not_found")
        projection = self.get_workflow_projection(tenant_id, str(activation["workflow_id"]))
        if projection is None:
            raise WorkflowNotFound("workflow_not_found")
        return activation, investigation, projection

    @staticmethod
    def _require_manifest_link(
        payload: Mapping[str, Any], manifest: Mapping[str, Any], name: str
    ) -> None:
        for field in (
            "tenant_id",
            "case_id",
            "case_revision_id",
            "workflow_id",
            "checkpoint_id",
            "context_manifest_id",
        ):
            if payload.get(field) != manifest.get(field):
                reason = (
                    "tenant_identity_mismatch" if field == "tenant_id" else "causation_mismatch"
                )
                raise WorkflowError(f"{name}_{reason}")

    def begin_investigation(
        self,
        tenant_id: str,
        case_id: str,
        context_manifest: Mapping[str, Any],
        *,
        transcript_id: str,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject:
        """Persist one Context Manifest before the workflow enters investigation."""

        if not isinstance(transcript_id, str) or not transcript_id:
            raise WorkflowError("investigation_transcript_invalid")
        try:
            validate_context_manifest(context_manifest, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("context_manifest_invalid") from error
        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            raise WorkflowNotFound("workflow_not_found")
        workflow_id = str(activation["workflow_id"])
        manifest = dict(context_manifest)
        for field in ("tenant_id", "case_id", "case_revision_id", "workflow_id"):
            if manifest[field] != activation[field]:
                raise WorkflowError(
                    "tenant_identity_mismatch" if field == "tenant_id" else "causation_mismatch"
                )
        existing = self._investigation_activation(tenant_id, workflow_id)
        if existing is not None:
            existing_manifest = existing["manifest"]
            if (
                existing_manifest["context_manifest_id"] != manifest["context_manifest_id"]
                or existing_manifest["context_sha256"] != manifest["context_sha256"]
                or existing["transcript_id"] != transcript_id
            ):
                raise WorkflowError("investigation_activation_conflict")
        else:
            checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
            if checkpoint is None or checkpoint["payload"]["current_state"] != TICKET_READY:
                raise WorkflowError("investigation_predecessor_invalid")
            if manifest["checkpoint_id"] != checkpoint["payload"]["checkpoint_id"]:
                raise WorkflowError("investigation_checkpoint_mismatch")
            investigation_id = _stable_identifier(
                "investigation",
                {
                    "workflow_id": workflow_id,
                    "context_manifest_id": manifest["context_manifest_id"],
                    "context_sha256": manifest["context_sha256"],
                },
            )
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO investigation_activations (
                        tenant_id, investigation_id, workflow_id, checkpoint_id, case_id,
                        case_revision_id, context_manifest_id, context_sha256,
                        environment_snapshot_sha256, evidence_references_json, transcript_id,
                        action_budget, tool_budget, no_progress_limit, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        investigation_id,
                        workflow_id,
                        manifest["checkpoint_id"],
                        manifest["case_id"],
                        manifest["case_revision_id"],
                        manifest["context_manifest_id"],
                        manifest["context_sha256"],
                        manifest["environment_snapshot_sha256"],
                        _canonical_json(manifest["evidence_references"]),
                        transcript_id,
                        manifest["action_budget"],
                        manifest["tool_budget"],
                        manifest["no_progress_limit"],
                        manifest["created_at"],
                    ),
                )
                connection.commit()
            except sqlite3.DatabaseError as error:
                connection.rollback()
                raise WorkflowError("investigation_activation_failed") from error
            finally:
                connection.close()
            existing = self._investigation_activation(tenant_id, workflow_id)
            if existing is None:
                raise WorkflowError("investigation_journal_invalid")
        projection = self.get_workflow_projection(tenant_id, workflow_id)
        if projection is None:
            raise WorkflowNotFound("workflow_not_found")
        if projection["state"] == TICKET_READY:
            checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
            if checkpoint is None:
                raise WorkflowError("investigation_journal_invalid")
            self._transition(
                activation,
                checkpoint,
                transition_kind=INVESTIGATION_STARTED,
                next_state=INVESTIGATING,
                resume_state=INVESTIGATING,
                causation_event_id=f"investigation:{existing['investigation_id']}",
                fault_profile=fault_profile,
            )
        elif projection["state"] not in {INVESTIGATING, RESPONSE_READY}:
            raise WorkflowError("investigation_state_not_allowlisted")
        return dict(existing["manifest"])

    def _existing_agent_step(
        self, tenant_id: str, workflow_id: str, step_id: str
    ) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM agent_steps
                WHERE tenant_id = ? AND workflow_id = ? AND step_id = ?
                """,
                (tenant_id, workflow_id, step_id),
            ).fetchone()
            return None if row is None else _row_dict(row)
        finally:
            connection.close()

    def record_agent_action(
        self,
        tenant_id: str,
        case_id: str,
        action: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject:
        """Persist one schema-validated non-authoritative Agent action exactly once."""

        activation, investigation, projection = self._require_investigation(tenant_id, case_id)
        manifest = investigation["manifest"]
        try:
            validate_agent_action(action, self._contract_root, context_manifest=manifest)
        except ContractValidationError as error:
            raise WorkflowError("agent_action_invalid") from error
        self._require_manifest_link(action, manifest, "agent_action")
        workflow_id = str(activation["workflow_id"])
        existing = self._existing_agent_step(tenant_id, workflow_id, str(action["step_id"]))
        if existing is not None:
            if (
                existing["action_type"] != action["action_type"]
                or existing["action_sha256"] != action["action_sha256"]
                or existing["context_manifest_id"] != action["context_manifest_id"]
            ):
                raise WorkflowError("agent_step_conflict")
            return dict(action)
        if projection["state"] != INVESTIGATING:
            raise WorkflowError("investigation_state_not_allowlisted")
        agent_step_id = _stable_identifier(
            "agent_step", {"workflow_id": workflow_id, "step_id": action["step_id"]}
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO agent_steps (
                    tenant_id, agent_step_id, workflow_id, checkpoint_id,
                    context_manifest_id, step_id, action_type, action_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    agent_step_id,
                    workflow_id,
                    action["checkpoint_id"],
                    action["context_manifest_id"],
                    action["step_id"],
                    action["action_type"],
                    action["action_sha256"],
                    action["created_at"],
                ),
            )
            connection.commit()
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("agent_step_persist_failed") from error
        finally:
            connection.close()
        self._interrupt(fault_profile, "agent-action")
        return dict(action)

    def _existing_tool_result(self, tenant_id: str, tool_request_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM investigation_tool_results
                WHERE tenant_id = ? AND tool_request_id = ?
                """,
                (tenant_id, tool_request_id),
            ).fetchone()
            return None if row is None else _row_dict(row)
        finally:
            connection.close()

    def record_tool_exchange(
        self,
        tenant_id: str,
        case_id: str,
        tool_request: Mapping[str, Any],
        tool_result: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None = None,
    ) -> tuple[JsonObject, JsonObject]:
        """Persist a fixture read and redacted evidence once; no write tool exists."""

        activation, investigation, projection = self._require_investigation(tenant_id, case_id)
        manifest = investigation["manifest"]
        try:
            validate_tool_request(tool_request, self._contract_root, context_manifest=manifest)
            validate_tool_result(tool_result, self._contract_root, tool_request=tool_request)
        except ContractValidationError as error:
            raise WorkflowError("investigation_tool_contract_invalid") from error
        self._require_manifest_link(tool_request, manifest, "tool_request")
        self._require_manifest_link(tool_result, manifest, "tool_result")
        existing_result = self._existing_tool_result(
            tenant_id, str(tool_request["tool_request_id"])
        )
        if existing_result is not None:
            if (
                existing_result["content_sha256"] != tool_result["content_sha256"]
                or existing_result["evidence_id"] != tool_result["evidence_id"]
                or existing_result["context_manifest_id"] != tool_result["context_manifest_id"]
            ):
                raise WorkflowError("tool_result_conflict")
            return dict(tool_request), dict(tool_result)
        if projection["state"] != INVESTIGATING:
            raise WorkflowError("investigation_state_not_allowlisted")
        workflow_id = str(activation["workflow_id"])
        action = self._existing_agent_step(tenant_id, workflow_id, str(tool_request["step_id"]))
        expected_action = f"read_{tool_request['tool_name']}"
        if action is None or action["action_type"] != expected_action:
            raise WorkflowError("tool_request_action_mismatch")
        connection = self._connect()
        try:
            tool_count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {INVESTIGATION_TOOL_REQUESTS_TABLE} "
                    "WHERE tenant_id = ? AND workflow_id = ?",
                    (tenant_id, workflow_id),
                ).fetchone()[0]
            )
            if tool_count >= int(manifest["tool_budget"]):
                raise WorkflowError("investigation_tool_budget_exceeded")
            connection.execute("BEGIN IMMEDIATE")
            existing_request = connection.execute(
                f"""
                SELECT request_sha256, tool_name, context_manifest_id
                FROM {INVESTIGATION_TOOL_REQUESTS_TABLE}
                WHERE tenant_id = ? AND tool_request_id = ?
                """,
                (tenant_id, tool_request["tool_request_id"]),
            ).fetchone()
            if existing_request is None:
                connection.execute(
                    f"""
                    INSERT INTO {INVESTIGATION_TOOL_REQUESTS_TABLE} (
                        tenant_id, tool_request_id, workflow_id, checkpoint_id,
                        context_manifest_id, step_id, tool_name, request_sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        tool_request["tool_request_id"],
                        workflow_id,
                        tool_request["checkpoint_id"],
                        tool_request["context_manifest_id"],
                        tool_request["step_id"],
                        tool_request["tool_name"],
                        tool_request["request_sha256"],
                        tool_request["created_at"],
                    ),
                )
            elif (
                existing_request["request_sha256"] != tool_request["request_sha256"]
                or existing_request["tool_name"] != tool_request["tool_name"]
                or existing_request["context_manifest_id"] != tool_request["context_manifest_id"]
            ):
                raise WorkflowError("tool_request_conflict")
            connection.execute(
                """
                INSERT INTO investigation_tool_results (
                    tenant_id, tool_result_id, workflow_id, checkpoint_id,
                    context_manifest_id, tool_name, tool_request_id, evidence_id,
                    content_sha256, redaction_classification, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    tool_result["tool_result_id"],
                    workflow_id,
                    tool_result["checkpoint_id"],
                    tool_result["context_manifest_id"],
                    tool_result["tool_name"],
                    tool_result["tool_request_id"],
                    tool_result["evidence_id"],
                    tool_result["content_sha256"],
                    tool_result["redaction_classification"],
                    tool_result["recorded_at"],
                ),
            )
            connection.commit()
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("tool_result_persist_failed") from error
        finally:
            connection.close()
        self._interrupt(fault_profile, "tool-result")
        return dict(tool_request), dict(tool_result)

    def _candidate_payload(
        self, activation: Mapping[str, Any], row: Mapping[str, Any]
    ) -> JsonObject:
        try:
            evidence_hashes = json.loads(str(row["evidence_hashes_json"]))
        except json.JSONDecodeError as error:
            raise WorkflowError("investigation_journal_invalid") from error
        if not isinstance(evidence_hashes, list):
            raise WorkflowError("investigation_journal_invalid")
        return {
            "schema_id": RESPONSE_CANDIDATE_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": row["tenant_id"],
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": row["workflow_id"],
            "checkpoint_id": row["checkpoint_id"],
            "context_manifest_id": row["context_manifest_id"],
            "candidate_id": row["candidate_id"],
            "context_sha256": row["context_sha256"],
            "evidence_hashes": evidence_hashes,
            "candidate_sha256": row["candidate_sha256"],
            "risk": row["risk"],
            "next_step": row["next_step"],
            "created_at": row["created_at"],
        }

    def record_response_candidate(
        self,
        tenant_id: str,
        case_id: str,
        candidate: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject:
        """Persist an evidence-bound internal candidate without approval or delivery."""

        activation, investigation, projection = self._require_investigation(tenant_id, case_id)
        manifest = investigation["manifest"]
        try:
            validate_response_candidate(candidate, self._contract_root, context_manifest=manifest)
        except ContractValidationError as error:
            raise WorkflowError("response_candidate_invalid") from error
        self._require_manifest_link(candidate, manifest, "response_candidate")
        workflow_id = str(activation["workflow_id"])
        connection = self._connect()
        try:
            existing = connection.execute(
                """
                SELECT * FROM investigation_candidates
                WHERE tenant_id = ? AND candidate_id = ?
                """,
                (tenant_id, candidate["candidate_id"]),
            ).fetchone()
            if existing is not None:
                existing_payload = self._candidate_payload(activation, _row_dict(existing))
                if existing_payload["candidate_sha256"] != candidate["candidate_sha256"]:
                    raise WorkflowError("response_candidate_conflict")
                return existing_payload
            if projection["state"] != INVESTIGATING:
                raise WorkflowError("investigation_state_not_allowlisted")
            response_action_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM agent_steps
                    WHERE tenant_id = ? AND workflow_id = ? AND action_type = 'response_candidate'
                    """,
                    (tenant_id, workflow_id),
                ).fetchone()[0]
            )
            if response_action_count != 1:
                raise WorkflowError("response_candidate_action_missing")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO investigation_candidates (
                    tenant_id, candidate_id, workflow_id, checkpoint_id,
                    context_manifest_id, context_sha256, evidence_hashes_json,
                    candidate_sha256, risk, next_step, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    candidate["candidate_id"],
                    workflow_id,
                    candidate["checkpoint_id"],
                    candidate["context_manifest_id"],
                    candidate["context_sha256"],
                    _canonical_json(candidate["evidence_hashes"]),
                    candidate["candidate_sha256"],
                    candidate["risk"],
                    candidate["next_step"],
                    candidate["created_at"],
                ),
            )
            connection.commit()
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("response_candidate_persist_failed") from error
        finally:
            connection.close()
        self._interrupt(fault_profile, "candidate")
        return dict(candidate)

    def _verifier_outcome_payload(
        self, activation: Mapping[str, Any], row: Mapping[str, Any]
    ) -> JsonObject:
        return {
            "schema_id": VERIFIER_OUTCOME_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": row["tenant_id"],
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": row["workflow_id"],
            "checkpoint_id": row["checkpoint_id"],
            "context_manifest_id": row["context_manifest_id"],
            "verifier_outcome_id": row["verifier_outcome_id"],
            "candidate_id": row["candidate_id"],
            "candidate_sha256": row["candidate_sha256"],
            "outcome": row["outcome"],
            "reason_code": row["reason_code"],
            "recorded_at": row["recorded_at"],
        }

    def _deterministic_verifier_reason(
        self,
        tenant_id: str,
        workflow_id: str,
        manifest: Mapping[str, Any],
        candidate: Mapping[str, Any],
    ) -> tuple[str, str]:
        connection = self._connect()
        try:
            steps = [
                _row_dict(row)
                for row in connection.execute(
                    """
                    SELECT step_id, action_type FROM agent_steps
                    WHERE tenant_id = ? AND workflow_id = ? ORDER BY rowid ASC
                    """,
                    (tenant_id, workflow_id),
                ).fetchall()
            ]
            results = [
                _row_dict(row)
                for row in connection.execute(
                    """
                    SELECT tool_name, content_sha256, redaction_classification, context_manifest_id
                    FROM investigation_tool_results
                    WHERE tenant_id = ? AND workflow_id = ? ORDER BY rowid ASC
                    """,
                    (tenant_id, workflow_id),
                ).fetchall()
            ]
        finally:
            connection.close()
        if len(steps) > int(manifest["action_budget"]):
            return "rejected", "action_budget_exceeded"
        if len(results) > int(manifest["tool_budget"]):
            return "rejected", "tool_budget_exceeded"
        if not steps or steps[-1]["action_type"] != "response_candidate":
            return "rejected", "response_candidate_action_missing"
        if any(
            result["context_manifest_id"] != manifest["context_manifest_id"] for result in results
        ):
            return "rejected", "evidence_context_mismatch"
        if any(result["redaction_classification"] != "synthetic" for result in results):
            return "rejected", "evidence_redaction_invalid"
        required_tools = ("crm", "monitoring", "knowledge")
        if tuple(result["tool_name"] for result in results) != required_tools:
            return "rejected", "required_evidence_missing"
        evidence_hashes = [str(result["content_sha256"]) for result in results]
        if list(candidate["evidence_hashes"]) != evidence_hashes:
            return "rejected", "evidence_reference_mismatch"
        if candidate["context_sha256"] != manifest["context_sha256"]:
            return "rejected", "context_hash_mismatch"
        return "verified", "evidence_complete"

    def _advance_verified_candidate(
        self,
        activation: Mapping[str, Any],
        verifier_outcome: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject | None:
        if verifier_outcome.get("outcome") != "verified":
            return self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        checkpoint = self._latest_checkpoint(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        if checkpoint is None:
            raise WorkflowError("investigation_journal_invalid")
        state = checkpoint["payload"]["current_state"]
        if state == RESPONSE_READY:
            return self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        if state != INVESTIGATING:
            raise WorkflowError("investigation_state_not_allowlisted")
        self._transition(
            activation,
            checkpoint,
            transition_kind=RESPONSE_CANDIDATE_VERIFIED,
            next_state=RESPONSE_READY,
            resume_state=RESPONSE_READY,
            causation_event_id=f"verifier:{verifier_outcome['verifier_outcome_id']}",
            fault_profile=fault_profile,
        )
        return self.get_workflow_projection(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )

    def verify_response_candidate(
        self,
        tenant_id: str,
        case_id: str,
        candidate_id: str,
        *,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject:
        """Compute and persist a verifier decision; callers cannot supply the decision."""

        activation, investigation, _ = self._require_investigation(tenant_id, case_id)
        workflow_id = str(activation["workflow_id"])
        connection = self._connect()
        try:
            candidate_row = connection.execute(
                """
                SELECT * FROM investigation_candidates
                WHERE tenant_id = ? AND workflow_id = ? AND candidate_id = ?
                """,
                (tenant_id, workflow_id, candidate_id),
            ).fetchone()
            if candidate_row is None:
                raise WorkflowError("response_candidate_not_found")
            candidate = self._candidate_payload(activation, _row_dict(candidate_row))
            existing_row = connection.execute(
                """
                SELECT * FROM investigation_verifier_outcomes
                WHERE tenant_id = ? AND candidate_id = ?
                """,
                (tenant_id, candidate_id),
            ).fetchone()
        finally:
            connection.close()
        try:
            validate_response_candidate(
                candidate,
                self._contract_root,
                context_manifest=investigation["manifest"],
            )
        except ContractValidationError as error:
            raise WorkflowError("response_candidate_invalid") from error
        if existing_row is not None:
            outcome = self._verifier_outcome_payload(activation, _row_dict(existing_row))
            self._advance_verified_candidate(activation, outcome, fault_profile=fault_profile)
            return outcome
        decision, reason_code = self._deterministic_verifier_reason(
            tenant_id, workflow_id, investigation["manifest"], candidate
        )
        verifier_outcome_id = _stable_identifier(
            "verifier_outcome",
            {
                "workflow_id": workflow_id,
                "candidate_id": candidate["candidate_id"],
                "candidate_sha256": candidate["candidate_sha256"],
                "outcome": decision,
            },
        )
        outcome = {
            "schema_id": VERIFIER_OUTCOME_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": tenant_id,
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": workflow_id,
            "checkpoint_id": candidate["checkpoint_id"],
            "context_manifest_id": candidate["context_manifest_id"],
            "verifier_outcome_id": verifier_outcome_id,
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": candidate["candidate_sha256"],
            "outcome": decision,
            "reason_code": reason_code,
            "recorded_at": self._now(),
        }
        try:
            validate_verifier_outcome(outcome, self._contract_root, candidate=candidate)
        except ContractValidationError as error:
            raise WorkflowError("verifier_outcome_invalid") from error
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO investigation_verifier_outcomes (
                    tenant_id, verifier_outcome_id, workflow_id, checkpoint_id,
                    context_manifest_id, candidate_id, candidate_sha256, outcome,
                    reason_code, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    outcome["verifier_outcome_id"],
                    workflow_id,
                    outcome["checkpoint_id"],
                    outcome["context_manifest_id"],
                    outcome["candidate_id"],
                    outcome["candidate_sha256"],
                    outcome["outcome"],
                    outcome["reason_code"],
                    outcome["recorded_at"],
                ),
            )
            connection.commit()
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("verifier_outcome_persist_failed") from error
        finally:
            connection.close()
        self._interrupt(fault_profile, "verifier")
        self._advance_verified_candidate(activation, outcome, fault_profile=fault_profile)
        return outcome

    def _recover_investigation(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> JsonObject | None:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        investigation = self._investigation_activation(tenant_id, workflow_id)
        if investigation is None:
            return self.get_workflow_projection(tenant_id, workflow_id)
        state = str(checkpoint["payload"]["current_state"])
        if state == TICKET_READY:
            self._transition(
                activation,
                checkpoint,
                transition_kind=INVESTIGATION_STARTED,
                next_state=INVESTIGATING,
                resume_state=INVESTIGATING,
                causation_event_id=f"investigation:{investigation['investigation_id']}",
                fault_profile=fault_profile,
            )
            checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
            if checkpoint is None:
                raise WorkflowError("investigation_journal_invalid")
            state = str(checkpoint["payload"]["current_state"])
        if state != INVESTIGATING:
            return self.get_workflow_projection(tenant_id, workflow_id)
        connection = self._connect()
        try:
            outcome_row = connection.execute(
                """
                SELECT * FROM investigation_verifier_outcomes
                WHERE tenant_id = ? AND workflow_id = ? AND outcome = 'verified'
                ORDER BY rowid DESC LIMIT 1
                """,
                (tenant_id, workflow_id),
            ).fetchone()
        finally:
            connection.close()
        if outcome_row is None:
            return self.get_workflow_projection(tenant_id, workflow_id)
        outcome = self._verifier_outcome_payload(activation, _row_dict(outcome_row))
        return self._advance_verified_candidate(activation, outcome, fault_profile=fault_profile)

    def investigation_facts_for_case(self, tenant_id: str, case_id: str) -> JsonObject | None:
        """Return only tenant-scoped identifiers, hashes, and safe replay capability facts."""

        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            return None
        workflow_id = str(activation["workflow_id"])
        investigation = self._investigation_activation(tenant_id, workflow_id)
        if investigation is None:
            return None
        connection = self._connect()
        try:
            steps = [
                {
                    "step_id": row["step_id"],
                    "action_type": row["action_type"],
                    "action_sha256": row["action_sha256"],
                    "created_at": row["created_at"],
                }
                for row in connection.execute(
                    """
                    SELECT step_id, action_type, action_sha256, created_at FROM agent_steps
                    WHERE tenant_id = ? AND workflow_id = ? ORDER BY rowid ASC
                    """,
                    (tenant_id, workflow_id),
                ).fetchall()
            ]
            tools = [
                {
                    "tool_name": row["tool_name"],
                    "evidence_id": row["evidence_id"],
                    "content_sha256": row["content_sha256"],
                    "redaction_classification": row["redaction_classification"],
                    "recorded_at": row["recorded_at"],
                }
                for row in connection.execute(
                    """
                    SELECT tool_name, evidence_id, content_sha256,
                           redaction_classification, recorded_at
                    FROM investigation_tool_results
                    WHERE tenant_id = ? AND workflow_id = ? ORDER BY rowid ASC
                    """,
                    (tenant_id, workflow_id),
                ).fetchall()
            ]
            candidate_row = connection.execute(
                """
                SELECT * FROM investigation_candidates
                WHERE tenant_id = ? AND workflow_id = ? ORDER BY rowid DESC LIMIT 1
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            verifier_row = connection.execute(
                """
                SELECT * FROM investigation_verifier_outcomes
                WHERE tenant_id = ? AND workflow_id = ? ORDER BY rowid DESC LIMIT 1
                """,
                (tenant_id, workflow_id),
            ).fetchone()
        finally:
            connection.close()
        return {
            "workflow_id": workflow_id,
            "context_manifest": dict(investigation["manifest"]),
            "agent_steps": steps,
            "tool_evidence": tools,
            "response_candidate": None
            if candidate_row is None
            else self._candidate_payload(activation, _row_dict(candidate_row)),
            "verifier_outcome": None
            if verifier_row is None
            else self._verifier_outcome_payload(activation, _row_dict(verifier_row)),
            "model_invocation": False,
            "external_write": False,
            "approval": False,
            "outbound_delivery": False,
            "customer_resolution": False,
        }

    def export_investigation_inspection(self, tenant_id: str, case_id: str) -> JsonObject | None:
        """Export a content-addressed investigation-only snapshot with no ledger payloads."""

        facts = self.investigation_facts_for_case(tenant_id, case_id)
        if facts is None:
            return None
        projection = self.get_workflow_for_case(tenant_id, case_id)
        if projection is None:
            raise WorkflowError("workflow_not_found")
        data = {
            "inspection_schema_version": "weflow-investigation-inspection.v1",
            "tenant_id": tenant_id,
            "case_id": case_id,
            "workflow_id": facts["workflow_id"],
            "workflow_state": projection["state"],
            "context_manifest": facts["context_manifest"],
            "agent_steps": facts["agent_steps"],
            "tool_evidence": facts["tool_evidence"],
            "response_candidate": facts["response_candidate"],
            "verifier_outcome": facts["verifier_outcome"],
            "model_invocation": False,
            "external_write": False,
            "approval": False,
            "outbound_delivery": False,
            "customer_resolution": False,
        }
        return {**data, "content_sha256": _sha256(data)}

    @staticmethod
    def _change4_payload(row: Mapping[str, Any], name: str) -> JsonObject:
        try:
            payload = json.loads(str(row["payload_json"]))
        except (KeyError, json.JSONDecodeError) as error:
            raise WorkflowError("policy_journal_invalid") from error
        if not isinstance(payload, dict):
            raise WorkflowError("policy_journal_invalid")
        return payload

    def _checkpoint_by_id(self, tenant_id: str, checkpoint_id: str) -> JsonObject:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM workflow_checkpoints WHERE tenant_id = ? AND checkpoint_id = ?",
                (tenant_id, checkpoint_id),
            ).fetchone()
            if row is None:
                raise WorkflowError("workflow_journal_invalid")
            record = _row_dict(row)
            record["payload"] = self._checkpoint_payload(record)
            return record
        finally:
            connection.close()

    def _policy_activation_for_workflow(
        self, tenant_id: str, workflow_id: str
    ) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM policy_approval_activations
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            return None if row is None else _row_dict(row)
        finally:
            connection.close()

    def _grant_for_workflow(self, tenant_id: str, workflow_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM capability_grants
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            return None if row is None else self._change4_payload(_row_dict(row), "grant")
        finally:
            connection.close()

    def _grant_is_active(self, tenant_id: str, grant_id: str) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT 1 FROM capability_grant_status_events
                WHERE tenant_id = ? AND grant_id = ?
                """,
                (tenant_id, grant_id),
            ).fetchone()
            return row is None
        finally:
            connection.close()

    def _policy_decision_for_workflow(self, tenant_id: str, workflow_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM policy_decisions
                WHERE tenant_id = ? AND workflow_id = ?
                  AND action = 'outbound_delivery.execute'
                ORDER BY rowid DESC LIMIT 1
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            return None if row is None else self._change4_payload(_row_dict(row), "policy")
        finally:
            connection.close()

    def _authorization_binding_for_workflow(
        self, tenant_id: str, workflow_id: str
    ) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM authorization_bindings
                WHERE tenant_id = ? AND workflow_id = ?
                ORDER BY rowid DESC LIMIT 1
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            return None if row is None else self._change4_payload(_row_dict(row), "binding")
        finally:
            connection.close()

    def _approval_request_for_workflow(self, tenant_id: str, workflow_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM approval_requests
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            return (
                None if row is None else self._change4_payload(_row_dict(row), "approval-request")
            )
        finally:
            connection.close()

    def _approval_decision_for_request(
        self, tenant_id: str, approval_request_id: str
    ) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM approval_decisions
                WHERE tenant_id = ? AND approval_request_id = ?
                """,
                (tenant_id, approval_request_id),
            ).fetchone()
            return (
                None if row is None else self._change4_payload(_row_dict(row), "approval-decision")
            )
        finally:
            connection.close()

    def _change4_candidate_material(
        self, activation: Mapping[str, Any]
    ) -> tuple[JsonObject, list[str]]:
        facts = self.investigation_facts_for_case(
            str(activation["tenant_id"]), str(activation["case_id"])
        )
        if facts is None:
            raise WorkflowError("policy_continuation_predecessor_invalid")
        candidate = facts.get("response_candidate")
        outcome = facts.get("verifier_outcome")
        if (
            not isinstance(candidate, Mapping)
            or not isinstance(outcome, Mapping)
            or outcome.get("outcome") != "verified"
            or candidate.get("candidate_sha256") != outcome.get("candidate_sha256")
        ):
            raise WorkflowError("policy_continuation_predecessor_invalid")
        evidence_hashes = candidate.get("evidence_hashes")
        if not isinstance(evidence_hashes, list) or not evidence_hashes:
            raise WorkflowError("policy_continuation_predecessor_invalid")
        return dict(candidate), [str(item) for item in evidence_hashes]

    def _ensure_policy_approval_activation(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
    ) -> JsonObject:
        """Persist the explicit Change 4 opt-in; old RESPONSE_READY replays never call it."""

        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        current = checkpoint["payload"]
        if current["current_state"] != RESPONSE_READY:
            existing = self._policy_activation_for_workflow(tenant_id, workflow_id)
            if existing is None:
                raise WorkflowError("policy_continuation_not_available")
            return existing
        fixture = api_503_policy_fixture(self._clock())
        if tenant_id != fixture["tenant_id"]:
            raise WorkflowError("policy_fixture_tenant_denied")
        candidate, evidence_hashes = self._change4_candidate_material(activation)
        controller_subject_id = "fixture-controller-alpha"
        record = {
            "tenant_id": tenant_id,
            "policy_approval_activation_id": _stable_identifier(
                "policy_approval_activation",
                {"workflow_id": workflow_id, "fixture_id": API_503_POLICY_FIXTURE_ID},
            ),
            "workflow_id": workflow_id,
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "source_checkpoint_id": current["checkpoint_id"],
            "fixture_id": API_503_POLICY_FIXTURE_ID,
            "policy_version": fixture["policy_version"],
            "delivery_resource_id": fixture["delivery_resource_id"],
            "delivery_resource_scope": fixture["delivery_resource_scope"],
            "data_classification": fixture["data_classification"],
            "delivery_budget": fixture["delivery_budget"],
            "controller_subject_id": controller_subject_id,
            "controller_role": FIXTURE_CONTROLLER_ROLE,
            "candidate_hash": candidate["candidate_sha256"],
            "evidence_hashes_json": _canonical_json(evidence_hashes),
            "activated_at": self._now(),
        }
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM policy_approval_activations
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            if existing is not None:
                existing_record = _row_dict(existing)
                for field in (
                    "source_checkpoint_id",
                    "fixture_id",
                    "candidate_hash",
                    "evidence_hashes_json",
                    "delivery_resource_id",
                    "data_classification",
                ):
                    if existing_record[field] != record[field]:
                        raise WorkflowError("policy_activation_conflict")
                connection.commit()
                return existing_record
            connection.execute(
                """
                INSERT INTO policy_approval_activations (
                    tenant_id, policy_approval_activation_id, workflow_id, case_id,
                    case_revision_id, source_checkpoint_id, fixture_id, policy_version,
                    delivery_resource_id, delivery_resource_scope, data_classification,
                    delivery_budget, controller_subject_id, controller_role, candidate_hash,
                    evidence_hashes_json, activated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(
                    record[field]
                    for field in (
                        "tenant_id",
                        "policy_approval_activation_id",
                        "workflow_id",
                        "case_id",
                        "case_revision_id",
                        "source_checkpoint_id",
                        "fixture_id",
                        "policy_version",
                        "delivery_resource_id",
                        "delivery_resource_scope",
                        "data_classification",
                        "delivery_budget",
                        "controller_subject_id",
                        "controller_role",
                        "candidate_hash",
                        "evidence_hashes_json",
                        "activated_at",
                    )
                ),
            )
            connection.commit()
            return record
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("policy_activation_persist_failed") from error
        finally:
            connection.close()

    def _ensure_fixture_grant(
        self, activation: Mapping[str, Any], policy_activation: Mapping[str, Any]
    ) -> JsonObject:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        existing = self._grant_for_workflow(tenant_id, workflow_id)
        if existing is not None:
            return existing
        grant = issue_fixture_grant(
            tenant_id=tenant_id,
            subject_id=str(policy_activation["controller_subject_id"]),
            role=str(policy_activation["controller_role"]),
            now=self._clock(),
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = connection.execute(
                "SELECT * FROM capability_grants WHERE tenant_id = ? AND workflow_id = ?",
                (tenant_id, workflow_id),
            ).fetchone()
            if existing_row is not None:
                connection.commit()
                return self._change4_payload(_row_dict(existing_row), "grant")
            connection.execute(
                """
                INSERT INTO capability_grants (
                    tenant_id, grant_id, workflow_id, grant_sha256, grant_version,
                    subject_id, role, resource_scope, data_classifications_json,
                    issued_at, expires_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    grant["grant_id"],
                    workflow_id,
                    grant["grant_sha256"],
                    grant["grant_version"],
                    grant["subject_id"],
                    grant["role"],
                    grant["resource_scope"],
                    _canonical_json(grant["data_classifications"]),
                    grant["issued_at"],
                    grant["expires_at"],
                    _canonical_json(grant),
                ),
            )
            connection.commit()
            return grant
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("capability_grant_persist_failed") from error
        finally:
            connection.close()

    def _ensure_policy_decision(
        self,
        activation: Mapping[str, Any],
        policy_activation: Mapping[str, Any],
        grant: Mapping[str, Any],
    ) -> JsonObject:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        candidate, evidence_hashes = self._change4_candidate_material(activation)
        decision = evaluate_fixture_policy(
            tenant_id=tenant_id,
            subject_id=str(policy_activation["controller_subject_id"]),
            role=str(policy_activation["controller_role"]),
            action="outbound_delivery.execute",
            case_id=str(activation["case_id"]),
            case_revision_id=str(activation["case_revision_id"]),
            workflow_id=workflow_id,
            checkpoint_id=str(policy_activation["source_checkpoint_id"]),
            workflow_version=int(
                self._checkpoint_by_id(tenant_id, str(policy_activation["source_checkpoint_id"]))[
                    "payload"
                ]["workflow_version"]
            ),
            candidate_hash=str(candidate["candidate_sha256"]),
            evidence_hashes=evidence_hashes,
            grant=grant if self._grant_is_active(tenant_id, str(grant["grant_id"])) else None,
            resource_id=str(policy_activation["delivery_resource_id"]),
            data_classification=str(policy_activation["data_classification"]),
            remaining_budget=int(policy_activation["delivery_budget"]),
            now=self._clock(),
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM policy_decisions
                WHERE tenant_id = ? AND workflow_id = ? AND action = ?
                  AND policy_input_sha256 = ?
                """,
                (tenant_id, workflow_id, decision["action"], decision["policy_input_sha256"]),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._change4_payload(_row_dict(existing), "policy")
            connection.execute(
                """
                INSERT INTO policy_decisions (
                    tenant_id, policy_decision_id, workflow_id, checkpoint_id, action,
                    policy_decision_sha256, policy_input_sha256, decision, reason_code,
                    policy_version, grant_id, grant_sha256, candidate_hash,
                    evidence_hashes_json, subject_id, role, resource_id,
                    data_classification, workflow_version, payload_json, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    decision["policy_decision_id"],
                    workflow_id,
                    decision["checkpoint_id"],
                    decision["action"],
                    decision["policy_decision_sha256"],
                    decision["policy_input_sha256"],
                    decision["decision"],
                    decision["reason_code"],
                    decision["policy_version"],
                    decision["grant_id"],
                    decision["grant_sha256"],
                    decision["candidate_hash"],
                    _canonical_json(decision["evidence_hashes"]),
                    decision["subject_id"],
                    decision["role"],
                    decision["resource_id"],
                    decision["data_classification"],
                    decision["workflow_version"],
                    _canonical_json(decision),
                    decision["decided_at"],
                ),
            )
            connection.commit()
            return decision
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("policy_decision_persist_failed") from error
        finally:
            connection.close()

    def _ensure_authorization_binding(
        self,
        activation: Mapping[str, Any],
        policy_activation: Mapping[str, Any],
        grant: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> JsonObject:
        if decision.get("decision") != "allow":
            raise WorkflowError("policy_denied")
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        binding = bind_fixture_authorization(
            decision=decision,
            grant=grant,
            remaining_budget=int(policy_activation["delivery_budget"]),
            expires_at=self._clock() + timedelta(minutes=15),
            created_at=self._clock(),
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM authorization_bindings WHERE tenant_id = ? AND workflow_id = ?",
                (tenant_id, workflow_id),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._change4_payload(_row_dict(existing), "binding")
            connection.execute(
                """
                INSERT INTO authorization_bindings (
                    tenant_id, authorization_binding_id, authorization_binding_sha256,
                    workflow_id, policy_decision_id, grant_id, checkpoint_id,
                    workflow_version, candidate_hash, evidence_hashes_json, expires_at,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    binding["authorization_binding_id"],
                    binding["authorization_binding_sha256"],
                    workflow_id,
                    binding["policy_decision_id"],
                    binding["grant_id"],
                    binding["checkpoint_id"],
                    binding["workflow_version"],
                    binding["candidate_hash"],
                    _canonical_json(binding["evidence_hashes"]),
                    binding["expires_at"],
                    _canonical_json(binding),
                    binding["created_at"],
                ),
            )
            connection.commit()
            return binding
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("authorization_binding_persist_failed") from error
        finally:
            connection.close()

    def _ensure_approval_request(
        self, activation: Mapping[str, Any], binding: Mapping[str, Any]
    ) -> JsonObject:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        request = build_approval_request(binding, created_at=self._clock())
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM approval_requests WHERE tenant_id = ? AND workflow_id = ?",
                (tenant_id, workflow_id),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._change4_payload(_row_dict(existing), "approval-request")
            connection.execute(
                """
                INSERT INTO approval_requests (
                    tenant_id, approval_request_id, workflow_id, authorization_binding_sha256,
                    checkpoint_id, workflow_version, payload_json, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    request["approval_request_id"],
                    workflow_id,
                    request["authorization_binding_sha256"],
                    request["checkpoint_id"],
                    request["workflow_version"],
                    _canonical_json(request),
                    request["created_at"],
                    request["expires_at"],
                ),
            )
            connection.commit()
            return request
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("approval_request_persist_failed") from error
        finally:
            connection.close()

    def activate_policy_approval(
        self,
        tenant_id: str,
        case_id: str,
        *,
        fixture_id: str = API_503_POLICY_FIXTURE_ID,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject:
        """Explicitly continue the named fixture; this is not exposed as a general API action."""

        if fixture_id != API_503_POLICY_FIXTURE_ID:
            raise WorkflowError("policy_fixture_not_allowlisted")
        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            raise WorkflowNotFound("workflow_not_found")
        checkpoint = self._latest_checkpoint(tenant_id, str(activation["workflow_id"]))
        if checkpoint is None:
            raise WorkflowError("workflow_journal_invalid")
        self._ensure_policy_approval_activation(activation, checkpoint)
        return self._recover_policy_approval(activation, checkpoint, fault_profile=fault_profile)

    def _authorization_profile_is_current(
        self,
        activation: Mapping[str, Any],
        binding: Mapping[str, Any],
        decision: Mapping[str, Any],
        grant: Mapping[str, Any],
    ) -> bool:
        """Fail closed on any changed candidate, evidence, grant state, or expiry."""

        if not self._grant_is_active(str(activation["tenant_id"]), str(grant["grant_id"])):
            return False
        try:
            candidate, evidence_hashes = self._change4_candidate_material(activation)
            validate_change4_authorization_profile(
                binding,
                grant,
                decision,
                action="outbound_delivery.execute",
                current_case_revision_id=str(activation["case_revision_id"]),
                current_checkpoint_id=str(binding["checkpoint_id"]),
                current_workflow_version=int(binding["workflow_version"]),
                current_candidate_hash=str(candidate["candidate_sha256"]),
                current_evidence_hashes=evidence_hashes,
                resource_id=API_503_DELIVERY_RESOURCE_ID,
                data_classification="synthetic",
                effective_tenant_id=str(activation["tenant_id"]),
                now=self._clock(),
            )
        except (ContractValidationError, WorkflowError, KeyError, TypeError, ValueError):
            return False
        return True

    def _persist_approval_decision(
        self,
        activation: Mapping[str, Any],
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> tuple[JsonObject, bool]:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM approval_decisions
                WHERE tenant_id = ? AND approval_request_id = ?
                """,
                (tenant_id, request["approval_request_id"]),
            ).fetchone()
            if existing is not None:
                payload = self._change4_payload(_row_dict(existing), "approval-decision")
                same = (
                    payload.get("decision") == decision.get("decision")
                    and payload.get("approver_id") == decision.get("approver_id")
                    and payload.get("approver_role") == decision.get("approver_role")
                    and payload.get("decision_sha256") == decision.get("decision_sha256")
                )
                connection.commit()
                if not same:
                    raise WorkflowError("approval_decision_conflict")
                return payload, False
            connection.execute(
                """
                INSERT INTO approval_decisions (
                    tenant_id, approval_decision_id, approval_request_id, workflow_id,
                    authorization_binding_sha256, workflow_version, decision,
                    decision_sha256, approver_id, approver_role, payload_json, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    decision["approval_decision_id"],
                    request["approval_request_id"],
                    workflow_id,
                    decision["authorization_binding_sha256"],
                    decision["workflow_version"],
                    decision["decision"],
                    decision["decision_sha256"],
                    decision["approver_id"],
                    decision["approver_role"],
                    _canonical_json(decision),
                    decision["decided_at"],
                ),
            )
            connection.commit()
            return dict(decision), True
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("approval_decision_persist_failed") from error
        finally:
            connection.close()

    def _apply_persisted_approval_decision(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        request: Mapping[str, Any],
        decision: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> JsonObject:
        state = str(checkpoint["payload"]["current_state"])
        if state == WAITING_FOR_OPERATOR:
            projection = self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        if state != AWAITING_APPROVAL:
            projection = self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        if decision.get("decision") != "approved":
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=AUTHORIZATION_DENIED,
                next_state=WAITING_FOR_OPERATOR,
                resume_state=WAITING_FOR_OPERATOR,
                causation_event_id=f"approval:{decision['approval_decision_id']}",
                fault_profile=fault_profile,
            )
            projection = self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        binding = self._authorization_binding_for_workflow(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        grant = self._grant_for_workflow(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        policy = self._policy_decision_for_workflow(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        if binding is None or grant is None or policy is None:
            raise WorkflowError("policy_journal_invalid")
        if not self._authorization_profile_is_current(activation, binding, policy, grant):
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=AUTHORIZATION_DENIED,
                next_state=WAITING_FOR_OPERATOR,
                resume_state=WAITING_FOR_OPERATOR,
                causation_event_id=f"approval-invalid:{decision['approval_decision_id']}",
                fault_profile=fault_profile,
            )
            projection = self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        try:
            candidate, evidence_hashes = self._change4_candidate_material(activation)
            validate_hash_bound_approval(
                request,
                decision,
                binding,
                current_case_revision_id=str(activation["case_revision_id"]),
                current_checkpoint_id=str(binding["checkpoint_id"]),
                current_workflow_version=int(binding["workflow_version"]),
                current_candidate_hash=str(candidate["candidate_sha256"]),
                current_evidence_hashes=evidence_hashes,
                effective_tenant_id=str(activation["tenant_id"]),
                effective_approver_id=str(decision["approver_id"]),
                effective_approver_role=FIXTURE_APPROVER_ROLE,
                now=self._clock(),
            )
        except ContractValidationError:
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=AUTHORIZATION_DENIED,
                next_state=WAITING_FOR_OPERATOR,
                resume_state=WAITING_FOR_OPERATOR,
                causation_event_id=f"approval-invalid:{decision['approval_decision_id']}",
                fault_profile=fault_profile,
            )
            projection = self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        checkpoint = self._transition(
            activation,
            checkpoint,
            transition_kind=APPROVAL_GRANTED,
            next_state=DELIVERING,
            resume_state=DELIVERING,
            causation_event_id=f"approval:{decision['approval_decision_id']}",
            fault_profile=fault_profile,
        )
        return self._recover_delivery(activation, checkpoint, fault_profile=fault_profile)

    def _recover_policy_approval(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> JsonObject:
        """Resume only an already durable opt-in, never a historical ResponseReady replay."""

        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        policy_activation = self._policy_activation_for_workflow(tenant_id, workflow_id)
        if policy_activation is None:
            projection = self.get_workflow_projection(tenant_id, workflow_id)
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        grant = self._ensure_fixture_grant(activation, policy_activation)
        decision = self._ensure_policy_decision(activation, policy_activation, grant)
        self._interrupt(fault_profile, "policy")
        if decision.get("decision") != "allow":
            projection = self.get_workflow_projection(tenant_id, workflow_id)
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        binding = self._ensure_authorization_binding(activation, policy_activation, grant, decision)
        request = self._ensure_approval_request(activation, binding)
        self._interrupt(fault_profile, "approval-request")
        checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
        if checkpoint is None:
            raise WorkflowError("workflow_journal_invalid")
        state = str(checkpoint["payload"]["current_state"])
        if state == RESPONSE_READY:
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=POLICY_APPROVAL_ACTIVATED,
                next_state=AWAITING_APPROVAL,
                resume_state=AWAITING_APPROVAL,
                causation_event_id=f"approval-request:{request['approval_request_id']}",
                fault_profile=fault_profile,
            )
            state = AWAITING_APPROVAL
        if state == AWAITING_APPROVAL:
            persisted = self._approval_decision_for_request(
                tenant_id, str(request["approval_request_id"])
            )
            if persisted is None:
                projection = self.get_workflow_projection(tenant_id, workflow_id)
                if projection is None:
                    raise WorkflowError("workflow_journal_invalid")
                return projection
            return self._apply_persisted_approval_decision(
                activation, checkpoint, request, persisted, fault_profile=fault_profile
            )
        if state == DELIVERING:
            return self._recover_delivery(activation, checkpoint, fault_profile=fault_profile)
        projection = self.get_workflow_projection(tenant_id, workflow_id)
        if projection is None:
            raise WorkflowError("workflow_journal_invalid")
        return projection

    def submit_approval_decision(
        self,
        tenant_id: str,
        case_id: str,
        *,
        approval_request_id: str,
        decision: str,
        expected_workflow_version: int,
        approver_id: str,
        approver_role: str,
        fault_profile: FaultProfile | None = None,
    ) -> WorkflowCommandResult:
        """Append one fixture-role-bound decision; payloads cannot select authority."""

        if decision not in {"approved", "rejected"}:
            raise WorkflowError("approval_decision_invalid")
        if approver_role != FIXTURE_APPROVER_ROLE:
            raise WorkflowError("approval_actor_not_authorized")
        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            raise WorkflowNotFound("workflow_not_found")
        workflow_id = str(activation["workflow_id"])
        request = self._approval_request_for_workflow(tenant_id, workflow_id)
        if request is None or request.get("approval_request_id") != approval_request_id:
            raise WorkflowNotFound("workflow_not_found")
        checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
        if checkpoint is None:
            raise WorkflowError("workflow_journal_invalid")
        existing = self._approval_decision_for_request(tenant_id, approval_request_id)
        if existing is not None:
            if (
                existing.get("decision") != decision
                or existing.get("approver_id") != approver_id
                or existing.get("approver_role") != approver_role
            ):
                raise WorkflowError("approval_decision_conflict")
            projection = self._apply_persisted_approval_decision(
                activation, checkpoint, request, existing, fault_profile=fault_profile
            )
            return WorkflowCommandResult("deduplicated", projection)
        if int(checkpoint["payload"]["workflow_version"]) != expected_workflow_version:
            raise WorkflowError("workflow_version_conflict")
        if checkpoint["payload"]["current_state"] != AWAITING_APPROVAL:
            raise WorkflowError("approval_decision_not_available")
        candidate_decision = build_approval_decision(
            request,
            approver_id=approver_id,
            approver_role=approver_role,
            decision=decision,
            decided_at=self._clock(),
        )
        persisted, created = self._persist_approval_decision(
            activation, request, candidate_decision
        )
        if created:
            self._interrupt(fault_profile, "approval-decision")
        projection = self._apply_persisted_approval_decision(
            activation, checkpoint, request, persisted, fault_profile=fault_profile
        )
        return WorkflowCommandResult("accepted" if created else "deduplicated", projection)

    def revoke_fixture_grant(self, tenant_id: str, case_id: str) -> None:
        """Fixture/control-only revocation used by deterministic safety and recovery tests."""

        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            raise WorkflowNotFound("workflow_not_found")
        grant = self._grant_for_workflow(tenant_id, str(activation["workflow_id"]))
        if grant is None:
            raise WorkflowError("capability_grant_not_found")
        event_id = _stable_identifier(
            "grant_status", {"grant_id": grant["grant_id"], "status": "revoked"}
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT reason_code FROM capability_grant_status_events
                WHERE tenant_id = ? AND grant_id = ? AND status = 'revoked'
                """,
                (tenant_id, grant["grant_id"]),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO capability_grant_status_events (
                        tenant_id, grant_status_event_id, grant_id, status,
                        reason_code, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        event_id,
                        grant["grant_id"],
                        "revoked",
                        "fixture_grant_revoked",
                        self._now(),
                    ),
                )
            connection.commit()
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("capability_grant_revocation_failed") from error
        finally:
            connection.close()

    def _delivery_intent_for_workflow(self, tenant_id: str, workflow_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM outbound_delivery_intents
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            return None if row is None else self._change4_payload(_row_dict(row), "delivery-intent")
        finally:
            connection.close()

    def _delivery_observations(self, tenant_id: str, intent_id: str) -> list[JsonObject]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM outbound_delivery_observations
                WHERE tenant_id = ? AND intent_id = ?
                ORDER BY recorded_at ASC, observation_id ASC
                """,
                (tenant_id, intent_id),
            ).fetchall()
            return [self._change4_payload(_row_dict(row), "delivery-observation") for row in rows]
        finally:
            connection.close()

    def _delivery_completion_for_intent(self, tenant_id: str, intent_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM outbound_delivery_completions
                WHERE tenant_id = ? AND intent_id = ?
                """,
                (tenant_id, intent_id),
            ).fetchone()
            return (
                None
                if row is None
                else self._change4_payload(_row_dict(row), "delivery-completion")
            )
        finally:
            connection.close()

    def _pending_delivery_intent_ids(self, tenant_id: str, workflow_id: str) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT intent.intent_id
                FROM outbound_delivery_intents AS intent
                LEFT JOIN outbound_delivery_completions AS completion
                  ON completion.tenant_id = intent.tenant_id
                 AND completion.intent_id = intent.intent_id
                WHERE intent.tenant_id = ? AND intent.workflow_id = ?
                  AND completion.completion_id IS NULL
                ORDER BY intent.intent_id ASC
                """,
                (tenant_id, workflow_id),
            ).fetchall()
            return [str(row["intent_id"]) for row in rows]
        finally:
            connection.close()

    def _completed_delivery_intent_ids(self, tenant_id: str, workflow_id: str) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT intent.intent_id
                FROM outbound_delivery_intents AS intent
                JOIN outbound_delivery_completions AS completion
                  ON completion.tenant_id = intent.tenant_id
                 AND completion.intent_id = intent.intent_id
                WHERE intent.tenant_id = ? AND intent.workflow_id = ?
                ORDER BY intent.intent_id ASC
                """,
                (tenant_id, workflow_id),
            ).fetchall()
            return [str(row["intent_id"]) for row in rows]
        finally:
            connection.close()

    def _all_pending_intent_ids(self, tenant_id: str, workflow_id: str) -> list[str]:
        return sorted(
            set(self._unresolved_intent_ids(tenant_id, workflow_id))
            | set(self._pending_delivery_intent_ids(tenant_id, workflow_id))
        )

    def _all_completed_intent_ids(self, tenant_id: str, workflow_id: str) -> list[str]:
        return sorted(
            set(self._completed_intent_ids(tenant_id, workflow_id))
            | set(self._completed_delivery_intent_ids(tenant_id, workflow_id))
        )

    def _ensure_delivery_intent(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        binding: Mapping[str, Any],
    ) -> tuple[JsonObject, bool]:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        existing = self._delivery_intent_for_workflow(tenant_id, workflow_id)
        if existing is not None:
            return existing, False
        conversation_id = "conversation-api-503"
        natural_key = ":".join(
            (
                tenant_id,
                "fixture-local-im",
                conversation_id,
                str(activation["case_id"]),
                str(activation["case_revision_id"]),
                str(binding["candidate_hash"]),
                str(binding["authorization_binding_sha256"]),
            )
        )
        intended_state_hash = _sha256(
            {
                "candidate_hash": binding["candidate_hash"],
                "authorization_binding_sha256": binding["authorization_binding_sha256"],
                "delivery_resource_id": API_503_DELIVERY_RESOURCE_ID,
            }
        )
        payload: JsonObject = {
            "schema_id": OUTBOUND_DELIVERY_INTENT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": tenant_id,
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": workflow_id,
            "checkpoint_id": checkpoint["payload"]["checkpoint_id"],
            "intent_id": _stable_identifier(
                "outbound_delivery_intent", {"workflow_id": workflow_id, "natural_key": natural_key}
            ),
            "effect_kind": "fixture-local-outbound-delivery",
            "operation": "deliver",
            "channel": "fixture-local-im",
            "conversation_id": conversation_id,
            "delivery_resource_id": API_503_DELIVERY_RESOURCE_ID,
            "candidate_hash": binding["candidate_hash"],
            "authorization_binding_sha256": binding["authorization_binding_sha256"],
            "natural_key": natural_key,
            "intended_state_hash": intended_state_hash,
            "idempotency_key": stable_idempotency_key(
                tenant_id=tenant_id,
                provider_id="fixture-local-im",
                operation="deliver",
                natural_key=natural_key,
                intended_state_hash=intended_state_hash,
            ),
            "evidence_hashes": list(binding["evidence_hashes"]),
            "correlation_id": activation["correlation_id"],
            "created_at": self._now(),
        }
        try:
            validate_outbound_delivery_intent(payload, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("outbound_delivery_intent_invalid") from error
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = connection.execute(
                "SELECT * FROM outbound_delivery_intents WHERE tenant_id = ? AND workflow_id = ?",
                (tenant_id, workflow_id),
            ).fetchone()
            if existing_row is not None:
                connection.commit()
                return self._change4_payload(_row_dict(existing_row), "delivery-intent"), False
            connection.execute(
                """
                INSERT INTO outbound_delivery_intents (
                    tenant_id, intent_id, workflow_id, checkpoint_id, case_id,
                    case_revision_id, authorization_binding_sha256, candidate_hash,
                    evidence_hashes_json, channel, conversation_id, delivery_resource_id,
                    natural_key, intended_state_hash, idempotency_key, correlation_id,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    payload["intent_id"],
                    workflow_id,
                    payload["checkpoint_id"],
                    payload["case_id"],
                    payload["case_revision_id"],
                    payload["authorization_binding_sha256"],
                    payload["candidate_hash"],
                    _canonical_json(payload["evidence_hashes"]),
                    payload["channel"],
                    payload["conversation_id"],
                    payload["delivery_resource_id"],
                    payload["natural_key"],
                    payload["intended_state_hash"],
                    payload["idempotency_key"],
                    payload["correlation_id"],
                    _canonical_json(payload),
                    payload["created_at"],
                ),
            )
            connection.commit()
            return payload, True
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("outbound_delivery_intent_persist_failed") from error
        finally:
            connection.close()

    def _reconcile_delivery_intent(self, intent: Mapping[str, Any]) -> DeliveryOutcome:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT * FROM fixture_delivery_records
                WHERE tenant_id = ? AND natural_key = ?
                ORDER BY version ASC
                """,
                (intent["tenant_id"], intent["natural_key"]),
            ).fetchall()
            if not rows:
                return DeliveryOutcome("absent", None, None, None, "fixture_delivery_absent")
            if len(rows) != 1 or int(rows[0]["version"]) != 1:
                return DeliveryOutcome("conflict", None, None, None, "fixture_delivery_conflict")
            row = rows[0]
            return DeliveryOutcome(
                "present",
                str(row["delivery_id"]),
                int(row["version"]),
                str(row["content_sha256"]),
                "fixture_delivery_present",
            )
        finally:
            connection.close()

    def _execute_delivery_intent(self, intent: Mapping[str, Any]) -> DeliveryOutcome:
        """The only adapter: local SQLite records, no sockets, credentials, or raw content."""

        tenant_id = str(intent["tenant_id"])
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_operation = connection.execute(
                """
                SELECT delivery_id, observed_version, content_sha256
                FROM fixture_delivery_operations
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, intent["idempotency_key"]),
            ).fetchone()
            if existing_operation is not None:
                connection.commit()
                return DeliveryOutcome(
                    "present",
                    str(existing_operation["delivery_id"]),
                    int(existing_operation["observed_version"]),
                    str(existing_operation["content_sha256"]),
                    "fixture_delivery_idempotent",
                )
            existing_record = connection.execute(
                """
                SELECT delivery_id, version, content_sha256
                FROM fixture_delivery_records
                WHERE tenant_id = ? AND natural_key = ?
                ORDER BY version ASC
                """,
                (tenant_id, intent["natural_key"]),
            ).fetchone()
            if existing_record is not None:
                connection.commit()
                return DeliveryOutcome(
                    "present",
                    str(existing_record["delivery_id"]),
                    int(existing_record["version"]),
                    str(existing_record["content_sha256"]),
                    "fixture_delivery_reconciled",
                )
            delivery_id = _stable_identifier(
                "fixture_delivery", {"tenant_id": tenant_id, "natural_key": intent["natural_key"]}
            )
            content_sha256 = str(intent["candidate_hash"])
            connection.execute(
                """
                INSERT INTO fixture_delivery_records (
                    tenant_id, delivery_id, natural_key, version, content_sha256,
                    data_classification, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    delivery_id,
                    intent["natural_key"],
                    1,
                    content_sha256,
                    "synthetic",
                    self._now(),
                ),
            )
            connection.execute(
                """
                INSERT INTO fixture_delivery_operations (
                    tenant_id, idempotency_key, natural_key, delivery_id,
                    observed_version, content_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    intent["idempotency_key"],
                    intent["natural_key"],
                    delivery_id,
                    1,
                    content_sha256,
                    self._now(),
                ),
            )
            connection.commit()
            return DeliveryOutcome(
                "present", delivery_id, 1, content_sha256, "fixture_delivery_recorded"
            )
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("fixture_delivery_execute_failed") from error
        finally:
            connection.close()

    def _record_delivery_observation(
        self,
        intent: Mapping[str, Any],
        *,
        phase: str,
        outcome: DeliveryOutcome,
    ) -> JsonObject:
        payload: JsonObject = {
            "schema_id": OUTBOUND_DELIVERY_OBSERVATION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": intent["tenant_id"],
            "case_id": intent["case_id"],
            "case_revision_id": intent["case_revision_id"],
            "workflow_id": intent["workflow_id"],
            "checkpoint_id": intent["checkpoint_id"],
            "observation_id": _stable_identifier(
                "outbound_delivery_observation",
                {
                    "intent_id": intent["intent_id"],
                    "phase": phase,
                    "status": outcome.status,
                    "delivery_id": outcome.delivery_id,
                },
            ),
            "intent_id": intent["intent_id"],
            "status": outcome.status,
            "observed_delivery_id": outcome.delivery_id,
            "observed_version": outcome.version,
            "content_sha256": outcome.content_sha256,
            "reason_code": outcome.reason_code,
            "recorded_at": self._now(),
        }
        try:
            validate_outbound_delivery_observation(payload, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("outbound_delivery_observation_invalid") from error
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM outbound_delivery_observations
                WHERE tenant_id = ? AND observation_id = ?
                """,
                (intent["tenant_id"], payload["observation_id"]),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._change4_payload(_row_dict(existing), "delivery-observation")
            connection.execute(
                """
                INSERT INTO outbound_delivery_observations (
                    tenant_id, observation_id, intent_id, workflow_id, checkpoint_id,
                    status, observed_delivery_id, observed_version, content_sha256,
                    reason_code, payload_json, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["tenant_id"],
                    payload["observation_id"],
                    payload["intent_id"],
                    payload["workflow_id"],
                    payload["checkpoint_id"],
                    payload["status"],
                    payload["observed_delivery_id"],
                    payload["observed_version"],
                    payload["content_sha256"],
                    payload["reason_code"],
                    _canonical_json(payload),
                    payload["recorded_at"],
                ),
            )
            connection.commit()
            return payload
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("outbound_delivery_observation_persist_failed") from error
        finally:
            connection.close()

    def _record_delivery_completion(
        self, intent: Mapping[str, Any], observation: Mapping[str, Any]
    ) -> JsonObject:
        if (
            observation.get("status") != "present"
            or not isinstance(observation.get("observed_delivery_id"), str)
            or not isinstance(observation.get("observed_version"), int)
            or not isinstance(observation.get("content_sha256"), str)
        ):
            raise WorkflowError("outbound_delivery_completion_predecessor_invalid")
        payload: JsonObject = {
            "schema_id": OUTBOUND_DELIVERY_COMPLETION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": intent["tenant_id"],
            "case_id": intent["case_id"],
            "case_revision_id": intent["case_revision_id"],
            "workflow_id": intent["workflow_id"],
            "checkpoint_id": intent["checkpoint_id"],
            "completion_id": _stable_identifier(
                "outbound_delivery_completion", {"intent_id": intent["intent_id"]}
            ),
            "intent_id": intent["intent_id"],
            "observation_id": observation["observation_id"],
            "observed_delivery_id": observation["observed_delivery_id"],
            "observed_version": observation["observed_version"],
            "content_sha256": observation["content_sha256"],
            "completed_at": self._now(),
        }
        try:
            validate_outbound_delivery_completion(payload, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("outbound_delivery_completion_invalid") from error
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM outbound_delivery_completions
                WHERE tenant_id = ? AND intent_id = ?
                """,
                (intent["tenant_id"], intent["intent_id"]),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._change4_payload(_row_dict(existing), "delivery-completion")
            connection.execute(
                """
                INSERT INTO outbound_delivery_completions (
                    tenant_id, completion_id, intent_id, workflow_id, checkpoint_id,
                    observation_id, observed_delivery_id, observed_version, content_sha256,
                    payload_json, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["tenant_id"],
                    payload["completion_id"],
                    payload["intent_id"],
                    payload["workflow_id"],
                    payload["checkpoint_id"],
                    payload["observation_id"],
                    payload["observed_delivery_id"],
                    payload["observed_version"],
                    payload["content_sha256"],
                    _canonical_json(payload),
                    payload["completed_at"],
                ),
            )
            connection.commit()
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("outbound_delivery_completion_persist_failed") from error
        finally:
            connection.close()
        binding = self._authorization_binding_for_workflow(
            str(intent["tenant_id"]), str(intent["workflow_id"])
        )
        if binding is None:
            raise WorkflowError("policy_journal_invalid")
        try:
            validate_outbound_delivery_chain(
                intent,
                self._delivery_observations(str(intent["tenant_id"]), str(intent["intent_id"])),
                [payload],
                binding,
                self._contract_root,
            )
        except ContractValidationError as error:
            raise WorkflowError("outbound_delivery_chain_invalid") from error
        return payload

    def _process_delivery_intent(
        self, intent: Mapping[str, Any], *, fault_profile: FaultProfile | None
    ) -> tuple[str, JsonObject | None]:
        existing = self._delivery_completion_for_intent(
            str(intent["tenant_id"]), str(intent["intent_id"])
        )
        if existing is not None:
            return "complete", existing
        if fault_profile is not None and fault_profile.reconciliation_timeout:
            self._record_delivery_observation(
                intent,
                phase="reconcile-timeout",
                outcome=DeliveryOutcome("unknown", None, None, None, "reconciliation_timeout"),
            )
            return "blocked", None
        reconciled = self._reconcile_delivery_intent(intent)
        observation = self._record_delivery_observation(
            intent, phase="reconcile", outcome=reconciled
        )
        if reconciled.status in {"unknown", "conflict"}:
            return "blocked", None
        outcome = reconciled
        if reconciled.status == "absent":
            outcome = self._execute_delivery_intent(intent)
            self._interrupt(fault_profile, "delivery-execute")
            if outcome.status != "present":
                self._record_delivery_observation(intent, phase="execute", outcome=outcome)
                return "blocked", None
            self._interrupt(fault_profile, "delivery-lost-response")
            observation = self._record_delivery_observation(
                intent, phase="execute", outcome=outcome
            )
        if outcome.status != "present":
            return "blocked", None
        self._interrupt(fault_profile, "delivery-observation")
        completion = self._record_delivery_completion(intent, observation)
        self._interrupt(fault_profile, "delivery-completion")
        return "complete", completion

    def _authorization_denial_projection(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        reason: str,
        fault_profile: FaultProfile | None,
    ) -> JsonObject:
        if checkpoint["payload"]["current_state"] not in {AWAITING_APPROVAL, DELIVERING}:
            projection = self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        self._transition(
            activation,
            checkpoint,
            transition_kind=AUTHORIZATION_DENIED,
            next_state=WAITING_FOR_OPERATOR,
            resume_state=WAITING_FOR_OPERATOR,
            causation_event_id=f"authorization-denied:{reason}",
            fault_profile=fault_profile,
            pending_intent_ids=self._all_pending_intent_ids(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            ),
            completed_intent_ids=self._all_completed_intent_ids(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            ),
        )
        projection = self.get_workflow_projection(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        if projection is None:
            raise WorkflowError("workflow_journal_invalid")
        return projection

    def _recover_delivery(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> JsonObject:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        if checkpoint["payload"]["current_state"] != DELIVERING:
            projection = self.get_workflow_projection(tenant_id, workflow_id)
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        binding = self._authorization_binding_for_workflow(tenant_id, workflow_id)
        grant = self._grant_for_workflow(tenant_id, workflow_id)
        policy = self._policy_decision_for_workflow(tenant_id, workflow_id)
        request = self._approval_request_for_workflow(tenant_id, workflow_id)
        if binding is None or grant is None or policy is None or request is None:
            return self._authorization_denial_projection(
                activation, checkpoint, reason="missing", fault_profile=fault_profile
            )
        approval = self._approval_decision_for_request(
            tenant_id, str(request["approval_request_id"])
        )
        if approval is None or not self._authorization_profile_is_current(
            activation, binding, policy, grant
        ):
            return self._authorization_denial_projection(
                activation, checkpoint, reason="stale", fault_profile=fault_profile
            )
        try:
            candidate, evidence_hashes = self._change4_candidate_material(activation)
            validate_hash_bound_approval(
                request,
                approval,
                binding,
                current_case_revision_id=str(activation["case_revision_id"]),
                current_checkpoint_id=str(binding["checkpoint_id"]),
                current_workflow_version=int(binding["workflow_version"]),
                current_candidate_hash=str(candidate["candidate_sha256"]),
                current_evidence_hashes=evidence_hashes,
                effective_tenant_id=tenant_id,
                effective_approver_id=str(approval["approver_id"]),
                effective_approver_role=FIXTURE_APPROVER_ROLE,
                now=self._clock(),
            )
        except ContractValidationError:
            return self._authorization_denial_projection(
                activation, checkpoint, reason="approval", fault_profile=fault_profile
            )
        intent, created = self._ensure_delivery_intent(activation, checkpoint, binding)
        if created:
            self._interrupt(fault_profile, "delivery-intent")
        checkpoint = self._ensure_checkpoint(
            activation,
            current_state=DELIVERING,
            resume_state=DELIVERING,
            pending_intent_ids=self._all_pending_intent_ids(tenant_id, workflow_id),
            completed_intent_ids=self._all_completed_intent_ids(tenant_id, workflow_id),
            causation_event_id=f"delivery-intent:{intent['intent_id']}",
            transition_kind=None,
        )
        disposition, completion = self._process_delivery_intent(intent, fault_profile=fault_profile)
        if disposition != "complete" or completion is None:
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=RECONCILIATION_REQUIRED,
                next_state=NEEDS_RECONCILIATION,
                resume_state=DELIVERING,
                causation_event_id=f"delivery-reconciliation:{intent['intent_id']}",
                fault_profile=fault_profile,
                pending_intent_ids=self._all_pending_intent_ids(tenant_id, workflow_id),
                completed_intent_ids=self._all_completed_intent_ids(tenant_id, workflow_id),
            )
            projection = self.get_workflow_projection(tenant_id, workflow_id)
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        checkpoint = self._ensure_checkpoint(
            activation,
            current_state=DELIVERING,
            resume_state=DELIVERING,
            pending_intent_ids=self._all_pending_intent_ids(tenant_id, workflow_id),
            completed_intent_ids=self._all_completed_intent_ids(tenant_id, workflow_id),
            causation_event_id=f"delivery-completion:{completion['completion_id']}",
            transition_kind=None,
        )
        self._transition(
            activation,
            checkpoint,
            transition_kind=DELIVERY_COMPLETE,
            next_state=DELIVERY_RECORDED,
            resume_state=DELIVERY_RECORDED,
            causation_event_id=f"delivery-completion:{completion['completion_id']}",
            fault_profile=fault_profile,
        )
        self._interrupt(fault_profile, "delivery-transition")
        projection = self.get_workflow_projection(tenant_id, workflow_id)
        if projection is None:
            raise WorkflowError("workflow_journal_invalid")
        return projection

    def _recover_delivery_reconciliation(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> JsonObject:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        intent = self._delivery_intent_for_workflow(tenant_id, workflow_id)
        if intent is None:
            raise WorkflowError("policy_journal_invalid")
        disposition, completion = self._process_delivery_intent(intent, fault_profile=fault_profile)
        if disposition != "complete" or completion is None:
            projection = self.get_workflow_projection(tenant_id, workflow_id)
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return projection
        checkpoint = self._transition(
            activation,
            checkpoint,
            transition_kind=RECONCILIATION_COMPLETE,
            next_state=DELIVERING,
            resume_state=DELIVERING,
            causation_event_id=f"delivery-reconciled:{completion['completion_id']}",
            fault_profile=fault_profile,
            pending_intent_ids=self._all_pending_intent_ids(tenant_id, workflow_id),
            completed_intent_ids=self._all_completed_intent_ids(tenant_id, workflow_id),
        )
        return self._recover_delivery(activation, checkpoint, fault_profile=fault_profile)

    def policy_approval_facts_for_case(self, tenant_id: str, case_id: str) -> JsonObject | None:
        """Expose only tenant-scoped safe authorization and local-adapter metadata."""

        activation = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation is None:
            return None
        workflow_id = str(activation["workflow_id"])
        policy_activation = self._policy_activation_for_workflow(tenant_id, workflow_id)
        if policy_activation is None:
            return None
        grant = self._grant_for_workflow(tenant_id, workflow_id)
        policy = self._policy_decision_for_workflow(tenant_id, workflow_id)
        binding = self._authorization_binding_for_workflow(tenant_id, workflow_id)
        request = self._approval_request_for_workflow(tenant_id, workflow_id)
        approval = (
            None
            if request is None
            else self._approval_decision_for_request(tenant_id, str(request["approval_request_id"]))
        )
        intent = self._delivery_intent_for_workflow(tenant_id, workflow_id)
        completion = (
            None
            if intent is None
            else self._delivery_completion_for_intent(tenant_id, str(intent["intent_id"]))
        )
        projection = self.get_workflow_projection(tenant_id, workflow_id)
        if projection is None:
            raise WorkflowError("workflow_not_found")
        return {
            "fixture_id": policy_activation["fixture_id"],
            "workflow_id": workflow_id,
            "state": projection["state"],
            "workflow_version": projection["workflow_version"],
            "policy_activation": {
                "source_checkpoint_id": policy_activation["source_checkpoint_id"],
                "policy_version": policy_activation["policy_version"],
                "delivery_resource_id": policy_activation["delivery_resource_id"],
                "data_classification": policy_activation["data_classification"],
                "delivery_budget": policy_activation["delivery_budget"],
            },
            "capability_grant": None
            if grant is None
            else {
                "grant_id": grant["grant_id"],
                "grant_version": grant.get("grant_version"),
                "grant_sha256": grant.get("grant_sha256"),
                "status": "active"
                if self._grant_is_active(tenant_id, str(grant["grant_id"]))
                else "revoked",
                "expires_at": grant["expires_at"],
            },
            "policy_decision": None
            if policy is None
            else {
                "policy_decision_id": policy["policy_decision_id"],
                "policy_decision_sha256": policy.get("policy_decision_sha256"),
                "decision": policy["decision"],
                "reason_code": policy["reason_code"],
                "policy_version": policy.get("policy_version"),
            },
            "authorization_binding": None
            if binding is None
            else {
                "authorization_binding_id": binding["authorization_binding_id"],
                "authorization_binding_sha256": binding["authorization_binding_sha256"],
                "candidate_hash": binding["candidate_hash"],
                "evidence_hashes": list(binding["evidence_hashes"]),
                "expires_at": binding["expires_at"],
            },
            "approval_request": None
            if request is None
            else {
                "approval_request_id": request["approval_request_id"],
                "authorization_binding_sha256": request.get("authorization_binding_sha256"),
                "expires_at": request["expires_at"],
            },
            "approval_decision": None
            if approval is None
            else {
                "approval_decision_id": approval["approval_decision_id"],
                "decision": approval["decision"],
                "decision_sha256": approval.get("decision_sha256"),
                "approver_role": approval.get("approver_role"),
                "expires_at": approval["expires_at"],
            },
            "outbound_delivery": None
            if intent is None
            else {
                "intent_id": intent["intent_id"],
                "idempotency_key": intent["idempotency_key"],
                "natural_key": intent["natural_key"],
                "delivery_recorded": completion is not None,
                "completion_id": None if completion is None else completion["completion_id"],
                "content_sha256": None if completion is None else completion["content_sha256"],
            },
            "fixture_local": True,
            "real_external_write": False,
            "customer_resolution": False,
        }

    def export_policy_approval_inspection(self, tenant_id: str, case_id: str) -> JsonObject | None:
        facts = self.policy_approval_facts_for_case(tenant_id, case_id)
        if facts is None:
            return None
        data = {
            "inspection_schema_version": "weflow-policy-approval-inspection.v1",
            "tenant_id": tenant_id,
            "case_id": case_id,
            "facts": facts,
            "raw_candidate_content": False,
            "raw_tool_output": False,
            "real_external_write": False,
            "customer_resolution": False,
        }
        return {**data, "content_sha256": _sha256(data)}

    @staticmethod
    def _interrupt(fault_profile: FaultProfile | None, point: str) -> None:
        if fault_profile is not None and point in fault_profile.interrupt_after:
            raise WorkflowInterrupted(f"fault_injected:{point}")

    def _intent_for_operation(
        self,
        tenant_id: str,
        workflow_id: str,
        operation: str,
    ) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM side_effect_intents
                WHERE tenant_id = ? AND workflow_id = ? AND operation = ?
                """,
                (tenant_id, workflow_id, operation),
            ).fetchone()
            if row is None:
                return None
            record = _row_dict(row)
            record["payload"] = self._intent_payload(record)
            return record
        finally:
            connection.close()

    def _completion_for_intent(self, tenant_id: str, intent_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM side_effect_completions
                WHERE tenant_id = ? AND intent_id = ?
                """,
                (tenant_id, intent_id),
            ).fetchone()
            return None if row is None else self._completion_payload(_row_dict(row))
        finally:
            connection.close()

    def _completed_intent_ids(self, tenant_id: str, workflow_id: str) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT intent_id FROM side_effect_completions
                WHERE tenant_id = ? AND workflow_id = ?
                ORDER BY intent_id ASC
                """,
                (tenant_id, workflow_id),
            ).fetchall()
            return [str(row["intent_id"]) for row in rows]
        finally:
            connection.close()

    def _unresolved_intent_ids(self, tenant_id: str, workflow_id: str) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT intent_id FROM side_effect_intents
                WHERE tenant_id = ? AND workflow_id = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM side_effect_completions completion
                      WHERE completion.tenant_id = side_effect_intents.tenant_id
                        AND completion.intent_id = side_effect_intents.intent_id
                  )
                ORDER BY intent_id ASC
                """,
                (tenant_id, workflow_id),
            ).fetchall()
            return [str(row["intent_id"]) for row in rows]
        finally:
            connection.close()

    def _ensure_intent(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        operation: str,
    ) -> tuple[JsonObject, bool]:
        if operation not in {FIND_OR_CREATE, WORKFLOW_HANDOFF}:
            raise WorkflowError("workflow_effect_not_allowlisted")
        checkpoint_payload = checkpoint["payload"]
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        natural_key = f"{tenant_id}:{activation['case_id']}:{activation['case_revision_id']}"
        intended_state_hash = _sha256(
            {
                "workflow_id": workflow_id,
                "operation": operation,
                "content_reference": "fixture-local-ticket-handoff.v1",
            }
        )
        idempotency_key = stable_idempotency_key(
            tenant_id=tenant_id,
            provider_id=LOCAL_TICKET_PROVIDER_ID,
            operation=operation,
            natural_key=natural_key,
            intended_state_hash=intended_state_hash,
        )
        intent_id = _stable_identifier(
            "side_effect_intent",
            {
                "workflow_id": workflow_id,
                "operation": operation,
                "idempotency_key": idempotency_key,
            },
        )
        payload = {
            "schema_id": SIDE_EFFECT_INTENT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": tenant_id,
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": workflow_id,
            "checkpoint_id": checkpoint_payload["checkpoint_id"],
            "intent_id": intent_id,
            "effect_kind": LOCAL_TICKET_EFFECT_KIND,
            "operation": operation,
            "natural_key": natural_key,
            "intended_state_hash": intended_state_hash,
            "idempotency_key": idempotency_key,
            "evidence_references": [f"source-event:{activation['source_event_id']}"],
            "correlation_id": activation["correlation_id"],
            "created_at": self._now(),
        }
        try:
            from weflow_contracts import validate_side_effect_intent

            validate_side_effect_intent(payload, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("workflow_intent_invalid") from error

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM side_effect_intents
                WHERE tenant_id = ? AND workflow_id = ? AND operation = ?
                """,
                (tenant_id, workflow_id, operation),
            ).fetchone()
            if existing is not None:
                record = _row_dict(existing)
                existing_payload = self._intent_payload(record)
                identity_fields = (
                    "intent_id",
                    "natural_key",
                    "intended_state_hash",
                    "idempotency_key",
                    "case_id",
                    "case_revision_id",
                )
                if any(existing_payload[field] != payload[field] for field in identity_fields):
                    raise WorkflowError("workflow_intent_conflict")
                connection.commit()
                record["payload"] = existing_payload
                return record, False
            connection.execute(
                """
                INSERT INTO side_effect_intents (
                    tenant_id, intent_id, workflow_id, checkpoint_id, case_id,
                    case_revision_id, effect_kind, operation, natural_key, intended_state_hash,
                    idempotency_key, evidence_references_json, correlation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["tenant_id"],
                    payload["intent_id"],
                    payload["workflow_id"],
                    payload["checkpoint_id"],
                    payload["case_id"],
                    payload["case_revision_id"],
                    payload["effect_kind"],
                    payload["operation"],
                    payload["natural_key"],
                    payload["intended_state_hash"],
                    payload["idempotency_key"],
                    _canonical_json(payload["evidence_references"]),
                    payload["correlation_id"],
                    payload["created_at"],
                ),
            )
            connection.commit()
            return {**payload, "payload": payload}, True
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_intent_failed") from error
        finally:
            connection.close()

    def _expected_handoff_version(self, intent: Mapping[str, Any]) -> int | None:
        if intent["operation"] != WORKFLOW_HANDOFF:
            return None
        prior = self._intent_for_operation(
            str(intent["tenant_id"]), str(intent["workflow_id"]), FIND_OR_CREATE
        )
        if prior is None:
            return None
        completion = self._completion_for_intent(str(intent["tenant_id"]), str(prior["intent_id"]))
        if completion is None:
            return None
        return int(completion["observed_version"])

    @staticmethod
    def _outcome_from_revision(row: Mapping[str, Any]) -> TicketOutcome:
        outcome_sha256 = _sha256(
            {
                "ticket_id": row["ticket_id"],
                "version": row["version"],
                "natural_key": row["natural_key"],
                "content_sha256": row["content_sha256"],
            }
        )
        return TicketOutcome(
            status="present",
            ticket_id=str(row["ticket_id"]),
            version=int(row["version"]),
            outcome_sha256=outcome_sha256,
        )

    def _latest_ticket(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        natural_key: str,
    ) -> JsonObject | None:
        row = connection.execute(
            """
            SELECT * FROM fixture_ticket_revisions
            WHERE tenant_id = ? AND natural_key = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (tenant_id, natural_key),
        ).fetchone()
        return None if row is None else _row_dict(row)

    def _reconcile_intent(self, intent: Mapping[str, Any]) -> TicketOutcome:
        tenant_id = str(intent["tenant_id"])
        connection = self._connect()
        try:
            operation = connection.execute(
                """
                SELECT ticket_id, observed_version, outcome_sha256
                FROM fixture_ticket_operations
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, intent["idempotency_key"]),
            ).fetchone()
            if operation is not None:
                return TicketOutcome(
                    status="present",
                    ticket_id=str(operation["ticket_id"]),
                    version=int(operation["observed_version"]),
                    outcome_sha256=str(operation["outcome_sha256"]),
                )
            latest = self._latest_ticket(connection, tenant_id, str(intent["natural_key"]))
            if intent["operation"] == FIND_OR_CREATE:
                return (
                    TicketOutcome("absent", None, None, None)
                    if latest is None
                    else self._outcome_from_revision(latest)
                )
            expected_version = self._expected_handoff_version(intent)
            if latest is None or expected_version is None:
                return TicketOutcome("conflict", None, None, None, "ticket_predecessor_missing")
            if int(latest["version"]) == expected_version:
                return TicketOutcome("absent", None, None, None)
            return TicketOutcome(
                "conflict",
                str(latest["ticket_id"]),
                int(latest["version"]),
                self._outcome_from_revision(latest).outcome_sha256,
                "expected_version_conflict",
            )
        finally:
            connection.close()

    def _execute_intent(self, intent: Mapping[str, Any]) -> TicketOutcome:
        tenant_id = str(intent["tenant_id"])
        natural_key = str(intent["natural_key"])
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_operation = connection.execute(
                """
                SELECT ticket_id, observed_version, outcome_sha256
                FROM fixture_ticket_operations
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, intent["idempotency_key"]),
            ).fetchone()
            if existing_operation is not None:
                connection.commit()
                return TicketOutcome(
                    "present",
                    str(existing_operation["ticket_id"]),
                    int(existing_operation["observed_version"]),
                    str(existing_operation["outcome_sha256"]),
                )
            latest = self._latest_ticket(connection, tenant_id, natural_key)
            if intent["operation"] == FIND_OR_CREATE:
                if latest is None:
                    ticket_id = _stable_identifier(
                        "fixture_ticket",
                        {"tenant_id": tenant_id, "natural_key": natural_key},
                    )
                    latest = {
                        "tenant_id": tenant_id,
                        "ticket_id": ticket_id,
                        "natural_key": natural_key,
                        "version": 1,
                        "content_sha256": str(intent["intended_state_hash"]),
                        "operation": FIND_OR_CREATE,
                        "created_at": self._now(),
                    }
                    connection.execute(
                        """
                        INSERT INTO fixture_ticket_revisions (
                            tenant_id, ticket_id, natural_key, version, content_sha256,
                            operation, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            latest["tenant_id"],
                            latest["ticket_id"],
                            latest["natural_key"],
                            latest["version"],
                            latest["content_sha256"],
                            latest["operation"],
                            latest["created_at"],
                        ),
                    )
            elif intent["operation"] == WORKFLOW_HANDOFF:
                expected_version = self._expected_handoff_version(intent)
                if (
                    latest is None
                    or expected_version is None
                    or int(latest["version"]) != expected_version
                ):
                    connection.rollback()
                    return TicketOutcome("conflict", None, None, None, "expected_version_conflict")
                latest = {
                    "tenant_id": tenant_id,
                    "ticket_id": latest["ticket_id"],
                    "natural_key": natural_key,
                    "version": int(latest["version"]) + 1,
                    "content_sha256": str(intent["intended_state_hash"]),
                    "operation": WORKFLOW_HANDOFF,
                    "created_at": self._now(),
                }
                connection.execute(
                    """
                    INSERT INTO fixture_ticket_revisions (
                        tenant_id, ticket_id, natural_key, version, content_sha256,
                        operation, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        latest["tenant_id"],
                        latest["ticket_id"],
                        latest["natural_key"],
                        latest["version"],
                        latest["content_sha256"],
                        latest["operation"],
                        latest["created_at"],
                    ),
                )
            else:
                raise WorkflowError("workflow_effect_not_allowlisted")
            outcome = self._outcome_from_revision(latest)
            connection.execute(
                """
                INSERT INTO fixture_ticket_operations (
                    tenant_id, idempotency_key, operation, natural_key, expected_version,
                    ticket_id, observed_version, outcome_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    intent["idempotency_key"],
                    intent["operation"],
                    natural_key,
                    self._expected_handoff_version(intent),
                    outcome.ticket_id,
                    outcome.version,
                    outcome.outcome_sha256,
                    self._now(),
                ),
            )
            connection.commit()
            return outcome
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("fixture_ticket_operation_failed") from error
        finally:
            connection.close()

    def _record_observation(
        self,
        intent: Mapping[str, Any],
        *,
        phase: str,
        outcome: TicketOutcome,
    ) -> JsonObject:
        if outcome.status not in {"absent", "present", "unknown", "conflict"}:
            raise WorkflowError("workflow_observation_invalid")
        intent_payload = intent["payload"] if "payload" in intent else intent
        observation_id = _stable_identifier(
            "side_effect_observation",
            {
                "intent_id": intent_payload["intent_id"],
                "phase": phase,
                "status": outcome.status,
                "ticket_id": outcome.ticket_id,
                "version": outcome.version,
                "outcome_sha256": outcome.outcome_sha256,
                "reason_code": outcome.reason_code,
            },
        )
        payload = {
            "schema_id": SIDE_EFFECT_OBSERVATION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": intent_payload["tenant_id"],
            "case_id": intent_payload["case_id"],
            "case_revision_id": intent_payload["case_revision_id"],
            "workflow_id": intent_payload["workflow_id"],
            "checkpoint_id": intent_payload["checkpoint_id"],
            "observation_id": observation_id,
            "intent_id": intent_payload["intent_id"],
            "status": outcome.status,
            "observed_ticket_id": outcome.ticket_id,
            "observed_version": outcome.version,
            "outcome_sha256": outcome.outcome_sha256,
            "reason_code": outcome.reason_code,
            "recorded_at": self._now(),
        }
        try:
            from weflow_contracts import validate_side_effect_observation

            validate_side_effect_observation(payload, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("workflow_observation_invalid") from error
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM side_effect_observations
                WHERE tenant_id = ? AND observation_id = ?
                """,
                (payload["tenant_id"], observation_id),
            ).fetchone()
            if existing is not None:
                existing_payload = self._observation_payload(_row_dict(existing))
                expected = {key: value for key, value in payload.items() if key != "recorded_at"}
                actual = {
                    key: value for key, value in existing_payload.items() if key != "recorded_at"
                }
                if actual != expected:
                    raise WorkflowError("workflow_observation_conflict")
                connection.commit()
                return existing_payload
            connection.execute(
                """
                INSERT INTO side_effect_observations (
                    tenant_id, observation_id, intent_id, workflow_id, checkpoint_id,
                    case_id, case_revision_id, status, observed_ticket_id, observed_version,
                    outcome_sha256, reason_code, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["tenant_id"],
                    payload["observation_id"],
                    payload["intent_id"],
                    payload["workflow_id"],
                    payload["checkpoint_id"],
                    payload["case_id"],
                    payload["case_revision_id"],
                    payload["status"],
                    payload["observed_ticket_id"],
                    payload["observed_version"],
                    payload["outcome_sha256"],
                    payload["reason_code"],
                    payload["recorded_at"],
                ),
            )
            connection.commit()
            return payload
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_observation_failed") from error
        finally:
            connection.close()

    def _record_completion(
        self,
        intent: Mapping[str, Any],
        observation: Mapping[str, Any],
    ) -> JsonObject:
        if (
            observation["status"] != "present"
            or not isinstance(observation["observed_ticket_id"], str)
            or not isinstance(observation["observed_version"], int)
            or not isinstance(observation["outcome_sha256"], str)
        ):
            raise WorkflowError("workflow_completion_predecessor_invalid")
        intent_payload = intent["payload"] if "payload" in intent else intent
        completion_id = _stable_identifier(
            "side_effect_completion",
            {
                "intent_id": intent_payload["intent_id"],
                "observation_id": observation["observation_id"],
            },
        )
        payload = {
            "schema_id": SIDE_EFFECT_COMPLETION_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": intent_payload["tenant_id"],
            "case_id": intent_payload["case_id"],
            "case_revision_id": intent_payload["case_revision_id"],
            "workflow_id": intent_payload["workflow_id"],
            "checkpoint_id": intent_payload["checkpoint_id"],
            "completion_id": completion_id,
            "intent_id": intent_payload["intent_id"],
            "observation_id": observation["observation_id"],
            "observed_ticket_id": observation["observed_ticket_id"],
            "observed_version": observation["observed_version"],
            "result_sha256": observation["outcome_sha256"],
            "completed_at": self._now(),
        }
        try:
            from weflow_contracts import validate_side_effect_completion

            validate_side_effect_completion(payload, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("workflow_completion_invalid") from error
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM side_effect_completions
                WHERE tenant_id = ? AND intent_id = ?
                """,
                (payload["tenant_id"], payload["intent_id"]),
            ).fetchone()
            if existing is not None:
                existing_payload = self._completion_payload(_row_dict(existing))
                comparison_fields = (
                    "completion_id",
                    "observation_id",
                    "observed_ticket_id",
                    "observed_version",
                    "result_sha256",
                )
                if any(existing_payload[field] != payload[field] for field in comparison_fields):
                    raise WorkflowError("workflow_completion_conflict")
                connection.commit()
                return existing_payload
            connection.execute(
                """
                INSERT INTO side_effect_completions (
                    tenant_id, completion_id, intent_id, workflow_id, checkpoint_id,
                    case_id, case_revision_id, observation_id, observed_ticket_id,
                    observed_version, result_sha256, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["tenant_id"],
                    payload["completion_id"],
                    payload["intent_id"],
                    payload["workflow_id"],
                    payload["checkpoint_id"],
                    payload["case_id"],
                    payload["case_revision_id"],
                    payload["observation_id"],
                    payload["observed_ticket_id"],
                    payload["observed_version"],
                    payload["result_sha256"],
                    payload["completed_at"],
                ),
            )
            connection.commit()
            return payload
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_completion_failed") from error
        finally:
            connection.close()

    def _process_intent(
        self,
        intent: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> tuple[str, JsonObject | None]:
        """Run one immutable effect protocol and return only a safe durable outcome."""

        intent_payload = intent["payload"] if "payload" in intent else intent
        existing_completion = self._completion_for_intent(
            str(intent_payload["tenant_id"]), str(intent_payload["intent_id"])
        )
        if existing_completion is not None:
            return "complete", existing_completion
        if fault_profile is not None and fault_profile.reconciliation_timeout:
            self._record_observation(
                intent,
                phase="reconcile-timeout",
                outcome=TicketOutcome("unknown", None, None, None, "reconciliation_timeout"),
            )
            return "blocked", None
        reconciled = self._reconcile_intent(intent_payload)
        observation = self._record_observation(intent, phase="reconcile", outcome=reconciled)
        self._interrupt(fault_profile, "reconcile")
        if reconciled.status in {"unknown", "conflict"}:
            return "blocked", None
        outcome = reconciled
        if reconciled.status == "absent":
            outcome = self._execute_intent(intent_payload)
            self._interrupt(fault_profile, "execute")
            if outcome.status != "present":
                self._record_observation(intent, phase="execute", outcome=outcome)
                return "blocked", None
            self._interrupt(fault_profile, "lost-response")
            observation = self._record_observation(intent, phase="execute", outcome=outcome)
        if outcome.status != "present":
            return "blocked", None
        self._interrupt(fault_profile, "observation")
        completion = self._record_completion(intent, observation)
        self._interrupt(fault_profile, "completion")
        return "complete", completion

    def _sync_case_state(
        self, activation: Mapping[str, Any], checkpoint: Mapping[str, Any]
    ) -> None:
        transition_kind = checkpoint["transition_kind"]
        if transition_kind is None:
            return
        payload = checkpoint["payload"]
        checkpoint_sequence = int(payload["checkpoint_sequence"])
        if checkpoint_sequence <= 1:
            raise WorkflowError("workflow_checkpoint_predecessor_invalid")
        checkpoints = self._checkpoints(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        previous = checkpoints[-2]["payload"]
        case_projection = self.ledger.get_case_projection(
            str(activation["tenant_id"]), str(activation["case_id"])
        )
        if case_projection is None:
            raise WorkflowError("workflow_not_found")
        if case_projection["state"] == payload["current_state"]:
            return
        try:
            self.ledger._append_workflow_state_event(
                tenant_id=str(activation["tenant_id"]),
                case_id=str(activation["case_id"]),
                case_revision_id=str(activation["case_revision_id"]),
                workflow_id=str(activation["workflow_id"]),
                checkpoint_id=str(payload["checkpoint_id"]),
                transition_kind=str(transition_kind),
                from_state=str(previous["current_state"]),
                to_state=str(payload["current_state"]),
                resume_state=str(payload["resume_state"]),
                correlation_id=str(activation["correlation_id"]),
                occurred_at=str(payload["created_at"]),
            )
        except CaseLedgerError as error:
            raise WorkflowError(error.reason_code) from error

    def _transition(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        transition_kind: str,
        next_state: str,
        resume_state: str,
        causation_event_id: str | None,
        fault_profile: FaultProfile | None,
        pending_intent_ids: Sequence[str] | None = None,
        completed_intent_ids: Sequence[str] | None = None,
    ) -> JsonObject:
        current = checkpoint["payload"]
        try:
            validate_transition(
                str(current["current_state"]),
                transition_kind,
                next_state,
                resume_state=resume_state,
                unresolved_effect=bool(current["pending_intent_ids"]),
            )
        except WorkflowTransitionError as error:
            raise WorkflowError(error.reason_code) from error
        next_checkpoint = self._ensure_checkpoint(
            activation,
            current_state=next_state,
            resume_state=resume_state,
            pending_intent_ids=(
                current["pending_intent_ids"] if pending_intent_ids is None else pending_intent_ids
            ),
            completed_intent_ids=(
                current["completed_intent_ids"]
                if completed_intent_ids is None
                else completed_intent_ids
            ),
            causation_event_id=causation_event_id,
            transition_kind=transition_kind,
        )
        self._interrupt(fault_profile, "checkpoint")
        self._sync_case_state(activation, next_checkpoint)
        return next_checkpoint

    def _record_sla_expiry(
        self, activation: Mapping[str, Any], checkpoint: Mapping[str, Any]
    ) -> None:
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        event_id = _stable_identifier("workflow_sla", {"workflow_id": workflow_id})
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT checkpoint_id, deadline_at, reason_code
                FROM workflow_sla_events
                WHERE tenant_id = ? AND workflow_id = ?
                """,
                (tenant_id, workflow_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["checkpoint_id"] != checkpoint["payload"]["checkpoint_id"]
                    or existing["deadline_at"] != activation["sla_deadline_at"]
                    or existing["reason_code"] != "synthetic_sla_expired"
                ):
                    raise WorkflowError("workflow_sla_conflict")
                connection.commit()
                return
            connection.execute(
                """
                INSERT INTO workflow_sla_events (
                    tenant_id, sla_event_id, workflow_id, checkpoint_id, deadline_at,
                    reason_code, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    event_id,
                    workflow_id,
                    checkpoint["payload"]["checkpoint_id"],
                    activation["sla_deadline_at"],
                    "synthetic_sla_expired",
                    self._now(),
                ),
            )
            connection.commit()
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_sla_failed") from error
        finally:
            connection.close()

    def _enter_reconciliation(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        causation_event_id: str,
        fault_profile: FaultProfile | None,
    ) -> JsonObject:
        current = checkpoint["payload"]
        if current["current_state"] == NEEDS_RECONCILIATION:
            return checkpoint
        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        return self._transition(
            activation,
            checkpoint,
            transition_kind=RECONCILIATION_REQUIRED,
            next_state=NEEDS_RECONCILIATION,
            resume_state=str(current["current_state"]),
            causation_event_id=causation_event_id,
            fault_profile=fault_profile,
            pending_intent_ids=self._all_pending_intent_ids(tenant_id, workflow_id),
            completed_intent_ids=self._all_completed_intent_ids(tenant_id, workflow_id),
        )

    def _drive_effect(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        operation: str,
        *,
        fault_profile: FaultProfile | None,
    ) -> tuple[JsonObject, bool]:
        """Persist/recover one effect, advancing only after a known completion."""

        intent, created = self._ensure_intent(activation, checkpoint, operation)
        if created:
            self._interrupt(fault_profile, "intent")
        current = checkpoint["payload"]
        completed = self._completed_intent_ids(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        pending = self._unresolved_intent_ids(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        before_checkpoint_id = str(current["checkpoint_id"])
        checkpoint = self._ensure_checkpoint(
            activation,
            current_state=str(current["current_state"]),
            resume_state=str(current["current_state"]),
            pending_intent_ids=pending,
            completed_intent_ids=completed,
            causation_event_id=f"intent:{intent['intent_id']}",
            transition_kind=None,
        )
        if checkpoint["payload"]["checkpoint_id"] != before_checkpoint_id:
            self._interrupt(fault_profile, "checkpoint")
        disposition, completion = self._process_intent(intent, fault_profile=fault_profile)
        if disposition != "complete" or completion is None:
            checkpoint = self._enter_reconciliation(
                activation,
                checkpoint,
                causation_event_id=f"intent:{intent['intent_id']}",
                fault_profile=fault_profile,
            )
            return checkpoint, False
        completed = self._completed_intent_ids(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        pending = self._unresolved_intent_ids(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        previous_checkpoint_id = str(checkpoint["payload"]["checkpoint_id"])
        checkpoint = self._ensure_checkpoint(
            activation,
            current_state=str(checkpoint["payload"]["current_state"]),
            resume_state=str(checkpoint["payload"]["current_state"]),
            pending_intent_ids=pending,
            completed_intent_ids=completed,
            causation_event_id=f"completion:{completion['completion_id']}",
            transition_kind=None,
        )
        if checkpoint["payload"]["checkpoint_id"] != previous_checkpoint_id:
            self._interrupt(fault_profile, "checkpoint")
        return checkpoint, True

    def _recover_reconciliation(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> JsonObject | None:
        unresolved = self._unresolved_intent_ids(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        if unresolved:
            connection = self._connect()
            try:
                row = connection.execute(
                    """
                    SELECT * FROM side_effect_intents
                    WHERE tenant_id = ? AND intent_id = ?
                    """,
                    (activation["tenant_id"], unresolved[0]),
                ).fetchone()
                if row is None:
                    raise WorkflowError("workflow_journal_invalid")
                intent = _row_dict(row)
                intent["payload"] = self._intent_payload(intent)
            finally:
                connection.close()
            disposition, completion = self._process_intent(intent, fault_profile=fault_profile)
            if disposition != "complete" or completion is None:
                return self.get_workflow_projection(
                    str(activation["tenant_id"]), str(activation["workflow_id"])
                )
            unresolved = self._unresolved_intent_ids(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
            completed = self._completed_intent_ids(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        else:
            completed = self._completed_intent_ids(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        if unresolved:
            return self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        resumed = self._transition(
            activation,
            checkpoint,
            transition_kind=RECONCILIATION_COMPLETE,
            next_state=str(checkpoint["payload"]["resume_state"]),
            resume_state=str(checkpoint["payload"]["resume_state"]),
            causation_event_id="reconciliation:known-outcome",
            fault_profile=fault_profile,
            pending_intent_ids=[],
            completed_intent_ids=completed,
        )
        return self._recover_workflow(activation, resumed, fault_profile=fault_profile)

    def _recover_workflow(
        self,
        activation: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
        *,
        fault_profile: FaultProfile | None,
    ) -> JsonObject | None:
        current = checkpoint["payload"]
        state = str(current["current_state"])
        handoff = self._intent_for_operation(
            str(activation["tenant_id"]), str(activation["workflow_id"]), WORKFLOW_HANDOFF
        )
        handoff_complete = (
            handoff is not None
            and self._completion_for_intent(str(activation["tenant_id"]), str(handoff["intent_id"]))
            is not None
        )
        if (
            _parse_timestamp(self._now()) >= _parse_timestamp(str(activation["sla_deadline_at"]))
            and not handoff_complete
            and state not in {WAITING_FOR_OPERATOR, NEEDS_RECONCILIATION, CANCELLED}
        ):
            self._record_sla_expiry(activation, checkpoint)
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=SLA_EXPIRED,
                next_state=WAITING_FOR_OPERATOR,
                resume_state=WAITING_FOR_OPERATOR,
                causation_event_id="synthetic-sla-expired",
                fault_profile=fault_profile,
            )
            return self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        policy_activation = self._policy_activation_for_workflow(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )
        if state == NEEDS_RECONCILIATION:
            if (
                policy_activation is not None
                and checkpoint["payload"]["resume_state"] == DELIVERING
            ):
                return self._recover_delivery_reconciliation(
                    activation, checkpoint, fault_profile=fault_profile
                )
            return self._recover_reconciliation(activation, checkpoint, fault_profile=fault_profile)
        if state in {RESPONSE_READY, AWAITING_APPROVAL, DELIVERING}:
            if policy_activation is None:
                if state == RESPONSE_READY:
                    # Retained Change 3 response candidates are deliberately inert.
                    return self.get_workflow_projection(
                        str(activation["tenant_id"]), str(activation["workflow_id"])
                    )
                raise WorkflowError("policy_journal_invalid")
            return self._recover_policy_approval(
                activation, checkpoint, fault_profile=fault_profile
            )
        if state in {TICKET_READY, INVESTIGATING}:
            return self._recover_investigation(activation, checkpoint, fault_profile=fault_profile)
        if state in {PAUSED, WAITING_FOR_OPERATOR, CANCELLED} or is_terminal(state):
            return self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        if state != RECEIVED:
            raise WorkflowError("workflow_state_not_allowlisted")
        checkpoint, find_complete = self._drive_effect(
            activation,
            checkpoint,
            FIND_OR_CREATE,
            fault_profile=fault_profile,
        )
        if not find_complete:
            return self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        checkpoint, handoff_complete = self._drive_effect(
            activation,
            checkpoint,
            WORKFLOW_HANDOFF,
            fault_profile=fault_profile,
        )
        if not handoff_complete:
            return self.get_workflow_projection(
                str(activation["tenant_id"]), str(activation["workflow_id"])
            )
        checkpoint = self._transition(
            activation,
            checkpoint,
            transition_kind=TICKET_HANDOFF_COMPLETE,
            next_state=TICKET_READY,
            resume_state=TICKET_READY,
            causation_event_id="ticket-handoff:complete",
            fault_profile=fault_profile,
        )
        return self.get_workflow_projection(
            str(activation["tenant_id"]), str(activation["workflow_id"])
        )

    def run_case(
        self,
        tenant_id: str,
        case_id: str,
        case_revision_id: str,
        *,
        sla_policy: Mapping[str, Any] | None = None,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject | None:
        """Activate one accepted Case revision and drive/recover its local workflow."""

        workflow_id, created = self.activate_case(
            tenant_id,
            case_id,
            case_revision_id,
            sla_policy=sla_policy,
        )
        if created:
            self._interrupt(fault_profile, "activation")
        return self.recover_workflow(tenant_id, workflow_id, fault_profile=fault_profile)

    def recover_workflow(
        self,
        tenant_id: str,
        workflow_id: str,
        *,
        fault_profile: FaultProfile | None = None,
    ) -> JsonObject | None:
        """Recover solely from durable source facts; no in-memory retry state is used."""

        self.ledger.rebuild_projection()
        self.rebuild_workflow_projection()
        activation = self._activation(tenant_id, workflow_id)
        checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
        if checkpoint is None:
            checkpoint = self._ensure_checkpoint(
                activation,
                current_state=RECEIVED,
                resume_state=RECEIVED,
                pending_intent_ids=[],
                completed_intent_ids=[],
                causation_event_id=str(activation["source_event_id"]),
                transition_kind=None,
            )
            self._interrupt(fault_profile, "checkpoint")
        self._sync_case_state(activation, checkpoint)
        self.rebuild_workflow_projection()
        checkpoint = self._recover_pending_commands(activation)
        return self._recover_workflow(activation, checkpoint, fault_profile=fault_profile)

    def recover_all(self, *, fault_profile: FaultProfile | None = None) -> list[JsonObject | None]:
        """Activate eligible unclaimed Case revisions, then recover every durable workflow."""

        self._activate_pending_cases(fault_profile=fault_profile)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT tenant_id, workflow_id FROM workflow_activations "
                "ORDER BY tenant_id, workflow_id"
            ).fetchall()
        finally:
            connection.close()
        return [
            self.recover_workflow(
                str(row["tenant_id"]), str(row["workflow_id"]), fault_profile=fault_profile
            )
            for row in rows
        ]

    def _activate_pending_cases(self, *, fault_profile: FaultProfile | None) -> None:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT revision.tenant_id, revision.case_id, revision.case_revision_id
                FROM case_revisions AS revision
                JOIN case_projection AS projection
                  ON projection.tenant_id = revision.tenant_id
                 AND projection.case_id = revision.case_id
                LEFT JOIN workflow_activations AS activation
                  ON activation.tenant_id = revision.tenant_id
                 AND activation.case_id = revision.case_id
                 AND activation.case_revision_id = revision.case_revision_id
                 AND activation.workflow_definition_version = ?
                WHERE revision.revision = 1
                  AND projection.state = ?
                  AND activation.workflow_id IS NULL
                ORDER BY revision.tenant_id, revision.case_id
                """,
                (WORKFLOW_DEFINITION_VERSION, RECEIVED),
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            self.run_case(
                str(row["tenant_id"]),
                str(row["case_id"]),
                str(row["case_revision_id"]),
                fault_profile=fault_profile,
            )

    def _command_checkpoint_exists(
        self,
        tenant_id: str,
        workflow_id: str,
        command_id: str,
    ) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT 1 FROM workflow_checkpoints
                WHERE tenant_id = ? AND workflow_id = ? AND causation_event_id = ?
                """,
                (tenant_id, workflow_id, f"command:{command_id}"),
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    def _apply_persisted_command(
        self,
        activation: Mapping[str, Any],
        command: Mapping[str, Any],
    ) -> WorkflowCommandResult:
        """Finish a durable command after a crash without reinterpreting its payload.

        Commands are immutable source facts. A matching checkpoint causation proves
        application; without it recovery applies the original allowlisted command
        against exactly the workflow version it recorded. This closes the window
        between persisting a command and appending its checkpoint.
        """

        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        command_id = str(command["command_id"])
        command_type = str(command["command_type"])
        if self._command_checkpoint_exists(tenant_id, workflow_id, command_id):
            projection = self.get_workflow_projection(tenant_id, workflow_id)
            if projection is None:
                raise WorkflowError("workflow_journal_invalid")
            return WorkflowCommandResult("deduplicated", projection)

        checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
        if checkpoint is None:
            raise WorkflowError("workflow_command_recovery_conflict")
        current = checkpoint["payload"]
        state = str(current["current_state"])
        if int(current["workflow_version"]) != int(command["expected_workflow_version"]):
            raise WorkflowError("workflow_command_recovery_conflict")

        disposition = "accepted"
        if command_type == PAUSE:
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=PAUSE,
                next_state=PAUSED,
                resume_state=state,
                causation_event_id=f"command:{command_id}",
                fault_profile=None,
            )
        elif command_type == RESUME:
            checkpoint = self._transition(
                activation,
                checkpoint,
                transition_kind=RESUME,
                next_state=str(current["resume_state"]),
                resume_state=str(current["resume_state"]),
                causation_event_id=f"command:{command_id}",
                fault_profile=None,
            )
        elif command_type == CANCEL:
            unresolved = self._all_pending_intent_ids(tenant_id, workflow_id)
            if unresolved:
                disposition = "requires_reconciliation"
                checkpoint = self._enter_reconciliation(
                    activation,
                    checkpoint,
                    causation_event_id=f"command:{command_id}",
                    fault_profile=None,
                )
            elif state == NEEDS_RECONCILIATION:
                # The durable command is already represented by the blocked state;
                # it cannot bypass reconciliation or manufacture a cancellation.
                disposition = "requires_reconciliation"
            else:
                checkpoint = self._transition(
                    activation,
                    checkpoint,
                    transition_kind=CANCEL,
                    next_state=CANCELLED,
                    resume_state=CANCELLED,
                    causation_event_id=f"command:{command_id}",
                    fault_profile=None,
                )
        else:
            raise WorkflowError("workflow_command_not_allowlisted")

        self.rebuild_workflow_projection()
        projection = self.get_workflow_projection(tenant_id, workflow_id)
        if projection is None:
            raise WorkflowError("workflow_journal_invalid")
        return WorkflowCommandResult(disposition, projection)

    def _recover_pending_commands(
        self,
        activation: Mapping[str, Any],
    ) -> JsonObject:
        """Apply durable commands before ordinary effect progress resumes."""

        tenant_id = str(activation["tenant_id"])
        workflow_id = str(activation["workflow_id"])
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT command_id, command_type, expected_workflow_version
                FROM workflow_commands
                WHERE tenant_id = ? AND workflow_id = ?
                ORDER BY accepted_at ASC, command_id ASC
                """,
                (tenant_id, workflow_id),
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            command = _row_dict(row)
            checkpoint = self._latest_checkpoint(tenant_id, workflow_id)
            if checkpoint is None:
                raise WorkflowError("workflow_command_recovery_conflict")
            if (
                command["command_type"] == CANCEL
                and checkpoint["payload"]["current_state"] == NEEDS_RECONCILIATION
            ):
                continue
            if self._command_checkpoint_exists(tenant_id, workflow_id, str(command["command_id"])):
                continue
            self._apply_persisted_command(activation, command)
        latest = self._latest_checkpoint(tenant_id, workflow_id)
        if latest is None:
            raise WorkflowError("workflow_journal_invalid")
        return latest

    def submit_command(
        self,
        tenant_id: str,
        case_id: str,
        *,
        command_id: str,
        command_type: str,
        expected_workflow_version: int,
    ) -> WorkflowCommandResult:
        """Apply only tenant-derived pause/resume/cancel commands with exact versioning."""

        if command_type not in {PAUSE, RESUME, CANCEL} or not command_id:
            raise WorkflowError("workflow_command_not_allowlisted")
        activation_row = self._activation_for_case_for_tenant(tenant_id, case_id)
        if activation_row is None:
            raise WorkflowNotFound("workflow_not_found")
        activation = activation_row
        checkpoint = self._latest_checkpoint(tenant_id, str(activation["workflow_id"]))
        if checkpoint is None:
            checkpoint = self._ensure_checkpoint(
                activation,
                current_state=RECEIVED,
                resume_state=RECEIVED,
                pending_intent_ids=[],
                completed_intent_ids=[],
                causation_event_id=str(activation["source_event_id"]),
                transition_kind=None,
            )
            self.rebuild_workflow_projection()
        current = checkpoint["payload"]
        command_payload_sha256 = _sha256(
            {
                "case_id": case_id,
                "command_type": command_type,
                "expected_workflow_version": expected_workflow_version,
            }
        )
        command = {
            "schema_id": WORKFLOW_COMMAND_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": tenant_id,
            "case_id": activation["case_id"],
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": activation["workflow_id"],
            "command_id": command_id,
            "command_type": command_type,
            "expected_workflow_version": expected_workflow_version,
            "command_payload_sha256": command_payload_sha256,
            "requested_at": self._now(),
        }
        try:
            validate_workflow_command(command, self._contract_root)
        except ContractValidationError as error:
            raise WorkflowError("workflow_command_invalid") from error
        fingerprint = _sha256(
            {
                "command_id": command_id,
                "command_type": command_type,
                "expected_workflow_version": expected_workflow_version,
                "command_payload_sha256": command_payload_sha256,
            }
        )
        connection = self._connect()
        duplicate_command = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT command_type, expected_workflow_version, command_payload_sha256,
                       command_fingerprint
                FROM workflow_commands
                WHERE tenant_id = ? AND workflow_id = ? AND command_id = ?
                """,
                (tenant_id, activation["workflow_id"], command_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["command_type"] != command_type
                    or existing["expected_workflow_version"] != expected_workflow_version
                    or existing["command_payload_sha256"] != command_payload_sha256
                    or existing["command_fingerprint"] != fingerprint
                ):
                    raise WorkflowError("workflow_command_conflict")
                connection.commit()
                duplicate_command = True
            else:
                latest_version = int(
                    connection.execute(
                        """
                        SELECT workflow_version FROM workflow_checkpoints
                        WHERE tenant_id = ? AND workflow_id = ?
                        ORDER BY checkpoint_sequence DESC
                        LIMIT 1
                        """,
                        (tenant_id, activation["workflow_id"]),
                    ).fetchone()[0]
                )
                try:
                    validate_workflow_command_version(
                        command,
                        latest_version,
                        self._contract_root,
                        effective_tenant_id=tenant_id,
                    )
                except ContractValidationError as error:
                    raise WorkflowError("workflow_version_conflict") from error
                state = str(current["current_state"])
                unresolved_before = self._all_pending_intent_ids(
                    tenant_id, str(activation["workflow_id"])
                )
                try:
                    if command_type == PAUSE:
                        validate_transition(state, PAUSE, PAUSED, resume_state=state)
                    elif command_type == RESUME:
                        validate_transition(
                            state,
                            RESUME,
                            str(current["resume_state"]),
                            resume_state=str(current["resume_state"]),
                        )
                    elif not unresolved_before and state != NEEDS_RECONCILIATION:
                        validate_transition(
                            state,
                            CANCEL,
                            CANCELLED,
                            resume_state=CANCELLED,
                            unresolved_effect=False,
                        )
                except WorkflowTransitionError as error:
                    raise WorkflowError(error.reason_code) from error
                connection.execute(
                    """
                    INSERT INTO workflow_commands (
                        tenant_id, workflow_id, command_id, command_type,
                        expected_workflow_version, command_payload_sha256,
                        command_fingerprint, requested_at, accepted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tenant_id,
                        activation["workflow_id"],
                        command_id,
                        command_type,
                        expected_workflow_version,
                        command_payload_sha256,
                        fingerprint,
                        command["requested_at"],
                        self._now(),
                    ),
                )
                connection.commit()
        except WorkflowError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise WorkflowError("workflow_command_failed") from error
        finally:
            connection.close()

        result = self._apply_persisted_command(activation, command)
        if duplicate_command:
            return WorkflowCommandResult("deduplicated", result.projection)
        return result

    def _activation_for_case_for_tenant(self, tenant_id: str, case_id: str) -> JsonObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM workflow_activations
                WHERE tenant_id = ? AND case_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (tenant_id, case_id),
            ).fetchone()
            return None if row is None else _row_dict(row)
        finally:
            connection.close()

    @staticmethod
    def _workflow_snapshot_columns() -> dict[str, tuple[str, ...]]:
        return {
            "workflow_activations": (
                "tenant_id",
                "workflow_id",
                "activation_id",
                "case_id",
                "case_revision_id",
                "workflow_definition_version",
                "source_event_id",
                "correlation_id",
                "sla_policy_id",
                "sla_policy_version",
                "sla_deadline_seconds",
                "sla_deadline_at",
                "created_at",
            ),
            "workflow_runs": (
                "tenant_id",
                "run_id",
                "workflow_id",
                "run_sequence",
                "state",
                "run_status",
                "reason_code",
                "created_at",
            ),
            "workflow_commands": (
                "tenant_id",
                "workflow_id",
                "command_id",
                "command_type",
                "expected_workflow_version",
                "command_payload_sha256",
                "command_fingerprint",
                "requested_at",
                "accepted_at",
            ),
            "workflow_checkpoints": (
                "tenant_id",
                "checkpoint_id",
                "workflow_id",
                "case_id",
                "case_revision_id",
                "workflow_definition_version",
                "checkpoint_sequence",
                "previous_checkpoint_id",
                "current_state",
                "resume_state",
                "workflow_version",
                "sla_deadline_at",
                "pending_intent_ids_json",
                "completed_intent_ids_json",
                "causation_event_id",
                "correlation_id",
                "content_sha256",
                "transition_kind",
                "created_at",
            ),
            "workflow_sla_events": (
                "tenant_id",
                "sla_event_id",
                "workflow_id",
                "checkpoint_id",
                "deadline_at",
                "reason_code",
                "recorded_at",
            ),
            "side_effect_intents": (
                "tenant_id",
                "intent_id",
                "workflow_id",
                "checkpoint_id",
                "case_id",
                "case_revision_id",
                "effect_kind",
                "operation",
                "natural_key",
                "intended_state_hash",
                "idempotency_key",
                "evidence_references_json",
                "correlation_id",
                "created_at",
            ),
            "side_effect_observations": (
                "tenant_id",
                "observation_id",
                "intent_id",
                "workflow_id",
                "checkpoint_id",
                "case_id",
                "case_revision_id",
                "status",
                "observed_ticket_id",
                "observed_version",
                "outcome_sha256",
                "reason_code",
                "recorded_at",
            ),
            "side_effect_completions": (
                "tenant_id",
                "completion_id",
                "intent_id",
                "workflow_id",
                "checkpoint_id",
                "case_id",
                "case_revision_id",
                "observation_id",
                "observed_ticket_id",
                "observed_version",
                "result_sha256",
                "completed_at",
            ),
            "investigation_activations": (
                "tenant_id",
                "investigation_id",
                "workflow_id",
                "checkpoint_id",
                "case_id",
                "case_revision_id",
                "context_manifest_id",
                "context_sha256",
                "environment_snapshot_sha256",
                "evidence_references_json",
                "transcript_id",
                "action_budget",
                "tool_budget",
                "no_progress_limit",
                "created_at",
            ),
            "agent_steps": (
                "tenant_id",
                "agent_step_id",
                "workflow_id",
                "checkpoint_id",
                "context_manifest_id",
                "step_id",
                "action_type",
                "action_sha256",
                "created_at",
            ),
            INVESTIGATION_TOOL_REQUESTS_TABLE: (
                "tenant_id",
                "tool_request_id",
                "workflow_id",
                "checkpoint_id",
                "context_manifest_id",
                "step_id",
                "tool_name",
                "request_sha256",
                "created_at",
            ),
            "investigation_tool_results": (
                "tenant_id",
                "tool_result_id",
                "workflow_id",
                "checkpoint_id",
                "context_manifest_id",
                "tool_name",
                "tool_request_id",
                "evidence_id",
                "content_sha256",
                "redaction_classification",
                "recorded_at",
            ),
            "investigation_candidates": (
                "tenant_id",
                "candidate_id",
                "workflow_id",
                "checkpoint_id",
                "context_manifest_id",
                "context_sha256",
                "evidence_hashes_json",
                "candidate_sha256",
                "risk",
                "next_step",
                "created_at",
            ),
            "investigation_verifier_outcomes": (
                "tenant_id",
                "verifier_outcome_id",
                "workflow_id",
                "checkpoint_id",
                "context_manifest_id",
                "candidate_id",
                "candidate_sha256",
                "outcome",
                "reason_code",
                "recorded_at",
            ),
            "fixture_ticket_revisions": (
                "tenant_id",
                "ticket_id",
                "natural_key",
                "version",
                "content_sha256",
                "operation",
                "created_at",
            ),
            "fixture_ticket_operations": (
                "tenant_id",
                "idempotency_key",
                "operation",
                "natural_key",
                "expected_version",
                "ticket_id",
                "observed_version",
                "outcome_sha256",
                "created_at",
            ),
            "policy_approval_activations": (
                "tenant_id",
                "policy_approval_activation_id",
                "workflow_id",
                "case_id",
                "case_revision_id",
                "source_checkpoint_id",
                "fixture_id",
                "policy_version",
                "delivery_resource_id",
                "delivery_resource_scope",
                "data_classification",
                "delivery_budget",
                "controller_subject_id",
                "controller_role",
                "candidate_hash",
                "evidence_hashes_json",
                "activated_at",
            ),
            "capability_grants": (
                "tenant_id",
                "grant_id",
                "workflow_id",
                "grant_sha256",
                "grant_version",
                "subject_id",
                "role",
                "resource_scope",
                "data_classifications_json",
                "issued_at",
                "expires_at",
                "payload_json",
            ),
            "capability_grant_status_events": (
                "tenant_id",
                "grant_status_event_id",
                "grant_id",
                "status",
                "reason_code",
                "recorded_at",
            ),
            "policy_decisions": (
                "tenant_id",
                "policy_decision_id",
                "workflow_id",
                "checkpoint_id",
                "action",
                "policy_decision_sha256",
                "policy_input_sha256",
                "decision",
                "reason_code",
                "policy_version",
                "grant_id",
                "grant_sha256",
                "candidate_hash",
                "evidence_hashes_json",
                "subject_id",
                "role",
                "resource_id",
                "data_classification",
                "workflow_version",
                "payload_json",
                "decided_at",
            ),
            "authorization_bindings": (
                "tenant_id",
                "authorization_binding_id",
                "authorization_binding_sha256",
                "workflow_id",
                "policy_decision_id",
                "grant_id",
                "checkpoint_id",
                "workflow_version",
                "candidate_hash",
                "evidence_hashes_json",
                "expires_at",
                "payload_json",
                "created_at",
            ),
            "approval_requests": (
                "tenant_id",
                "approval_request_id",
                "workflow_id",
                "authorization_binding_sha256",
                "checkpoint_id",
                "workflow_version",
                "payload_json",
                "created_at",
                "expires_at",
            ),
            "approval_decisions": (
                "tenant_id",
                "approval_decision_id",
                "approval_request_id",
                "workflow_id",
                "authorization_binding_sha256",
                "workflow_version",
                "decision",
                "decision_sha256",
                "approver_id",
                "approver_role",
                "payload_json",
                "decided_at",
            ),
            "outbound_delivery_intents": (
                "tenant_id",
                "intent_id",
                "workflow_id",
                "checkpoint_id",
                "case_id",
                "case_revision_id",
                "authorization_binding_sha256",
                "candidate_hash",
                "evidence_hashes_json",
                "channel",
                "conversation_id",
                "delivery_resource_id",
                "natural_key",
                "intended_state_hash",
                "idempotency_key",
                "correlation_id",
                "payload_json",
                "created_at",
            ),
            "outbound_delivery_observations": (
                "tenant_id",
                "observation_id",
                "intent_id",
                "workflow_id",
                "checkpoint_id",
                "status",
                "observed_delivery_id",
                "observed_version",
                "content_sha256",
                "reason_code",
                "payload_json",
                "recorded_at",
            ),
            "outbound_delivery_completions": (
                "tenant_id",
                "completion_id",
                "intent_id",
                "workflow_id",
                "checkpoint_id",
                "observation_id",
                "observed_delivery_id",
                "observed_version",
                "content_sha256",
                "payload_json",
                "completed_at",
            ),
            "fixture_delivery_records": (
                "tenant_id",
                "delivery_id",
                "natural_key",
                "version",
                "content_sha256",
                "data_classification",
                "created_at",
            ),
            "fixture_delivery_operations": (
                "tenant_id",
                "idempotency_key",
                "natural_key",
                "delivery_id",
                "observed_version",
                "content_sha256",
                "created_at",
            ),
        }

    def export_snapshot(self, tenant_id: str) -> JsonObject:
        """Export a content-addressed workflow journal linked to an unchanged ledger snapshot."""

        ledger_snapshot = self.ledger.export_snapshot(tenant_id)
        columns_by_table = self._workflow_snapshot_columns()
        connection = self._connect()
        try:
            journal = {}
            for table, columns in columns_by_table.items():
                rows = connection.execute(
                    f"SELECT {', '.join(columns)} FROM {table} "
                    "WHERE tenant_id = ? ORDER BY rowid ASC",
                    (tenant_id,),
                ).fetchall()
                journal[table] = [_row_dict(row) for row in rows]
        finally:
            connection.close()
        data = {
            "snapshot_schema_version": WORKFLOW_SNAPSHOT_SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "ledger_snapshot": ledger_snapshot,
            "ledger_snapshot_sha256": ledger_snapshot["content_sha256"],
            "workflow_journal_schema_version": "weflow-durable-workflow-journal.v1",
            "workflow_journal": journal,
        }
        return {**data, "content_sha256": _sha256(data)}

    def _replay_case_events_from_journal(self, tenant_id: str) -> None:
        connection = self._connect()
        try:
            activations = [
                _row_dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM workflow_activations
                    WHERE tenant_id = ?
                    ORDER BY workflow_id ASC
                    """,
                    (tenant_id,),
                ).fetchall()
            ]
        finally:
            connection.close()
        for activation in activations:
            checkpoints = self._checkpoints(tenant_id, str(activation["workflow_id"]))
            for index, checkpoint in enumerate(checkpoints):
                transition_kind = checkpoint["transition_kind"]
                if transition_kind is None:
                    continue
                if index == 0:
                    raise WorkflowError("workflow_journal_invalid")
                previous = checkpoints[index - 1]["payload"]
                payload = checkpoint["payload"]
                try:
                    self.ledger._append_workflow_state_event(
                        tenant_id=tenant_id,
                        case_id=str(activation["case_id"]),
                        case_revision_id=str(activation["case_revision_id"]),
                        workflow_id=str(activation["workflow_id"]),
                        checkpoint_id=str(payload["checkpoint_id"]),
                        transition_kind=str(transition_kind),
                        from_state=str(previous["current_state"]),
                        to_state=str(payload["current_state"]),
                        resume_state=str(payload["resume_state"]),
                        correlation_id=str(activation["correlation_id"]),
                        occurred_at=str(payload["created_at"]),
                    )
                except CaseLedgerError as error:
                    raise WorkflowError(error.reason_code) from error

    @classmethod
    def restore_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        path: str | Path,
        *,
        clock: Clock | None = None,
        contract_root: Path | None = None,
    ) -> SQLiteDurableWorkflow:
        """Restore a verified workflow snapshot only into a fresh local store."""

        payload = dict(snapshot)
        digest = payload.pop("content_sha256", None)
        if not isinstance(digest, str) or digest != _sha256(payload):
            raise WorkflowError("workflow_snapshot_hash_mismatch")
        expected_keys = {
            "snapshot_schema_version",
            "tenant_id",
            "ledger_snapshot",
            "ledger_snapshot_sha256",
            "workflow_journal_schema_version",
            "workflow_journal",
        }
        if set(payload) != expected_keys:
            raise WorkflowError("workflow_snapshot_invalid")
        if (
            payload["snapshot_schema_version"] != WORKFLOW_SNAPSHOT_SCHEMA_VERSION
            or payload["workflow_journal_schema_version"] != "weflow-durable-workflow-journal.v1"
            or not isinstance(payload["tenant_id"], str)
            or not isinstance(payload["ledger_snapshot"], Mapping)
            or payload["ledger_snapshot_sha256"] != payload["ledger_snapshot"].get("content_sha256")
        ):
            raise WorkflowError("workflow_snapshot_invalid")
        target = Path(path)
        if target.exists():
            raise WorkflowError("snapshot_restore_requires_fresh_store")
        restored_ledger = SQLiteCaseLedger.restore_snapshot(
            payload["ledger_snapshot"],
            target,
            clock=clock,
            contract_root=contract_root,
        )
        restored = cls(restored_ledger, clock=clock, contract_root=contract_root)
        journal = payload["workflow_journal"]
        columns_by_table = cls._workflow_snapshot_columns()
        if not isinstance(journal, Mapping) or set(journal) != set(columns_by_table):
            raise WorkflowError("workflow_snapshot_invalid")
        connection = restored._connect()
        journal_error: WorkflowError | None = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            for table, columns in columns_by_table.items():
                records = journal[table]
                if not isinstance(records, list):
                    raise WorkflowError("workflow_snapshot_invalid")
                placeholders = ", ".join("?" for _ in columns)
                statement = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                for record in records:
                    if (
                        not isinstance(record, Mapping)
                        or set(record) != set(columns)
                        or record.get("tenant_id") != payload["tenant_id"]
                    ):
                        raise WorkflowError("workflow_snapshot_invalid")
                    connection.execute(statement, tuple(record[column] for column in columns))
            connection.commit()
        except WorkflowError as error:
            connection.rollback()
            journal_error = error
        except sqlite3.DatabaseError as error:
            connection.rollback()
            journal_error = WorkflowError("workflow_snapshot_invalid")
            journal_error.__cause__ = error
        finally:
            connection.close()
        if journal_error is not None:
            target.unlink(missing_ok=True)
            raise journal_error
        try:
            restored.rebuild_workflow_projection()
            restored._replay_case_events_from_journal(str(payload["tenant_id"]))
            restored.ledger.rebuild_projection()
            restored.validate_projection_agreement()
        except (CaseLedgerError, WorkflowError):
            target.unlink(missing_ok=True)
            raise
        return restored

    def validate_projection_agreement(self) -> None:
        """Prove source, transition-event, and derived-projection agreement after recovery."""

        self.ledger.rebuild_projection()
        self.rebuild_workflow_projection()
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT tenant_id, workflow_id, case_id, state FROM workflow_projection"
            ).fetchall()
            activations = connection.execute(
                "SELECT * FROM workflow_activations ORDER BY tenant_id, workflow_id"
            ).fetchall()
            for activation_row in activations:
                activation = _row_dict(activation_row)
                checkpoints = []
                for checkpoint_row in connection.execute(
                    """
                    SELECT * FROM workflow_checkpoints
                    WHERE tenant_id = ? AND workflow_id = ?
                    ORDER BY checkpoint_sequence ASC
                    """,
                    (activation["tenant_id"], activation["workflow_id"]),
                ).fetchall():
                    checkpoint = _row_dict(checkpoint_row)
                    checkpoint["payload"] = self._checkpoint_payload(checkpoint)
                    checkpoints.append(checkpoint)
                self._validate_case_event_agreement(connection, activation, checkpoints)
        finally:
            connection.close()
        for row in rows:
            case_projection = self.ledger.get_case_projection(
                str(row["tenant_id"]), str(row["case_id"])
            )
            if case_projection is None or case_projection["state"] != row["state"]:
                raise WorkflowError("workflow_case_projection_mismatch")
