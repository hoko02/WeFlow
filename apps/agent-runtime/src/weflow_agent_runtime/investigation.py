"""Replay-only investigation loop with no model, credential, or external-write path."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from weflow_contracts import (
    AGENT_ACTION_SCHEMA_ID,
    CONTEXT_MANIFEST_SCHEMA_ID,
    RESPONSE_CANDIDATE_SCHEMA_ID,
    TOOL_REQUEST_SCHEMA_ID,
    TOOL_RESULT_SCHEMA_ID,
    validate_agent_action,
    validate_context_manifest,
    validate_response_candidate,
    validate_tool_request,
    validate_tool_result,
)
from weflow_control_kernel.config import load_config
from weflow_control_kernel.durable_workflow import (
    FaultProfile,
    SQLiteDurableWorkflow,
    WorkflowError,
)
from weflow_extension_sdk import select_provider

JsonObject = dict[str, Any]
_ACTIONS = frozenset(
    {
        "read_crm",
        "read_monitoring",
        "read_knowledge",
        "needs_information",
        "needs_operator",
        "response_candidate",
    }
)
_READ_ACTIONS = {
    "read_crm": "crm",
    "read_monitoring": "monitoring",
    "read_knowledge": "knowledge",
}
_TERMINAL_ACTIONS = frozenset({"needs_information", "needs_operator", "response_candidate"})
_FORBIDDEN_FIXTURE_KEYS = frozenset(
    {
        "body",
        "content",
        "credential",
        "message",
        "prompt",
        "raw",
        "token",
    }
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_identifier(prefix: str, material: object) -> str:
    return f"{prefix}_{_sha256({'prefix': prefix, 'material': material})[:32]}"


def _find_repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "fixtures" / "investigation").is_dir() and (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate
    raise RuntimeError("WeFlow repository root could not be located")


def _assert_safe_fixture_tree(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("invalid_investigation_fixture")
            normalized = key.lower()
            if (
                normalized in _FORBIDDEN_FIXTURE_KEYS
                or normalized.startswith("raw_")
                or normalized.endswith("_token")
            ):
                raise ValueError("unsafe_investigation_fixture")
            _assert_safe_fixture_tree(child)
    elif isinstance(value, list):
        for child in value:
            _assert_safe_fixture_tree(child)


def _load_named_investigation_file(
    fixture_id: str, suffix: str, root: Path | None = None
) -> JsonObject:
    if not fixture_id or any(character in fixture_id for character in "/\\"):
        raise ValueError("invalid_investigation_fixture_id")
    path = (
        (root or _find_repository_root())
        / "fixtures"
        / "investigation"
        / f"{fixture_id}.{suffix}.json"
    )
    if not path.is_file():
        raise ValueError("investigation_fixture_not_found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("invalid_investigation_fixture") from error
    if not isinstance(payload, dict) or payload.get("fixture_id") != fixture_id:
        raise ValueError("invalid_investigation_fixture")
    _assert_safe_fixture_tree(payload)
    return payload


def load_investigation_transcript(fixture_id: str, root: Path | None = None) -> JsonObject:
    """Load only a checked-in action transcript with bounded safe fields."""

    payload = _load_named_investigation_file(fixture_id, "transcript", root)
    expected = {
        "fixture_id",
        "synthetic",
        "intake_fixture_id",
        "environment_snapshot_sha256",
        "action_budget",
        "tool_budget",
        "no_progress_limit",
        "actions",
        "required_tools",
        "candidate",
    }
    if set(payload) != expected or payload.get("synthetic") is not True:
        raise ValueError("invalid_investigation_transcript")
    if (
        not isinstance(payload["intake_fixture_id"], str)
        or not payload["intake_fixture_id"]
        or any(character in payload["intake_fixture_id"] for character in "/\\")
        or not isinstance(payload["environment_snapshot_sha256"], str)
        or len(payload["environment_snapshot_sha256"]) != 64
        or not isinstance(payload["action_budget"], int)
        or not isinstance(payload["tool_budget"], int)
        or not isinstance(payload["no_progress_limit"], int)
        or min(payload["action_budget"], payload["tool_budget"], payload["no_progress_limit"]) < 1
    ):
        raise ValueError("invalid_investigation_transcript")
    actions = payload["actions"]
    if (
        not isinstance(actions, list)
        or not actions
        or any(not isinstance(action, str) or action not in _ACTIONS for action in actions)
        or actions[-1] not in _TERMINAL_ACTIONS
        or any(action in _TERMINAL_ACTIONS for action in actions[:-1])
        or len(actions) > payload["action_budget"]
    ):
        raise ValueError("invalid_investigation_transcript")
    required_tools = payload["required_tools"]
    if (
        not isinstance(required_tools, list)
        or tuple(required_tools) != ("crm", "monitoring", "knowledge")
        or [tool for action, tool in _READ_ACTIONS.items() if action in actions] != required_tools
        or sum(action in _READ_ACTIONS for action in actions) > payload["tool_budget"]
    ):
        raise ValueError("invalid_investigation_transcript")
    candidate = payload["candidate"]
    if (
        not isinstance(candidate, Mapping)
        or set(candidate) != {"risk", "next_step", "candidate_material_sha256"}
        or candidate.get("risk") not in {"low", "medium", "high"}
        or candidate.get("next_step") not in {"operator_review", "awaiting_information"}
        or not isinstance(candidate.get("candidate_material_sha256"), str)
        or len(str(candidate["candidate_material_sha256"])) != 64
    ):
        raise ValueError("invalid_investigation_transcript")
    return payload


def load_investigation_tool_fixture(fixture_id: str, root: Path | None = None) -> JsonObject:
    """Load the three fixture-local read resources without exposing their raw payloads."""

    payload = _load_named_investigation_file(fixture_id, "tools", root)
    if set(payload) != {"fixture_id", "synthetic", "tenant_id", "resources"}:
        raise ValueError("invalid_investigation_tool_fixture")
    resources = payload.get("resources")
    if (
        payload.get("synthetic") is not True
        or not isinstance(payload.get("tenant_id"), str)
        or not isinstance(resources, Mapping)
        or set(resources) != {"crm", "monitoring", "knowledge"}
    ):
        raise ValueError("invalid_investigation_tool_fixture")
    for resource in resources.values():
        if (
            not isinstance(resource, Mapping)
            or set(resource) != {"resource_key", "redacted_summary_sha256"}
            or not isinstance(resource.get("resource_key"), str)
            or not isinstance(resource.get("redacted_summary_sha256"), str)
            or len(str(resource["redacted_summary_sha256"])) != 64
        ):
            raise ValueError("invalid_investigation_tool_fixture")
    return payload


def compile_context_manifest(
    workflow: SQLiteDurableWorkflow,
    tenant_id: str,
    case_id: str,
    transcript: Mapping[str, Any],
) -> JsonObject:
    """Create one immutable Context Manifest from a TICKET_READY checkpoint."""

    projection = workflow.get_workflow_for_case(tenant_id, case_id)
    checkpoints = workflow.list_workflow_checkpoints_for_case(tenant_id, case_id)
    if (
        projection is None
        or checkpoints is None
        or projection["state"] != "TICKET_READY"
        or not checkpoints
    ):
        raise WorkflowError("investigation_predecessor_invalid")
    checkpoint = checkpoints[-1]
    material = {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "case_revision_id": projection["case_revision_id"],
        "workflow_id": projection["workflow_id"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "environment_snapshot_sha256": transcript["environment_snapshot_sha256"],
        "action_budget": transcript["action_budget"],
        "tool_budget": transcript["tool_budget"],
        "no_progress_limit": transcript["no_progress_limit"],
    }
    context_sha256 = _sha256(material)
    manifest = {
        "schema_id": CONTEXT_MANIFEST_SCHEMA_ID,
        "schema_version": "v1",
        **material,
        "context_manifest_id": _stable_identifier("context", material),
        "context_sha256": context_sha256,
        "evidence_references": [],
        "created_at": checkpoint["created_at"],
    }
    validate_context_manifest(manifest)
    return manifest


class ReplayInvestigationAgent:
    """Turns a named transcript into schema-valid proposals, never state commands."""

    def __init__(self, transcript: Mapping[str, Any]) -> None:
        self.transcript = dict(transcript)

    def actions(self, manifest: Mapping[str, Any]) -> list[JsonObject]:
        generated: list[JsonObject] = []
        for index, action_type in enumerate(self.transcript["actions"], start=1):
            material = {
                "fixture_id": self.transcript["fixture_id"],
                "context_sha256": manifest["context_sha256"],
                "step": index,
                "action_type": action_type,
            }
            action = {
                "schema_id": AGENT_ACTION_SCHEMA_ID,
                "schema_version": "v1",
                "tenant_id": manifest["tenant_id"],
                "case_id": manifest["case_id"],
                "case_revision_id": manifest["case_revision_id"],
                "workflow_id": manifest["workflow_id"],
                "checkpoint_id": manifest["checkpoint_id"],
                "context_manifest_id": manifest["context_manifest_id"],
                "step_id": f"step-{index:03d}",
                "action_type": action_type,
                "action_sha256": _sha256(material),
                "created_at": manifest["created_at"],
            }
            validate_agent_action(action, context_manifest=manifest)
            generated.append(action)
        return generated


class FixtureInvestigationToolGateway:
    """Tenant-scoped fixture reads that emit only redacted content-addressed evidence."""

    def __init__(self, fixture: Mapping[str, Any], candidate_fixture: Mapping[str, Any]) -> None:
        self.fixture = dict(fixture)
        self._candidate_fixture = dict(candidate_fixture)

    def read(
        self, manifest: Mapping[str, Any], action: Mapping[str, Any]
    ) -> tuple[JsonObject, JsonObject]:
        action_type = action.get("action_type")
        tool_name = _READ_ACTIONS.get(str(action_type))
        if tool_name is None or manifest["tenant_id"] != self.fixture["tenant_id"]:
            raise WorkflowError("investigation_tool_denied")
        resource = self.fixture["resources"][tool_name]
        request_material = {
            "tenant_id": manifest["tenant_id"],
            "workflow_id": manifest["workflow_id"],
            "context_manifest_id": manifest["context_manifest_id"],
            "step_id": action["step_id"],
            "tool_name": tool_name,
            "resource_key": resource["resource_key"],
        }
        request_id = _stable_identifier("tool_request", request_material)
        request = {
            "schema_id": TOOL_REQUEST_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": manifest["tenant_id"],
            "case_id": manifest["case_id"],
            "case_revision_id": manifest["case_revision_id"],
            "workflow_id": manifest["workflow_id"],
            "checkpoint_id": manifest["checkpoint_id"],
            "context_manifest_id": manifest["context_manifest_id"],
            "tool_request_id": request_id,
            "step_id": action["step_id"],
            "tool_name": tool_name,
            "request_sha256": _sha256(request_material),
            "created_at": manifest["created_at"],
        }
        result = {
            "schema_id": TOOL_RESULT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": manifest["tenant_id"],
            "case_id": manifest["case_id"],
            "case_revision_id": manifest["case_revision_id"],
            "workflow_id": manifest["workflow_id"],
            "checkpoint_id": manifest["checkpoint_id"],
            "context_manifest_id": manifest["context_manifest_id"],
            "tool_name": tool_name,
            "tool_result_id": _stable_identifier("tool_result", request_id),
            "tool_request_id": request_id,
            "evidence_id": _stable_identifier("evidence", request_id),
            "content_sha256": resource["redacted_summary_sha256"],
            "redaction_classification": "synthetic",
            "recorded_at": manifest["created_at"],
        }
        validate_tool_request(request, context_manifest=manifest)
        validate_tool_result(result, tool_request=request)
        return request, result

    def candidate(self, manifest: Mapping[str, Any], evidence_hashes: Sequence[str]) -> JsonObject:
        candidate_fixture = self.transcript_candidate
        material = {
            "context_sha256": manifest["context_sha256"],
            "evidence_hashes": list(evidence_hashes),
            "candidate_material_sha256": candidate_fixture["candidate_material_sha256"],
        }
        candidate = {
            "schema_id": RESPONSE_CANDIDATE_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": manifest["tenant_id"],
            "case_id": manifest["case_id"],
            "case_revision_id": manifest["case_revision_id"],
            "workflow_id": manifest["workflow_id"],
            "checkpoint_id": manifest["checkpoint_id"],
            "context_manifest_id": manifest["context_manifest_id"],
            "candidate_id": _stable_identifier("candidate", material),
            "context_sha256": manifest["context_sha256"],
            "evidence_hashes": list(evidence_hashes),
            "candidate_sha256": _sha256(material),
            "risk": candidate_fixture["risk"],
            "next_step": candidate_fixture["next_step"],
            "created_at": manifest["created_at"],
        }
        validate_response_candidate(
            candidate, context_manifest=manifest, evidence_hashes=evidence_hashes
        )
        return candidate

    @property
    def transcript_candidate(self) -> Mapping[str, Any]:
        return self._candidate_fixture


def run_investigation_replay(
    workflow: SQLiteDurableWorkflow,
    tenant_id: str,
    case_id: str,
    *,
    fixture_id: str = "api-503-investigation",
    root: Path | None = None,
    environment: Mapping[str, str] | None = None,
    fault_profile: FaultProfile | None = None,
) -> JsonObject:
    """Run or safely resume one deterministic replay investigation from durable facts."""

    config = load_config(environment)
    provider = select_provider(config)
    transcript = load_investigation_transcript(fixture_id, root)
    tool_fixture = load_investigation_tool_fixture(fixture_id, root)
    if tool_fixture["tenant_id"] != tenant_id:
        raise WorkflowError("tenant_identity_mismatch")
    existing_facts = workflow.investigation_facts_for_case(tenant_id, case_id)
    if existing_facts is None:
        manifest = compile_context_manifest(workflow, tenant_id, case_id, transcript)
    else:
        manifest = existing_facts["context_manifest"]
    workflow.begin_investigation(
        tenant_id,
        case_id,
        manifest,
        transcript_id=fixture_id,
        fault_profile=fault_profile,
    )
    agent = ReplayInvestigationAgent(transcript)
    gateway = FixtureInvestigationToolGateway(tool_fixture, transcript["candidate"])
    evidence_hashes: list[str] = []
    previous_action: str | None = None
    no_progress_count = 0
    action_count = 0
    tool_count = 0
    for action in agent.actions(manifest):
        action_count += 1
        if action_count > int(manifest["action_budget"]):
            return {
                "report_type": "weflow-replay-investigation.v1",
                "fixture_id": fixture_id,
                "provider_id": provider.provider_id,
                "terminal_outcome": "needs_operator",
                "reason_code": "action_budget_exceeded",
                "model_invocation": False,
                "external_write": False,
                "approval": False,
                "outbound_delivery": False,
                "customer_resolution": False,
            }
        action_type = str(action["action_type"])
        if action_type == previous_action:
            no_progress_count += 1
        else:
            no_progress_count = 1
        previous_action = action_type
        if no_progress_count >= int(manifest["no_progress_limit"]):
            return {
                "report_type": "weflow-replay-investigation.v1",
                "fixture_id": fixture_id,
                "provider_id": provider.provider_id,
                "terminal_outcome": "needs_operator",
                "reason_code": "no_progress_limit_reached",
                "model_invocation": False,
                "external_write": False,
                "approval": False,
                "outbound_delivery": False,
                "customer_resolution": False,
            }
        workflow.record_agent_action(tenant_id, case_id, action, fault_profile=fault_profile)
        if action_type in _READ_ACTIONS:
            tool_count += 1
            if tool_count > int(manifest["tool_budget"]):
                return {
                    "report_type": "weflow-replay-investigation.v1",
                    "fixture_id": fixture_id,
                    "provider_id": provider.provider_id,
                    "terminal_outcome": "needs_operator",
                    "reason_code": "tool_budget_exceeded",
                    "model_invocation": False,
                    "external_write": False,
                    "approval": False,
                    "outbound_delivery": False,
                    "customer_resolution": False,
                }
            request, result = gateway.read(manifest, action)
            workflow.record_tool_exchange(
                tenant_id,
                case_id,
                request,
                result,
                fault_profile=fault_profile,
            )
            evidence_hashes.append(str(result["content_sha256"]))
            continue
        if action_type in {"needs_information", "needs_operator"}:
            return {
                "report_type": "weflow-replay-investigation.v1",
                "fixture_id": fixture_id,
                "provider_id": provider.provider_id,
                "terminal_outcome": action_type,
                "reason_code": action_type,
                "model_invocation": False,
                "external_write": False,
                "approval": False,
                "outbound_delivery": False,
                "customer_resolution": False,
            }
        candidate = gateway.candidate(manifest, evidence_hashes)
        workflow.record_response_candidate(
            tenant_id,
            case_id,
            candidate,
            fault_profile=fault_profile,
        )
        outcome = workflow.verify_response_candidate(
            tenant_id,
            case_id,
            str(candidate["candidate_id"]),
            fault_profile=fault_profile,
        )
        projection = workflow.get_workflow_for_case(tenant_id, case_id)
        return {
            "report_type": "weflow-replay-investigation.v1",
            "fixture_id": fixture_id,
            "provider_id": provider.provider_id,
            "terminal_outcome": "response_candidate",
            "verifier_outcome": outcome["outcome"],
            "verifier_reason_code": outcome["reason_code"],
            "state": None if projection is None else projection["state"],
            "candidate_id": candidate["candidate_id"],
            "evidence_hashes": evidence_hashes,
            "model_invocation": False,
            "external_write": False,
            "approval": False,
            "outbound_delivery": False,
            "customer_resolution": False,
        }
    raise WorkflowError("investigation_transcript_terminal_missing")
