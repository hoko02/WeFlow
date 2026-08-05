#!/usr/bin/env python
"""Validate redacted reconciliation evidence for archived Changes 4 and 5.

This tool intentionally validates only repository-local JSON artifacts. It never runs
providers, connectors, Docker, or application workflows; existing offline command
surfaces generate those artifacts separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = frozenset({"passed", "failed", "timed_out", "unavailable"})
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")

CHANGE_CONFIG: dict[str, dict[str, str]] = {
    "add-policy-and-approval-gates": {
        "archive_path": "openspec/changes/archive/2026-08-04-add-policy-and-approval-gates",
        "acceptance": "reports/change-4-acceptance.json",
        "strict_validation": "reports/change-4-openspec-validation.json",
        "manifest": "reports/change-4-reconciliation-manifest.json",
        "guide": "docs/development/change-4-policy-approval-gates.md",
    },
    "add-evidence-and-trajectory-replay": {
        "archive_path": "openspec/changes/archive/2026-08-04-add-evidence-and-trajectory-replay",
        "acceptance": "reports/change-5-evidence-trajectory-acceptance.json",
        "strict_validation": "reports/change-5-openspec-validation.json",
        "manifest": "reports/change-5-reconciliation-manifest.json",
        "guide": "docs/development/change-5-evidence-trajectory-replay.md",
    },
}
AGGREGATE_VERIFICATION = "reports/change-4-5-reconciliation-verification.json"
CANONICAL_REPORT_PATHS = frozenset(
    [AGGREGATE_VERIFICATION]
    + [
        path
        for config in CHANGE_CONFIG.values()
        for path in config.values()
        if path.startswith("reports/")
    ]
)
LEGACY_DOCUMENTED_REPORT_PATHS = frozenset(
    {
        "reports/change-0-acceptance.json",
        "reports/change-0-openspec-validation.json",
        "reports/change-1-acceptance.json",
        "reports/change-1-openspec-validation.json",
        "reports/change-2-acceptance.json",
        "reports/change-2-openspec-validation.json",
        "reports/change-2-verification.json",
        "reports/change-3-acceptance.json",
        "reports/change-3-openspec-validation.json",
        "reports/change-3-verification.json",
    }
)
ALLOWED_DOCUMENTED_REPORT_PATHS = CANONICAL_REPORT_PATHS | LEGACY_DOCUMENTED_REPORT_PATHS
DOCUMENTATION_PATHS = (
    "README.md",
    "docs/PROJECT_MEMORY.md",
    "docs/development/change-4-policy-approval-gates.md",
    "docs/development/change-5-evidence-trajectory-replay.md",
)
SCOPE_LANGUAGE_REQUIREMENTS = {
    "docs/development/change-4-policy-approval-gates.md": {
        "2026-08-04-add-policy-and-approval-gates",
        "fixture-only",
        "offline",
        "real external write",
        "customer resolution",
        "live connector",
    },
    "docs/development/change-5-evidence-trajectory-replay.md": {
        "2026-08-04-add-evidence-and-trajectory-replay",
        "fixture-local",
        "offline",
        "real provider",
        "external delivery",
        "customer receipt/resolution",
    },
}
STALE_ARCHIVE_LANGUAGE = (
    "sync/archive remains a separate finalization action",
    "OpenSpec sync/archive is a separate finalization action",
)
REPORT_PATH = re.compile(r"reports/[a-z0-9][a-z0-9-]*\.json")

SAFE_ACCEPTANCE_FIELDS = frozenset(
    {
        "accepted",
        "agent_step_count",
        "api_503_policy_approval_delivery",
        "approval_decision_count",
        "authorization_denial",
        "authorization_bindings",
        "approval_decisions",
        "approval_requests",
        "authorized",
        "business_workflow_implemented",
        "capabilities",
        "capability_grant_status_events",
        "capability_grants",
        "credentials_required",
        "customer_resolution",
        "customer_resolution_enabled",
        "delivery_completion_count",
        "delivery_intent_count",
        "delivery_operation_count",
        "delivery_record_count",
        "determinism",
        "docker_available",
        "docker_required",
        "docker_service_boundary_verified",
        "duplicate_delivery",
        "environment_limits",
        "external_write",
        "external_writes_enabled",
        "failure_code",
        "fault_point",
        "fault_recovery",
        "fixture_approval_enabled",
        "fixture_evidence_trajectory_replay_implemented",
        "fixture_id",
        "fixture_local",
        "fixture_outbound_delivery_enabled",
        "fixture_outcomes",
        "fixture_policy_approval_delivery_implemented",
        "fixture_delivery_recorded",
        "fixture_delivery_operations",
        "fixture_delivery_records",
        "intentional_nondeterministic_fields",
        "interrupted_recovery",
        "live_approval_enabled",
        "live_outbound_delivery_enabled",
        "live_trace_exporter_enabled",
        "model_credentials_required",
        "model_invocation",
        "multi_agent_enabled",
        "network_allowed",
        "network_required",
        "node_available",
        "node_count",
        "node_required_for_core_acceptance",
        "node_required_for_typescript_and_console_checks",
        "offline",
        "outcome",
        "outbound_delivery_completions",
        "outbound_delivery_intents",
        "outbound_delivery_observations",
        "policy_approval_activations",
        "policy_decisions",
        "real_external_write",
        "real_provider_enabled",
        "reason_code",
        "reconciliation_timeout",
        "repeated_baseline_equal",
        "replayed_root_sha256",
        "report_type",
        "source_counts",
        "state",
        "tampered_lineage",
        "trajectory_root_sha256",
        "verification_outcome",
        "workflow_version",
    }
)
FORBIDDEN_FIELDS = frozenset(
    {
        "approval_rationale",
        "connection_string",
        "console_output",
        "delivery_content",
        "prompt",
        "raw",
        "raw_message",
        "stderr",
        "stdout",
        "tool_output",
        "transcript",
    }
)


class EvidenceValidationError(ValueError):
    """A stable, redacted reason code for invalid reconciliation evidence."""


def _require(condition: bool, reason_code: str) -> None:
    if not condition:
        raise EvidenceValidationError(reason_code)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceValidationError("evidence_json_unreadable") from error
    _require(isinstance(payload, dict), "evidence_json_not_object")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_safe_value(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _require(isinstance(key, str), "evidence_field_not_string")
            _require(key not in FORBIDDEN_FIELDS, "evidence_unsafe_field")
            _require(key in SAFE_ACCEPTANCE_FIELDS, "evidence_unknown_field")
            _validate_safe_value(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_safe_value(nested)
    elif isinstance(value, str):
        _require("\n" not in value and "\r" not in value, "evidence_raw_text_value")
    else:
        _require(isinstance(value, (bool, int, float)) or value is None, "evidence_value_invalid")


def _validate_acceptance_report(report: Mapping[str, Any], change: str) -> None:
    expected_type = (
        "weflow-change-4-policy-approval-acceptance.v1"
        if change == "add-policy-and-approval-gates"
        else "weflow-change-5-evidence-trajectory-acceptance.v1"
    )
    _require(report.get("report_type") == expected_type, "acceptance_report_type_invalid")
    _require(isinstance(report.get("accepted"), bool), "acceptance_report_accepted_invalid")
    _require(report.get("offline") is True, "acceptance_report_not_offline")
    _validate_safe_value(dict(report))


def _validate_strict_report(report: Mapping[str, Any], change: str) -> None:
    allowed = {
        "report_type",
        "change",
        "command",
        "strict",
        "valid",
        "issues",
        "outcome",
        "elapsed_seconds",
        "exit_code",
    }
    _require(set(report) <= allowed, "strict_report_unknown_field")
    _require(
        report.get("report_type") == "weflow-openspec-validation.v1",
        "strict_report_type_invalid",
    )
    _require(report.get("change") == change, "strict_report_change_invalid")
    _require(report.get("strict") is True, "strict_report_not_strict")
    _require(isinstance(report.get("valid"), bool), "strict_report_valid_invalid")
    _require(isinstance(report.get("issues"), list), "strict_report_issues_invalid")
    _require(
        all(isinstance(issue, str) and SAFE_CODE.fullmatch(issue) for issue in report["issues"]),
        "strict_report_issue_unsafe",
    )
    _require(report.get("outcome") in OUTCOMES, "strict_report_outcome_invalid")
    _require(
        isinstance(report.get("elapsed_seconds"), (int, float)),
        "strict_report_elapsed_invalid",
    )
    _require(isinstance(report.get("exit_code"), int), "strict_report_exit_code_invalid")
    if report["outcome"] == "passed":
        _require(report["valid"] is True, "strict_report_pass_not_valid")
        _require(report["issues"] == [], "strict_report_pass_has_issues")
        _require(report["exit_code"] == 0, "strict_report_pass_exit_code_invalid")
    else:
        _require(report["valid"] is False, "strict_report_nonpass_marked_valid")


def _validate_aggregate_report(report: Mapping[str, Any]) -> None:
    allowed = {
        "report_type",
        "command",
        "outcome",
        "elapsed_seconds",
        "exit_code",
        "outer_timeout_seconds",
        "cleanup",
        "environment",
        "limitations",
    }
    _require(set(report) <= allowed, "aggregate_report_unknown_field")
    _require(
        report.get("report_type") == "weflow-change-4-5-reconciliation-verification.v1",
        "aggregate_report_type_invalid",
    )
    _require(report.get("outcome") in OUTCOMES, "aggregate_report_outcome_invalid")
    _require(
        isinstance(report.get("elapsed_seconds"), (int, float)),
        "aggregate_report_elapsed_invalid",
    )
    _require(isinstance(report.get("exit_code"), int) or report.get("exit_code") is None,
             "aggregate_report_exit_code_invalid")
    _require(report.get("outer_timeout_seconds") == 900, "aggregate_report_timeout_invalid")
    cleanup = report.get("cleanup")
    _require(isinstance(cleanup, dict), "aggregate_report_cleanup_invalid")
    _require(
        set(cleanup) <= {"required", "completed"},
        "aggregate_report_cleanup_unknown_field",
    )
    _require(
        all(isinstance(value, bool) for value in cleanup.values()),
        "aggregate_report_cleanup_value_invalid",
    )
    if report.get("outcome") == "timed_out":
        _require(cleanup == {"required": True, "completed": True}, "timeout_cleanup_incomplete")
    if report.get("outcome") == "passed":
        _require(report.get("exit_code") == 0, "passed_report_exit_code_invalid")


def validate_report(path: Path, change: str, kind: str) -> dict[str, Any]:
    report = _load_json(path)
    if kind == "acceptance":
        _validate_acceptance_report(report, change)
    elif kind == "strict_validation":
        _validate_strict_report(report, change)
    elif kind == "aggregate_verification":
        _validate_aggregate_report(report)
    else:
        raise EvidenceValidationError("manifest_artifact_kind_invalid")
    return report


def _report_supports_passing(report: Mapping[str, Any], kind: str) -> bool:
    if kind == "acceptance":
        return report.get("accepted") is True
    if kind == "strict_validation":
        return (
            report.get("outcome") == "passed"
            and report.get("valid") is True
            and report.get("issues") == []
            and report.get("exit_code") == 0
        )
    if kind == "aggregate_verification":
        return report.get("outcome") == "passed" and report.get("exit_code") == 0
    return False


def _manifest_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    _require(path.is_relative_to((root / "reports").resolve()), "manifest_artifact_path_invalid")
    return path


def _validate_command(command: Mapping[str, Any]) -> None:
    allowed = {"kind", "command", "outcome", "elapsed_seconds", "exit_code"}
    _require(set(command) == allowed, "manifest_command_fields_invalid")
    _require(command.get("kind") in {"acceptance", "strict_validation", "aggregate_verification"},
             "manifest_command_kind_invalid")
    _require(isinstance(command.get("command"), str), "manifest_command_identity_invalid")
    _require(command.get("outcome") in OUTCOMES, "manifest_command_outcome_invalid")
    _require(
        isinstance(command.get("elapsed_seconds"), (int, float)),
        "manifest_command_elapsed_invalid",
    )
    _require(isinstance(command.get("exit_code"), int) or command.get("exit_code") is None,
             "manifest_command_exit_code_invalid")
    if command.get("outcome") == "passed":
        _require(command.get("exit_code") == 0, "manifest_pass_exit_code_invalid")


def validate_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    allowed = {
        "report_type",
        "change",
        "archive_path",
        "source_commit",
        "reconciled_on",
        "artifacts",
        "commands",
        "environment",
        "limitations",
    }
    _require(set(manifest) == allowed, "manifest_fields_invalid")
    _require(
        manifest.get("report_type") == "weflow-archive-evidence-manifest.v1",
        "manifest_report_type_invalid",
    )
    change = manifest.get("change")
    _require(isinstance(change, str) and change in CHANGE_CONFIG, "manifest_change_invalid")
    config = CHANGE_CONFIG[change]
    _require(
        manifest.get("archive_path") == config["archive_path"],
        "manifest_archive_path_invalid",
    )
    _require((root / config["archive_path"]).is_dir(), "manifest_archive_missing")
    _require(
        isinstance(manifest.get("source_commit"), str)
        and COMMIT_SHA.fullmatch(manifest["source_commit"]),
        "manifest_source_commit_invalid",
    )
    _require(
        isinstance(manifest.get("reconciled_on"), str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", manifest["reconciled_on"]),
        "manifest_date_invalid",
    )

    artifacts = manifest.get("artifacts")
    _require(isinstance(artifacts, list), "manifest_artifacts_invalid")
    expected_paths = {
        "acceptance": config["acceptance"],
        "strict_validation": config["strict_validation"],
        "aggregate_verification": AGGREGATE_VERIFICATION,
    }
    found_kinds: set[str] = set()
    artifact_outcomes: dict[str, str] = {}
    for artifact in artifacts:
        _require(isinstance(artifact, dict), "manifest_artifact_invalid")
        _require(
            set(artifact) == {"kind", "path", "sha256", "outcome"},
            "manifest_artifact_fields_invalid",
        )
        kind = artifact.get("kind")
        _require(isinstance(kind, str) and kind in expected_paths and kind not in found_kinds,
                 "manifest_artifact_kind_invalid")
        _require(artifact.get("path") == expected_paths[kind], "manifest_artifact_path_invalid")
        _require(isinstance(artifact.get("sha256"), str) and SHA256.fullmatch(artifact["sha256"]),
                 "manifest_artifact_hash_invalid")
        _require(artifact.get("outcome") in OUTCOMES, "manifest_artifact_outcome_invalid")
        report_path = _manifest_path(root, expected_paths[kind])
        _require(report_path.is_file(), "manifest_referenced_evidence_missing")
        report = validate_report(report_path, change, kind)
        if artifact["outcome"] == "passed":
            _require(_report_supports_passing(report, kind), "manifest_pass_not_supported")
        _require(sha256_file(report_path) == artifact["sha256"], "manifest_artifact_hash_mismatch")
        found_kinds.add(kind)
        artifact_outcomes[kind] = artifact["outcome"]
    _require(found_kinds == set(expected_paths), "manifest_artifact_set_incomplete")

    commands = manifest.get("commands")
    _require(isinstance(commands, list), "manifest_commands_invalid")
    command_outcomes: dict[str, str] = {}
    for command in commands:
        _require(isinstance(command, dict), "manifest_command_invalid")
        _validate_command(command)
        kind = str(command["kind"])
        _require(kind not in command_outcomes, "manifest_command_duplicate")
        command_outcomes[kind] = str(command["outcome"])
    _require(set(command_outcomes) == set(expected_paths), "manifest_command_set_incomplete")
    _require(command_outcomes == artifact_outcomes, "manifest_outcome_mismatch")

    environment = manifest.get("environment")
    _require(isinstance(environment, dict), "manifest_environment_invalid")
    _require(set(environment) == {"node_available", "node_version", "docker_available"},
             "manifest_environment_fields_invalid")
    _require(isinstance(environment["node_available"], bool), "manifest_node_availability_invalid")
    _require(isinstance(environment["node_version"], str) or environment["node_version"] is None,
             "manifest_node_version_invalid")
    _require(
        isinstance(environment["docker_available"], bool),
        "manifest_docker_availability_invalid",
    )
    limitations = manifest.get("limitations")
    _require(
        isinstance(limitations, list)
        and all(isinstance(item, str) and SAFE_CODE.fullmatch(item) for item in limitations),
        "manifest_limitations_invalid",
    )
    return manifest


def referenced_report_paths(paths: Iterable[Path]) -> set[str]:
    references: set[str] = set()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        references.update(REPORT_PATH.findall(text))
    return references


def validate_documentation_references(root: Path) -> set[str]:
    paths = [root / relative_path for relative_path in DOCUMENTATION_PATHS]
    _require(all(path.is_file() for path in paths), "documentation_path_missing")
    references = referenced_report_paths(paths)
    unknown = references - ALLOWED_DOCUMENTED_REPORT_PATHS
    _require(not unknown, "documentation_report_path_untracked")
    missing = [reference for reference in references if not (root / reference).is_file()]
    _require(not missing, "documentation_report_missing")
    return references


def validate_scope_language(root: Path) -> None:
    for relative_path, required_phrases in SCOPE_LANGUAGE_REQUIREMENTS.items():
        text = (root / relative_path).read_text(encoding="utf-8")
        _require(
            all(phrase in text for phrase in required_phrases),
            "documentation_scope_language_missing",
        )
        _require(
            not any(phrase in text for phrase in STALE_ARCHIVE_LANGUAGE),
            "documentation_archive_status_stale",
        )


def validate_repository_evidence(root: Path = ROOT) -> dict[str, Any]:
    manifests = [root / config["manifest"] for config in CHANGE_CONFIG.values()]
    for manifest_path in manifests:
        _require(manifest_path.is_file(), "reconciliation_manifest_missing")
        validate_manifest(root, manifest_path)
    references = validate_documentation_references(root)
    validate_scope_language(root)
    return {
        "report_type": "weflow-archive-evidence-check.v1",
        "passed": True,
        "manifest_count": len(manifests),
        "documented_report_count": len(references),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.parse_args(argv)
    try:
        report = validate_repository_evidence(ROOT)
    except EvidenceValidationError as error:
        report = {
            "report_type": "weflow-archive-evidence-check.v1",
            "passed": False,
            "reason_code": str(error),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
