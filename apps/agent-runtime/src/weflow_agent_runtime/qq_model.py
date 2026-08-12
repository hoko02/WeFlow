"""Bounded single-model proposal runtime for the Stage 3 QQ workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from weflow_contracts import (
    CONTEXT_MANIFEST_SCHEMA_ID,
    QQ_MODEL_CASE_BUDGET_SCHEMA_ID,
    QQ_MODEL_INVOCATION_EVIDENCE_SCHEMA_ID,
    TOOL_REQUEST_SCHEMA_ID,
    TOOL_RESULT_SCHEMA_ID,
    validate_tool_request,
    validate_tool_result,
)
from weflow_contracts import (
    evaluation_canonical_sha256 as canonical_sha256,
)
from weflow_contracts.live import (
    MODEL_TOOL_OBSERVATION_SCHEMA_ID,
    validate_model_tool_observation,
)
from weflow_control_kernel.qq_model import (
    QQModelRuntimeResult,
    QQModelWorkflowConfig,
    SQLiteQQModelJournal,
    render_model_candidate,
)

from .live_provider import AgentTurnProvider, ProviderBoundaryError, ProviderTurnResult
from .live_runtime import compile_live_prompt, normalize_model_proposal

JsonObject = dict[str, Any]
_READ_ACTIONS = {
    "read_crm": "crm",
    "read_monitoring": "monitoring",
    "read_knowledge": "knowledge",
}
_SAFE_TERMINALS = {
    "needs_information": ("needs_information", "model_needs_information"),
    "needs_operator": ("needs_operator", "model_needs_operator"),
}


def _timestamp(now: datetime) -> str:
    return now.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _identifier(prefix: str, material: object) -> str:
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{prefix}_{digest[:32]}"


def _usage_block(
    *,
    provider_calls: int,
    input_tokens: int,
    output_tokens: int,
    tool_calls: int,
    actions: int,
    no_progress: int,
    wall_time_ms: int,
    estimated_cost: float,
) -> JsonObject:
    return {
        "provider_calls": provider_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "tool_calls": tool_calls,
        "actions": actions,
        "no_progress": no_progress,
        "wall_time_ms": wall_time_ms,
        "estimated_cost": round(estimated_cost, 12),
    }


class BoundedQQModelAssistRuntime:
    """Run one closed proposal loop; never approve, deliver, or mutate a case."""

    def __init__(
        self,
        *,
        journal: SQLiteQQModelJournal,
        config: QQModelWorkflowConfig,
        task_record: Mapping[str, Any],
        prompt_template: Mapping[str, Any],
        policy_profile: Mapping[str, Any],
        budget_profile: Mapping[str, Any],
        price_profile: Mapping[str, Any],
        provider: AgentTurnProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._journal = journal
        self._config = config
        self._task_record = copy.deepcopy(dict(task_record))
        self._prompt_template = dict(prompt_template)
        self._policy_profile = dict(policy_profile)
        self._budget_profile = dict(budget_profile)
        self._price_profile = dict(price_profile)
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC))
        if self._policy_profile.get("external_business_write") is not False:
            raise ValueError("stage3_policy_external_write_denied")
        if self._policy_profile.get("approval") is not False:
            raise ValueError("stage3_policy_approval_denied")
        if self._policy_profile.get("delivery") is not False:
            raise ValueError("stage3_policy_delivery_denied")

    def _mapped_task(self, request: Mapping[str, Any], issue_view: str) -> JsonObject:
        record = copy.deepcopy(self._task_record)
        record["task"]["tenant_id"] = request["tenant_id"]
        record["context"]["tenant_id"] = request["tenant_id"]
        record["context"]["qq_issue_untrusted"] = issue_view
        return record

    def _manifest(self, request: Mapping[str, Any], context: Mapping[str, Any]) -> JsonObject:
        return {
            "schema_id": CONTEXT_MANIFEST_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": request["tenant_id"],
            "case_id": request["case_id"],
            "case_revision_id": request["case_revision_id"],
            "workflow_id": f"qq-model:{request['assist_request_id']}",
            "checkpoint_id": "qq-model-assist",
            "context_manifest_id": context["context_id"],
            "context_sha256": context["context_sha256"],
            "environment_snapshot_sha256": context["source_profile_sha256"],
            "evidence_references": list(context["ordered_source_sha256s"]),
            "action_budget": int(self._budget_profile["action_limit"]),
            "tool_budget": int(self._budget_profile["tool_limit"]),
            "no_progress_limit": int(self._budget_profile["no_progress_limit"]),
            "created_at": context["created_at"],
        }

    def _budget(
        self,
        *,
        request: Mapping[str, Any],
        used: Mapping[str, Any],
        sequence: int,
        pessimistic_unknown: bool,
    ) -> JsonObject:
        profile = self._budget_profile
        reserved = _usage_block(
            provider_calls=int(profile["provider_call_limit"]),
            input_tokens=int(profile["input_token_limit"]),
            output_tokens=int(profile["output_token_limit"]),
            tool_calls=int(profile["tool_limit"]),
            actions=int(profile["action_limit"]),
            no_progress=int(profile["no_progress_limit"]),
            wall_time_ms=int(profile["wall_time_ms"]),
            estimated_cost=float(profile["estimated_cost_limit"]),
        )
        payload = {
            "schema_id": QQ_MODEL_CASE_BUDGET_SCHEMA_ID,
            "schema_version": "v1",
            "budget_id": _identifier(
                "qqmab",
                {"request": request["assist_request_id"], "sequence": sequence},
            ),
            "budget_sha256": "0" * 64,
            "tenant_id": request["tenant_id"],
            "case_id": request["case_id"],
            "case_revision_id": request["case_revision_id"],
            "assist_request_id": request["assist_request_id"],
            "handler_binding_id": request["handler_binding_id"],
            "profile_sha256": self._config.budget_profile_sha256,
            "reserved": reserved,
            "used": dict(used),
            "pessimistic_unknown_accounted": pessimistic_unknown,
            "recorded_at": _timestamp(self._clock()),
        }
        payload["budget_sha256"] = canonical_sha256(payload, without="budget_sha256")
        return payload

    def _invocation(
        self,
        *,
        request: Mapping[str, Any],
        context: Mapping[str, Any],
        turn_index: int,
        reservation: Mapping[str, int],
        status: str,
        result: ProviderTurnResult | None,
        intent_sha256: str | None = None,
        failure_classification: str | None = None,
    ) -> JsonObject:
        logical_turn_id = _identifier(
            "qqmat", {"request": request["assist_request_id"], "turn": turn_index}
        )
        invocation_id = _identifier("qqmai", {"turn": logical_turn_id})
        created_at = _timestamp(self._clock())
        intent_material = {
            "invocation_id": invocation_id,
            "logical_turn_id": logical_turn_id,
            "request_sha256": request["request_sha256"],
            "context_sha256": context["context_sha256"],
            "reservation": dict(reservation),
            "provider_profile_sha256": self._config.provider_profile_sha256,
            "model_id_sha256": self._config.model_id_sha256,
            "price_profile_sha256": self._config.price_profile_sha256,
        }
        claimed_intent = intent_sha256 or canonical_sha256(intent_material)
        observed = status != "intent_recorded"
        if result is None:
            usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            request_reference = None
            response_sha256 = None
            latency_ms = 0
        else:
            usage = {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
            }
            request_reference = result.request_reference_sha256
            response_sha256 = result.response_sha256
            latency_ms = result.provider_latency_ms
        payload = {
            "schema_id": QQ_MODEL_INVOCATION_EVIDENCE_SCHEMA_ID,
            "schema_version": "v1",
            "invocation_id": invocation_id,
            "logical_turn_id": logical_turn_id,
            "assist_request_id": request["assist_request_id"],
            "context_id": context["context_id"],
            "context_sha256": context["context_sha256"],
            "tenant_id": request["tenant_id"],
            "case_id": request["case_id"],
            "case_revision_id": request["case_revision_id"],
            "handler_binding_id": request["handler_binding_id"],
            "intent_sha256": claimed_intent,
            "observation_id": (
                _identifier("qqmao", {"invocation": invocation_id}) if observed else None
            ),
            "status": status,
            "request_reference_sha256": request_reference,
            "response_sha256": response_sha256,
            "provider_profile_sha256": self._config.provider_profile_sha256,
            "model_id_sha256": self._config.model_id_sha256,
            "price_profile_sha256": self._config.price_profile_sha256,
            "reservation": dict(reservation),
            "usage": usage,
            "provider_latency_ms": latency_ms,
            "estimated_cost": self._cost(usage["input_tokens"], usage["output_tokens"]),
            "failure_classification": failure_classification,
            "intent_created_at": created_at,
            "observed_at": _timestamp(self._clock()) if observed else None,
            "evidence_sha256": "0" * 64,
        }
        payload["evidence_sha256"] = canonical_sha256(payload, without="evidence_sha256")
        return payload

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        return round(
            (
                input_tokens * float(self._price_profile["input_per_million_tokens"])
                + output_tokens * float(self._price_profile["output_per_million_tokens"])
            )
            / 1_000_000,
            12,
        )

    def _tool_exchange(
        self,
        *,
        manifest: Mapping[str, Any],
        task_record: Mapping[str, Any],
        action: Mapping[str, Any],
        tool_name: str,
    ) -> tuple[JsonObject, JsonObject]:
        source = task_record["tools"][tool_name]
        reference = task_record["task"]["tool_sources"][tool_name]
        request_material = {
            "tenant_id": manifest["tenant_id"],
            "context_sha256": manifest["context_sha256"],
            "step_id": action["step_id"],
            "tool_name": tool_name,
            "source_sha256": reference["sha256"],
        }
        tool_request_id = _identifier("qqmtr", request_material)
        tool_request = {
            "schema_id": TOOL_REQUEST_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": manifest["tenant_id"],
            "case_id": manifest["case_id"],
            "case_revision_id": manifest["case_revision_id"],
            "workflow_id": manifest["workflow_id"],
            "checkpoint_id": manifest["checkpoint_id"],
            "context_manifest_id": manifest["context_manifest_id"],
            "tool_request_id": tool_request_id,
            "step_id": action["step_id"],
            "tool_name": tool_name,
            "request_sha256": canonical_sha256(request_material),
            "created_at": action["created_at"],
        }
        evidence_id = _identifier("qqmev", {"request": tool_request_id})
        tool_result = {
            "schema_id": TOOL_RESULT_SCHEMA_ID,
            "schema_version": "v1",
            "tenant_id": manifest["tenant_id"],
            "case_id": manifest["case_id"],
            "case_revision_id": manifest["case_revision_id"],
            "workflow_id": manifest["workflow_id"],
            "checkpoint_id": manifest["checkpoint_id"],
            "context_manifest_id": manifest["context_manifest_id"],
            "tool_name": tool_name,
            "tool_result_id": _identifier("qqmtrs", {"request": tool_request_id}),
            "tool_request_id": tool_request_id,
            "evidence_id": evidence_id,
            "content_sha256": reference["sha256"],
            "redaction_classification": "synthetic",
            "recorded_at": action["created_at"],
        }
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
        validate_tool_request(tool_request, context_manifest=manifest)
        validate_tool_result(tool_result, tool_request=tool_request)
        validate_model_tool_observation(observation)
        return tool_result, observation

    def _finish(
        self,
        *,
        request: Mapping[str, Any],
        started: float,
        used: JsonObject,
        usage_available: bool,
        pessimistic_unknown: bool,
        terminal_outcome: str,
        reason_code: str,
        candidate_text: str | None,
        evidence_hashes: list[str],
        action_sha256: str | None,
        invocation: JsonObject | None,
    ) -> QQModelRuntimeResult:
        elapsed = max(0, round((time.monotonic() - started) * 1000))
        used["wall_time_ms"] = min(
            int(self._budget_profile["wall_time_ms"]),
            int(used["wall_time_ms"]) + elapsed,
        )
        provider_latency_ms = int(used.get("provider_latency_ms", 0))
        budget_used = {key: value for key, value in used.items() if key != "provider_latency_ms"}
        final_sequence = int(used["provider_calls"]) * 2 + 2
        budget = self._budget(
            request=request,
            used=budget_used,
            sequence=final_sequence,
            pessimistic_unknown=pessimistic_unknown,
        )
        self._journal.append_budget(budget, final_sequence)
        summary = {
            "available": usage_available,
            "provider_calls": used["provider_calls"],
            "input_tokens": used["input_tokens"],
            "output_tokens": used["output_tokens"],
            "total_tokens": used["total_tokens"],
            "estimated_cost": used["estimated_cost"],
            "currency": self._price_profile["currency"],
            "provider_latency_ms": provider_latency_ms,
            "end_to_end_latency_ms": used["wall_time_ms"],
        }
        return QQModelRuntimeResult(
            terminal_outcome=terminal_outcome,
            reason_code=reason_code,
            candidate_text=candidate_text,
            ordered_evidence_sha256s=tuple(evidence_hashes),
            action_sha256=action_sha256,
            invocation_evidence=invocation,
            budget=budget,
            usage_summary=summary,
        )

    def safe_stop(
        self,
        *,
        request: Mapping[str, Any],
        terminal_outcome: str,
        reason_code: str,
    ) -> QQModelRuntimeResult:
        """Persist a zero-contact bounded outcome for a pre-provider policy denial."""

        used = self._journal.prior_case_budget_usage(
            str(request["case_id"]),
            exclude_assist_request_id=str(request["assist_request_id"]),
        )
        used["provider_latency_ms"] = 0
        return self._finish(
            request=request,
            started=time.monotonic(),
            used=used,
            usage_available=True,
            pessimistic_unknown=False,
            terminal_outcome=terminal_outcome,
            reason_code=reason_code,
            candidate_text=None,
            evidence_hashes=[],
            action_sha256=None,
            invocation=None,
        )

    def run(
        self,
        *,
        request: Mapping[str, Any],
        context: Mapping[str, Any],
        issue_view: str,
    ) -> QQModelRuntimeResult:
        started = time.monotonic()
        task_record = self._mapped_task(request, issue_view)
        manifest = self._manifest(request, context)
        observations: list[tuple[str, JsonObject]] = []
        evidence_hashes: list[str] = []
        history: list[JsonObject] = []
        previous_action: str | None = None
        retry_count = 0
        usage_available = True
        pessimistic_unknown = False
        last_invocation: JsonObject | None = None
        used = self._journal.prior_case_budget_usage(
            str(request["case_id"]),
            exclude_assist_request_id=str(request["assist_request_id"]),
        )
        used["provider_latency_ms"] = 0
        initial = self._budget(
            request=request,
            used={key: value for key, value in used.items() if key != "provider_latency_ms"},
            sequence=0,
            pessimistic_unknown=False,
        )
        self._journal.append_budget(initial, 0)

        for persisted in self._journal.tool_results(str(request["assist_request_id"])):
            tool_name = str(persisted["tool_name"])
            source = task_record["tools"][tool_name]
            reference = str(persisted["evidence_id"])
            observation = {
                "schema_id": MODEL_TOOL_OBSERVATION_SCHEMA_ID,
                "schema_version": "v1",
                "tool_name": tool_name,
                "source_id": source["source_id"],
                "source_sha256": persisted["content_sha256"],
                "classification": "untrusted_synthetic",
                "summary": source["summary"],
                "status": source["status"],
                "facts": list(source["facts"]),
            }
            validate_model_tool_observation(observation)
            observations.append((reference, observation))
            evidence_hashes.append(str(persisted["content_sha256"]))
            used["tool_calls"] += 1

        while used["provider_calls"] < int(self._budget_profile["provider_call_limit"]):
            if used["actions"] >= int(self._budget_profile["action_limit"]):
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome="budget_exhausted",
                    reason_code="action_budget_exhausted",
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=None,
                    invocation=last_invocation,
                )
            turn_index = used["provider_calls"] + 1
            logical_turn_id = _identifier(
                "qqmat", {"request": request["assist_request_id"], "turn": turn_index}
            )
            recovered = self._journal.invocation_for_turn(logical_turn_id)
            if recovered is not None:
                intent, observation = recovered
                used["provider_calls"] += 1
                if observation is None:
                    reservation = intent["reservation"]
                    used["input_tokens"] += int(reservation["input_tokens"])
                    used["output_tokens"] += int(reservation["output_tokens"])
                    used["total_tokens"] = used["input_tokens"] + used["output_tokens"]
                    used["estimated_cost"] = round(
                        used["estimated_cost"]
                        + self._cost(
                            int(reservation["input_tokens"]),
                            int(reservation["output_tokens"]),
                        ),
                        12,
                    )
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=False,
                        pessimistic_unknown=True,
                        terminal_outcome="provider_outcome_unknown",
                        reason_code="recovery_missing_provider_observation",
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=None,
                        invocation=intent,
                    )
                recovered_usage = observation["usage"]
                used_input = int(recovered_usage["input_tokens"])
                used_output = int(recovered_usage["output_tokens"])
                if observation["status"] == "provider_outcome_unknown" and not (
                    used_input or used_output
                ):
                    used_input = int(observation["reservation"]["input_tokens"])
                    used_output = int(observation["reservation"]["output_tokens"])
                    usage_available = False
                    pessimistic_unknown = True
                used["input_tokens"] += used_input
                used["output_tokens"] += used_output
                used["total_tokens"] = used["input_tokens"] + used["output_tokens"]
                used["estimated_cost"] = round(
                    used["estimated_cost"] + self._cost(used_input, used_output), 12
                )
                used["provider_latency_ms"] += int(observation["provider_latency_ms"])
                last_invocation = observation
                if observation["status"] != "completed":
                    unknown = observation["status"] == "provider_outcome_unknown"
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=usage_available,
                        pessimistic_unknown=pessimistic_unknown or unknown,
                        terminal_outcome=(
                            "provider_outcome_unknown" if unknown else "malformed_model_output"
                        ),
                        reason_code=str(
                            observation.get("failure_classification")
                            or "recovery_provider_observation_not_completed"
                        ),
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=None,
                        invocation=observation,
                    )
                action = self._journal.action_for_turn(logical_turn_id)
                if action is None:
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=usage_available,
                        pessimistic_unknown=pessimistic_unknown,
                        terminal_outcome="malformed_model_output",
                        reason_code="recovery_action_evidence_missing",
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=None,
                        invocation=observation,
                    )
                used["actions"] += 1
                action_type = str(action["action_type"])
                if action_type == previous_action:
                    used["no_progress"] += 1
                previous_action = action_type
                history.append(
                    {
                        "turn": turn_index,
                        "action_type": action_type,
                        "reason_code": "recovered_conclusive_action",
                    }
                )
                if action_type in _READ_ACTIONS:
                    tool_name = _READ_ACTIONS[action_type]
                    if tool_name not in [item[1]["tool_name"] for item in observations]:
                        tool_result, model_observation = self._tool_exchange(
                            manifest=manifest,
                            task_record=task_record,
                            action=action,
                            tool_name=tool_name,
                        )
                        self._journal.append_tool_result(
                            str(request["assist_request_id"]),
                            used["tool_calls"] + 1,
                            tool_result,
                        )
                        used["tool_calls"] += 1
                        observations.append((str(tool_result["evidence_id"]), model_observation))
                        evidence_hashes.append(str(tool_result["content_sha256"]))
                    continue
                if action_type in _SAFE_TERMINALS:
                    terminal, default_reason = _SAFE_TERMINALS[action_type]
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=usage_available,
                        pessimistic_unknown=pessimistic_unknown,
                        terminal_outcome=terminal,
                        reason_code=f"recovered_{default_reason}",
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=str(action["action_sha256"]),
                        invocation=observation,
                    )
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome="malformed_model_output",
                    reason_code="recovery_candidate_content_unavailable",
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=str(action["action_sha256"]),
                    invocation=observation,
                )
            turn = compile_live_prompt(
                manifest=manifest,
                task_record=task_record,
                prompt_template=self._prompt_template,
                policy_profile=self._policy_profile,
                observations=observations,
                history=history,
                max_output_tokens=min(600, int(self._budget_profile["output_token_limit"])),
                request_timeout_ms=int(self._budget_profile["request_timeout_ms"]),
                thinking_mode=str(self._budget_profile["thinking_mode"]),
            )
            prompt_chars = len("\n".join(turn.system_instructions)) + len(turn.user_content)
            reserved_input = max(1, math.ceil(prompt_chars / 4))
            reserved_output = turn.max_output_tokens
            if (
                used["input_tokens"] + reserved_input
                > int(self._budget_profile["input_token_limit"])
                or used["output_tokens"] + reserved_output
                > int(self._budget_profile["output_token_limit"])
                or used["total_tokens"] + reserved_input + reserved_output
                > int(self._budget_profile["total_token_limit"])
                or used["estimated_cost"] + self._cost(reserved_input, reserved_output)
                > float(self._budget_profile["estimated_cost_limit"])
                or max(0, round((time.monotonic() - started) * 1000))
                >= int(self._budget_profile["wall_time_ms"])
            ):
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome="budget_exhausted",
                    reason_code="provider_budget_exhausted",
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=None,
                    invocation=last_invocation,
                )
            reservation = {
                "input_tokens": reserved_input,
                "output_tokens": reserved_output,
                "total_tokens": reserved_input + reserved_output,
            }
            provider_sequence = int(used["provider_calls"]) * 2 + 1
            provider_checkpoint = self._budget(
                request=request,
                used={key: value for key, value in used.items() if key != "provider_latency_ms"},
                sequence=provider_sequence,
                pessimistic_unknown=pessimistic_unknown,
            )
            self._journal.append_budget(provider_checkpoint, provider_sequence)
            intent = self._invocation(
                request=request,
                context=context,
                turn_index=turn_index,
                reservation=reservation,
                status="intent_recorded",
                result=None,
            )
            self._journal.append_invocation_evidence(intent)
            provider_boundary_failed = False
            try:
                provider_result = self._provider.propose(turn)
            except ProviderBoundaryError:
                provider_result = None
                provider_boundary_failed = True
            except Exception:  # provider outcome is intentionally treated as unknown
                provider_result = None
            used["provider_calls"] += 1
            if provider_result is None:
                status = (
                    "malformed_model_output"
                    if provider_boundary_failed
                    else "provider_outcome_unknown"
                )
                classification = status
                pessimistic_unknown = not provider_boundary_failed
                used_input = reserved_input
                used_output = reserved_output
                usage_available = False
            else:
                if provider_result.status == "completed":
                    status = "completed"
                elif provider_result.status == "observed_retryable_error":
                    status = "retryable_error"
                elif provider_result.status == "provider_outcome_unknown":
                    status = "provider_outcome_unknown"
                else:
                    status = "malformed_model_output"
                classification = provider_result.failure_classification
                if provider_result.usage_available:
                    used_input = provider_result.input_tokens
                    used_output = provider_result.output_tokens
                else:
                    used_input = reserved_input
                    used_output = reserved_output
                    usage_available = False
                if status == "provider_outcome_unknown":
                    pessimistic_unknown = True
            used["input_tokens"] += used_input
            used["output_tokens"] += used_output
            used["total_tokens"] = used["input_tokens"] + used["output_tokens"]
            used["estimated_cost"] = round(
                used["estimated_cost"] + self._cost(used_input, used_output), 12
            )
            if provider_result is not None:
                used["provider_latency_ms"] += provider_result.provider_latency_ms
            observation = self._invocation(
                request=request,
                context=context,
                turn_index=turn_index,
                reservation=reservation,
                status=status,
                result=provider_result,
                intent_sha256=str(intent["intent_sha256"]),
                failure_classification=classification,
            )
            self._journal.append_invocation_evidence(observation)
            last_invocation = observation
            if status == "retryable_error" and provider_result is not None:
                if provider_result.retryable and retry_count < int(
                    self._budget_profile["retry_limit"]
                ):
                    retry_count += 1
                    continue
            if status != "completed" or provider_result is None:
                terminal = (
                    "provider_outcome_unknown"
                    if status == "provider_outcome_unknown"
                    else "malformed_model_output"
                )
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome=terminal,
                    reason_code=str(classification or status),
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=None,
                    invocation=observation,
                )
            proposal = provider_result.proposal
            if proposal is None:
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome="malformed_model_output",
                    reason_code="model_proposal_missing",
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=None,
                    invocation=observation,
                )
            try:
                action = normalize_model_proposal(
                    proposal,
                    manifest,
                    turn_index=turn_index,
                    created_at=_timestamp(self._clock()),
                )
            except (TypeError, ValueError, RuntimeError):
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome="malformed_model_output",
                    reason_code="model_proposal_schema_invalid",
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=None,
                    invocation=observation,
                )
            self._journal.append_action(str(request["assist_request_id"]), logical_turn_id, action)
            used["actions"] += 1
            action_type = str(action["action_type"])
            if action_type == previous_action:
                used["no_progress"] += 1
                if used["no_progress"] >= int(self._budget_profile["no_progress_limit"]):
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=usage_available,
                        pessimistic_unknown=pessimistic_unknown,
                        terminal_outcome="needs_operator",
                        reason_code="no_progress_limit_reached",
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=str(action["action_sha256"]),
                        invocation=observation,
                    )
            previous_action = action_type
            history.append(
                {
                    "turn": turn_index,
                    "action_type": action_type,
                    "reason_code": proposal.get("reason_code"),
                }
            )
            if action_type in _READ_ACTIONS:
                tool_name = _READ_ACTIONS[action_type]
                required = list(task_record["context"]["required_evidence"])
                if (
                    used["tool_calls"] >= int(self._budget_profile["tool_limit"])
                    or tool_name in [item[1]["tool_name"] for item in observations]
                    or tool_name != required[len(observations)]
                ):
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=usage_available,
                        pessimistic_unknown=pessimistic_unknown,
                        terminal_outcome="policy_denied",
                        reason_code="tool_order_or_scope_denied",
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=str(action["action_sha256"]),
                        invocation=observation,
                    )
                tool_sequence = int(used["provider_calls"]) * 2
                tool_checkpoint = self._budget(
                    request=request,
                    used={
                        key: value for key, value in used.items() if key != "provider_latency_ms"
                    },
                    sequence=tool_sequence,
                    pessimistic_unknown=pessimistic_unknown,
                )
                self._journal.append_budget(tool_checkpoint, tool_sequence)
                try:
                    tool_result, model_observation = self._tool_exchange(
                        manifest=manifest,
                        task_record=task_record,
                        action=action,
                        tool_name=tool_name,
                    )
                except (KeyError, TypeError, ValueError, RuntimeError):
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=usage_available,
                        pessimistic_unknown=pessimistic_unknown,
                        terminal_outcome="policy_denied",
                        reason_code="tool_source_validation_denied",
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=str(action["action_sha256"]),
                        invocation=observation,
                    )
                self._journal.append_tool_result(
                    str(request["assist_request_id"]),
                    used["tool_calls"] + 1,
                    tool_result,
                )
                used["tool_calls"] += 1
                observations.append((str(tool_result["evidence_id"]), model_observation))
                evidence_hashes.append(str(tool_result["content_sha256"]))
                if model_observation["status"] == "timed_out":
                    return self._finish(
                        request=request,
                        started=started,
                        used=used,
                        usage_available=usage_available,
                        pessimistic_unknown=pessimistic_unknown,
                        terminal_outcome="tool_timeout",
                        reason_code="declared_tool_timeout",
                        candidate_text=None,
                        evidence_hashes=evidence_hashes,
                        action_sha256=str(action["action_sha256"]),
                        invocation=observation,
                    )
                continue
            if action_type in _SAFE_TERMINALS:
                terminal, default_reason = _SAFE_TERMINALS[action_type]
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome=terminal,
                    reason_code=str(proposal.get("reason_code") or default_reason),
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=str(action["action_sha256"]),
                    invocation=observation,
                )
            references = proposal.get("evidence_references")
            current_references = [item[0] for item in observations]
            if (
                action_type != "response_candidate"
                or references != current_references
                or len(evidence_hashes) != 3
                or not isinstance(proposal.get("draft"), Mapping)
            ):
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome="policy_denied",
                    reason_code="candidate_evidence_binding_denied",
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=str(action["action_sha256"]),
                    invocation=observation,
                )
            try:
                candidate_text = render_model_candidate(proposal["draft"])
            except (TypeError, ValueError, RuntimeError):
                return self._finish(
                    request=request,
                    started=started,
                    used=used,
                    usage_available=usage_available,
                    pessimistic_unknown=pessimistic_unknown,
                    terminal_outcome="malformed_model_output",
                    reason_code="model_candidate_shape_invalid",
                    candidate_text=None,
                    evidence_hashes=evidence_hashes,
                    action_sha256=str(action["action_sha256"]),
                    invocation=observation,
                )
            return self._finish(
                request=request,
                started=started,
                used=used,
                usage_available=usage_available,
                pessimistic_unknown=pessimistic_unknown,
                terminal_outcome="response_ready",
                reason_code="deterministic_candidate_verified",
                candidate_text=candidate_text,
                evidence_hashes=evidence_hashes,
                action_sha256=str(action["action_sha256"]),
                invocation=observation,
            )
        return self._finish(
            request=request,
            started=started,
            used=used,
            usage_available=usage_available,
            pessimistic_unknown=pessimistic_unknown,
            terminal_outcome="budget_exhausted",
            reason_code="provider_call_budget_exhausted",
            candidate_text=None,
            evidence_hashes=evidence_hashes,
            action_sha256=None,
            invocation=last_invocation,
        )


__all__ = ["BoundedQQModelAssistRuntime"]
