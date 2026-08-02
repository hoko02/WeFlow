"""Additive SQLite schema for the deterministic Change 2 workflow journal."""

from __future__ import annotations

import sqlite3

WORKFLOW_JOURNAL_SCHEMA_VERSION = "weflow-durable-workflow-journal.v1"

WORKFLOW_SOURCE_TABLES = (
    "workflow_journal_metadata",
    "workflow_activations",
    "workflow_runs",
    "workflow_commands",
    "workflow_checkpoints",
    "workflow_sla_events",
    "side_effect_intents",
    "side_effect_observations",
    "side_effect_completions",
    "fixture_ticket_revisions",
    "fixture_ticket_operations",
)


class WorkflowJournalSchemaError(ValueError):
    """Raised when a store cannot safely interpret durable workflow source records."""


def _ensure_business_event_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(business_events)").fetchall()
    }
    if "workflow_id" not in columns:
        connection.execute("ALTER TABLE business_events ADD COLUMN workflow_id TEXT")
    if "workflow_checkpoint_id" not in columns:
        connection.execute("ALTER TABLE business_events ADD COLUMN workflow_checkpoint_id TEXT")


def _ensure_side_effect_intent_columns(connection: sqlite3.Connection) -> None:
    """Apply additive source-column migrations for pre-release workflow stores."""

    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(side_effect_intents)").fetchall()
    }
    if "effect_kind" not in columns:
        connection.execute(
            "ALTER TABLE side_effect_intents ADD COLUMN effect_kind TEXT NOT NULL "
            "DEFAULT 'fixture-local-ticket'"
        )


def initialize_workflow_journal_schema(connection: sqlite3.Connection) -> None:
    """Install only additive tables and reject a journal version we do not understand."""

    _ensure_business_event_columns(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflow_journal_metadata (
            schema_version TEXT NOT NULL PRIMARY KEY,
            installed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_activations (
            tenant_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            activation_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            workflow_definition_version TEXT NOT NULL,
            source_event_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            sla_policy_id TEXT NOT NULL,
            sla_policy_version TEXT NOT NULL,
            sla_deadline_seconds INTEGER NOT NULL CHECK (sla_deadline_seconds > 0),
            sla_deadline_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, workflow_id),
            UNIQUE (tenant_id, activation_id),
            UNIQUE (tenant_id, case_id, case_revision_id, workflow_definition_version),
            FOREIGN KEY (tenant_id, case_revision_id)
                REFERENCES case_revisions (tenant_id, case_revision_id)
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            tenant_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            run_sequence INTEGER NOT NULL CHECK (run_sequence >= 1),
            state TEXT NOT NULL,
            run_status TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, run_id),
            UNIQUE (tenant_id, workflow_id, run_sequence),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS workflow_commands (
            tenant_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            command_id TEXT NOT NULL,
            command_type TEXT NOT NULL,
            expected_workflow_version INTEGER NOT NULL CHECK (expected_workflow_version >= 0),
            command_payload_sha256 TEXT NOT NULL,
            command_fingerprint TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            accepted_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, workflow_id, command_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS workflow_checkpoints (
            tenant_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            workflow_definition_version TEXT NOT NULL,
            checkpoint_sequence INTEGER NOT NULL CHECK (checkpoint_sequence >= 1),
            previous_checkpoint_id TEXT,
            current_state TEXT NOT NULL,
            resume_state TEXT NOT NULL,
            workflow_version INTEGER NOT NULL CHECK (workflow_version >= 0),
            sla_deadline_at TEXT NOT NULL,
            pending_intent_ids_json TEXT NOT NULL,
            completed_intent_ids_json TEXT NOT NULL,
            causation_event_id TEXT,
            correlation_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            transition_kind TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, checkpoint_id),
            UNIQUE (tenant_id, workflow_id, checkpoint_sequence),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS workflow_sla_events (
            tenant_id TEXT NOT NULL,
            sla_event_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            deadline_at TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, sla_event_id),
            UNIQUE (tenant_id, workflow_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS side_effect_intents (
            tenant_id TEXT NOT NULL,
            intent_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            effect_kind TEXT NOT NULL CHECK (effect_kind = 'fixture-local-ticket'),
            operation TEXT NOT NULL,
            natural_key TEXT NOT NULL,
            intended_state_hash TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            evidence_references_json TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, intent_id),
            UNIQUE (tenant_id, idempotency_key),
            UNIQUE (tenant_id, workflow_id, operation),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS side_effect_observations (
            tenant_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            intent_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            status TEXT NOT NULL,
            observed_ticket_id TEXT,
            observed_version INTEGER,
            outcome_sha256 TEXT,
            reason_code TEXT,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, observation_id),
            FOREIGN KEY (tenant_id, intent_id)
                REFERENCES side_effect_intents (tenant_id, intent_id)
        );

        CREATE TABLE IF NOT EXISTS side_effect_completions (
            tenant_id TEXT NOT NULL,
            completion_id TEXT NOT NULL,
            intent_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            observed_ticket_id TEXT NOT NULL,
            observed_version INTEGER NOT NULL CHECK (observed_version >= 1),
            result_sha256 TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, completion_id),
            UNIQUE (tenant_id, intent_id),
            FOREIGN KEY (tenant_id, intent_id)
                REFERENCES side_effect_intents (tenant_id, intent_id)
        );

        CREATE TABLE IF NOT EXISTS fixture_ticket_revisions (
            tenant_id TEXT NOT NULL,
            ticket_id TEXT NOT NULL,
            natural_key TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version >= 1),
            content_sha256 TEXT NOT NULL,
            operation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, ticket_id, version),
            UNIQUE (tenant_id, natural_key, version)
        );

        CREATE TABLE IF NOT EXISTS fixture_ticket_operations (
            tenant_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            operation TEXT NOT NULL,
            natural_key TEXT NOT NULL,
            expected_version INTEGER,
            ticket_id TEXT NOT NULL,
            observed_version INTEGER NOT NULL CHECK (observed_version >= 1),
            outcome_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, idempotency_key),
            FOREIGN KEY (tenant_id, ticket_id, observed_version)
                REFERENCES fixture_ticket_revisions (tenant_id, ticket_id, version)
        );

        CREATE TABLE IF NOT EXISTS workflow_projection (
            tenant_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            workflow_definition_version TEXT NOT NULL,
            state TEXT NOT NULL,
            run_status TEXT NOT NULL,
            workflow_version INTEGER NOT NULL,
            latest_checkpoint_id TEXT NOT NULL,
            latest_checkpoint_sequence INTEGER NOT NULL,
            sla_deadline_at TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, workflow_id),
            UNIQUE (tenant_id, case_id, case_revision_id, workflow_definition_version)
        );

        CREATE INDEX IF NOT EXISTS workflow_activation_case_lookup
            ON workflow_activations (tenant_id, case_id, case_revision_id);
        CREATE INDEX IF NOT EXISTS workflow_checkpoint_lookup
            ON workflow_checkpoints (tenant_id, workflow_id, checkpoint_sequence);
        CREATE INDEX IF NOT EXISTS workflow_intent_natural_key_lookup
            ON side_effect_intents (tenant_id, natural_key);
        CREATE INDEX IF NOT EXISTS workflow_observation_intent_lookup
            ON side_effect_observations (tenant_id, intent_id, recorded_at);
        CREATE INDEX IF NOT EXISTS workflow_ticket_natural_key_lookup
            ON fixture_ticket_revisions (tenant_id, natural_key, version DESC);

        CREATE TRIGGER IF NOT EXISTS workflow_journal_metadata_no_update
        BEFORE UPDATE ON workflow_journal_metadata
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_journal_metadata_no_delete
        BEFORE DELETE ON workflow_journal_metadata
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_activations_no_update
        BEFORE UPDATE ON workflow_activations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_activations_no_delete
        BEFORE DELETE ON workflow_activations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_runs_no_update
        BEFORE UPDATE ON workflow_runs
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_runs_no_delete
        BEFORE DELETE ON workflow_runs
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_commands_no_update
        BEFORE UPDATE ON workflow_commands
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_commands_no_delete
        BEFORE DELETE ON workflow_commands
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_checkpoints_no_update
        BEFORE UPDATE ON workflow_checkpoints
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_checkpoints_no_delete
        BEFORE DELETE ON workflow_checkpoints
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_sla_events_no_update
        BEFORE UPDATE ON workflow_sla_events
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS workflow_sla_events_no_delete
        BEFORE DELETE ON workflow_sla_events
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS side_effect_intents_no_update
        BEFORE UPDATE ON side_effect_intents
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS side_effect_intents_no_delete
        BEFORE DELETE ON side_effect_intents
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS side_effect_observations_no_update
        BEFORE UPDATE ON side_effect_observations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS side_effect_observations_no_delete
        BEFORE DELETE ON side_effect_observations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS side_effect_completions_no_update
        BEFORE UPDATE ON side_effect_completions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS side_effect_completions_no_delete
        BEFORE DELETE ON side_effect_completions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_ticket_revisions_no_update
        BEFORE UPDATE ON fixture_ticket_revisions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_ticket_revisions_no_delete
        BEFORE DELETE ON fixture_ticket_revisions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_ticket_operations_no_update
        BEFORE UPDATE ON fixture_ticket_operations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_ticket_operations_no_delete
        BEFORE DELETE ON fixture_ticket_operations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        """
    )
    versions = {
        str(row["schema_version"])
        for row in connection.execute(
            "SELECT schema_version FROM workflow_journal_metadata"
        ).fetchall()
    }
    if not versions:
        _ensure_side_effect_intent_columns(connection)
        connection.execute(
            "INSERT INTO workflow_journal_metadata (schema_version, installed_at) VALUES (?, ?)",
            (WORKFLOW_JOURNAL_SCHEMA_VERSION, "1970-01-01T00:00:00Z"),
        )
        return
    if versions != {WORKFLOW_JOURNAL_SCHEMA_VERSION}:
        raise WorkflowJournalSchemaError("workflow_journal_schema_unsupported")
    _ensure_side_effect_intent_columns(connection)


def validate_workflow_journal_schema(connection: sqlite3.Connection) -> None:
    """Fail closed when a stored journal advertises an unsupported schema version."""

    try:
        versions = {
            str(row["schema_version"])
            for row in connection.execute(
                "SELECT schema_version FROM workflow_journal_metadata"
            ).fetchall()
        }
    except sqlite3.DatabaseError as error:
        raise WorkflowJournalSchemaError("workflow_journal_schema_missing") from error
    if versions != {WORKFLOW_JOURNAL_SCHEMA_VERSION}:
        raise WorkflowJournalSchemaError("workflow_journal_schema_unsupported")
