"""Dedicated Stage 3 preflight and dual-provider construction boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weflow_agent_runtime.live_provider import (
    OpenAICompatibleProvider,
    UrllibJsonTransport,
)
from weflow_agent_runtime.qq_model import BoundedQQModelAssistRuntime
from weflow_control_kernel.ledger import IntakeRejected, SQLiteCaseLedger
from weflow_control_kernel.qq_handler import (
    QQ_HANDLER_REQUIRED_CAPABILITIES,
    QQHandlerAuthorizationDenied,
    QQHandlerConfig,
    QQHandlerEventRejected,
    QQHandlerStateConflict,
    SQLiteQQHandlerJournal,
)
from weflow_control_kernel.qq_model import (
    QQ_STAGE3_MODEL_CAPABILITIES,
    QQ_STAGE3_QQ_CAPABILITIES,
    QQModelActivationDenied,
    QQModelHandlerWorkflowService,
    QQModelWorkflowConfig,
    SQLiteQQModelJournal,
)
from weflow_control_kernel.qq_pairing import resolve_stage1_pairing_environment
from weflow_control_kernel.qq_sandbox import (
    QQAcknowledgementController,
    QQEventRejected,
    QQSandboxConfig,
    QQSandboxIntakeService,
    SQLiteQQSandboxJournal,
)
from weflow_testkit.live_evaluation import (
    LiveCredential,
    LiveEvaluationConfig,
    load_live_credential,
    parse_live_evaluation_config,
)
from weflow_testkit.qq_model_profile import (
    LoadedQQModelProfile,
    load_qq_model_profile,
    qq_model_id_sha256,
    qq_model_provider_profile_sha256,
)

from .qq_adapter import RealQQPassiveAcknowledgementTransport
from .qq_handler_adapter import RealQQHandlerTransport
from .qq_handler_runner import (
    _LiveGateway,
    normalize_live_customer_intake,
)

JsonObject = dict[str, Any]
AddressResolver = Callable[[str, int], Sequence[str]]
LiveDiagnostic = Callable[[JsonObject], None]


def _readiness_resolver(_host: str, _port: int) -> Sequence[str]:
    return ("93.184.216.34",)


def _resolve_host(host: str, port: int) -> Sequence[str]:
    return tuple(
        sorted(
            {str(item[4][0]) for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        )
    )


def _enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() not in {"", "0", "false", "no", "off"}


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _bounded_store(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise QQModelActivationDenied("stage3_store_outside_repository") from error
    if resolved.name != "qq-sandbox.sqlite3" or resolved.parent.name != ".weflow":
        raise QQModelActivationDenied("stage3_store_not_bounded")
    return resolved


def _capabilities(value: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in (value or "").split(",") if part.strip())


@dataclass(frozen=True)
class Stage3Preflight:
    root: Path
    store_path: Path
    loaded_profile: LoadedQQModelProfile
    handler_config: QQHandlerConfig
    model_config: QQModelWorkflowConfig
    binding: JsonObject
    live_config: LiveEvaluationConfig
    readiness: JsonObject


@dataclass(frozen=True, repr=False)
class ActiveStage3:
    preflight: Stage3Preflight
    handler_config: QQHandlerConfig
    model_config: QQModelWorkflowConfig
    credential: LiveCredential
    provider: OpenAICompatibleProvider


def prepare_stage3_preflight(
    *,
    root: Path,
    store_path: str | Path,
    confirm_live_qq: bool,
    confirm_live_model: bool,
    pairing_id: str | None,
    handler_binding_id: str | None,
    endpoint: str | None,
    model: str | None,
    profile_path: str,
    environ: Mapping[str, str] | None = None,
    resolver: AddressResolver = _readiness_resolver,
) -> Stage3Preflight:
    """Validate all public/local gates without reading either provider credential."""

    source = os.environ if environ is None else environ
    if confirm_live_qq is not True:
        raise QQModelActivationDenied("stage3_live_qq_confirmation_required")
    if confirm_live_model is not True:
        raise QQModelActivationDenied("stage3_live_model_confirmation_required")
    if _capabilities(source.get("WEFLOW_QQ_CAPABILITIES")) != QQ_STAGE3_QQ_CAPABILITIES:
        raise QQModelActivationDenied("stage3_qq_capability_scope_denied")
    if _capabilities(source.get("WEFLOW_QQ_MODEL_CAPABILITIES")) != QQ_STAGE3_MODEL_CAPABILITIES:
        raise QQModelActivationDenied("stage3_model_capability_scope_denied")
    forbidden_switches = (
        "WEFLOW_EXTERNAL_WRITE_ENABLED",
        "WEFLOW_MULTI_AGENT_ENABLED",
        "WEFLOW_QQ_MAIL_ENABLED",
        "WEFLOW_QQ_ATTACHMENT_ENABLED",
        "WEFLOW_PROVIDER_ALLOW_LIVE",
        "WEFLOW_PROVIDER_API_KEY",
    )
    if any(_enabled(source.get(name)) for name in forbidden_switches):
        raise QQModelActivationDenied("stage3_unrelated_authority_denied")
    if source.get("WEFLOW_PROVIDER_MODE", "openai-compatible").strip().lower() != (
        "openai-compatible"
    ):
        raise QQModelActivationDenied("stage3_provider_mode_denied")
    if source.get("WEFLOW_QQ_SANDBOX_GROUP_OPENID") or source.get("WEFLOW_QQ_TENANT_ID"):
        raise QQModelActivationDenied("stage3_direct_qq_scope_override_denied")

    repository_root = root.resolve()
    bounded_store = _bounded_store(repository_root, store_path)
    loaded = load_qq_model_profile(repository_root, profile_path=profile_path)
    profile = loaded.profile
    app_id = source.get("WEFLOW_QQ_APP_ID", "").strip()
    selected_pairing = (pairing_id or source.get("WEFLOW_QQ_SANDBOX_PAIRING_ID", "")).strip()
    selected_handler = (
        handler_binding_id or source.get("WEFLOW_QQ_HANDLER_BINDING_ID", "")
    ).strip()
    if not app_id or not selected_pairing or not selected_handler:
        raise QQModelActivationDenied("stage3_selector_configuration_missing")

    selector_values = resolve_stage1_pairing_environment(
        {
            "WEFLOW_QQ_APP_ID": app_id,
            "WEFLOW_QQ_SANDBOX_PAIRING_ID": selected_pairing,
        },
        store_path=bounded_store,
    )
    tenant_id = selector_values.get("WEFLOW_QQ_TENANT_ID", "")
    group_openid = selector_values.get("WEFLOW_QQ_SANDBOX_GROUP_OPENID", "")
    if not tenant_id or not group_openid:
        raise QQModelActivationDenied("stage3_pairing_locator_not_current")

    public_handler = QQHandlerConfig(
        app_id=app_id,
        client_secret="not-a-real-secret",
        tenant_id=tenant_id,
        stage1_pairing_id=selected_pairing,
        group_openid=group_openid,
        identity_salt="preflight-only-not-an-identity-secret",
        store_path=bounded_store,
        repository_root=repository_root,
        capabilities=QQ_HANDLER_REQUIRED_CAPABILITIES,
    )
    binding = SQLiteQQHandlerJournal(bounded_store, contract_root=repository_root).active_binding(
        selected_handler
    )
    expected_scope = (
        public_handler.app_id_hash,
        public_handler.tenant_id_hash,
        public_handler.group_openid_hash,
        selected_pairing,
    )
    actual_scope = (
        binding.get("app_id_hash"),
        binding.get("tenant_id_hash"),
        binding.get("group_openid_hash"),
        binding.get("stage1_pairing_id"),
    )
    if actual_scope != expected_scope:
        raise QQModelActivationDenied("stage3_handler_binding_scope_mismatch")

    selected_endpoint = endpoint or source.get(
        "WEFLOW_LIVE_MODEL_ENDPOINT", str(profile["provider"]["endpoint"])
    )
    selected_model = model or source.get(
        "WEFLOW_LIVE_MODEL_MODEL", str(profile["provider"]["model"])
    )
    if selected_endpoint != profile["provider"]["endpoint"]:
        raise QQModelActivationDenied("stage3_provider_endpoint_mismatch")
    if selected_model != profile["provider"]["model"]:
        raise QQModelActivationDenied("stage3_model_profile_mismatch")
    live_config = parse_live_evaluation_config(
        replace(loaded.suite, budget_profile=loaded.budget_profile),
        confirm_live=confirm_live_model,
        endpoint=selected_endpoint,
        model=selected_model,
        provider_mode="openai-compatible",
        resolver=resolver,
    )
    if live_config.provider_profile_sha256 != qq_model_provider_profile_sha256(
        profile
    ) or live_config.model_id_sha256 != qq_model_id_sha256(profile):
        raise QQModelActivationDenied("stage3_provider_profile_mismatch")

    model_config = QQModelWorkflowConfig(
        handler=public_handler,
        stage3_profile_id=str(profile["profile_id"]),
        stage3_profile_sha256=str(profile["profile_sha256"]),
        source_profile_sha256=_canonical(profile["source_references"]),
        prompt_template_sha256=str(profile["prompt_reference"]["sha256"]),
        policy_profile_sha256=str(profile["policy_reference"]["sha256"]),
        budget_profile_sha256=str(profile["budget_reference"]["sha256"]),
        provider_profile_sha256=live_config.provider_profile_sha256,
        model_id_sha256=live_config.model_id_sha256,
        price_profile_sha256=live_config.price_profile_sha256,
    )
    readiness = model_config.readiness(selected_handler, selector_resolved=True)
    return Stage3Preflight(
        root=repository_root,
        store_path=bounded_store,
        loaded_profile=loaded,
        handler_config=public_handler,
        model_config=model_config,
        binding=dict(binding),
        live_config=live_config,
        readiness=readiness,
    )


def activate_stage3(
    *,
    root: Path,
    store_path: str | Path,
    confirm_live_qq: bool,
    confirm_live_model: bool,
    pairing_id: str | None,
    handler_binding_id: str | None,
    endpoint: str | None,
    model: str | None,
    profile_path: str,
    environ: Mapping[str, str] | None = None,
    resolver: AddressResolver | None = None,
) -> ActiveStage3:
    """Resolve public gates and DNS before reading process-only credentials."""

    source = os.environ if environ is None else environ
    preflight = prepare_stage3_preflight(
        root=root,
        store_path=store_path,
        confirm_live_qq=confirm_live_qq,
        confirm_live_model=confirm_live_model,
        pairing_id=pairing_id,
        handler_binding_id=handler_binding_id,
        endpoint=endpoint,
        model=model,
        profile_path=profile_path,
        environ=source,
        resolver=resolver or _resolve_host,
    )
    client_secret = source.get("WEFLOW_QQ_CLIENT_SECRET", "").strip()
    identity_salt = source.get("WEFLOW_QQ_IDENTITY_SALT", "").strip()
    if not client_secret or len(identity_salt.encode("utf-8")) < 32:
        raise QQModelActivationDenied("stage3_qq_credential_configuration_missing")
    credential = load_live_credential(preflight.live_config, source)
    handler = QQHandlerConfig(
        app_id=preflight.handler_config.app_id,
        client_secret=client_secret,
        tenant_id=preflight.handler_config.tenant_id,
        stage1_pairing_id=preflight.handler_config.stage1_pairing_id,
        group_openid=preflight.handler_config.group_openid,
        identity_salt=identity_salt,
        store_path=preflight.store_path,
        repository_root=preflight.root,
        capabilities=QQ_HANDLER_REQUIRED_CAPABILITIES,
    )
    public = preflight.model_config
    model_config = QQModelWorkflowConfig(
        handler=handler,
        stage3_profile_id=public.stage3_profile_id,
        stage3_profile_sha256=public.stage3_profile_sha256,
        source_profile_sha256=public.source_profile_sha256,
        prompt_template_sha256=public.prompt_template_sha256,
        policy_profile_sha256=public.policy_profile_sha256,
        budget_profile_sha256=public.budget_profile_sha256,
        provider_profile_sha256=public.provider_profile_sha256,
        model_id_sha256=public.model_id_sha256,
        price_profile_sha256=public.price_profile_sha256,
    )
    provider = OpenAICompatibleProvider(
        endpoint=preflight.live_config.endpoint,
        model=preflight.live_config.model,
        auth=credential,
        transport=UrllibJsonTransport(),
    )
    return ActiveStage3(preflight, handler, model_config, credential, provider)


class QQModelLiveRunFailed(RuntimeError):
    """Bounded diagnostic that never carries provider, prompt, issue, or identity bodies."""

    def __init__(
        self,
        reason_code: str,
        *,
        network_contacted: bool,
        model_invocation: bool,
        case_mutation: bool,
        external_write_attempted: bool,
    ) -> None:
        self.reason_code = reason_code
        self.network_contacted = network_contacted
        self.model_invocation = model_invocation
        self.case_mutation = case_mutation
        self.external_write_attempted = external_write_attempted
        super().__init__(reason_code)


def _safe_live_reason(error: BaseException) -> str:
    value = getattr(error, "reason_code", None) or str(error)
    if isinstance(value, str) and value and len(value) <= 96:
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
        lowered = value.lower()
        if set(lowered).issubset(allowed):
            return lowered
    return "stage3_live_workflow_failed"


async def _run_live_stage3(
    active: ActiveStage3,
    diagnostic: LiveDiagnostic | None = None,
) -> tuple[JsonObject, JsonObject]:
    from qq_model_workflow_verifier import verify_qq_model_workflow_evidence

    handler = active.handler_config
    model_config = active.model_config
    loaded = active.preflight.loaded_profile
    journal = SQLiteQQModelJournal(handler.store_path, contract_root=handler.repository_root)
    binding = journal.active_binding(str(active.preflight.binding["handler_binding_id"]))
    runtime = BoundedQQModelAssistRuntime(
        journal=journal,
        config=model_config,
        task_record=loaded.task_record,
        prompt_template=loaded.suite.prompt_template,
        policy_profile=loaded.suite.policy_profile,
        budget_profile=loaded.budget_profile,
        price_profile=loaded.suite.price_profile,
        provider=active.provider,
    )
    service = QQModelHandlerWorkflowService(
        config=model_config,
        binding=binding,
        journal=journal,
        runtime=runtime,
        ordered_source_sha256s=[
            str(item["sha256"]) for item in loaded.profile["source_references"]
        ],
    )
    stage1_config = QQSandboxConfig(
        app_id=handler.app_id,
        client_secret=handler.client_secret,
        group_openid=handler.group_openid,
        tenant_id=handler.tenant_id,
        identity_salt=handler.identity_salt,
    )
    stage1_journal = SQLiteQQSandboxJournal(
        handler.store_path, contract_root=handler.repository_root
    )
    stage1 = QQSandboxIntakeService(
        SQLiteCaseLedger(handler.store_path, contract_root=handler.repository_root),
        stage1_journal,
        stage1_config,
        contract_root=handler.repository_root,
    )
    gateway = _LiveGateway(handler)
    network_contacted = False
    model_invocation = False
    case_mutation = False
    external_write_attempted = False
    commands: list[str] = []
    case_id: str | None = None
    try:
        await gateway.open()
        network_contacted = True
        await gateway.wait_until_ready()
        if gateway.session_id is None or gateway.ready_sequence is None:
            raise QQModelLiveRunFailed(
                "stage3_gateway_ready_missing",
                network_contacted=True,
                model_invocation=False,
                case_mutation=False,
                external_write_attempted=False,
            )
        stage1_journal.record_cursor(
            stage1_config,
            sequence=gateway.ready_sequence,
            status="identified",
            session_id=gateway.session_id,
        )
        if diagnostic is not None:
            diagnostic(
                {
                    "report_type": "weflow-qq-model-workflow-live-progress.v1",
                    "phase": "gateway_ready",
                    "gateway_ready": True,
                    "network_contacted": True,
                    "group_event_received": False,
                    "case_mutation": False,
                    "model_invocation": False,
                    "external_write_attempted": False,
                }
            )
        assert gateway.access_token is not None
        ack_transport = RealQQPassiveAcknowledgementTransport(
            gateway.client, stage1_config, gateway.access_token
        )
        handler_transport = RealQQHandlerTransport(
            gateway.client,
            access_token=gateway.access_token,
            group_openid=handler.group_openid,
            user_openid=journal.private_locator(binding["handler_binding_id"], "c2c-user"),
        )
        accepted = None
        minimized = None
        rejected_event_count = 0
        while accepted is None:
            event = await gateway.next_event()
            try:
                minimized = normalize_live_customer_intake(event, config=handler)
                accepted = stage1.accept(event, session_id=gateway.session_id)
            except (IntakeRejected, QQEventRejected, QQHandlerEventRejected) as error:
                rejected_event_count += 1
                if diagnostic is not None:
                    diagnostic(
                        {
                            "report_type": "weflow-qq-model-workflow-live-progress.v1",
                            "phase": "group_event_rejected",
                            "gateway_ready": True,
                            "network_contacted": True,
                            "group_event_received": True,
                            "rejected_event_count": rejected_event_count,
                            "reason_code": _safe_live_reason(error),
                            "case_mutation": False,
                            "model_invocation": False,
                            "external_write_attempted": False,
                        }
                    )
                continue
        case_mutation = True
        acknowledgement = QQAcknowledgementController(
            stage1_journal, ack_transport, stage1_config
        ).process(str(accepted.intent["intent_id"]))
        external_write_attempted = True
        if acknowledgement["status"] != "completed":
            raise QQModelLiveRunFailed(
                "stage3_acknowledgement_not_completed",
                network_contacted=True,
                model_invocation=False,
                case_mutation=True,
                external_write_attempted=True,
            )
        assert minimized is not None
        case_id = str(accepted.intake.case_id)
        journal.create_issue_artifact(
            binding=binding,
            case_id=case_id,
            case_revision_id=str(accepted.intake.case_revision_id),
            source_message_id_hash=str(accepted.intent["source_message_id_hash"]),
            content=str(minimized["content"]),
        )
        notification = journal.execute_notification(
            journal.create_notification_intent(case_id, binding),
            binding=binding,
            transport=handler_transport,
        )
        external_write_attempted = True
        if notification["status"] != "accepted":
            raise QQModelLiveRunFailed(
                "stage3_handler_notification_not_accepted",
                network_contacted=True,
                model_invocation=False,
                case_mutation=True,
                external_write_attempted=True,
            )
        final = None
        while final is None:
            event = await gateway.next_event()
            if event.get("t") == "C2C_MESSAGE_CREATE":
                try:
                    response = service.handle_private_event(event)
                    model_invocation = model_invocation or (
                        response.command.get("command") == "assist"
                    )
                    service.execute_private_response(response, transport=handler_transport)
                    external_write_attempted = True
                    commands.append(str(response.command["command"]))
                except (
                    QQHandlerAuthorizationDenied,
                    QQHandlerEventRejected,
                    QQHandlerStateConflict,
                ):
                    continue
                continue
            try:
                approval = service.handle_group_approval(event)
                final = service.execute_final_response(approval, transport=handler_transport)
                external_write_attempted = True
            except (
                QQHandlerAuthorizationDenied,
                QQHandlerEventRejected,
                QQHandlerStateConflict,
            ):
                continue
        if final.get("provider_accepted") is not True:
            raise QQHandlerStateConflict("stage3_final_provider_not_accepted")
        evidence = journal.model_evidence_for_case(case_id)
        invocations = evidence["invocations"]
        live_model_verified = bool(invocations) and all(
            item["status"] == "completed"
            and item["response_sha256"] is not None
            and item["usage"]["total_tokens"] > 0
            for item in invocations
        )
        candidate_verified = (
            evidence["binding"] is not None
            and evidence["action"] is not None
            and evidence["action"]["action_type"] == "response_candidate"
        )
        if not live_model_verified or not candidate_verified:
            raise QQHandlerStateConflict("stage3_live_model_candidate_not_verified")
        budget_used = evidence["budget"]["used"]
        model_usage = {
            "available": True,
            "provider_calls": budget_used["provider_calls"],
            "input_tokens": budget_used["input_tokens"],
            "output_tokens": budget_used["output_tokens"],
            "total_tokens": budget_used["total_tokens"],
            "estimated_cost": budget_used["estimated_cost"],
            "currency": "USD",
            "provider_latency_ms": sum(int(item["provider_latency_ms"]) for item in invocations),
            "end_to_end_latency_ms": budget_used["wall_time_ms"],
        }
        report = journal.build_model_acceptance_report(
            config=model_config,
            binding=binding,
            case_id=case_id,
            mode="qq-model-integrated-live",
            qq_intake_ack_verified=True,
            handler_private_workflow_verified=all(
                command in commands for command in ("pull", "accept", "assist")
            ),
            live_model_contact_verified=True,
            candidate_verification_verified=True,
            group_approval_verified=True,
            final_provider_accepted=True,
            artifact_deletion_verified=evidence["deletion_count"] >= 2,
            network_contacted=True,
            external_write_attempted=True,
            model_usage=model_usage,
        )
        verification = verify_qq_model_workflow_evidence(
            root=handler.repository_root,
            report=report,
            evidence=evidence,
            expected_mode="qq-model-integrated-live",
            now=datetime.now(UTC),
        )
        return report, verification
    except QQModelLiveRunFailed:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        if case_id is not None:
            model_invocation = model_invocation or (
                journal.model_counts(case_id).get("model_invocation_count", 0) > 0
            )
        raise QQModelLiveRunFailed(
            _safe_live_reason(error),
            network_contacted=network_contacted,
            model_invocation=model_invocation,
            case_mutation=case_mutation,
            external_write_attempted=external_write_attempted,
        ) from error
    finally:
        await gateway.close()


def run_live_stage3_case(
    *,
    root: Path,
    store_path: str | Path,
    confirm_live_qq: bool,
    confirm_live_model: bool,
    pairing_id: str | None,
    handler_binding_id: str | None,
    endpoint: str | None,
    model: str | None,
    profile_path: str,
    diagnostic: LiveDiagnostic | None = None,
) -> tuple[JsonObject, JsonObject]:
    active = activate_stage3(
        root=root,
        store_path=store_path,
        confirm_live_qq=confirm_live_qq,
        confirm_live_model=confirm_live_model,
        pairing_id=pairing_id,
        handler_binding_id=handler_binding_id,
        endpoint=endpoint,
        model=model,
        profile_path=profile_path,
    )
    return asyncio.run(_run_live_stage3(active, diagnostic))


def recover_completed_live_stage3_reports(
    *,
    root: Path,
    store_path: str | Path,
    confirm_live_qq: bool,
    confirm_live_model: bool,
    pairing_id: str | None,
    handler_binding_id: str | None,
    endpoint: str | None,
    model: str | None,
    profile_path: str,
    case_id: str,
) -> tuple[JsonObject, JsonObject]:
    """Rebuild reports from a completed live Case without provider contact or effects."""

    from qq_model_workflow_verifier import verify_qq_model_workflow_evidence

    prepared = prepare_stage3_preflight(
        root=root,
        store_path=store_path,
        confirm_live_qq=confirm_live_qq,
        confirm_live_model=confirm_live_model,
        pairing_id=pairing_id,
        handler_binding_id=handler_binding_id,
        endpoint=endpoint,
        model=model,
        profile_path=profile_path,
    )
    journal = SQLiteQQModelJournal(prepared.store_path, contract_root=prepared.root)
    evidence = journal.model_evidence_for_case(case_id)
    request = evidence["request"]
    candidate = evidence["binding"]
    outcome = evidence["outcome"]
    approval = evidence["approval_decision"]
    final = evidence["final_result"]
    projection = journal.case_projection(case_id)
    invocations = evidence["invocations"]
    binding_id = str(prepared.binding["handler_binding_id"])
    if (
        request["case_id"] != case_id
        or request["tenant_id"] != prepared.model_config.handler.tenant_id
        or request["handler_binding_id"] != binding_id
        or request["stage3_profile_sha256"] != prepared.model_config.stage3_profile_sha256
        or candidate["handler_binding_id"] != binding_id
        or projection["handler_binding_id"] != binding_id
        or projection["status"] != "FINAL_ACCEPTED"
        or outcome["terminal_outcome"] != "response_ready"
        or outcome["private_preview_id"] != evidence["preview"]["preview_id"]
        or approval["decision"] != "approved"
        or final["status"] != "accepted"
        or final["provider_accepted"] is not True
        or evidence["acknowledgement_count"] != 1
        or evidence["notification_count"] != 1
        or evidence["deletion_count"] < 2
        or evidence["lifecycle_status"] != "DELETED"
        or not invocations
        or any(
            item["status"] != "completed"
            or item["response_sha256"] is None
            or item["usage"]["total_tokens"] <= 0
            for item in invocations
        )
    ):
        raise QQHandlerStateConflict("stage3_completed_case_evidence_incomplete")
    budget_used = evidence["budget"]["used"]
    model_usage = {
        "available": True,
        "provider_calls": budget_used["provider_calls"],
        "input_tokens": budget_used["input_tokens"],
        "output_tokens": budget_used["output_tokens"],
        "total_tokens": budget_used["total_tokens"],
        "estimated_cost": budget_used["estimated_cost"],
        "currency": "USD",
        "provider_latency_ms": sum(int(item["provider_latency_ms"]) for item in invocations),
        "end_to_end_latency_ms": budget_used["wall_time_ms"],
    }
    report = journal.build_model_acceptance_report(
        config=prepared.model_config,
        binding=prepared.binding,
        case_id=case_id,
        mode="qq-model-integrated-live",
        qq_intake_ack_verified=True,
        handler_private_workflow_verified=True,
        live_model_contact_verified=True,
        candidate_verification_verified=True,
        group_approval_verified=True,
        final_provider_accepted=True,
        artifact_deletion_verified=True,
        network_contacted=True,
        external_write_attempted=True,
        model_usage=model_usage,
    )
    verification = verify_qq_model_workflow_evidence(
        root=prepared.root,
        report=report,
        evidence=evidence,
        expected_mode="qq-model-integrated-live",
        now=datetime.now(UTC),
    )
    return report, verification


__all__ = [
    "ActiveStage3",
    "LiveDiagnostic",
    "QQModelLiveRunFailed",
    "Stage3Preflight",
    "activate_stage3",
    "prepare_stage3_preflight",
    "recover_completed_live_stage3_reports",
    "run_live_stage3_case",
]
