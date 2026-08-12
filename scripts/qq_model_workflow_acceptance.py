"""Credential-free integrated Stage 3 acceptance using the real deterministic kernels."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from qq_model_workflow_verifier import verify_qq_model_workflow_evidence
from weflow_agent_runtime.live_provider import ProviderTurnInput, ProviderTurnResult
from weflow_agent_runtime.qq_model import BoundedQQModelAssistRuntime
from weflow_contracts import MODEL_ACTION_PROPOSAL_SCHEMA_ID, canonical_sha256
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_handler import (
    QQ_HANDLER_REQUIRED_CAPABILITIES,
    QQHandlerConfig,
    begin_handler_pairing,
    normalize_handler_pairing_event,
)
from weflow_control_kernel.qq_handler_transport import FakeQQHandlerTransport
from weflow_control_kernel.qq_model import (
    QQModelHandlerWorkflowService,
    QQModelWorkflowConfig,
    SQLiteQQModelJournal,
)
from weflow_control_kernel.qq_sandbox import (
    QQAcknowledgementController,
    QQSandboxConfig,
    QQSandboxIntakeService,
    SQLiteQQSandboxJournal,
)
from weflow_control_kernel.qq_transport import FakeQQPassiveAcknowledgementTransport
from weflow_testkit.qq_model_profile import (
    load_qq_model_profile,
    qq_model_id_sha256,
    qq_model_provider_profile_sha256,
)

JsonObject = dict[str, Any]
NOW = datetime(2026, 8, 12, 0, 0, 1, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class ReviewedReplayModel:
    """Use the same Provider protocol and prompt, with no model or network contact."""

    def __init__(self) -> None:
        self.calls = 0

    def propose(self, turn: ProviderTurnInput) -> ProviderTurnResult:
        self.calls += 1
        prompt = json.loads(turn.user_content)
        references = prompt["trusted_runtime"]["current_evidence_references"]
        read_actions = ("read_crm", "read_monitoring", "read_knowledge")
        if self.calls <= 3:
            proposal: JsonObject = {
                "schema_id": MODEL_ACTION_PROPOSAL_SCHEMA_ID,
                "schema_version": "v1",
                "action_type": read_actions[self.calls - 1],
                "reason_code": None,
                "evidence_references": [],
                "draft": None,
            }
        else:
            proposal = {
                "schema_id": MODEL_ACTION_PROPOSAL_SCHEMA_ID,
                "schema_version": "v1",
                "action_type": "response_candidate",
                "reason_code": None,
                "evidence_references": references,
                "draft": {
                    "summary": "合成监控显示 API 503 与上游队列饱和相关。",
                    "diagnosis": "受审的合成 CRM、监控与知识证据相互一致。",
                    "next_steps": ["继续流量切换并观察 15 分钟"],
                    "risk": "low",
                },
            }
        return ProviderTurnResult(
            status="completed",
            proposal=proposal,
            request_reference_sha256=None,
            response_sha256=canonical_sha256(proposal),
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            usage_available=False,
            provider_latency_ms=0,
            failure_classification=None,
            retryable=False,
            live_contact=False,
        )


def _group_intake() -> JsonObject:
    return {
        "op": 0,
        "s": 42,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "stage3-customer-intake",
            "group_openid": "stage3-offline-group",
            "author": {"member_openid": "stage3-customer-member"},
            "content": "SYNTHETIC_ISSUE_API_503_STAGE3_OFFLINE",
            "timestamp": "2026-08-12T00:00:00Z",
        },
    }


def _handler_event(
    *, surface: str, content: str, message_id: str, sequence: int, clock: MutableClock
) -> JsonObject:
    data: JsonObject = {
        "id": message_id,
        "content": content,
        "timestamp": clock().isoformat().replace("+00:00", "Z"),
        "author": (
            {"member_openid": "stage3-handler-member"}
            if surface == "group"
            else {"user_openid": "stage3-handler-user"}
        ),
    }
    if surface == "group":
        data["group_openid"] = "stage3-offline-group"
    return {
        "t": "GROUP_AT_MESSAGE_CREATE" if surface == "group" else "C2C_MESSAGE_CREATE",
        "s": sequence,
        "d": data,
    }


def _stage1_locator(
    journal: SQLiteQQModelJournal, config: QQHandlerConfig, clock: MutableClock
) -> None:
    with closing(sqlite3.connect(journal.path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS qq_pairing_locators(
              pairing_id TEXT PRIMARY KEY, app_id_hash TEXT NOT NULL,
              tenant_id TEXT NOT NULL, tenant_id_hash TEXT NOT NULL,
              group_openid TEXT NOT NULL, group_openid_hash TEXT NOT NULL,
              expires_at TEXT NOT NULL, status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO qq_pairing_locators VALUES(?,?,?,?,?,?,?,?)",
            (
                config.stage1_pairing_id,
                config.app_id_hash,
                config.tenant_id,
                config.tenant_id_hash,
                config.group_openid,
                config.group_openid_hash,
                (clock() + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "COMPLETED",
            ),
        )
        connection.commit()


def run_qq_model_workflow_offline_acceptance(
    root: Path,
) -> tuple[JsonObject, JsonObject]:
    with TemporaryDirectory(prefix="weflow-qq-model-") as temporary:
        workspace = Path(temporary)
        store = workspace / ".weflow" / "qq-sandbox.sqlite3"
        clock = MutableClock()
        stage1_config = QQSandboxConfig(
            app_id="stage3-offline-app",
            client_secret="not-a-real-secret",
            group_openid="stage3-offline-group",
            tenant_id="tenant-stage3-offline",
            identity_salt="stage3-offline-identity-salt",
        )
        ledger = SQLiteCaseLedger(store, clock=FixedClock(NOW), contract_root=root)
        stage1_journal = SQLiteQQSandboxJournal(store, clock=FixedClock(NOW), contract_root=root)
        stage1 = QQSandboxIntakeService(
            ledger,
            stage1_journal,
            stage1_config,
            clock=FixedClock(NOW),
            contract_root=root,
        )
        accepted = stage1.accept(_group_intake(), session_id="stage3-offline-session")
        ack_transport = FakeQQPassiveAcknowledgementTransport("stage3-offline-group")
        acknowledgement = QQAcknowledgementController(
            stage1_journal,
            ack_transport,
            stage1_config,
            clock=FixedClock(NOW),
        ).process(str(accepted.intent["intent_id"]))
        if acknowledgement["status"] != "completed" or ack_transport.send_calls != 1:
            raise RuntimeError("stage3_offline_ack_not_completed_once")

        handler = QQHandlerConfig(
            app_id=stage1_config.app_id,
            client_secret=stage1_config.client_secret,
            tenant_id=stage1_config.tenant_id,
            stage1_pairing_id="qqpair_33333333333333333333333333333333",
            group_openid=stage1_config.group_openid,
            identity_salt="stage3-offline-handler-identity-salt-32",
            store_path=store,
            repository_root=root,
            capabilities=QQ_HANDLER_REQUIRED_CAPABILITIES,
        )
        journal = SQLiteQQModelJournal(store, clock=clock, contract_root=root)
        _stage1_locator(journal, handler, clock)
        tokens = iter(("G" * 32, "C" * 32))
        pairing = begin_handler_pairing(
            handler, clock=clock, token_factory=lambda: next(tokens), contract_root=root
        )
        journal.record_pairing_session(pairing)
        for challenge, event in (
            (
                pairing.group,
                _handler_event(
                    surface="group",
                    content=f"@机器人 {pairing.group.plaintext}",
                    message_id="stage3-handler-pair-group",
                    sequence=1,
                    clock=clock,
                ),
            ),
            (
                pairing.c2c,
                _handler_event(
                    surface="c2c",
                    content=pairing.c2c.plaintext,
                    message_id="stage3-handler-pair-c2c",
                    sequence=2,
                    clock=clock,
                ),
            ),
        ):
            journal.record_pairing_observation(
                challenge,
                normalize_handler_pairing_event(
                    event, config=handler, challenge=challenge, now=clock()
                ),
            )
        binding = journal.confirm_handler_binding(
            config=handler,
            pairing_session_id=pairing.session_id,
            operator_confirmation="CONFIRM-DUAL-QQ-HANDLER",
        )
        case_id = str(accepted.intake.case_id)
        journal.create_issue_artifact(
            binding=binding,
            case_id=case_id,
            case_revision_id=str(accepted.intake.case_revision_id),
            source_message_id_hash=str(accepted.intent["source_message_id_hash"]),
            content="SYNTHETIC_ISSUE_API_503_STAGE3_OFFLINE",
        )
        loaded = load_qq_model_profile(root, now=clock())
        profile = loaded.profile
        model_config = QQModelWorkflowConfig(
            handler=handler,
            stage3_profile_id=profile["profile_id"],
            stage3_profile_sha256=profile["profile_sha256"],
            source_profile_sha256=canonical_sha256(profile["source_references"]),
            prompt_template_sha256=profile["prompt_reference"]["sha256"],
            policy_profile_sha256=profile["policy_reference"]["sha256"],
            budget_profile_sha256=profile["budget_reference"]["sha256"],
            provider_profile_sha256=qq_model_provider_profile_sha256(profile),
            model_id_sha256=qq_model_id_sha256(profile),
            price_profile_sha256=profile["price_reference"]["profile_sha256"],
        )
        provider = ReviewedReplayModel()
        runtime = BoundedQQModelAssistRuntime(
            journal=journal,
            config=model_config,
            task_record=loaded.task_record,
            prompt_template=loaded.suite.prompt_template,
            policy_profile=loaded.suite.policy_profile,
            budget_profile=loaded.budget_profile,
            price_profile=loaded.suite.price_profile,
            provider=provider,
            clock=clock,
        )
        service = QQModelHandlerWorkflowService(
            config=model_config,
            binding=binding,
            journal=journal,
            runtime=runtime,
            ordered_source_sha256s=[item["sha256"] for item in profile["source_references"]],
        )
        qq_transport = FakeQQHandlerTransport(handler.group_openid, "stage3-handler-user")
        notification = journal.execute_notification(
            journal.create_notification_intent(case_id, binding),
            binding=binding,
            transport=qq_transport,
        )
        pull = service.handle_private_event(
            _handler_event(
                surface="c2c",
                content=f"WF-PULL {case_id} 1",
                message_id="stage3-pull",
                sequence=3,
                clock=clock,
            )
        )
        service.execute_private_response(pull, transport=qq_transport)
        accept = service.handle_private_event(
            _handler_event(
                surface="c2c",
                content=f"WF-ACCEPT {case_id} 1",
                message_id="stage3-accept",
                sequence=4,
                clock=clock,
            )
        )
        service.execute_private_response(accept, transport=qq_transport)
        assist_event = _handler_event(
            surface="c2c",
            content=f"WF-ASSIST {case_id} 2",
            message_id="stage3-assist",
            sequence=5,
            clock=clock,
        )
        assist = service.handle_private_event(assist_event)
        service.execute_private_response(assist, transport=qq_transport)
        duplicate = service.handle_private_event(assist_event)
        service.execute_private_response(duplicate, transport=qq_transport)
        if provider.calls != 4 or not duplicate.duplicate:
            raise RuntimeError("stage3_duplicate_assist_reinvoked_model")
        approval_metadata = assist.content.split("WF-APPROVE ", 1)[1]
        approval = service.handle_group_approval(
            _handler_event(
                surface="group",
                content=f"@机器人 WF-APPROVE {approval_metadata}",
                message_id="stage3-approve",
                sequence=6,
                clock=clock,
            )
        )
        final = service.execute_final_response(approval, transport=qq_transport)
        if not final["provider_accepted"] or qq_transport.passive_group_calls != 1:
            raise RuntimeError("stage3_final_reply_not_accepted_once")
        evidence = journal.model_evidence_for_case(case_id)
        budget_used = evidence["budget"]["used"]
        model_usage = {
            "available": False,
            "provider_calls": budget_used["provider_calls"],
            "input_tokens": budget_used["input_tokens"],
            "output_tokens": budget_used["output_tokens"],
            "total_tokens": budget_used["total_tokens"],
            "estimated_cost": budget_used["estimated_cost"],
            "currency": "USD",
            "provider_latency_ms": 0,
            "end_to_end_latency_ms": budget_used["wall_time_ms"],
        }
        report = journal.build_model_acceptance_report(
            config=model_config,
            binding=binding,
            case_id=case_id,
            mode="offline-fake",
            qq_intake_ack_verified=True,
            handler_private_workflow_verified=True,
            live_model_contact_verified=False,
            candidate_verification_verified=True,
            group_approval_verified=True,
            final_provider_accepted=True,
            artifact_deletion_verified=evidence["deletion_count"] >= 2,
            network_contacted=False,
            external_write_attempted=False,
            model_usage=model_usage,
        )
        if notification["status"] != "accepted":
            raise RuntimeError("stage3_handler_notification_not_accepted")
        verification = verify_qq_model_workflow_evidence(
            root=root,
            report=report,
            evidence=evidence,
            expected_mode="offline-fake",
            now=clock(),
        )
        serialized = json.dumps(
            {"report": report, "verification": verification},
            sort_keys=True,
            separators=(",", ":"),
        )
        forbidden = (
            stage1_config.client_secret,
            handler.identity_salt,
            handler.group_openid,
            "stage3-customer-member",
            "stage3-handler-member",
            "stage3-handler-user",
            "SYNTHETIC_ISSUE_API_503_STAGE3_OFFLINE",
            "合成监控显示",
        )
        if any(value in serialized for value in forbidden):
            raise RuntimeError("stage3_offline_report_privacy_violation")
        return report, verification


__all__ = ["run_qq_model_workflow_offline_acceptance"]
