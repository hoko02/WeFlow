"""Dedicated six-task x five-attempt live-model evaluation acceptance runner."""

from __future__ import annotations

import hashlib
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weflow_agent_runtime.investigation import compile_context_manifest
from weflow_agent_runtime.live_provider import (
    OpenAICompatibleProvider,
    OpenAICompatibleTransport,
    UrllibJsonTransport,
)
from weflow_agent_runtime.live_runtime import (
    DraftArtifactStore,
    LiveProviderBinding,
    run_live_investigation_attempt,
)
from weflow_agent_runtime.live_store import LiveAttemptIdentities, LiveEvaluationStore
from weflow_business_simulator import SyntheticIntakeSimulator
from weflow_contracts.evaluation import canonical_sha256
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_testkit.live_evaluation import (
    LiveCredential,
    LiveEvaluationConfig,
    LoadedLiveSuite,
)
from weflow_testkit.live_grading import (
    LiveEvaluationGradingError,
    build_accepted_live_report,
    grade_hard_gates,
    materialize_live_attempt,
    publish_json_atomic,
    safe_diagnostics,
)

JsonObject = dict[str, Any]
_SAFE_REASON = re.compile(r"^[a-z0-9_.:-]{1,100}$")
_SAFE_ERROR_CLASS_NAMES = frozenset(
    {
        "LiveBudgetExceeded",
        "LiveBudgetIntegrityError",
        "LiveConfigurationDenied",
        "LiveEvaluationGradingError",
        "LiveEvaluationValidationError",
        "LiveRuntimeError",
        "LiveStoreError",
        "ProviderBoundaryError",
        "WorkflowError",
    }
)


def safe_reason(error: BaseException) -> str:
    reason = str(error)
    if type(error).__name__ in _SAFE_ERROR_CLASS_NAMES and _SAFE_REASON.fullmatch(reason):
        return reason
    return "live_evaluation_failed"


def _provider_binding(config: LiveEvaluationConfig) -> LiveProviderBinding:
    return LiveProviderBinding(
        provider_profile_id=config.provider_profile_id,
        provider_profile_sha256=config.provider_profile_sha256,
        model_id_sha256=config.model_id_sha256,
        price_profile_id=config.price_profile_id,
        price_profile_sha256=config.price_profile_sha256,
    )


def _binding_dict(binding: LiveProviderBinding) -> JsonObject:
    return {
        "provider_profile_id": binding.provider_profile_id,
        "provider_profile_sha256": binding.provider_profile_sha256,
        "model_id_sha256": binding.model_id_sha256,
        "price_profile_id": binding.price_profile_id,
        "price_profile_sha256": binding.price_profile_sha256,
    }


def _task_hashes(suite: LoadedLiveSuite) -> dict[str, str]:
    return {item["task_id"]: item["sha256"] for item in suite.suite["tasks"]}


def execute_live_suite(
    *,
    root: Path,
    suite: LoadedLiveSuite,
    config: LiveEvaluationConfig,
    auth: LiveCredential,
    transport: OpenAICompatibleTransport,
    retain_redacted_drafts: bool = False,
) -> JsonObject:
    """Execute all 30 attempts using fresh workflow and evaluation stores."""

    root = root.resolve()
    evaluation_session_id = f"live-session:{uuid.uuid4().hex}"
    session_started = datetime.now(UTC)
    binding = _provider_binding(config)
    provider = OpenAICompatibleProvider(
        endpoint=config.endpoint,
        model=config.model,
        auth=auth,
        transport=transport,
    )
    task_hashes = _task_hashes(suite)
    attempts: list[JsonObject] = []
    metrics: list[JsonObject] = []
    failures: list[JsonObject] = []
    config_sha256 = canonical_sha256(config.public_dict())
    retained_root = root / ".weflow" / "live-eval-artifacts"
    DraftArtifactStore(retained_root, retain_diagnostics=True).cleanup_expired(now=session_started)
    diagnostics_root = (
        retained_root / hashlib.sha256(evaluation_session_id.encode("utf-8")).hexdigest()
    )

    for record in suite.records:
        task = record["task"]
        for attempt_index in range(1, int(task["attempt_count"]) + 1):
            identities = LiveAttemptIdentities(
                evaluation_session_id,
                str(task["task_id"]),
                attempt_index,
            )
            try:
                with tempfile.TemporaryDirectory(prefix="weflow-live-attempt-") as temporary:
                    attempt_root = Path(temporary)
                    ledger = SQLiteCaseLedger(
                        attempt_root / "workflow.sqlite3",
                        clock=FixedClock(session_started),
                        contract_root=root,
                    )
                    workflow = SQLiteDurableWorkflow(
                        ledger,
                        clock=FixtureClock(session_started),
                        contract_root=root,
                    )
                    accepted = SyntheticIntakeSimulator(root=root).submit_fixture(
                        ledger, "api-503-first-delivery"
                    )
                    projection = workflow.run_case(
                        str(task["tenant_id"]),
                        accepted.case_id,
                        accepted.case_revision_id,
                    )
                    if projection is None or projection["state"] != "TICKET_READY":
                        raise LiveEvaluationGradingError("ticket_ready_precondition_failed")
                    transcript = {
                        "environment_snapshot_sha256": task["context_source"]["sha256"],
                        "action_budget": suite.budget_profile["action_limit"],
                        "tool_budget": suite.budget_profile["tool_limit"],
                        "no_progress_limit": suite.budget_profile["no_progress_limit"],
                    }
                    manifest = compile_context_manifest(
                        workflow,
                        str(task["tenant_id"]),
                        accepted.case_id,
                        transcript,
                    )
                    store = LiveEvaluationStore(attempt_root / "live.sqlite3")
                    store.append_session(
                        evaluation_session_id=evaluation_session_id,
                        suite_id=str(suite.suite["suite_id"]),
                        tenant_id=str(task["tenant_id"]),
                        config_sha256=config_sha256,
                        created_at=str(manifest["created_at"]),
                    )
                    artifact_root = (
                        diagnostics_root / str(task["task_id"]) / str(attempt_index)
                        if retain_redacted_drafts
                        else attempt_root / "artifacts"
                    )
                    artifact_store = DraftArtifactStore(
                        artifact_root, retain_diagnostics=retain_redacted_drafts
                    )
                    artifact_store.cleanup_expired(now=session_started)
                    result = run_live_investigation_attempt(
                        workflow=workflow,
                        tenant_id=str(task["tenant_id"]),
                        case_id=accepted.case_id,
                        manifest=manifest,
                        task_record=record,
                        prompt_template=suite.prompt_template,
                        policy_profile=suite.policy_profile,
                        budget_profile=suite.budget_profile,
                        price_profile=suite.price_profile,
                        provider_binding=binding,
                        provider=provider,
                        store=store,
                        identities=identities,
                        artifact_store=artifact_store,
                    )
                    store_snapshot = store.attempt_snapshot(identities.attempt_id)
                    workflow_facts = workflow.investigation_facts_for_case(
                        str(task["tenant_id"]), accepted.case_id
                    )
                    if workflow_facts is None:
                        raise LiveEvaluationGradingError("workflow_facts_missing")
                    gates = grade_hard_gates(
                        task_record=record,
                        prompt_template=suite.prompt_template,
                        budget_profile=suite.budget_profile,
                        provider_binding=_binding_dict(binding),
                        result=result,
                        store_snapshot=store_snapshot,
                        workflow_facts=workflow_facts,
                        explicitly_authorized=True,
                    )
                    metric, attempt = materialize_live_attempt(
                        task_record=record,
                        task_sha256=task_hashes[str(task["task_id"])],
                        attempt_index=attempt_index,
                        evaluation_session_id=evaluation_session_id,
                        model_id_sha256=config.model_id_sha256,
                        price_profile=suite.price_profile,
                        result=result,
                        store_snapshot=store_snapshot,
                        workflow_facts=workflow_facts,
                        hard_gates=gates,
                    )
                    metrics.append(metric)
                    attempts.append(attempt)
            except (OSError, RuntimeError, ValueError) as error:
                failures.append(
                    {
                        "evaluation_task_id": task["task_id"],
                        "attempt_id": identities.attempt_id,
                        "attempt_index": attempt_index,
                        "reason_code": safe_reason(error),
                    }
                )

    expected = {
        str(record["task"]["task_id"]): tuple(record["oracle"]["expected_outcomes"])
        for record in suite.records
    }
    eligible = isinstance(transport, UrllibJsonTransport)
    return {
        "evaluation_session_id": evaluation_session_id,
        "attempts": attempts,
        "metrics": metrics,
        "failures": failures,
        "expected_outcomes": expected,
        "provider_binding": _binding_dict(binding),
        "live_verification_eligible": eligible,
    }


def build_verification_record(report: JsonObject, execution: JsonObject) -> JsonObject:
    payload = {
        "report_type": "weflow-live-model-evaluation-verification.v1",
        "evaluation_session_id": report["evaluation_session_id"],
        "report_sha256": report["report_sha256"],
        "attempt_count": len(execution["attempts"]),
        "metric_count": len(execution["metrics"]),
        "attempts": execution["attempts"],
        "metrics": execution["metrics"],
        "failures": execution["failures"],
        "limitations": report["limitations"],
        "verification_sha256": "",
    }
    payload["verification_sha256"] = canonical_sha256(payload, without="verification_sha256")
    return payload


def finalize_live_suite(
    *,
    root: Path,
    suite: LoadedLiveSuite,
    config: LiveEvaluationConfig,
    execution: JsonObject,
    output_path: Path,
    verification_path: Path,
    diagnostics_path: Path,
) -> JsonObject:
    """Publish only a fully accepted real-transport report, with report last."""

    try:
        if execution["failures"]:
            raise LiveEvaluationGradingError("live_attempt_execution_failed")
        report = build_accepted_live_report(
            evaluation_session_id=execution["evaluation_session_id"],
            suite=suite.suite,
            suite_sha256=suite.suite_sha256,
            provider_profile_sha256=config.provider_profile_sha256,
            model_id_sha256=config.model_id_sha256,
            prompt_template_sha256=suite.suite["prompt_template"]["sha256"],
            price_profile=suite.price_profile,
            attempts=execution["attempts"],
            metrics=execution["metrics"],
            expected_outcomes=execution["expected_outcomes"],
            live_verification_eligible=bool(execution["live_verification_eligible"]),
        )
        verification = build_verification_record(report, execution)
        publish_json_atomic(verification_path, verification)
        publish_json_atomic(output_path, report)
        return report
    except LiveEvaluationGradingError as error:
        diagnostics = safe_diagnostics(
            execution["attempts"], execution["metrics"], safe_reason(error)
        )
        diagnostics["execution_failures"] = list(execution["failures"])
        publish_json_atomic(diagnostics_path, diagnostics)
        raise


def resolve_report_path(root: Path, value: str) -> Path:
    reports = (root / "reports").resolve()
    path = (root / value).resolve()
    if path.parent != reports:
        raise LiveEvaluationGradingError("report_output_must_be_directly_under_reports")
    return path


def run_and_publish_live_acceptance(
    *,
    root: Path,
    suite: LoadedLiveSuite,
    config: LiveEvaluationConfig,
    auth: LiveCredential,
    output: str,
    verification_output: str,
    diagnostics_output: str,
    retain_redacted_drafts: bool = False,
) -> JsonObject:
    transport = UrllibJsonTransport()
    execution = execute_live_suite(
        root=root,
        suite=suite,
        config=config,
        auth=auth,
        transport=transport,
        retain_redacted_drafts=retain_redacted_drafts,
    )
    return finalize_live_suite(
        root=root,
        suite=suite,
        config=config,
        execution=execution,
        output_path=resolve_report_path(root, output),
        verification_path=resolve_report_path(root, verification_output),
        diagnostics_path=resolve_report_path(root, diagnostics_output),
    )


__all__ = [
    "build_verification_record",
    "execute_live_suite",
    "finalize_live_suite",
    "resolve_report_path",
    "run_and_publish_live_acceptance",
    "safe_reason",
]
