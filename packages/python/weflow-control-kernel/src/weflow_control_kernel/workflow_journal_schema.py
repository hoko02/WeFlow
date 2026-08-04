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
    "investigation_activations",
    "agent_steps",
    "investigation_tool_requests",
    "investigation_tool_results",
    "investigation_candidates",
    "investigation_verifier_outcomes",
    "fixture_ticket_revisions",
    "fixture_ticket_operations",
    "policy_approval_activations",
    "capability_grants",
    "capability_grant_status_events",
    "policy_decisions",
    "authorization_bindings",
    "approval_requests",
    "approval_decisions",
    "outbound_delivery_intents",
    "outbound_delivery_observations",
    "outbound_delivery_completions",
    "fixture_delivery_records",
    "fixture_delivery_operations",
    "evidence_artifacts",
    "evidence_trajectories",
    "evidence_reports",
    "trajectory_replay_results",
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


def _ensure_investigation_activation_columns(connection: sqlite3.Connection) -> None:
    """Keep a preview Change 3 store readable after an additive manifest-column upgrade."""

    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(investigation_activations)").fetchall()
    }
    if columns and "evidence_references_json" not in columns:
        connection.execute(
            "ALTER TABLE investigation_activations ADD COLUMN evidence_references_json "
            "TEXT NOT NULL DEFAULT '[]'"
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
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS investigation_activations (
            tenant_id TEXT NOT NULL,
            investigation_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            context_manifest_id TEXT NOT NULL,
            context_sha256 TEXT NOT NULL,
            environment_snapshot_sha256 TEXT NOT NULL,
            evidence_references_json TEXT NOT NULL,
            transcript_id TEXT NOT NULL,
            action_budget INTEGER NOT NULL CHECK (action_budget >= 1),
            tool_budget INTEGER NOT NULL CHECK (tool_budget >= 1),
            no_progress_limit INTEGER NOT NULL CHECK (no_progress_limit >= 1),
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, investigation_id),
            UNIQUE (tenant_id, workflow_id),
            UNIQUE (tenant_id, context_manifest_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS agent_steps (
            tenant_id TEXT NOT NULL,
            agent_step_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            context_manifest_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            action_type TEXT NOT NULL CHECK (action_type IN (
                'read_crm', 'read_monitoring', 'read_knowledge',
                'needs_information', 'needs_operator', 'response_candidate'
            )),
            action_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, agent_step_id),
            UNIQUE (tenant_id, workflow_id, step_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS investigation_tool_requests (
            tenant_id TEXT NOT NULL,
            tool_request_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            context_manifest_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            tool_name TEXT NOT NULL CHECK (tool_name IN ('crm', 'monitoring', 'knowledge')),
            request_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, tool_request_id),
            UNIQUE (tenant_id, workflow_id, step_id, tool_name),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS investigation_tool_results (
            tenant_id TEXT NOT NULL,
            tool_result_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            context_manifest_id TEXT NOT NULL,
            tool_name TEXT NOT NULL CHECK (tool_name IN ('crm', 'monitoring', 'knowledge')),
            tool_request_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            redaction_classification TEXT NOT NULL CHECK (redaction_classification = 'synthetic'),
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, tool_result_id),
            UNIQUE (tenant_id, tool_request_id),
            FOREIGN KEY (tenant_id, tool_request_id)
                REFERENCES investigation_tool_requests (tenant_id, tool_request_id)
        );

        CREATE TABLE IF NOT EXISTS investigation_candidates (
            tenant_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            context_manifest_id TEXT NOT NULL,
            context_sha256 TEXT NOT NULL,
            evidence_hashes_json TEXT NOT NULL,
            candidate_sha256 TEXT NOT NULL,
            risk TEXT NOT NULL CHECK (risk IN ('low', 'medium', 'high')),
            next_step TEXT NOT NULL CHECK (
                next_step IN ('operator_review', 'awaiting_information')
            ),
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, candidate_id),
            UNIQUE (tenant_id, workflow_id, candidate_sha256),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS investigation_verifier_outcomes (
            tenant_id TEXT NOT NULL,
            verifier_outcome_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            context_manifest_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            candidate_sha256 TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('verified', 'rejected')),
            reason_code TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, verifier_outcome_id),
            UNIQUE (tenant_id, candidate_id),
            FOREIGN KEY (tenant_id, candidate_id)
                REFERENCES investigation_candidates (tenant_id, candidate_id)
        );

        CREATE INDEX IF NOT EXISTS investigation_activation_lookup
            ON investigation_activations (tenant_id, workflow_id);
        CREATE INDEX IF NOT EXISTS agent_step_lookup
            ON agent_steps (tenant_id, workflow_id, step_id);
        CREATE INDEX IF NOT EXISTS investigation_tool_result_lookup
            ON investigation_tool_results (tenant_id, workflow_id, tool_request_id);

        CREATE TRIGGER IF NOT EXISTS investigation_activations_no_update
        BEFORE UPDATE ON investigation_activations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_activations_no_delete
        BEFORE DELETE ON investigation_activations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS agent_steps_no_update
        BEFORE UPDATE ON agent_steps
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS agent_steps_no_delete
        BEFORE DELETE ON agent_steps
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_tool_requests_no_update
        BEFORE UPDATE ON investigation_tool_requests
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_tool_requests_no_delete
        BEFORE DELETE ON investigation_tool_requests
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_tool_results_no_update
        BEFORE UPDATE ON investigation_tool_results
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_tool_results_no_delete
        BEFORE DELETE ON investigation_tool_results
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_candidates_no_update
        BEFORE UPDATE ON investigation_candidates
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_candidates_no_delete
        BEFORE DELETE ON investigation_candidates
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_verifier_outcomes_no_update
        BEFORE UPDATE ON investigation_verifier_outcomes
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS investigation_verifier_outcomes_no_delete
        BEFORE DELETE ON investigation_verifier_outcomes
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        """
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS policy_approval_activations (
            tenant_id TEXT NOT NULL,
            policy_approval_activation_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            source_checkpoint_id TEXT NOT NULL,
            fixture_id TEXT NOT NULL CHECK (fixture_id = 'api-503-policy-approval-delivery'),
            policy_version TEXT NOT NULL,
            delivery_resource_id TEXT NOT NULL CHECK (
                delivery_resource_id = 'fixture-local-im:api-503'
            ),
            delivery_resource_scope TEXT NOT NULL CHECK (
                delivery_resource_scope = 'fixture-local-im:api-503'
            ),
            data_classification TEXT NOT NULL CHECK (data_classification = 'synthetic'),
            delivery_budget INTEGER NOT NULL CHECK (delivery_budget >= 0),
            controller_subject_id TEXT NOT NULL,
            controller_role TEXT NOT NULL CHECK (controller_role = 'fixture-controller'),
            candidate_hash TEXT NOT NULL,
            evidence_hashes_json TEXT NOT NULL,
            activated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, policy_approval_activation_id),
            UNIQUE (tenant_id, workflow_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS capability_grants (
            tenant_id TEXT NOT NULL,
            grant_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            grant_sha256 TEXT NOT NULL,
            grant_version TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            role TEXT NOT NULL,
            resource_scope TEXT NOT NULL,
            data_classifications_json TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (tenant_id, grant_id),
            UNIQUE (tenant_id, grant_sha256),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS capability_grant_status_events (
            tenant_id TEXT NOT NULL,
            grant_status_event_id TEXT NOT NULL,
            grant_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('revoked', 'expired')),
            reason_code TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, grant_status_event_id),
            UNIQUE (tenant_id, grant_id, status),
            FOREIGN KEY (tenant_id, grant_id)
                REFERENCES capability_grants (tenant_id, grant_id)
        );

        CREATE TABLE IF NOT EXISTS policy_decisions (
            tenant_id TEXT NOT NULL,
            policy_decision_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK (
                action IN ('approval.request', 'approval.decide', 'outbound_delivery.execute')
            ),
            policy_decision_sha256 TEXT NOT NULL,
            policy_input_sha256 TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('allow', 'deny')),
            reason_code TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            grant_id TEXT NOT NULL,
            grant_sha256 TEXT NOT NULL,
            candidate_hash TEXT NOT NULL,
            evidence_hashes_json TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            role TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            data_classification TEXT NOT NULL,
            workflow_version INTEGER NOT NULL CHECK (workflow_version >= 0),
            payload_json TEXT NOT NULL,
            decided_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, policy_decision_id),
            UNIQUE (tenant_id, workflow_id, action, policy_input_sha256),
            UNIQUE (tenant_id, policy_decision_sha256),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS authorization_bindings (
            tenant_id TEXT NOT NULL,
            authorization_binding_id TEXT NOT NULL,
            authorization_binding_sha256 TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            policy_decision_id TEXT NOT NULL,
            grant_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            workflow_version INTEGER NOT NULL CHECK (workflow_version >= 0),
            candidate_hash TEXT NOT NULL,
            evidence_hashes_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, authorization_binding_id),
            UNIQUE (tenant_id, authorization_binding_sha256),
            UNIQUE (tenant_id, workflow_id, policy_decision_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS approval_requests (
            tenant_id TEXT NOT NULL,
            approval_request_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            authorization_binding_sha256 TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            workflow_version INTEGER NOT NULL CHECK (workflow_version >= 0),
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, approval_request_id),
            UNIQUE (tenant_id, workflow_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS approval_decisions (
            tenant_id TEXT NOT NULL,
            approval_decision_id TEXT NOT NULL,
            approval_request_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            authorization_binding_sha256 TEXT NOT NULL,
            workflow_version INTEGER NOT NULL CHECK (workflow_version >= 0),
            decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
            decision_sha256 TEXT NOT NULL,
            approver_id TEXT NOT NULL,
            approver_role TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            decided_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, approval_decision_id),
            UNIQUE (tenant_id, approval_request_id),
            UNIQUE (tenant_id, decision_sha256),
            FOREIGN KEY (tenant_id, approval_request_id)
                REFERENCES approval_requests (tenant_id, approval_request_id)
        );

        CREATE TABLE IF NOT EXISTS outbound_delivery_intents (
            tenant_id TEXT NOT NULL,
            intent_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            authorization_binding_sha256 TEXT NOT NULL,
            candidate_hash TEXT NOT NULL,
            evidence_hashes_json TEXT NOT NULL,
            channel TEXT NOT NULL CHECK (channel = 'fixture-local-im'),
            conversation_id TEXT NOT NULL,
            delivery_resource_id TEXT NOT NULL CHECK (
                delivery_resource_id = 'fixture-local-im:api-503'
            ),
            natural_key TEXT NOT NULL,
            intended_state_hash TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, intent_id),
            UNIQUE (tenant_id, idempotency_key),
            UNIQUE (tenant_id, workflow_id),
            FOREIGN KEY (tenant_id, workflow_id)
                REFERENCES workflow_activations (tenant_id, workflow_id)
        );

        CREATE TABLE IF NOT EXISTS outbound_delivery_observations (
            tenant_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            intent_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('absent', 'present', 'unknown', 'conflict')),
            observed_delivery_id TEXT,
            observed_version INTEGER,
            content_sha256 TEXT,
            reason_code TEXT,
            payload_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, observation_id),
            FOREIGN KEY (tenant_id, intent_id)
                REFERENCES outbound_delivery_intents (tenant_id, intent_id)
        );

        CREATE TABLE IF NOT EXISTS outbound_delivery_completions (
            tenant_id TEXT NOT NULL,
            completion_id TEXT NOT NULL,
            intent_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            checkpoint_id TEXT NOT NULL,
            observation_id TEXT NOT NULL,
            observed_delivery_id TEXT NOT NULL,
            observed_version INTEGER NOT NULL CHECK (observed_version >= 1),
            content_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, completion_id),
            UNIQUE (tenant_id, intent_id),
            FOREIGN KEY (tenant_id, intent_id)
                REFERENCES outbound_delivery_intents (tenant_id, intent_id)
        );

        CREATE TABLE IF NOT EXISTS fixture_delivery_records (
            tenant_id TEXT NOT NULL,
            delivery_id TEXT NOT NULL,
            natural_key TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version >= 1),
            content_sha256 TEXT NOT NULL,
            data_classification TEXT NOT NULL CHECK (data_classification = 'synthetic'),
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, delivery_id, version),
            UNIQUE (tenant_id, natural_key, version)
        );

        CREATE TABLE IF NOT EXISTS fixture_delivery_operations (
            tenant_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            natural_key TEXT NOT NULL,
            delivery_id TEXT NOT NULL,
            observed_version INTEGER NOT NULL CHECK (observed_version >= 1),
            content_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, idempotency_key),
            FOREIGN KEY (tenant_id, delivery_id, observed_version)
                REFERENCES fixture_delivery_records (tenant_id, delivery_id, version)
        );

        CREATE INDEX IF NOT EXISTS policy_activation_lookup
            ON policy_approval_activations (tenant_id, workflow_id);
        CREATE INDEX IF NOT EXISTS policy_decision_lookup
            ON policy_decisions (tenant_id, workflow_id, action);
        CREATE INDEX IF NOT EXISTS approval_request_lookup
            ON approval_requests (tenant_id, workflow_id);
        CREATE INDEX IF NOT EXISTS delivery_intent_natural_key_lookup
            ON outbound_delivery_intents (tenant_id, natural_key);
        CREATE INDEX IF NOT EXISTS delivery_observation_lookup
            ON outbound_delivery_observations (tenant_id, intent_id, recorded_at);
        CREATE INDEX IF NOT EXISTS fixture_delivery_natural_key_lookup
            ON fixture_delivery_records (tenant_id, natural_key, version DESC);

        CREATE TRIGGER IF NOT EXISTS policy_approval_activations_no_update
        BEFORE UPDATE ON policy_approval_activations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS policy_approval_activations_no_delete
        BEFORE DELETE ON policy_approval_activations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS capability_grants_no_update
        BEFORE UPDATE ON capability_grants
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS capability_grants_no_delete
        BEFORE DELETE ON capability_grants
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS capability_grant_status_events_no_update
        BEFORE UPDATE ON capability_grant_status_events
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS capability_grant_status_events_no_delete
        BEFORE DELETE ON capability_grant_status_events
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS policy_decisions_no_update
        BEFORE UPDATE ON policy_decisions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS policy_decisions_no_delete
        BEFORE DELETE ON policy_decisions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS authorization_bindings_no_update
        BEFORE UPDATE ON authorization_bindings
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS authorization_bindings_no_delete
        BEFORE DELETE ON authorization_bindings
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS approval_requests_no_update
        BEFORE UPDATE ON approval_requests
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS approval_requests_no_delete
        BEFORE DELETE ON approval_requests
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS approval_decisions_no_update
        BEFORE UPDATE ON approval_decisions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS approval_decisions_no_delete
        BEFORE DELETE ON approval_decisions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS outbound_delivery_intents_no_update
        BEFORE UPDATE ON outbound_delivery_intents
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS outbound_delivery_intents_no_delete
        BEFORE DELETE ON outbound_delivery_intents
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS outbound_delivery_observations_no_update
        BEFORE UPDATE ON outbound_delivery_observations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS outbound_delivery_observations_no_delete
        BEFORE DELETE ON outbound_delivery_observations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS outbound_delivery_completions_no_update
        BEFORE UPDATE ON outbound_delivery_completions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS outbound_delivery_completions_no_delete
        BEFORE DELETE ON outbound_delivery_completions
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_delivery_records_no_update
        BEFORE UPDATE ON fixture_delivery_records
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_delivery_records_no_delete
        BEFORE DELETE ON fixture_delivery_records
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_delivery_operations_no_update
        BEFORE UPDATE ON fixture_delivery_operations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        CREATE TRIGGER IF NOT EXISTS fixture_delivery_operations_no_delete
        BEFORE DELETE ON fixture_delivery_operations
        BEGIN
            SELECT RAISE(ABORT, 'append_only_violation');
        END;
        """
    )
    _ensure_investigation_activation_columns(connection)
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
