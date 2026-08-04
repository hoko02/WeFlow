# ruff: noqa: E501
"""Closed, redacted contracts for fixture-local evidence trajectories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .authorization import canonical_sha256, content_hash
from .validation import ContractValidationError, validate_payload

ARTIFACT_SCHEMA_ID = "https://weflow.local/contracts/v1/artifact.schema.json"
EVIDENCE_TRAJECTORY_SCHEMA_ID = "https://weflow.local/contracts/v1/evidence-trajectory.schema.json"
EVIDENCE_REPORT_SCHEMA_ID = "https://weflow.local/contracts/v1/evidence-report.schema.json"
TRAJECTORY_REPLAY_RESULT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/trajectory-replay-result.schema.json"
)


def _validate(payload: Mapping[str, Any], schema_id: str, name: str, root: Any = None) -> None:
    validate_payload(payload, root)
    if payload.get("schema_id") != schema_id:
        raise ContractValidationError(name, "unexpected_schema")


def _same(
    left: Mapping[str, Any], right: Mapping[str, Any], fields: Sequence[str], name: str
) -> None:
    for field in fields:
        if left.get(field) != right.get(field):
            reason = "tenant_identity_mismatch" if field == "tenant_id" else "causation_mismatch"
            raise ContractValidationError(name, reason)


def validate_artifact(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, ARTIFACT_SCHEMA_ID, "artifact", root)


def validate_evidence_trajectory(payload: Mapping[str, Any], root: Any = None) -> None:
    _validate(payload, EVIDENCE_TRAJECTORY_SCHEMA_ID, "evidence-trajectory", root)
    if payload.get("root_sha256") != content_hash(payload, without="root_sha256"):
        raise ContractValidationError("evidence-trajectory", "root_sha256_mismatch")
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        raise ContractValidationError("evidence-trajectory", "nodes_invalid")
    node_ids = [node.get("node_id") for node in nodes if isinstance(node, Mapping)]
    source_ids = [node.get("source_id") for node in nodes if isinstance(node, Mapping)]
    if len(node_ids) != len(nodes) or len(node_ids) != len(set(node_ids)):
        raise ContractValidationError("evidence-trajectory", "duplicate_node_identity")
    if len(source_ids) != len(nodes) or len(source_ids) != len(set(source_ids)):
        raise ContractValidationError("evidence-trajectory", "duplicate_source_identity")
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, Mapping) or node.get("sequence") != index:
            raise ContractValidationError("evidence-trajectory", "node_order_invalid")
        predecessor = node.get("predecessor_node_id")
        expected = None if index == 1 else node_ids[index - 2]
        if predecessor != expected:
            raise ContractValidationError("evidence-trajectory", "causal_predecessor_invalid")


def validate_evidence_report(
    payload: Mapping[str, Any], root: Any = None, *, trajectory: Mapping[str, Any] | None = None
) -> None:
    _validate(payload, EVIDENCE_REPORT_SCHEMA_ID, "evidence-report", root)
    if payload.get("content_sha256") != content_hash(payload, without="content_sha256"):
        raise ContractValidationError("evidence-report", "content_sha256_mismatch")
    if trajectory is not None:
        validate_evidence_trajectory(trajectory, root)
        _same(payload, trajectory, ("tenant_id", "trajectory_id"), "evidence-report")
        if payload.get("trajectory_root_sha256") != trajectory.get("root_sha256"):
            raise ContractValidationError("evidence-report", "trajectory_root_mismatch")
        if payload.get("node_count") != len(trajectory.get("nodes", [])):
            raise ContractValidationError("evidence-report", "node_count_mismatch")


def validate_trajectory_replay_result(
    payload: Mapping[str, Any],
    root: Any = None,
    *,
    trajectory: Mapping[str, Any] | None = None,
    report: Mapping[str, Any] | None = None,
) -> None:
    _validate(payload, TRAJECTORY_REPLAY_RESULT_SCHEMA_ID, "trajectory-replay-result", root)
    if payload.get("result_sha256") != content_hash(payload, without="result_sha256"):
        raise ContractValidationError("trajectory-replay-result", "result_sha256_mismatch")
    if trajectory is not None:
        validate_evidence_trajectory(trajectory, root)
        _same(payload, trajectory, ("tenant_id", "trajectory_id"), "trajectory-replay-result")
        if payload.get("recorded_root_sha256") != trajectory.get("root_sha256"):
            raise ContractValidationError("trajectory-replay-result", "recorded_root_mismatch")
    if report is not None:
        validate_evidence_report(report, root, trajectory=trajectory)
        _same(payload, report, ("tenant_id", "report_id"), "trajectory-replay-result")
        if payload.get("report_sha256") != report.get("content_sha256"):
            raise ContractValidationError("trajectory-replay-result", "report_hash_mismatch")
    verified = payload.get("verification_outcome") == "verified"
    if verified and (
        payload.get("recorded_root_sha256") != payload.get("replayed_root_sha256")
        or payload.get("failure_code") is not None
    ):
        raise ContractValidationError("trajectory-replay-result", "replay_root_mismatch")
    if not verified and payload.get("failure_code") != "lineage_invalid":
        raise ContractValidationError("trajectory-replay-result", "failure_code_invalid")


def trajectory_root(payload: Mapping[str, Any]) -> str:
    """Return the canonical root without trusting a caller-supplied digest."""

    return canonical_sha256({key: value for key, value in payload.items() if key != "root_sha256"})


def validate_evidence_chain(
    artifact: Mapping[str, Any],
    trajectory: Mapping[str, Any],
    report: Mapping[str, Any],
    replay_result: Mapping[str, Any],
    root: Any = None,
) -> None:
    validate_artifact(artifact, root)
    validate_evidence_trajectory(trajectory, root)
    validate_evidence_report(report, root, trajectory=trajectory)
    validate_trajectory_replay_result(replay_result, root, trajectory=trajectory, report=report)
    _same(
        artifact,
        trajectory,
        (
            "tenant_id",
            "case_id",
            "case_revision_id",
            "workflow_id",
            "trajectory_id",
            "report_profile_id",
        ),
        "artifact-trajectory",
    )
    _same(
        artifact,
        report,
        ("tenant_id", "artifact_id", "trajectory_id", "report_profile_id"),
        "evidence-report",
    )
    if artifact.get("content_sha256") != report.get("content_sha256"):
        raise ContractValidationError("artifact", "report_hash_mismatch")
