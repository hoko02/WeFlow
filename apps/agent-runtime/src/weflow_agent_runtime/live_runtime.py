"""Bounded single-Agent live loop that reuses the deterministic workflow verifier."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from weflow_contracts import (
    AGENT_ACTION_SCHEMA_ID,
    RESPONSE_CANDIDATE_SCHEMA_ID,
    TOOL_REQUEST_SCHEMA_ID,
    TOOL_RESULT_SCHEMA_ID,
    validate_agent_action,
    validate_response_candidate,
    validate_tool_request,
    validate_tool_result,
)
from weflow_contracts.evaluation import canonical_sha256
from weflow_contracts.live import (
    LIVE_CANDIDATE_BINDING_SCHEMA_ID,
    MODEL_INVOCATION_INTENT_SCHEMA_ID,
    MODEL_INVOCATION_OBSERVATION_SCHEMA_ID,
    MODEL_TOOL_OBSERVATION_SCHEMA_ID,
    RESPONSE_DRAFT_ARTIFACT_SCHEMA_ID,
    validate_live_candidate_binding,
    validate_model_action_proposal,
    validate_model_tool_observation,
    validate_response_draft_artifact,
)
from weflow_control_kernel.durable_workflow import SQLiteDurableWorkflow, WorkflowError

from .live_budget import LiveBudgetExceeded, LiveBudgetLedger, ProviderReservation
from .live_provider import AgentTurnProvider, ProviderTurnInput, ProviderTurnResult
from .live_store import LiveAttemptIdentities, LiveEvaluationStore, stable_identifier

JsonObject = dict[str, Any]
_READ_ACTIONS = {
    "read_crm": "crm",
    "read_monitoring": "monitoring",
    "read_knowledge": "knowledge",
}
_SAFE_TERMINALS = frozenset({"needs_information", "needs_operator"})
_DRAFT_FORBIDDEN = re.compile(
    r"(?i)(api[_ -]?key|bearer\s+[a-z0-9]|credential|password|private[_ -]?key|"
    r"i\s+approve|approved\s+by\s+me|sent\s+to\s+(the\s+)?customer|"
    r"customer\s+(is\s+)?resolved|case\s+(is\s+)?complete|external\s+write)"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class LiveRuntimeError(RuntimeError):
    """A closed runtime failure that does not include model or tool content."""


@dataclass(frozen=True)
class LiveProviderBinding:
    provider_profile_id: str
    provider_profile_sha256: str
    model_id_sha256: str
    price_profile_id: str
    price_profile_sha256: str


def _timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_model_proposal(
    proposal: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    turn_index: int,
    created_at: str,
) -> JsonObject:
    """Derive all authoritative AgentAction scope from an immutable manifest."""

    validate_model_action_proposal(proposal)
    material = {
        "context_sha256": manifest["context_sha256"],
        "step_id": f"step-{turn_index:03d}",
        "action_type": proposal["action_type"],
        "proposal_sha256": canonical_sha256(proposal),
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
        "step_id": material["step_id"],
        "action_type": proposal["action_type"],
        "action_sha256": canonical_sha256(material),
        "created_at": created_at,
    }
    validate_agent_action(action, context_manifest=manifest)
    return action


class LiveFixtureInvestigationToolGateway:
    """Return model-readable synthetic views while persisting only safe hashes."""

    def __init__(self, task_record: Mapping[str, Any]) -> None:
        self._record = task_record

    def observation_for_existing(self, tool_name: str, evidence_id: str) -> tuple[JsonObject, str]:
        source = self._record["tools"][tool_name]
        reference = self._record["task"]["tool_sources"][tool_name]
        observation = {
            "schema_id": MODEL_TOOL_OBSERVATION_SCHEMA_ID,
            "schema_version": "v1",
            "tool_name": tool_name,
            "source_id": source["source_id"],
            "source_sha256": reference["sha256"],
            "classification": "untrusted_synthetic",
            "summary": source["summary"],
            "status": source["status"],
            "facts": list(source["facts"]),
        }
        validate_model_tool_observation(observation)
        return observation, evidence_id

    def read(
        self, manifest: Mapping[str, Any], action: Mapping[str, Any]
    ) -> tuple[JsonObject, JsonObject, JsonObject, str]:
        tool_name = _READ_ACTIONS.get(str(action.get("action_type")))
        task = self._record["task"]
        if tool_name is None or task["tenant_id"] != manifest["tenant_id"]:
            raise WorkflowError("investigation_tool_denied")
        source = self._record["tools"][tool_name]
        if source["tenant_id"] != manifest["tenant_id"] or source["tool_name"] != tool_name:
            raise WorkflowError("tenant_identity_mismatch")
        source_reference = task["tool_sources"][tool_name]
        request_material = {
            "tenant_id": manifest["tenant_id"],
            "workflow_id": manifest["workflow_id"],
            "context_manifest_id": manifest["context_manifest_id"],
            "step_id": action["step_id"],
            "tool_name": tool_name,
            "source_sha256": source_reference["sha256"],
        }
        request_id = stable_identifier("tool-request", request_material)
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
            "request_sha256": canonical_sha256(request_material),
            "created_at": action["created_at"],
        }
        evidence_id = stable_identifier("evidence", {"tool_request_id": request_id})
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
            "tool_result_id": stable_identifier("tool-result", request_id),
            "tool_request_id": request_id,
            "evidence_id": evidence_id,
            "content_sha256": source_reference["sha256"],
            "redaction_classification": "synthetic",
            "recorded_at": action["created_at"],
        }
        validate_tool_request(request, context_manifest=manifest)
        validate_tool_result(result, tool_request=request)
        observation, reference = self.observation_for_existing(tool_name, evidence_id)
        return request, result, observation, reference


def compile_live_prompt(
    *,
    manifest: Mapping[str, Any],
    task_record: Mapping[str, Any],
    prompt_template: Mapping[str, Any],
    policy_profile: Mapping[str, Any],
    observations: Sequence[tuple[str, Mapping[str, Any]]],
    history: Sequence[Mapping[str, Any]],
    max_output_tokens: int,
    request_timeout_ms: int,
    thinking_mode: str,
) -> ProviderTurnInput:
    """Compile a bounded prompt with untrusted data isolated under one label."""

    if manifest["tenant_id"] != task_record["task"]["tenant_id"]:
        raise LiveRuntimeError("tenant_identity_mismatch")
    bounded_history = [
        {
            "turn": item["turn"],
            "action_type": item["action_type"],
            "reason_code": item.get("reason_code"),
        }
        for item in history[-int(prompt_template["max_history_items"]) :]
    ]
    evidence = [
        {"evidence_reference": reference, "observation": dict(observation)}
        for reference, observation in observations
    ]
    trusted_runtime = {
        "context_manifest_id": manifest["context_manifest_id"],
        "context_sha256": manifest["context_sha256"],
        "allowed_actions": list(policy_profile["allowed_actions"]),
        "allowed_tools": list(policy_profile["allowed_tools"]),
        "required_tool_order": list(task_record["context"]["required_evidence"]),
        "current_evidence_references": [item[0] for item in observations],
        "instructions": [
            "Choose exactly one action for this turn.",
            "Read tools have no arguments; request any unread required tool in order.",
            "For response_candidate, cite every applicable current evidence_reference exactly.",
            (
                "If evidence is missing, conflicting, timed out, or unsafe, "
                "choose a safe terminal action."
            ),
        ],
    }
    untrusted = {
        "context": dict(task_record["context"]),
        "tool_observations": evidence,
    }
    user_payload = {
        "trusted_runtime": trusted_runtime,
        prompt_template["untrusted_data_label"]: untrusted,
        "bounded_history": bounded_history,
    }
    user_content = json.dumps(
        user_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(user_content) > int(prompt_template["max_prompt_characters"]):
        raise LiveRuntimeError("live_prompt_too_large")
    return ProviderTurnInput(
        system_instructions=tuple(str(item) for item in prompt_template["system_instructions"]),
        user_content=user_content,
        max_output_tokens=max_output_tokens,
        request_timeout_ms=request_timeout_ms,
        thinking_mode=thinking_mode,
        temperature=float(task_record.get("temperature", 0)),
        top_p=float(task_record.get("top_p", 1)),
    )


class DraftArtifactStore:
    """Access-restricted local draft content store with explicit cleanup."""

    def __init__(self, root: Path, *, retain_diagnostics: bool = False) -> None:
        self.root = root.resolve()
        self.retain_diagnostics = retain_diagnostics
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    def put(self, artifact_id: str, content: bytes) -> Path:
        filename = _sha256_bytes(artifact_id.encode("utf-8")) + ".json"
        path = (self.root / filename).resolve()
        if path.parent != self.root:
            raise LiveRuntimeError("artifact_path_invalid")
        path.write_bytes(content)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path

    def remove(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise LiveRuntimeError("artifact_path_invalid")
        resolved.unlink(missing_ok=True)

    def cleanup_expired(self, *, now: datetime, max_age: timedelta = timedelta(hours=1)) -> int:
        removed = 0
        cutoff = now.timestamp() - max_age.total_seconds()
        for path in self.root.rglob("*.json"):
            if path.stat().st_mtime < cutoff:
                self.remove(path)
                removed += 1
        return removed


def _safe_draft_content(draft: Mapping[str, Any]) -> bytes:
    rendered = json.dumps(draft, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if _DRAFT_FORBIDDEN.search(rendered) or _EMAIL.search(rendered):
        raise LiveRuntimeError("response_draft_redaction_failed")
    return rendered.encode("utf-8")


def build_live_candidate(
    *,
    store: LiveEvaluationStore,
    artifact_store: DraftArtifactStore,
    identities: LiveAttemptIdentities,
    manifest: Mapping[str, Any],
    proposal: Mapping[str, Any],
    action: Mapping[str, Any],
    invocation_id: str,
    observation_id: str,
    evidence_by_reference: Mapping[str, str],
    created_at: str,
) -> tuple[JsonObject, JsonObject, JsonObject, Path]:
    """Redact and bind a model draft before deterministic verification."""

    draft = proposal.get("draft")
    references = proposal.get("evidence_references")
    if not isinstance(draft, Mapping) or not isinstance(references, list):
        raise LiveRuntimeError("response_draft_invalid")
    if set(references) != set(evidence_by_reference) or len(references) != len(
        evidence_by_reference
    ):
        raise LiveRuntimeError("response_draft_evidence_invalid")
    content = _safe_draft_content(draft)
    content_hash = _sha256_bytes(content)
    artifact_id = stable_identifier(
        "draft-artifact", {"attempt_id": identities.attempt_id, "content_sha256": content_hash}
    )
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    evidence_hashes = list(evidence_by_reference.values())
    artifact = {
        "schema_id": RESPONSE_DRAFT_ARTIFACT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": manifest["tenant_id"],
        "case_id": manifest["case_id"],
        "case_revision_id": manifest["case_revision_id"],
        "attempt_id": identities.attempt_id,
        "producer_invocation_id": invocation_id,
        "artifact_id": artifact_id,
        "content_sha256": content_hash,
        "media_type": "application/json",
        "classification": "synthetic_redacted",
        "claim_evidence_summary": [
            {
                "claim_sha256": canonical_sha256(
                    {"draft_content_sha256": content_hash, "evidence_sha256": evidence_hash}
                ),
                "evidence_sha256": evidence_hash,
            }
            for evidence_hash in evidence_hashes
        ],
        "retention_mode": (
            "redacted_diagnostics" if artifact_store.retain_diagnostics else "ephemeral"
        ),
        "created_at": created_at,
        "expires_at": _timestamp(created + timedelta(hours=1)),
        "producer": "live-model-evaluation",
        "artifact_sha256": "",
    }
    artifact["artifact_sha256"] = canonical_sha256(artifact, without="artifact_sha256")
    validate_response_draft_artifact(artifact)
    artifact_path = artifact_store.put(artifact_id, content)
    store.append_draft_artifact(artifact)

    candidate_material = {
        "context_sha256": manifest["context_sha256"],
        "evidence_hashes": evidence_hashes,
        "draft_content_sha256": content_hash,
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
        "candidate_id": stable_identifier("candidate", candidate_material),
        "context_sha256": manifest["context_sha256"],
        "evidence_hashes": evidence_hashes,
        "candidate_sha256": canonical_sha256(candidate_material),
        "risk": draft["risk"],
        "next_step": "operator_review",
        "created_at": created_at,
    }
    validate_response_candidate(
        candidate, context_manifest=manifest, evidence_hashes=evidence_hashes
    )
    binding = {
        "schema_id": LIVE_CANDIDATE_BINDING_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": manifest["tenant_id"],
        "case_id": manifest["case_id"],
        "case_revision_id": manifest["case_revision_id"],
        "workflow_id": manifest["workflow_id"],
        "checkpoint_id": manifest["checkpoint_id"],
        "context_manifest_id": manifest["context_manifest_id"],
        "context_sha256": manifest["context_sha256"],
        "attempt_id": identities.attempt_id,
        "invocation_id": invocation_id,
        "observation_id": observation_id,
        "step_id": action["step_id"],
        "action_sha256": action["action_sha256"],
        "draft_artifact_id": artifact_id,
        "draft_content_sha256": content_hash,
        "evidence_hashes": evidence_hashes,
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": candidate["candidate_sha256"],
        "verification_state": "pending",
        "binding_sha256": "",
    }
    binding["binding_sha256"] = canonical_sha256(binding, without="binding_sha256")
    validate_live_candidate_binding(binding)
    store.append_candidate_binding(binding)
    return artifact, candidate, binding, artifact_path


def _invocation_intent(
    *,
    identities: LiveAttemptIdentities,
    turn_index: int,
    invocation_id: str,
    manifest: Mapping[str, Any],
    task_record: Mapping[str, Any],
    prompt_template: Mapping[str, Any],
    binding: LiveProviderBinding,
    reservation: ProviderReservation,
    created_at: str,
) -> JsonObject:
    task = task_record["task"]
    source_hashes = [task["context_source"]["sha256"]]
    source_hashes.extend(
        task["tool_sources"][name]["sha256"] for name in sorted(task["tool_sources"])
    )
    payload = {
        "schema_id": MODEL_INVOCATION_INTENT_SCHEMA_ID,
        "schema_version": "v1",
        "tenant_id": manifest["tenant_id"],
        "evaluation_session_id": identities.evaluation_session_id,
        "suite_id": task["suite_id"],
        "evaluation_task_id": identities.evaluation_task_id,
        "attempt_id": identities.attempt_id,
        "logical_turn_id": identities.logical_turn_id(turn_index),
        "invocation_id": invocation_id,
        "context_manifest_id": manifest["context_manifest_id"],
        "context_sha256": manifest["context_sha256"],
        "prompt_template_id": prompt_template["prompt_template_id"],
        "prompt_template_sha256": task["prompt_template"]["sha256"],
        "source_sha256s": source_hashes,
        "provider_profile_id": binding.provider_profile_id,
        "provider_profile_sha256": binding.provider_profile_sha256,
        "model_id_sha256": binding.model_id_sha256,
        "price_profile_id": binding.price_profile_id,
        "price_profile_sha256": binding.price_profile_sha256,
        "reservation": reservation.as_contract_dict(),
        "created_at": created_at,
        "intent_sha256": "",
    }
    payload["intent_sha256"] = canonical_sha256(payload, without="intent_sha256")
    return payload


def _invocation_observation(
    *,
    intent: Mapping[str, Any],
    result: ProviderTurnResult,
    reservation: ProviderReservation,
    price_profile: Mapping[str, Any],
    observed_at: str,
) -> JsonObject:
    if result.usage_available:
        input_tokens, output_tokens, total_tokens = (
            result.input_tokens,
            result.output_tokens,
            result.total_tokens,
        )
        cost = round(
            (
                input_tokens * float(price_profile["input_per_million_tokens"])
                + output_tokens * float(price_profile["output_per_million_tokens"])
            )
            / 1_000_000,
            12,
        )
    else:
        input_tokens = reservation.input_tokens
        output_tokens = reservation.output_tokens
        total_tokens = reservation.total_tokens
        cost = reservation.estimated_cost
    payload = {
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
        "status": result.status,
        "request_reference_sha256": result.request_reference_sha256,
        "response_sha256": result.response_sha256,
        "usage": {
            "available": result.usage_available,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "provider_latency_ms": result.provider_latency_ms,
        "estimated_cost": cost,
        "currency": price_profile["currency"],
        "failure_classification": result.failure_classification,
        "observed_at": observed_at,
        "observation_sha256": "",
    }
    payload["observation_sha256"] = canonical_sha256(payload, without="observation_sha256")
    return payload


def _close_result(
    store: LiveEvaluationStore,
    identities: LiveAttemptIdentities,
    *,
    terminal_outcome: str,
    reason_code: str,
    completed_at: str,
    observations: Sequence[str],
    ledger: LiveBudgetLedger,
    started: float,
    **extra: object,
) -> JsonObject:
    store.close_attempt(
        identities.attempt_id,
        terminal_outcome=terminal_outcome,
        reason_code=reason_code,
        completed_at=completed_at,
    )
    return {
        "attempt_id": identities.attempt_id,
        "terminal_outcome": terminal_outcome,
        "reason_code": reason_code,
        "invocation_observation_ids": list(observations),
        "budget": ledger.snapshot(),
        "end_to_end_latency_ms": max(0, round((time.monotonic() - started) * 1000)),
        "approval_count": 0,
        "delivery_count": 0,
        "external_business_write_count": 0,
        "customer_outcome_unverified": True,
        **extra,
    }


def run_live_investigation_attempt(
    *,
    workflow: SQLiteDurableWorkflow,
    tenant_id: str,
    case_id: str,
    manifest: Mapping[str, Any],
    task_record: Mapping[str, Any],
    prompt_template: Mapping[str, Any],
    policy_profile: Mapping[str, Any],
    budget_profile: Mapping[str, Any],
    price_profile: Mapping[str, Any],
    provider_binding: LiveProviderBinding,
    provider: AgentTurnProvider,
    store: LiveEvaluationStore,
    identities: LiveAttemptIdentities,
    artifact_store: DraftArtifactStore,
) -> JsonObject:
    """Run one bounded live attempt; only the existing verifier may change state."""

    started = time.monotonic()
    created_at = str(manifest["created_at"])
    store.append_attempt(identities, created_at=created_at)
    ledger = LiveBudgetLedger(store, identities.attempt_id, budget_profile, price_profile)
    workflow.begin_investigation(
        tenant_id, case_id, manifest, transcript_id=str(task_record["task"]["task_id"])
    )
    gateway = LiveFixtureInvestigationToolGateway(task_record)
    durable = workflow.investigation_facts_for_case(tenant_id, case_id)
    if durable is None:
        raise LiveRuntimeError("investigation_facts_missing")
    observations: list[tuple[str, JsonObject]] = []
    evidence_by_reference: dict[str, str] = {}
    history: list[JsonObject] = []
    for item in durable["tool_evidence"]:
        observation, reference = gateway.observation_for_existing(
            str(item["tool_name"]), str(item["evidence_id"])
        )
        observations.append((reference, observation))
        evidence_by_reference[reference] = str(item["content_sha256"])
    for index, item in enumerate(durable["agent_steps"], start=1):
        history.append({"turn": index, "action_type": item["action_type"], "reason_code": None})
    observation_ids = [
        str(item["observation_id"])
        for item in store.attempt_snapshot(identities.attempt_id)["observations"]
    ]
    previous_action = history[-1]["action_type"] if history else None
    start_turn = len(history) + 1
    max_output_tokens = min(600, int(budget_profile["output_token_limit"]))

    for turn_index in range(start_turn, int(budget_profile["action_limit"]) + 1):
        logical_turn_id = store.append_turn(identities, turn_index, created_at=created_at)
        turn = compile_live_prompt(
            manifest=manifest,
            task_record=task_record,
            prompt_template=prompt_template,
            policy_profile=policy_profile,
            observations=observations,
            history=history,
            max_output_tokens=max_output_tokens,
            request_timeout_ms=int(budget_profile["request_timeout_ms"]),
            thinking_mode=str(budget_profile["thinking_mode"]),
        )
        reserved_input = max(
            1,
            len("\n".join(turn.system_instructions).encode("utf-8"))
            + len(turn.user_content.encode("utf-8")),
        )
        result: ProviderTurnResult | None = None
        invocation_id = observation_id = ""
        for retry_index in range(int(budget_profile["retry_limit"]) + 1):
            invocation_id = identities.invocation_id(turn_index, retry_index + 1)
            try:
                reservation = ledger.reserve_provider_call(
                    invocation_id,
                    input_tokens=reserved_input,
                    output_tokens=max_output_tokens,
                    current_wall_time_ms=max(0, round((time.monotonic() - started) * 1000)),
                    created_at=created_at,
                    retry_count=retry_index,
                )
            except LiveBudgetExceeded:
                return _close_result(
                    store,
                    identities,
                    terminal_outcome="budget_exhausted",
                    reason_code="live_budget_exhausted",
                    completed_at=_timestamp(),
                    observations=observation_ids,
                    ledger=ledger,
                    started=started,
                )
            intent = _invocation_intent(
                identities=identities,
                turn_index=turn_index,
                invocation_id=invocation_id,
                manifest=manifest,
                task_record=task_record,
                prompt_template=prompt_template,
                binding=provider_binding,
                reservation=reservation,
                created_at=created_at,
            )
            store.append_intent(intent)
            result = provider.propose(turn)
            observed_at = _timestamp()
            observation = _invocation_observation(
                intent=intent,
                result=result,
                reservation=reservation,
                price_profile=price_profile,
                observed_at=observed_at,
            )
            store.append_observation(observation)
            observation_id = str(observation["observation_id"])
            observation_ids.append(observation_id)
            if result.status != "provider_outcome_unknown":
                ledger.settle_provider_call(
                    reservation,
                    input_tokens=(
                        result.input_tokens if result.usage_available else reservation.input_tokens
                    ),
                    output_tokens=(
                        result.output_tokens
                        if result.usage_available
                        else reservation.output_tokens
                    ),
                    provider_latency_ms=result.provider_latency_ms,
                    retry_count=retry_index,
                    created_at=observed_at,
                )
            if not result.retryable:
                break
        if result is None or result.status != "completed" or result.proposal is None:
            status = "provider_outcome_unknown" if result is None else result.status
            return _close_result(
                store,
                identities,
                terminal_outcome=status,
                reason_code=(
                    "provider_result_unavailable"
                    if result is None
                    else str(result.failure_classification or result.status)
                ),
                completed_at=_timestamp(),
                observations=observation_ids,
                ledger=ledger,
                started=started,
            )
        if task_record["task"].get("fault_profile") == "budget_exhaustion":
            return _close_result(
                store,
                identities,
                terminal_outcome="budget_exhausted",
                reason_code="fault_injected_budget_exhaustion",
                completed_at=_timestamp(),
                observations=observation_ids,
                ledger=ledger,
                started=started,
            )

        proposal = result.proposal
        action = normalize_model_proposal(
            proposal, manifest, turn_index=turn_index, created_at=created_at
        )
        ledger.consume_action(str(action["action_sha256"]), created_at)
        action_type = str(action["action_type"])
        if action_type == previous_action:
            try:
                ledger.consume_no_progress(logical_turn_id, created_at)
                no_progress = ledger.snapshot()["no_progress_count"]
                if no_progress >= max(1, int(budget_profile["no_progress_limit"]) - 1):
                    return _close_result(
                        store,
                        identities,
                        terminal_outcome="needs_operator",
                        reason_code="no_progress_limit_reached",
                        completed_at=_timestamp(),
                        observations=observation_ids,
                        ledger=ledger,
                        started=started,
                    )
            except LiveBudgetExceeded:
                return _close_result(
                    store,
                    identities,
                    terminal_outcome="needs_operator",
                    reason_code="no_progress_limit_reached",
                    completed_at=_timestamp(),
                    observations=observation_ids,
                    ledger=ledger,
                    started=started,
                )
        previous_action = action_type
        store.record_normalized_action(logical_turn_id, str(action["action_sha256"]))
        workflow.record_agent_action(tenant_id, case_id, action)
        history.append(
            {
                "turn": turn_index,
                "action_type": action_type,
                "reason_code": proposal.get("reason_code"),
            }
        )

        if action_type in _READ_ACTIONS:
            request, tool_result, model_observation, reference = gateway.read(manifest, action)
            try:
                ledger.consume_tool(str(request["tool_request_id"]), created_at)
            except LiveBudgetExceeded:
                return _close_result(
                    store,
                    identities,
                    terminal_outcome="budget_exhausted",
                    reason_code="tool_budget_exhausted",
                    completed_at=_timestamp(),
                    observations=observation_ids,
                    ledger=ledger,
                    started=started,
                )
            workflow.record_tool_exchange(tenant_id, case_id, request, tool_result)
            observations.append((reference, model_observation))
            evidence_by_reference[reference] = str(tool_result["content_sha256"])
            if model_observation["status"] == "timed_out":
                return _close_result(
                    store,
                    identities,
                    terminal_outcome="tool_timeout",
                    reason_code="declared_tool_timeout",
                    completed_at=_timestamp(),
                    observations=observation_ids,
                    ledger=ledger,
                    started=started,
                )
            continue

        if action_type in _SAFE_TERMINALS:
            return _close_result(
                store,
                identities,
                terminal_outcome=action_type,
                reason_code=str(proposal["reason_code"]),
                completed_at=_timestamp(),
                observations=observation_ids,
                ledger=ledger,
                started=started,
            )

        artifact_path: Path | None = None
        try:
            artifact, candidate, candidate_binding, artifact_path = build_live_candidate(
                store=store,
                artifact_store=artifact_store,
                identities=identities,
                manifest=manifest,
                proposal=proposal,
                action=action,
                invocation_id=invocation_id,
                observation_id=observation_id,
                evidence_by_reference=evidence_by_reference,
                created_at=created_at,
            )
            workflow.record_response_candidate(tenant_id, case_id, candidate)
            verifier = workflow.verify_response_candidate(
                tenant_id, case_id, str(candidate["candidate_id"])
            )
            projection = workflow.get_workflow_for_case(tenant_id, case_id)
            terminal = (
                "response_ready"
                if verifier["outcome"] == "verified"
                and projection is not None
                and projection["state"] == "RESPONSE_READY"
                else "needs_operator"
            )
            return _close_result(
                store,
                identities,
                terminal_outcome=terminal,
                reason_code=str(verifier["reason_code"]),
                completed_at=_timestamp(),
                observations=observation_ids,
                ledger=ledger,
                started=started,
                candidate_binding_id=candidate_binding["binding_sha256"],
                verifier_outcome_id=verifier["verifier_outcome_id"],
                state=None if projection is None else projection["state"],
                draft_artifact_sha256=artifact["artifact_sha256"],
            )
        except LiveRuntimeError as error:
            return _close_result(
                store,
                identities,
                terminal_outcome="policy_denied",
                reason_code=str(error),
                completed_at=_timestamp(),
                observations=observation_ids,
                ledger=ledger,
                started=started,
            )
        finally:
            if artifact_path is not None and not artifact_store.retain_diagnostics:
                artifact_store.remove(artifact_path)

    return _close_result(
        store,
        identities,
        terminal_outcome="budget_exhausted",
        reason_code="action_budget_exhausted",
        completed_at=_timestamp(),
        observations=observation_ids,
        ledger=ledger,
        started=started,
    )


__all__ = [
    "DraftArtifactStore",
    "LiveFixtureInvestigationToolGateway",
    "LiveProviderBinding",
    "LiveRuntimeError",
    "build_live_candidate",
    "compile_live_prompt",
    "normalize_model_proposal",
    "run_live_investigation_attempt",
]
