# ruff: noqa: E501
"""Append-only, redacted evidence trajectories over retained offline workflow facts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from weflow_contracts import (
    ARTIFACT_SCHEMA_ID,
    EVIDENCE_REPORT_SCHEMA_ID,
    EVIDENCE_TRAJECTORY_SCHEMA_ID,
    TRAJECTORY_REPLAY_RESULT_SCHEMA_ID,
    ContractValidationError,
    content_hash,
    validate_artifact,
    validate_evidence_chain,
    validate_evidence_report,
    validate_evidence_trajectory,
    validate_trajectory_replay_result,
)

if TYPE_CHECKING:
    from .durable_workflow import SQLiteDurableWorkflow

JsonObject = dict[str, Any]
EVIDENCE_PROFILE_ID = "fixture-local-evidence.v1"
EVIDENCE_FIXTURE_ID = "api-503-policy-approval-delivery"
_ZERO_HASH = "0" * 64


class EvidenceLineageError(ValueError):
    """Safe error that intentionally never contains source payload values."""


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _stable_identifier(prefix: str, material: object) -> str:
    return f"{prefix}_{_sha256({'prefix': prefix, 'material': material})[:32]}"


def initialize_evidence_trajectory_schema(connection: sqlite3.Connection) -> None:
    """Create only additive evidence tables protected from update/delete."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS evidence_artifacts (
            tenant_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            trajectory_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, artifact_id),
            UNIQUE (tenant_id, trajectory_id)
        );
        CREATE TABLE IF NOT EXISTS evidence_trajectories (
            tenant_id TEXT NOT NULL,
            trajectory_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            case_revision_id TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            report_profile_id TEXT NOT NULL,
            root_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, trajectory_id),
            UNIQUE (tenant_id, case_id, case_revision_id, workflow_id, report_profile_id)
        );
        CREATE TABLE IF NOT EXISTS evidence_reports (
            tenant_id TEXT NOT NULL,
            report_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            trajectory_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, report_id),
            UNIQUE (tenant_id, artifact_id),
            UNIQUE (tenant_id, trajectory_id)
        );
        CREATE TABLE IF NOT EXISTS trajectory_replay_results (
            tenant_id TEXT NOT NULL,
            replay_result_id TEXT NOT NULL,
            trajectory_id TEXT NOT NULL,
            result_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, replay_result_id),
            UNIQUE (tenant_id, trajectory_id, result_sha256)
        );
        CREATE INDEX IF NOT EXISTS evidence_trajectory_case_lookup
            ON evidence_trajectories (tenant_id, case_id, workflow_id);
        CREATE INDEX IF NOT EXISTS evidence_report_trajectory_lookup
            ON evidence_reports (tenant_id, trajectory_id);
        CREATE TRIGGER IF NOT EXISTS evidence_artifacts_no_update
        BEFORE UPDATE ON evidence_artifacts BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        CREATE TRIGGER IF NOT EXISTS evidence_artifacts_no_delete
        BEFORE DELETE ON evidence_artifacts BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        CREATE TRIGGER IF NOT EXISTS evidence_trajectories_no_update
        BEFORE UPDATE ON evidence_trajectories BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        CREATE TRIGGER IF NOT EXISTS evidence_trajectories_no_delete
        BEFORE DELETE ON evidence_trajectories BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        CREATE TRIGGER IF NOT EXISTS evidence_reports_no_update
        BEFORE UPDATE ON evidence_reports BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        CREATE TRIGGER IF NOT EXISTS evidence_reports_no_delete
        BEFORE DELETE ON evidence_reports BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        CREATE TRIGGER IF NOT EXISTS trajectory_replay_results_no_update
        BEFORE UPDATE ON trajectory_replay_results BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        CREATE TRIGGER IF NOT EXISTS trajectory_replay_results_no_delete
        BEFORE DELETE ON trajectory_replay_results BEGIN SELECT RAISE(ABORT, 'append_only_violation'); END;
        """
    )


def _row(row: sqlite3.Row) -> JsonObject:
    return {key: row[key] for key in row.keys()}


def _one(
    connection: sqlite3.Connection, query: str, params: tuple[object, ...]
) -> JsonObject | None:
    row = connection.execute(query, params).fetchone()
    return None if row is None else _row(row)


def _rows(
    connection: sqlite3.Connection, query: str, params: tuple[object, ...]
) -> list[JsonObject]:
    return [_row(row) for row in connection.execute(query, params).fetchall()]


def _payload(row: Mapping[str, Any]) -> JsonObject:
    try:
        value = json.loads(str(row["payload_json"]))
    except (KeyError, json.JSONDecodeError) as error:
        raise EvidenceLineageError("lineage_invalid") from error
    if not isinstance(value, dict):
        raise EvidenceLineageError("lineage_invalid")
    return value


def _safe_hash(row: Mapping[str, Any], *fields: str) -> str:
    material = {field: row.get(field) for field in fields}
    return _sha256(material)


def _append_node(
    nodes: list[JsonObject],
    *,
    source_kind: str,
    source_identifier: object,
    digest: object,
    classification: str = "redacted",
) -> None:
    if not isinstance(source_identifier, str) or not source_identifier:
        raise EvidenceLineageError("lineage_invalid")
    if not isinstance(digest, str) or len(digest) != 64:
        raise EvidenceLineageError("lineage_invalid")
    source_id = f"{source_kind}:{source_identifier}"
    if any(node["source_id"] == source_id for node in nodes):
        raise EvidenceLineageError("lineage_invalid")
    sequence = len(nodes) + 1
    predecessor = None if not nodes else nodes[-1]["node_id"]
    node_id = _stable_identifier("evidence_node", {"source_id": source_id, "sequence": sequence})
    nodes.append(
        {
            "node_id": node_id,
            "sequence": sequence,
            "source_kind": source_kind,
            "source_id": source_id,
            "predecessor_node_id": predecessor,
            "content_sha256": digest,
            "classification": classification,
        }
    )


def _source_nodes(
    workflow: SQLiteDurableWorkflow, tenant_id: str, case_id: str
) -> tuple[JsonObject, list[JsonObject], str]:
    projection = workflow.ledger.get_case_projection(tenant_id, case_id)
    revisions = workflow.ledger.list_case_revisions(tenant_id, case_id)
    events = workflow.ledger.list_case_events(tenant_id, case_id)
    if projection is None or len(revisions) != 1 or not events:
        raise EvidenceLineageError("lineage_invalid")
    activation = workflow._activation_for_case_for_tenant(tenant_id, case_id)
    if activation is None or activation["case_revision_id"] != revisions[0]["case_revision_id"]:
        raise EvidenceLineageError("lineage_invalid")
    workflow_id = str(activation["workflow_id"])
    nodes: list[JsonObject] = []
    _append_node(
        nodes,
        source_kind="accepted_intake",
        source_identifier=str(events[0]["event_id"]),
        digest=str(events[0]["payload_sha256"]),
        classification="synthetic",
    )
    _append_node(
        nodes,
        source_kind="case_revision",
        source_identifier=str(revisions[0]["case_revision_id"]),
        digest=str(revisions[0]["source_event_fingerprint"]),
        classification="synthetic",
    )
    for event in events[1:]:
        _append_node(
            nodes,
            source_kind="case_event",
            source_identifier=str(event["event_id"]),
            digest=str(event["payload_sha256"]),
            classification="synthetic",
        )
    _append_node(
        nodes,
        source_kind="workflow_activation",
        source_identifier=str(activation["activation_id"]),
        digest=_safe_hash(
            activation, "workflow_id", "activation_id", "source_event_id", "created_at"
        ),
    )
    connection = workflow._connect()
    try:
        checkpoints = _rows(
            connection,
            "SELECT * FROM workflow_checkpoints WHERE tenant_id = ? AND workflow_id = ? ORDER BY checkpoint_sequence",
            (tenant_id, workflow_id),
        )
        investigation = _one(
            connection,
            "SELECT * FROM investigation_activations WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        )
        agent_steps = _rows(
            connection,
            "SELECT * FROM agent_steps WHERE tenant_id = ? AND workflow_id = ? ORDER BY step_id",
            (tenant_id, workflow_id),
        )
        tool_requests = _rows(
            connection,
            "SELECT * FROM investigation_tool_requests WHERE tenant_id = ? AND workflow_id = ? ORDER BY step_id, tool_name",
            (tenant_id, workflow_id),
        )
        tool_results = _rows(
            connection,
            "SELECT * FROM investigation_tool_results WHERE tenant_id = ? AND workflow_id = ? ORDER BY tool_request_id",
            (tenant_id, workflow_id),
        )
        candidates = _rows(
            connection,
            "SELECT * FROM investigation_candidates WHERE tenant_id = ? AND workflow_id = ? ORDER BY candidate_id",
            (tenant_id, workflow_id),
        )
        verifier = _rows(
            connection,
            "SELECT * FROM investigation_verifier_outcomes WHERE tenant_id = ? AND workflow_id = ? ORDER BY verifier_outcome_id",
            (tenant_id, workflow_id),
        )
        policy_activation = _one(
            connection,
            "SELECT * FROM policy_approval_activations WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        )
        grants = _rows(
            connection,
            "SELECT * FROM capability_grants WHERE tenant_id = ? AND workflow_id = ? ORDER BY grant_id",
            (tenant_id, workflow_id),
        )
        decisions = _rows(
            connection,
            "SELECT * FROM policy_decisions WHERE tenant_id = ? AND workflow_id = ? ORDER BY policy_decision_id",
            (tenant_id, workflow_id),
        )
        bindings = _rows(
            connection,
            "SELECT * FROM authorization_bindings WHERE tenant_id = ? AND workflow_id = ? ORDER BY authorization_binding_id",
            (tenant_id, workflow_id),
        )
        approvals = _rows(
            connection,
            "SELECT * FROM approval_requests WHERE tenant_id = ? AND workflow_id = ? ORDER BY approval_request_id",
            (tenant_id, workflow_id),
        )
        approval_decisions = _rows(
            connection,
            "SELECT * FROM approval_decisions WHERE tenant_id = ? AND workflow_id = ? ORDER BY approval_decision_id",
            (tenant_id, workflow_id),
        )
        delivery_intents = _rows(
            connection,
            "SELECT * FROM outbound_delivery_intents WHERE tenant_id = ? AND workflow_id = ? ORDER BY intent_id",
            (tenant_id, workflow_id),
        )
        delivery_completions = _rows(
            connection,
            "SELECT * FROM outbound_delivery_completions WHERE tenant_id = ? AND workflow_id = ? ORDER BY completion_id",
            (tenant_id, workflow_id),
        )
    finally:
        connection.close()
    if (
        not checkpoints
        or investigation is None
        or not agent_steps
        or not tool_requests
        or not tool_results
        or not candidates
        or not verifier
        or policy_activation is None
        or not grants
        or not decisions
        or not bindings
        or not approvals
    ):
        raise EvidenceLineageError("lineage_invalid")
    for checkpoint in checkpoints:
        payload = workflow._checkpoint_payload(checkpoint)
        if payload["content_sha256"] != checkpoint["content_sha256"]:
            raise EvidenceLineageError("lineage_invalid")
        _append_node(
            nodes,
            source_kind="workflow_checkpoint",
            source_identifier=str(checkpoint["checkpoint_id"]),
            digest=str(checkpoint["content_sha256"]),
        )
    _append_node(
        nodes,
        source_kind="context_manifest",
        source_identifier=str(investigation["context_manifest_id"]),
        digest=str(investigation["context_sha256"]),
    )
    for step in agent_steps:
        _append_node(
            nodes,
            source_kind="agent_step",
            source_identifier=str(step["agent_step_id"]),
            digest=str(step["action_sha256"]),
        )
    for request in tool_requests:
        _append_node(
            nodes,
            source_kind="tool_request",
            source_identifier=str(request["tool_request_id"]),
            digest=str(request["request_sha256"]),
        )
    for result in tool_results:
        _append_node(
            nodes,
            source_kind="tool_result",
            source_identifier=str(result["tool_result_id"]),
            digest=str(result["content_sha256"]),
            classification="synthetic",
        )
        _append_node(
            nodes,
            source_kind="evidence",
            source_identifier=str(result["evidence_id"]),
            digest=str(result["content_sha256"]),
            classification="synthetic",
        )
    for candidate in candidates:
        _append_node(
            nodes,
            source_kind="response_candidate",
            source_identifier=str(candidate["candidate_id"]),
            digest=str(candidate["candidate_sha256"]),
        )
    for outcome in verifier:
        _append_node(
            nodes,
            source_kind="verifier_outcome",
            source_identifier=str(outcome["verifier_outcome_id"]),
            digest=_safe_hash(outcome, "candidate_sha256", "outcome", "reason_code", "recorded_at"),
        )
    _append_node(
        nodes,
        source_kind="policy_activation",
        source_identifier=str(policy_activation["policy_approval_activation_id"]),
        digest=_safe_hash(
            policy_activation, "candidate_hash", "evidence_hashes_json", "activated_at"
        ),
    )
    for grant in grants:
        _append_node(
            nodes,
            source_kind="capability_grant",
            source_identifier=str(grant["grant_id"]),
            digest=str(grant["grant_sha256"]),
        )
    for decision in decisions:
        _append_node(
            nodes,
            source_kind="policy_decision",
            source_identifier=str(decision["policy_decision_id"]),
            digest=str(decision["policy_decision_sha256"]),
        )
    for binding in bindings:
        _append_node(
            nodes,
            source_kind="authorization_binding",
            source_identifier=str(binding["authorization_binding_id"]),
            digest=str(binding["authorization_binding_sha256"]),
        )
    for approval in approvals:
        _append_node(
            nodes,
            source_kind="approval_request",
            source_identifier=str(approval["approval_request_id"]),
            digest=_safe_hash(
                approval, "authorization_binding_sha256", "checkpoint_id", "created_at"
            ),
        )
    for decision in approval_decisions:
        _append_node(
            nodes,
            source_kind="approval_decision",
            source_identifier=str(decision["approval_decision_id"]),
            digest=str(decision["decision_sha256"]),
        )
    for intent in delivery_intents:
        _append_node(
            nodes,
            source_kind="delivery_intent",
            source_identifier=str(intent["intent_id"]),
            digest=str(_payload(intent).get("intended_state_hash", "")),
        )
    for completion in delivery_completions:
        _append_node(
            nodes,
            source_kind="delivery_completion",
            source_identifier=str(completion["completion_id"]),
            digest=str(completion["content_sha256"]),
            classification="synthetic",
        )
    final_state = str(workflow.get_workflow_projection(tenant_id, workflow_id)["state"])
    if final_state == "DELIVERY_RECORDED" and (
        len(delivery_intents) != 1 or len(delivery_completions) != 1
    ):
        raise EvidenceLineageError("lineage_invalid")
    return activation, nodes, final_state


def _outcome_for(state: str, requested_outcome: str | None) -> tuple[str, str | None]:
    allowed = {"fixture_delivery_recorded", "recovered_after_interruption"}
    if state == "DELIVERY_RECORDED":
        return (
            requested_outcome if requested_outcome in allowed else "fixture_delivery_recorded",
            None,
        )
    if state == "WAITING_FOR_OPERATOR":
        return "authorization_denied", "authorization_denied_grant_revoked"
    if state == "NEEDS_RECONCILIATION":
        return "needs_reconciliation", "needs_reconciliation"
    raise EvidenceLineageError("lineage_invalid")


def _load_payload(row: JsonObject | None) -> JsonObject | None:
    if row is None:
        return None
    return _payload(row)


def _safe_failure(reason: str = "lineage_invalid") -> JsonObject:
    return {
        "outcome": "lineage_invalid",
        "failure_code": reason,
        "network_required": False,
        "model_invocation": False,
        "external_write": False,
        "docker_required": False,
    }


def extract_evidence_trajectory(
    workflow: SQLiteDurableWorkflow,
    tenant_id: str,
    case_id: str,
    *,
    requested_outcome: str | None = None,
) -> JsonObject:
    """Persist an idempotent redacted trajectory/report; never advance workflow control."""

    try:
        activation, nodes, state = _source_nodes(workflow, tenant_id, case_id)
        outcome, failure_code = _outcome_for(state, requested_outcome)
    except (EvidenceLineageError, KeyError, TypeError):
        return _safe_failure()
    trajectory_id = _stable_identifier(
        "evidence_trajectory",
        {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "case_revision_id": activation["case_revision_id"],
            "workflow_id": activation["workflow_id"],
            "report_profile_id": EVIDENCE_PROFILE_ID,
        },
    )
    trajectory: JsonObject = {
        "schema_id": EVIDENCE_TRAJECTORY_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": tenant_id,
        "trajectory_id": trajectory_id,
        "case_id": case_id,
        "case_revision_id": activation["case_revision_id"],
        "workflow_id": activation["workflow_id"],
        "report_profile_id": EVIDENCE_PROFILE_ID,
        "root_sha256": "",
        "nodes": nodes,
        "created_at": activation["created_at"],
    }
    trajectory["root_sha256"] = content_hash(trajectory, without="root_sha256")
    report_id = _stable_identifier(
        "evidence_report",
        {
            "trajectory_root_sha256": trajectory["root_sha256"],
            "outcome": outcome,
            "report_profile_id": EVIDENCE_PROFILE_ID,
        },
    )
    artifact_id = _stable_identifier(
        "evidence_artifact",
        {"report_id": report_id, "trajectory_root_sha256": trajectory["root_sha256"]},
    )
    report: JsonObject = {
        "schema_id": EVIDENCE_REPORT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": tenant_id,
        "report_id": report_id,
        "artifact_id": artifact_id,
        "trajectory_id": trajectory_id,
        "trajectory_root_sha256": trajectory["root_sha256"],
        "report_profile_id": EVIDENCE_PROFILE_ID,
        "fixture_id": EVIDENCE_FIXTURE_ID,
        "outcome": outcome,
        "failure_code": failure_code,
        "node_count": len(nodes),
        "capabilities": {
            "network_required": False,
            "model_invocation": False,
            "external_write": False,
            "docker_required": False,
        },
        "content_sha256": "",
        "created_at": activation["created_at"],
    }
    report["content_sha256"] = content_hash(report, without="content_sha256")
    artifact: JsonObject = {
        "schema_id": ARTIFACT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": tenant_id,
        "artifact_id": artifact_id,
        "artifact_kind": "evidence_report",
        "case_id": case_id,
        "case_revision_id": activation["case_revision_id"],
        "workflow_id": activation["workflow_id"],
        "trajectory_id": trajectory_id,
        "report_profile_id": EVIDENCE_PROFILE_ID,
        "content_sha256": report["content_sha256"],
        "media_type": "application/vnd.weflow.evidence-report+json",
        "redaction_classification": "redacted",
        "created_at": activation["created_at"],
        "producer": "fixture-local-evidence",
    }
    try:
        validate_evidence_trajectory(trajectory, workflow._contract_root)
        validate_evidence_report(report, workflow._contract_root, trajectory=trajectory)
        validate_artifact(artifact, workflow._contract_root)
    except ContractValidationError:
        return _safe_failure()
    connection = workflow._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = _load_payload(
            _one(
                connection,
                "SELECT payload_json FROM evidence_trajectories WHERE tenant_id = ? AND trajectory_id = ?",
                (tenant_id, trajectory_id),
            )
        )
        if existing is not None:
            try:
                validate_evidence_trajectory(existing, workflow._contract_root)
            except ContractValidationError:
                connection.rollback()
                return _safe_failure()
            trajectory = existing
            report_row = _one(
                connection,
                "SELECT payload_json FROM evidence_reports WHERE tenant_id = ? AND trajectory_id = ?",
                (tenant_id, trajectory_id),
            )
            artifact_row = _one(
                connection,
                "SELECT payload_json FROM evidence_artifacts WHERE tenant_id = ? AND trajectory_id = ?",
                (tenant_id, trajectory_id),
            )
            if report_row is not None and artifact_row is not None:
                report = _payload(report_row)
                artifact = _payload(artifact_row)
                connection.commit()
                return {
                    "trajectory": trajectory,
                    "report": report,
                    "artifact": artifact,
                    "idempotent": True,
                }
        else:
            connection.execute(
                "INSERT INTO evidence_trajectories (tenant_id, trajectory_id, case_id, case_revision_id, workflow_id, report_profile_id, root_sha256, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    trajectory_id,
                    case_id,
                    activation["case_revision_id"],
                    activation["workflow_id"],
                    EVIDENCE_PROFILE_ID,
                    trajectory["root_sha256"],
                    _canonical(trajectory),
                    activation["created_at"],
                ),
            )
        connection.execute(
            "INSERT INTO evidence_artifacts (tenant_id, artifact_id, trajectory_id, content_sha256, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                artifact_id,
                trajectory_id,
                artifact["content_sha256"],
                _canonical(artifact),
                activation["created_at"],
            ),
        )
        connection.execute(
            "INSERT INTO evidence_reports (tenant_id, report_id, artifact_id, trajectory_id, content_sha256, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                report_id,
                artifact_id,
                trajectory_id,
                report["content_sha256"],
                _canonical(report),
                activation["created_at"],
            ),
        )
        connection.commit()
        return {
            "trajectory": trajectory,
            "report": report,
            "artifact": artifact,
            "idempotent": False,
        }
    except sqlite3.DatabaseError:
        connection.rollback()
        return _safe_failure()
    finally:
        connection.close()


def replay_evidence_trajectory(
    workflow: SQLiteDurableWorkflow, tenant_id: str, trajectory_id: str
) -> JsonObject:
    """Verify recorded lineage against current source facts without re-executing anything."""

    connection = workflow._connect()
    try:
        trajectory = _load_payload(
            _one(
                connection,
                "SELECT payload_json FROM evidence_trajectories WHERE tenant_id = ? AND trajectory_id = ?",
                (tenant_id, trajectory_id),
            )
        )
        report = _load_payload(
            _one(
                connection,
                "SELECT payload_json FROM evidence_reports WHERE tenant_id = ? AND trajectory_id = ?",
                (tenant_id, trajectory_id),
            )
        )
        artifact = _load_payload(
            _one(
                connection,
                "SELECT payload_json FROM evidence_artifacts WHERE tenant_id = ? AND trajectory_id = ?",
                (tenant_id, trajectory_id),
            )
        )
    finally:
        connection.close()
    if trajectory is None or report is None or artifact is None:
        return _safe_failure()
    try:
        validate_evidence_trajectory(trajectory, workflow._contract_root)
        validate_evidence_report(report, workflow._contract_root, trajectory=trajectory)
        validate_artifact(artifact, workflow._contract_root)
        _, replayed_nodes, _ = _source_nodes(workflow, tenant_id, str(trajectory["case_id"]))
        replayed = {**trajectory, "nodes": replayed_nodes, "root_sha256": ""}
        replayed["root_sha256"] = content_hash(replayed, without="root_sha256")
        verified = replayed["root_sha256"] == trajectory["root_sha256"]
    except (ContractValidationError, EvidenceLineageError, KeyError, TypeError):
        verified = False
        replayed = {"root_sha256": _ZERO_HASH}
    result: JsonObject = {
        "schema_id": TRAJECTORY_REPLAY_RESULT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": tenant_id,
        "replay_result_id": _stable_identifier(
            "trajectory_replay",
            {
                "trajectory_id": trajectory_id,
                "recorded_root": trajectory.get("root_sha256"),
                "replayed_root": replayed["root_sha256"],
            },
        ),
        "trajectory_id": trajectory_id,
        "report_id": report["report_id"],
        "report_sha256": report["content_sha256"],
        "recorded_root_sha256": trajectory["root_sha256"],
        "replayed_root_sha256": replayed["root_sha256"],
        "mode": "verification_replay",
        "verification_outcome": "verified" if verified else "lineage_invalid",
        "failure_code": None if verified else "lineage_invalid",
        "capabilities": {
            "network_required": False,
            "model_invocation": False,
            "external_write": False,
            "docker_required": False,
        },
        "result_sha256": "",
        "recorded_at": trajectory["created_at"],
    }
    result["result_sha256"] = content_hash(result, without="result_sha256")
    try:
        validate_trajectory_replay_result(
            result, workflow._contract_root, trajectory=trajectory, report=report
        )
        if verified:
            validate_evidence_chain(artifact, trajectory, report, result, workflow._contract_root)
    except ContractValidationError:
        return _safe_failure()
    connection = workflow._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = _load_payload(
            _one(
                connection,
                "SELECT payload_json FROM trajectory_replay_results WHERE tenant_id = ? AND trajectory_id = ? AND result_sha256 = ?",
                (tenant_id, trajectory_id, result["result_sha256"]),
            )
        )
        if existing is None:
            connection.execute(
                "INSERT INTO trajectory_replay_results (tenant_id, replay_result_id, trajectory_id, result_sha256, payload_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    result["replay_result_id"],
                    trajectory_id,
                    result["result_sha256"],
                    _canonical(result),
                    result["recorded_at"],
                ),
            )
        else:
            result = existing
        connection.commit()
    except sqlite3.DatabaseError:
        connection.rollback()
        return _safe_failure()
    finally:
        connection.close()
    return {
        "trajectory": trajectory,
        "report": report,
        "artifact": artifact,
        "replay_result": result,
    }


def evidence_report_for_case(
    workflow: SQLiteDurableWorkflow, tenant_id: str, case_id: str
) -> JsonObject | None:
    """Return a previously persisted report only; this function never triggers extraction."""

    activation = workflow._activation_for_case_for_tenant(tenant_id, case_id)
    if activation is None:
        return None
    connection = workflow._connect()
    try:
        row = _one(
            connection,
            "SELECT report.payload_json FROM evidence_reports AS report JOIN evidence_trajectories AS trajectory ON trajectory.tenant_id = report.tenant_id AND trajectory.trajectory_id = report.trajectory_id WHERE report.tenant_id = ? AND trajectory.case_id = ? ORDER BY report.report_id",
            (tenant_id, case_id),
        )
        return _load_payload(row)
    finally:
        connection.close()
