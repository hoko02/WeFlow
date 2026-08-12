"""Deterministic Stage 3 QQ model-assist state, policy, and handler service."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC
from typing import Any, Protocol

from weflow_contracts import (
    QQ_MODEL_ASSIST_COMMAND_SCHEMA_ID,
    QQ_MODEL_ASSIST_CONTEXT_SCHEMA_ID,
    QQ_MODEL_ASSIST_OUTCOME_SCHEMA_ID,
    QQ_MODEL_ASSIST_REQUEST_SCHEMA_ID,
    QQ_MODEL_CANDIDATE_BINDING_SCHEMA_ID,
    QQ_MODEL_PRIVATE_PREVIEW_SCHEMA_ID,
    QQ_MODEL_WORKFLOW_ACCEPTANCE_REPORT_SCHEMA_ID,
    QQ_MODEL_WORKFLOW_READINESS_SCHEMA_ID,
    qq_model_workflow_report_sha256,
    validate_qq_model_assist_command,
    validate_qq_model_assist_context,
    validate_qq_model_assist_outcome,
    validate_qq_model_assist_request,
    validate_qq_model_candidate_binding,
    validate_qq_model_case_budget,
    validate_qq_model_invocation_evidence,
    validate_qq_model_private_preview,
    validate_qq_model_workflow_acceptance_report,
    validate_qq_model_workflow_readiness,
)
from weflow_contracts import (
    evaluation_canonical_sha256 as canonical_sha256,
)

from .qq_handler import (
    QQHandlerAuthorizationDenied,
    QQHandlerConfig,
    QQHandlerEventRejected,
    QQHandlerStateConflict,
    QQHandlerTransport,
    QQPrivateCommand,
    SQLiteQQHandlerJournal,
    _hash,
    _id,
    _json,
    _parse,
    _ts,
    normalize_private_content,
    parse_private_command,
)
from .qq_handler_service import (
    QQGroupApprovalResponse,
    QQHandlerWorkflowService,
    QQPrivateWorkflowResponse,
)

JsonObject = dict[str, Any]

QQ_STAGE3_QQ_CAPABILITIES = (
    "qq.group_at.read",
    "qq.passive_ack.execute",
    "qq.c2c.read",
    "qq.c2c.notification.execute",
    "qq.c2c.passive_reply.execute",
    "qq.handler_approval.decide",
    "qq.final_reply.execute",
)
QQ_STAGE3_MODEL_CAPABILITIES = (
    "model.proposal.invoke",
    "fixture.crm.read",
    "fixture.monitoring.read",
    "fixture.knowledge.read",
)


class QQModelActivationDenied(QQHandlerAuthorizationDenied):
    """Fail-closed Stage 3 activation error carrying only a safe reason code."""


def reject_model_configuration_for_other_commands(
    environ: Mapping[str, str],
    *,
    allow_isolated_live_credential: bool = False,
) -> None:
    """Prevent Stage 3 authority from leaking into earlier or unrelated commands."""

    stage3_visible = (
        environ.get("WEFLOW_QQ_STAGE3_ACTIVE"),
        environ.get("WEFLOW_QQ_STAGE3_PROFILE"),
        environ.get("WEFLOW_QQ_MODEL_CAPABILITIES"),
    )
    if any(value for value in stage3_visible) or environ.get("WEFLOW_QQ_CAPABILITIES") == ",".join(
        QQ_STAGE3_QQ_CAPABILITIES
    ):
        raise QQModelActivationDenied("stage3_configuration_forbidden_for_command")
    if not allow_isolated_live_credential and environ.get("WEFLOW_LIVE_MODEL_API_KEY"):
        raise QQModelActivationDenied("live_model_credential_forbidden_for_command")


_ASSIST = re.compile(r"^WF-ASSIST (case_[a-f0-9]{24,64}) ([1-9][0-9]*)$")
_SAFE_REASON = re.compile(r"^[a-z0-9._-]{1,96}$")
_UNSAFE_ISSUE = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{8,}|\bBearer\s+[A-Za-z0-9._-]+|"
    r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|WF-(?:APPROVE|DRAFT|ACCEPT|PULL))"
)
_UNSAFE_MODEL_TEXT = re.compile(
    r"(?i)(?:i\s+approve|approved\s+by\s+me|sent\s+to\s+(?:the\s+)?customer|"
    r"customer\s+(?:is\s+)?resolved|case\s+(?:is\s+)?complete|external\s+write|"
    r"access[_ -]?token|client[_ -]?secret|api[_ -]?key|private[_ -]?key)"
)


@dataclass(frozen=True)
class QQModelWorkflowConfig:
    handler: QQHandlerConfig
    stage3_profile_id: str
    stage3_profile_sha256: str
    source_profile_sha256: str
    prompt_template_sha256: str
    policy_profile_sha256: str
    budget_profile_sha256: str
    provider_profile_sha256: str
    model_id_sha256: str
    price_profile_sha256: str
    qq_capabilities: tuple[str, ...] = QQ_STAGE3_QQ_CAPABILITIES
    model_capabilities: tuple[str, ...] = QQ_STAGE3_MODEL_CAPABILITIES

    def __post_init__(self) -> None:
        if self.qq_capabilities != QQ_STAGE3_QQ_CAPABILITIES:
            raise QQHandlerAuthorizationDenied("stage3_qq_capability_scope_denied")
        if self.model_capabilities != QQ_STAGE3_MODEL_CAPABILITIES:
            raise QQHandlerAuthorizationDenied("stage3_model_capability_scope_denied")

    @property
    def qq_capability_profile_hash(self) -> str:
        return _hash("|".join(self.qq_capabilities))

    @property
    def model_capability_profile_hash(self) -> str:
        return _hash("|".join(self.model_capabilities))

    def readiness(self, handler_binding_id: str, *, selector_resolved: bool) -> JsonObject:
        payload = {
            "schema_id": QQ_MODEL_WORKFLOW_READINESS_SCHEMA_ID,
            "schema_version": "v1",
            "mode": "qq-sandbox-live-model-workflow",
            "environment": "sandbox",
            "app_id_hash": self.handler.app_id_hash,
            "tenant_id_hash": self.handler.tenant_id_hash,
            "group_openid_hash": self.handler.group_openid_hash,
            "stage1_pairing_id": self.handler.stage1_pairing_id,
            "handler_binding_id": handler_binding_id,
            "qq_capability_profile_hash": self.qq_capability_profile_hash,
            "model_capability_profile_hash": self.model_capability_profile_hash,
            "stage3_profile_id": self.stage3_profile_id,
            "stage3_profile_sha256": self.stage3_profile_sha256,
            "provider_profile_sha256": self.provider_profile_sha256,
            "price_profile_sha256": self.price_profile_sha256,
            "budget_profile_sha256": self.budget_profile_sha256,
            "selector_resolved": selector_resolved,
            "profile_current": True,
            "network_contacted": False,
            "model_invocation": False,
            "case_mutation": False,
            "external_write_attempted": False,
            "ready": selector_resolved,
            "production_ready": False,
        }
        validate_qq_model_workflow_readiness(payload, self.handler.repository_root)
        return payload


@dataclass(frozen=True)
class QQModelRuntimeResult:
    terminal_outcome: str
    reason_code: str
    candidate_text: str | None
    ordered_evidence_sha256s: tuple[str, ...]
    action_sha256: str | None
    invocation_evidence: JsonObject | None
    budget: JsonObject
    usage_summary: JsonObject


class QQModelAssistRuntime(Protocol):
    def safe_stop(
        self,
        *,
        request: Mapping[str, Any],
        terminal_outcome: str,
        reason_code: str,
    ) -> QQModelRuntimeResult: ...

    def run(
        self,
        *,
        request: Mapping[str, Any],
        context: Mapping[str, Any],
        issue_view: str,
    ) -> QQModelRuntimeResult: ...


def parse_assist_command(content: str) -> QQPrivateCommand:
    normalized = unicodedata.normalize("NFKC", content).replace("\r", "").strip()
    if "\n" in normalized:
        raise QQHandlerEventRejected("assist_command_extra_content")
    matched = _ASSIST.fullmatch(normalized)
    if not matched:
        raise QQHandlerEventRejected("assist_command_unknown_or_malformed")
    return QQPrivateCommand("assist", matched.group(1), int(matched.group(2)))


def render_model_candidate(draft: Mapping[str, Any]) -> str:
    if set(draft) != {"summary", "diagnosis", "next_steps", "risk"}:
        raise QQHandlerStateConflict("model_candidate_shape_invalid")
    steps = draft["next_steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 3:
        raise QQHandlerStateConflict("model_candidate_steps_invalid")
    text = (
        f"{draft['summary']}\n诊断：{draft['diagnosis']}\n"
        + "下一步："
        + "；".join(str(item) for item in steps)
        + f"\n风险：{draft['risk']}"
    )
    normalized = normalize_private_content(text, candidate=True)
    if _UNSAFE_MODEL_TEXT.search(normalized):
        raise QQHandlerStateConflict("model_candidate_authority_claim_denied")
    return normalized


class SQLiteQQModelJournal(SQLiteQQHandlerJournal):
    """Append-only Stage 3 evidence beside, but not inside, archived Stage 2 records."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._initialize_model_tables()
        self.delete_expired_artifacts()

    def _initialize_model_tables(self) -> None:
        with self._connect() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS qq_model_assist_requests(
                    assist_request_id TEXT PRIMARY KEY, natural_key TEXT NOT NULL UNIQUE,
                    source_message_id_hash TEXT NOT NULL UNIQUE, case_id TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_contexts(
                    context_id TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_invocation_intents(
                    invocation_id TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL,
                    logical_turn_id TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_invocation_observations(
                    invocation_id TEXT PRIMARY KEY, observation_id TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_actions(
                    action_sha256 TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL,
                    logical_turn_id TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_tool_results(
                    tool_result_id TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL, content_sha256 TEXT NOT NULL,
                    record_json TEXT NOT NULL, UNIQUE(assist_request_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS qq_model_budget_snapshots(
                    budget_sha256 TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL, record_json TEXT NOT NULL,
                    UNIQUE(assist_request_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS qq_model_candidate_bindings(
                    binding_id TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL UNIQUE,
                    case_id TEXT NOT NULL, approval_request_id TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_candidate_lifecycle(
                    lifecycle_id TEXT PRIMARY KEY, binding_id TEXT NOT NULL,
                    status TEXT NOT NULL, reason_code TEXT NOT NULL, recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_private_previews(
                    preview_id TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS qq_model_assist_outcomes(
                    outcome_id TEXT PRIMARY KEY, assist_request_id TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS qq_model_request_no_update
                    BEFORE UPDATE ON qq_model_assist_requests
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_model_request_no_delete
                    BEFORE DELETE ON qq_model_assist_requests
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_model_context_no_update
                    BEFORE UPDATE ON qq_model_contexts
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_model_context_no_delete
                    BEFORE DELETE ON qq_model_contexts
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_model_invocation_intent_no_update
                    BEFORE UPDATE ON qq_model_invocation_intents
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_model_invocation_observation_no_update
                    BEFORE UPDATE ON qq_model_invocation_observations
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                CREATE TRIGGER IF NOT EXISTS qq_model_binding_no_update
                    BEFORE UPDATE ON qq_model_candidate_bindings
                    BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                """
            )
            tables = (
                "qq_model_assist_requests",
                "qq_model_contexts",
                "qq_model_invocation_intents",
                "qq_model_invocation_observations",
                "qq_model_actions",
                "qq_model_tool_results",
                "qq_model_budget_snapshots",
                "qq_model_candidate_bindings",
                "qq_model_candidate_lifecycle",
                "qq_model_private_previews",
                "qq_model_assist_outcomes",
            )
            for table in tables:
                trigger = table.removeprefix("qq_model_")
                c.executescript(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS qq_model_{trigger}_no_update
                        BEFORE UPDATE ON {table}
                        BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                    CREATE TRIGGER IF NOT EXISTS qq_model_{trigger}_no_delete
                        BEFORE DELETE ON {table}
                        BEGIN SELECT RAISE(ABORT,'append_only_violation'); END;
                    """
                )

    def create_assist_request(
        self,
        *,
        config: QQModelWorkflowConfig,
        binding: Mapping[str, Any],
        case_id: str,
        expected_version: int,
        source_message_id_hash: str,
    ) -> tuple[bool, JsonObject]:
        now = self._clock().astimezone(UTC)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT record_json FROM qq_model_assist_requests WHERE source_message_id_hash=?",
                (source_message_id_hash,),
            ).fetchone()
            if existing:
                record = json.loads(existing[0])
                if (
                    record["case_id"] != case_id
                    or record["expected_workflow_version"] != expected_version
                    or record["handler_binding_id"] != binding["handler_binding_id"]
                    or record["stage3_profile_sha256"] != config.stage3_profile_sha256
                ):
                    c.execute("ROLLBACK")
                    raise QQHandlerAuthorizationDenied("assist_source_conflict")
                c.execute("COMMIT")
                return False, record
            case = c.execute(
                "SELECT * FROM qq_handler_cases WHERE case_id=?", (case_id,)
            ).fetchone()
            if not case:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("assist_case_unavailable")
            self._authorize_case_row(case, binding=binding, expected_version=expected_version)
            if case["status"] != "ACCEPTED":
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("assist_requires_accepted_case")
            issue_row = c.execute(
                "SELECT record_json FROM qq_handler_artifacts WHERE artifact_id=?",
                (case["issue_artifact_id"],),
            ).fetchone()
            if not issue_row:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("assist_issue_unavailable")
            issue = json.loads(issue_row[0])
            if _parse(issue["expires_at"]) <= now:
                c.execute("ROLLBACK")
                raise QQHandlerAuthorizationDenied("assist_issue_expired")
            natural_key = canonical_sha256(
                {
                    "tenant": case["tenant_id"],
                    "case": case_id,
                    "revision": case["case_revision_id"],
                    "handler": binding["handler_binding_id"],
                    "version": expected_version,
                    "source": source_message_id_hash,
                    "profile": config.stage3_profile_sha256,
                }
            )
            request = {
                "schema_id": QQ_MODEL_ASSIST_REQUEST_SCHEMA_ID,
                "schema_version": "v1",
                "assist_request_id": _id("qqmar", {"natural_key": natural_key}),
                "natural_key": natural_key,
                "tenant_id": case["tenant_id"],
                "case_id": case_id,
                "case_revision_id": case["case_revision_id"],
                "handler_binding_id": binding["handler_binding_id"],
                "issue_artifact_id": case["issue_artifact_id"],
                "issue_content_sha256": issue["content_sha256"],
                "source_message_id_hash": source_message_id_hash,
                "expected_workflow_version": expected_version,
                "stage3_profile_sha256": config.stage3_profile_sha256,
                "qq_capability_profile_hash": config.qq_capability_profile_hash,
                "model_capability_profile_hash": config.model_capability_profile_hash,
                "policy_profile_sha256": config.policy_profile_sha256,
                "budget_profile_sha256": config.budget_profile_sha256,
                "status": "ASSIST_REQUESTED",
                "created_at": _ts(now),
                "expires_at": issue["expires_at"],
                "request_sha256": "0" * 64,
            }
            request["request_sha256"] = canonical_sha256(request, without="request_sha256")
            validate_qq_model_assist_request(request, self._contract_root)
            c.execute(
                "INSERT INTO qq_model_assist_requests VALUES(?,?,?,?,?)",
                (
                    request["assist_request_id"],
                    natural_key,
                    source_message_id_hash,
                    case_id,
                    _json(request),
                ),
            )
            c.execute(
                "UPDATE qq_handler_cases SET status='ASSIST_REQUESTED' WHERE case_id=?",
                (case_id,),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind="QQ_MODEL_ASSIST_REQUESTED",
                prior_version=expected_version,
                resulting_version=expected_version,
                correlation_id=case_id,
                causation_id=source_message_id_hash,
                reason_code="bound_handler_assist_requested",
                metadata={
                    "assist_request_id": request["assist_request_id"],
                    "request_sha256": request["request_sha256"],
                    "stage3_profile_sha256": config.stage3_profile_sha256,
                },
            )
            c.execute("COMMIT")
        return True, request

    def compile_context(
        self,
        *,
        config: QQModelWorkflowConfig,
        request: Mapping[str, Any],
        ordered_source_sha256s: Sequence[str],
    ) -> tuple[JsonObject, str]:
        with self._connect() as c:
            existing = c.execute(
                "SELECT record_json FROM qq_model_contexts WHERE assist_request_id=?",
                (request["assist_request_id"],),
            ).fetchone()
        issue_view = normalize_private_content(
            self.artifact_content(str(request["issue_artifact_id"])), candidate=False
        )
        if _UNSAFE_ISSUE.search(issue_view):
            raise QQHandlerAuthorizationDenied("assist_issue_model_egress_denied")
        if "503" not in issue_view.upper():
            raise QQHandlerAuthorizationDenied("assist_issue_profile_mismatch")
        issue_hash = _hash(issue_view)
        if issue_hash != request["issue_content_sha256"]:
            raise QQHandlerAuthorizationDenied("assist_issue_hash_mismatch")
        if existing:
            context = json.loads(existing[0])
            validate_qq_model_assist_context(context, self._contract_root)
            if context["issue_view_sha256"] != issue_hash:
                raise QQHandlerAuthorizationDenied("assist_context_conflict")
            return context, issue_view
        created = self._clock().astimezone(UTC)
        context = {
            "schema_id": QQ_MODEL_ASSIST_CONTEXT_SCHEMA_ID,
            "schema_version": "v1",
            "context_id": _id(
                "qqmacx",
                {"request": request["assist_request_id"], "issue": issue_hash},
            ),
            "context_sha256": "0" * 64,
            "tenant_id": request["tenant_id"],
            "case_id": request["case_id"],
            "case_revision_id": request["case_revision_id"],
            "handler_binding_id": request["handler_binding_id"],
            "assist_request_id": request["assist_request_id"],
            "issue_artifact_id": request["issue_artifact_id"],
            "issue_content_sha256": request["issue_content_sha256"],
            "issue_view_sha256": issue_hash,
            "issue_view_length": len(issue_view),
            "issue_classification": "untrusted_redacted_qq_issue",
            "source_profile_sha256": config.source_profile_sha256,
            "ordered_source_sha256s": list(ordered_source_sha256s),
            "prompt_template_sha256": config.prompt_template_sha256,
            "policy_profile_sha256": config.policy_profile_sha256,
            "provider_profile_sha256": config.provider_profile_sha256,
            "price_profile_sha256": config.price_profile_sha256,
            "qq_capability_profile_hash": config.qq_capability_profile_hash,
            "model_capability_profile_hash": config.model_capability_profile_hash,
            "budget_profile_sha256": config.budget_profile_sha256,
            "created_at": _ts(created),
        }
        context["context_sha256"] = canonical_sha256(context, without="context_sha256")
        validate_qq_model_assist_context(context, self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT OR IGNORE INTO qq_model_contexts VALUES(?,?,?)",
                (context["context_id"], request["assist_request_id"], _json(context)),
            )
            c.execute(
                "UPDATE qq_handler_cases SET status='INVESTIGATING' WHERE case_id=?",
                (request["case_id"],),
            )
            self._event(
                c,
                aggregate_id=str(request["case_id"]),
                event_kind="QQ_MODEL_INVESTIGATION_STARTED",
                prior_version=int(request["expected_workflow_version"]),
                resulting_version=int(request["expected_workflow_version"]),
                correlation_id=str(request["case_id"]),
                causation_id=str(request["assist_request_id"]),
                reason_code="model_safe_context_compiled",
                metadata={
                    "assist_request_id": request["assist_request_id"],
                    "context_id": context["context_id"],
                    "context_sha256": context["context_sha256"],
                    "issue_view_sha256": issue_hash,
                },
            )
            c.execute("COMMIT")
        return context, issue_view

    def append_invocation_evidence(self, evidence: Mapping[str, Any]) -> None:
        validate_qq_model_invocation_evidence(evidence, self._contract_root)
        table = (
            "qq_model_invocation_intents"
            if evidence["status"] == "intent_recorded"
            else "qq_model_invocation_observations"
        )
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            if table.endswith("intents"):
                existing = c.execute(
                    "SELECT record_json FROM qq_model_invocation_intents WHERE invocation_id=?",
                    (evidence["invocation_id"],),
                ).fetchone()
                if existing and json.loads(existing[0]) != dict(evidence):
                    c.execute("ROLLBACK")
                    raise QQHandlerStateConflict("model_invocation_intent_conflict")
                c.execute(
                    "INSERT OR IGNORE INTO qq_model_invocation_intents VALUES(?,?,?,?)",
                    (
                        evidence["invocation_id"],
                        evidence["assist_request_id"],
                        evidence["logical_turn_id"],
                        _json(evidence),
                    ),
                )
            else:
                existing = c.execute(
                    "SELECT record_json FROM qq_model_invocation_observations "
                    "WHERE invocation_id=?",
                    (evidence["invocation_id"],),
                ).fetchone()
                if existing and json.loads(existing[0]) != dict(evidence):
                    c.execute("ROLLBACK")
                    raise QQHandlerStateConflict("model_invocation_observation_conflict")
                c.execute(
                    "INSERT OR IGNORE INTO qq_model_invocation_observations VALUES(?,?,?)",
                    (
                        evidence["invocation_id"],
                        evidence["observation_id"],
                        _json(evidence),
                    ),
                )
            c.execute("COMMIT")

    def invocation_for_turn(
        self, logical_turn_id: str
    ) -> tuple[JsonObject, JsonObject | None] | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT record_json FROM qq_model_invocation_intents WHERE logical_turn_id=?",
                (logical_turn_id,),
            ).fetchone()
            if not row:
                return None
            intent = json.loads(row[0])
            observation = c.execute(
                "SELECT record_json FROM qq_model_invocation_observations WHERE invocation_id=?",
                (intent["invocation_id"],),
            ).fetchone()
        return intent, json.loads(observation[0]) if observation else None

    def context_for_request(self, assist_request_id: str) -> JsonObject | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT record_json FROM qq_model_contexts WHERE assist_request_id=?",
                (assist_request_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def invocation_observations_for_request(self, assist_request_id: str) -> list[JsonObject]:
        with self._connect() as c:
            rows = c.execute(
                "SELECT o.record_json FROM qq_model_invocation_observations o "
                "JOIN qq_model_invocation_intents i USING(invocation_id) "
                "WHERE i.assist_request_id=? ORDER BY i.rowid",
                (assist_request_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def candidate_binding_for_request(self, assist_request_id: str) -> JsonObject | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT record_json FROM qq_model_candidate_bindings WHERE assist_request_id=?",
                (assist_request_id,),
            ).fetchone()
        if not row:
            return None
        record = json.loads(row[0])
        current = self.current_model_binding(str(record["case_id"]))
        return record if current == record else None

    def append_action(
        self, assist_request_id: str, logical_turn_id: str, action: Mapping[str, Any]
    ) -> None:
        with self._connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO qq_model_actions VALUES(?,?,?,?)",
                (action["action_sha256"], assist_request_id, logical_turn_id, _json(action)),
            )

    def action_for_turn(self, logical_turn_id: str) -> JsonObject | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT record_json FROM qq_model_actions WHERE logical_turn_id=?",
                (logical_turn_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def append_tool_result(
        self, assist_request_id: str, sequence: int, tool_result: Mapping[str, Any]
    ) -> None:
        with self._connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO qq_model_tool_results VALUES(?,?,?,?,?)",
                (
                    tool_result["tool_result_id"],
                    assist_request_id,
                    sequence,
                    tool_result["content_sha256"],
                    _json(tool_result),
                ),
            )

    def tool_results(self, assist_request_id: str) -> list[JsonObject]:
        with self._connect() as c:
            rows = c.execute(
                "SELECT record_json FROM qq_model_tool_results "
                "WHERE assist_request_id=? ORDER BY sequence",
                (assist_request_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def append_budget(self, budget: Mapping[str, Any], sequence: int) -> None:
        validate_qq_model_case_budget(budget, self._contract_root)
        with self._connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO qq_model_budget_snapshots VALUES(?,?,?,?)",
                (budget["budget_sha256"], budget["assist_request_id"], sequence, _json(budget)),
            )

    def latest_budget(self, assist_request_id: str) -> JsonObject:
        with self._connect() as c:
            row = c.execute(
                "SELECT record_json FROM qq_model_budget_snapshots "
                "WHERE assist_request_id=? ORDER BY sequence DESC LIMIT 1",
                (assist_request_id,),
            ).fetchone()
        if not row:
            raise QQHandlerStateConflict("model_budget_missing")
        return json.loads(row[0])

    def prior_case_budget_usage(
        self, case_id: str, *, exclude_assist_request_id: str
    ) -> JsonObject:
        """Return cumulative final/latest usage from earlier assists for one Case."""

        with self._connect() as c:
            row = c.execute(
                "SELECT b.record_json FROM qq_model_budget_snapshots b "
                "JOIN qq_model_assist_requests r USING(assist_request_id) "
                "WHERE r.case_id=? AND r.assist_request_id<>? "
                "AND b.sequence=(SELECT MAX(b2.sequence) "
                "FROM qq_model_budget_snapshots b2 "
                "WHERE b2.assist_request_id=b.assist_request_id) "
                "ORDER BY b.rowid DESC LIMIT 1",
                (case_id, exclude_assist_request_id),
            ).fetchone()
        total: JsonObject = {
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "tool_calls": 0,
            "actions": 0,
            "no_progress": 0,
            "wall_time_ms": 0,
            "estimated_cost": 0.0,
        }
        if row:
            used = json.loads(row[0])["used"]
            for key in total:
                total[key] = float(used[key]) if key == "estimated_cost" else int(used[key])
        return total

    def create_model_candidate(
        self,
        *,
        config: QQModelWorkflowConfig,
        binding: Mapping[str, Any],
        request: Mapping[str, Any],
        context: Mapping[str, Any],
        result: QQModelRuntimeResult,
    ) -> tuple[JsonObject, JsonObject, JsonObject, JsonObject]:
        if (
            result.terminal_outcome != "response_ready"
            or result.candidate_text is None
            or result.action_sha256 is None
            or result.invocation_evidence is None
            or len(result.ordered_evidence_sha256s) != 3
        ):
            raise QQHandlerStateConflict("model_candidate_incomplete")
        text = normalize_private_content(result.candidate_text, candidate=True)
        if _UNSAFE_MODEL_TEXT.search(text):
            raise QQHandlerStateConflict("model_candidate_authority_claim_denied")
        model_binding: JsonObject = {}

        def finalize_model_candidate(
            c: sqlite3.Connection,
            artifact: Mapping[str, Any],
            revision: Mapping[str, Any],
            approval: Mapping[str, Any],
        ) -> None:
            budget = result.budget
            verifier_material = {
                "request": request["request_sha256"],
                "context": context["context_sha256"],
                "invocation": result.invocation_evidence["evidence_sha256"],
                "action": result.action_sha256,
                "evidence": list(result.ordered_evidence_sha256s),
                "candidate": artifact["content_sha256"],
                "budget": budget["budget_sha256"],
            }
            verifier_sha = canonical_sha256(verifier_material)
            verifier_id = _id("qqmvo", verifier_material)
            record = {
                "schema_id": QQ_MODEL_CANDIDATE_BINDING_SCHEMA_ID,
                "schema_version": "v1",
                "binding_id": _id(
                    "qqmcb",
                    {
                        "request": request["assist_request_id"],
                        "candidate": artifact["content_sha256"],
                    },
                ),
                "binding_sha256": "0" * 64,
                "tenant_id": request["tenant_id"],
                "case_id": request["case_id"],
                "case_revision_id": request["case_revision_id"],
                "workflow_version": revision["workflow_version"],
                "handler_binding_id": request["handler_binding_id"],
                "assist_request_id": request["assist_request_id"],
                "context_id": context["context_id"],
                "context_sha256": context["context_sha256"],
                "invocation_id": result.invocation_evidence["invocation_id"],
                "invocation_evidence_sha256": result.invocation_evidence["evidence_sha256"],
                "action_sha256": result.action_sha256,
                "ordered_evidence_sha256s": list(result.ordered_evidence_sha256s),
                "verifier_outcome_id": verifier_id,
                "verifier_outcome_sha256": verifier_sha,
                "budget_sha256": budget["budget_sha256"],
                "issue_artifact_id": request["issue_artifact_id"],
                "issue_content_sha256": request["issue_content_sha256"],
                "candidate_artifact_id": artifact["artifact_id"],
                "candidate_revision_id": revision["candidate_revision_id"],
                "candidate_sha256": artifact["content_sha256"],
                "approval_request_id": approval["approval_request_id"],
                "policy_profile_sha256": config.policy_profile_sha256,
                "qq_capability_profile_hash": config.qq_capability_profile_hash,
                "model_capability_profile_hash": config.model_capability_profile_hash,
                "provider_profile_sha256": config.provider_profile_sha256,
                "prompt_template_sha256": config.prompt_template_sha256,
                "price_profile_sha256": config.price_profile_sha256,
                "status": "CURRENT",
                "created_at": _ts(self._clock()),
            }
            record["binding_sha256"] = canonical_sha256(record, without="binding_sha256")
            validate_qq_model_candidate_binding(record, self._contract_root)
            c.execute(
                "INSERT INTO qq_model_candidate_bindings VALUES(?,?,?,?,?)",
                (
                    record["binding_id"],
                    request["assist_request_id"],
                    request["case_id"],
                    approval["approval_request_id"],
                    _json(record),
                ),
            )
            c.execute(
                "UPDATE qq_handler_cases SET status='RESPONSE_READY' WHERE case_id=?",
                (request["case_id"],),
            )
            self._event(
                c,
                aggregate_id=str(request["case_id"]),
                event_kind="QQ_MODEL_CANDIDATE_VERIFIED",
                prior_version=int(request["expected_workflow_version"]),
                resulting_version=int(revision["workflow_version"]),
                correlation_id=str(request["case_id"]),
                causation_id=str(request["assist_request_id"]),
                reason_code="deterministic_model_candidate_verified",
                metadata={
                    "model_candidate_binding_id": record["binding_id"],
                    "binding_sha256": record["binding_sha256"],
                    "verifier_outcome_id": verifier_id,
                    "verifier_outcome_sha256": verifier_sha,
                    "candidate_sha256": artifact["content_sha256"],
                },
            )
            model_binding.update(record)

        artifact, revision, approval = self.create_candidate_and_request(
            binding=binding,
            case_id=str(request["case_id"]),
            expected_version=int(request["expected_workflow_version"]),
            candidate_text=text,
            source_message_id_hash=str(request["source_message_id_hash"]),
            candidate_finalizer=finalize_model_candidate,
        )
        return artifact, revision, approval, model_binding

    def create_candidate_and_request(
        self,
        *,
        binding: Mapping[str, Any],
        case_id: str,
        expected_version: int,
        candidate_text: str,
        source_message_id_hash: str,
        candidate_finalizer: Callable[
            [
                sqlite3.Connection,
                Mapping[str, Any],
                Mapping[str, Any],
                Mapping[str, Any],
            ],
            None,
        ]
        | None = None,
    ) -> tuple[JsonObject, JsonObject, JsonObject]:
        """Create a replacement while invalidating model authority in one transaction."""

        def invalidate_model_predecessor(c: sqlite3.Connection, case: sqlite3.Row) -> None:
            prior_revision = case["current_candidate_revision_id"]
            if not prior_revision:
                return
            rows = c.execute(
                "SELECT record_json FROM qq_model_candidate_bindings "
                "WHERE case_id=? ORDER BY rowid DESC",
                (case_id,),
            ).fetchall()
            record = next(
                (
                    item
                    for item in (json.loads(row[0]) for row in rows)
                    if item["candidate_revision_id"] == prior_revision
                ),
                None,
            )
            if record is None:
                return
            lifecycle = c.execute(
                "SELECT status FROM qq_model_candidate_lifecycle WHERE binding_id=? "
                "ORDER BY rowid DESC LIMIT 1",
                (record["binding_id"],),
            ).fetchone()
            if lifecycle and lifecycle["status"] != "CURRENT":
                return
            now = _ts(self._clock())
            reason_code = "handler_model_candidate_replaced"
            lifecycle_id = _id(
                "qqmcl",
                {
                    "binding": record["binding_id"],
                    "status": "INVALIDATED",
                    "reason": reason_code,
                },
            )
            c.execute(
                "INSERT OR IGNORE INTO qq_model_candidate_lifecycle VALUES(?,?,?,?,?)",
                (lifecycle_id, record["binding_id"], "INVALIDATED", reason_code, now),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind="QQ_MODEL_CANDIDATE_INVALIDATED",
                prior_version=int(record["workflow_version"]),
                resulting_version=int(record["workflow_version"]),
                correlation_id=case_id,
                causation_id=str(record["binding_id"]),
                reason_code=reason_code,
                metadata={"model_candidate_binding_id": record["binding_id"]},
            )

        return super().create_candidate_and_request(
            binding=binding,
            case_id=case_id,
            expected_version=expected_version,
            candidate_text=candidate_text,
            source_message_id_hash=source_message_id_hash,
            predecessor_invalidator=invalidate_model_predecessor,
            candidate_finalizer=candidate_finalizer,
        )

    def create_private_preview(
        self,
        *,
        request: Mapping[str, Any],
        model_binding: Mapping[str, Any],
        passive_intent: Mapping[str, Any],
        evidence_summary_sha256: str,
    ) -> JsonObject:
        preview = {
            "schema_id": QQ_MODEL_PRIVATE_PREVIEW_SCHEMA_ID,
            "schema_version": "v1",
            "preview_id": _id("qqmpv", {"request": request["assist_request_id"]}),
            "tenant_id": request["tenant_id"],
            "case_id": request["case_id"],
            "case_revision_id": request["case_revision_id"],
            "handler_binding_id": request["handler_binding_id"],
            "assist_request_id": request["assist_request_id"],
            "source_message_id_hash": request["source_message_id_hash"],
            "candidate_artifact_id": model_binding["candidate_artifact_id"],
            "candidate_sha256": model_binding["candidate_sha256"],
            "evidence_count": len(model_binding["ordered_evidence_sha256s"]),
            "evidence_summary_sha256": evidence_summary_sha256,
            "budget_sha256": model_binding["budget_sha256"],
            "approval_request_id": model_binding["approval_request_id"],
            "candidate_hash_prefix": str(model_binding["candidate_sha256"])[:12],
            "workflow_version": model_binding["workflow_version"],
            "passive_reply_intent_id": passive_intent["intent_id"],
            "created_at": _ts(self._clock()),
            "preview_sha256": "0" * 64,
        }
        preview["preview_sha256"] = canonical_sha256(preview, without="preview_sha256")
        validate_qq_model_private_preview(preview, self._contract_root)
        with self._connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO qq_model_private_previews VALUES(?,?,?)",
                (preview["preview_id"], request["assist_request_id"], _json(preview)),
            )
        return preview

    def create_outcome(
        self,
        *,
        request: Mapping[str, Any],
        result: QQModelRuntimeResult,
        candidate_binding_id: str | None,
        preview_id: str | None,
    ) -> JsonObject:
        reason = result.reason_code if _SAFE_REASON.fullmatch(result.reason_code) else "safe_stop"
        outcome = {
            "schema_id": QQ_MODEL_ASSIST_OUTCOME_SCHEMA_ID,
            "schema_version": "v1",
            "outcome_id": _id("qqmao", {"request": request["assist_request_id"]}),
            "assist_request_id": request["assist_request_id"],
            "tenant_id": request["tenant_id"],
            "case_id": request["case_id"],
            "case_revision_id": request["case_revision_id"],
            "handler_binding_id": request["handler_binding_id"],
            "terminal_outcome": result.terminal_outcome,
            "reason_code": reason,
            "invocation_count": result.usage_summary["provider_calls"],
            "tool_count": len(result.ordered_evidence_sha256s),
            "candidate_binding_id": candidate_binding_id,
            "private_preview_id": preview_id,
            "manual_draft_available": True,
            "approval_authorized": False,
            "delivery_authorized": False,
            "customer_outcome_verified": False,
            "completed_at": _ts(self._clock()),
            "outcome_sha256": "0" * 64,
        }
        outcome["outcome_sha256"] = canonical_sha256(outcome, without="outcome_sha256")
        validate_qq_model_assist_outcome(outcome, self._contract_root)
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT record_json FROM qq_model_assist_outcomes WHERE assist_request_id=?",
                (request["assist_request_id"],),
            ).fetchone()
            if existing:
                c.execute("COMMIT")
                return json.loads(existing[0])
            c.execute(
                "INSERT INTO qq_model_assist_outcomes VALUES(?,?,?)",
                (outcome["outcome_id"], request["assist_request_id"], _json(outcome)),
            )
            if result.terminal_outcome != "response_ready":
                case = c.execute(
                    "SELECT workflow_version FROM qq_handler_cases WHERE case_id=?",
                    (request["case_id"],),
                ).fetchone()
                if not case:
                    c.execute("ROLLBACK")
                    raise QQHandlerStateConflict("handler_case_unavailable")
                prior_version = int(case["workflow_version"])
                next_version = prior_version + 1
                c.execute(
                    "UPDATE qq_handler_cases SET status='ACCEPTED', workflow_version=? "
                    "WHERE case_id=?",
                    (next_version, request["case_id"]),
                )
                self._event(
                    c,
                    aggregate_id=str(request["case_id"]),
                    event_kind="QQ_MODEL_ASSIST_STOPPED",
                    prior_version=prior_version,
                    resulting_version=next_version,
                    correlation_id=str(request["case_id"]),
                    causation_id=str(request["assist_request_id"]),
                    reason_code=reason,
                    metadata={
                        "assist_request_id": request["assist_request_id"],
                        "terminal_outcome": result.terminal_outcome,
                    },
                )
            c.execute("COMMIT")
        return outcome

    def outcome_for_request(self, assist_request_id: str) -> JsonObject | None:
        with self._connect() as c:
            row = c.execute(
                "SELECT record_json FROM qq_model_assist_outcomes WHERE assist_request_id=?",
                (assist_request_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def model_evidence_for_case(self, case_id: str) -> JsonObject:
        """Return the content-free Stage 3 lineage needed by an offline verifier."""

        with self._connect() as c:
            binding_row = c.execute(
                "SELECT record_json FROM qq_model_candidate_bindings "
                "WHERE case_id=? ORDER BY rowid DESC LIMIT 1",
                (case_id,),
            ).fetchone()
            if not binding_row:
                raise QQHandlerStateConflict("model_candidate_binding_missing")
            binding = json.loads(binding_row[0])
            assist_request_id = str(binding["assist_request_id"])

            def one(table: str, where: str, value: str) -> JsonObject:
                row = c.execute(
                    f"SELECT record_json FROM {table} WHERE {where}=? ORDER BY rowid DESC LIMIT 1",
                    (value,),
                ).fetchone()
                if not row:
                    raise QQHandlerStateConflict("model_lineage_record_missing")
                return json.loads(row[0])

            request = one("qq_model_assist_requests", "assist_request_id", assist_request_id)
            context = one("qq_model_contexts", "assist_request_id", assist_request_id)
            budget = one("qq_model_budget_snapshots", "assist_request_id", assist_request_id)
            invocation = one(
                "qq_model_invocation_observations",
                "invocation_id",
                str(binding["invocation_id"]),
            )
            invocations = [
                json.loads(row[0])
                for row in c.execute(
                    "SELECT o.record_json FROM qq_model_invocation_observations o "
                    "JOIN qq_model_invocation_intents i ON i.invocation_id=o.invocation_id "
                    "WHERE i.assist_request_id=? ORDER BY o.rowid",
                    (assist_request_id,),
                ).fetchall()
            ]
            action = one("qq_model_actions", "action_sha256", str(binding["action_sha256"]))
            preview = one("qq_model_private_previews", "assist_request_id", assist_request_id)
            outcome = one("qq_model_assist_outcomes", "assist_request_id", assist_request_id)
            tools = [
                json.loads(row[0])
                for row in c.execute(
                    "SELECT record_json FROM qq_model_tool_results "
                    "WHERE assist_request_id=? ORDER BY sequence",
                    (assist_request_id,),
                ).fetchall()
            ]
            approval_request = one(
                "qq_handler_approval_requests",
                "approval_request_id",
                str(binding["approval_request_id"]),
            )
            approval_decision = one(
                "qq_handler_approval_decisions",
                "approval_request_id",
                str(binding["approval_request_id"]),
            )
            passive_rows = c.execute(
                "SELECT i.record_json, r.result_json FROM qq_handler_passive_intents i "
                "LEFT JOIN qq_handler_passive_results r ON r.intent_id=i.intent_id "
                "WHERE i.case_id=? ORDER BY i.rowid",
                (case_id,),
            ).fetchall()
            final_intent = final_result = None
            for passive_row in passive_rows:
                candidate_intent = json.loads(passive_row[0])
                if candidate_intent.get("operation") == "qq.final_reply.execute":
                    final_intent = candidate_intent
                    final_result = (
                        json.loads(passive_row[1]) if passive_row[1] is not None else None
                    )
            if final_intent is None or final_result is None:
                raise QQHandlerStateConflict("model_final_effect_evidence_missing")
            deletion_count = c.execute(
                "SELECT COUNT(DISTINCT artifact_id) "
                "FROM qq_handler_artifact_lifecycle "
                "WHERE artifact_id IN (SELECT artifact_id FROM qq_handler_artifacts "
                "WHERE case_id=?) AND status='DELETED'",
                (case_id,),
            ).fetchone()[0]
            acknowledgement_count = sum(
                1
                for row in c.execute(
                    "SELECT i.record_json FROM qq_acknowledgement_intents i "
                    "JOIN qq_acknowledgement_completions a "
                    "ON a.tenant_id=i.tenant_id AND a.intent_id=i.intent_id "
                    "WHERE i.tenant_id=?",
                    (request["tenant_id"],),
                ).fetchall()
                if json.loads(row[0]).get("case_id") == case_id
            )
            notification_count = sum(
                1
                for row in c.execute(
                    "SELECT i.record_json FROM qq_handler_notification_intents i "
                    "JOIN qq_handler_notification_attempts a ON a.intent_id=i.intent_id "
                    "WHERE i.case_id=?",
                    (case_id,),
                ).fetchall()
                if json.loads(row[0]).get("handler_binding_id") == binding["handler_binding_id"]
            )
            lifecycle = c.execute(
                "SELECT status, reason_code FROM qq_model_candidate_lifecycle "
                "WHERE binding_id=? ORDER BY rowid DESC LIMIT 1",
                (binding["binding_id"],),
            ).fetchone()
        return {
            "request": request,
            "context": context,
            "budget": budget,
            "invocation": invocation,
            "binding": binding,
            "preview": preview,
            "outcome": outcome,
            "invocations": invocations,
            "action": action,
            "tool_results": tools,
            "lifecycle_status": lifecycle["status"] if lifecycle else "CURRENT",
            "lifecycle_reason_code": (lifecycle["reason_code"] if lifecycle else "current"),
            "approval_request": approval_request,
            "approval_decision": approval_decision,
            "final_intent": final_intent,
            "final_result": final_result,
            "deletion_count": deletion_count,
            "acknowledgement_count": acknowledgement_count,
            "notification_count": notification_count,
        }

    def current_model_binding(self, case_id: str) -> JsonObject | None:
        with self._connect() as c:
            rows = c.execute(
                "SELECT record_json FROM qq_model_candidate_bindings WHERE case_id=?",
                (case_id,),
            ).fetchall()
            for row in reversed(rows):
                record = json.loads(row[0])
                lifecycle = c.execute(
                    "SELECT status FROM qq_model_candidate_lifecycle WHERE binding_id=? "
                    "ORDER BY rowid DESC LIMIT 1",
                    (record["binding_id"],),
                ).fetchone()
                if not lifecycle or lifecycle["status"] == "CURRENT":
                    return record
        return None

    def invalidate_current_model_candidate(self, case_id: str, *, reason_code: str) -> None:
        record = self.current_model_binding(case_id)
        if not record:
            return
        now = _ts(self._clock())
        lifecycle_id = _id(
            "qqmcl",
            {"binding": record["binding_id"], "status": "INVALIDATED", "reason": reason_code},
        )
        with self._connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT OR IGNORE INTO qq_model_candidate_lifecycle VALUES(?,?,?,?,?)",
                (lifecycle_id, record["binding_id"], "INVALIDATED", reason_code, now),
            )
            self._event(
                c,
                aggregate_id=case_id,
                event_kind="QQ_MODEL_CANDIDATE_INVALIDATED",
                prior_version=int(record["workflow_version"]),
                resulting_version=int(record["workflow_version"]),
                correlation_id=case_id,
                causation_id=str(record["binding_id"]),
                reason_code=reason_code,
                metadata={"model_candidate_binding_id": record["binding_id"]},
            )
            c.execute("COMMIT")

    def assert_model_approval_current(
        self,
        approval_request_id: str,
        *,
        binding: Mapping[str, Any],
        expected_version: int,
    ) -> JsonObject:
        with self._connect() as c:
            row = c.execute(
                "SELECT record_json FROM qq_model_candidate_bindings WHERE approval_request_id=?",
                (approval_request_id,),
            ).fetchone()
        if not row:
            raise QQHandlerAuthorizationDenied("model_approval_binding_unavailable")
        record = json.loads(row[0])
        current = self.current_model_binding(str(record["case_id"]))
        case = self.case_projection(str(record["case_id"]))
        budget = self.latest_budget(str(record["assist_request_id"]))
        if (
            current != record
            or record["handler_binding_id"] != binding["handler_binding_id"]
            or record["workflow_version"] != expected_version
            or record["budget_sha256"] != budget["budget_sha256"]
            or case["current_approval_request_id"] != approval_request_id
            or case["current_candidate_revision_id"] != record["candidate_revision_id"]
            or case["status"] != "RESPONSE_READY"
        ):
            raise QQHandlerAuthorizationDenied("model_approval_binding_stale")
        validate_qq_model_candidate_binding(record, self._contract_root)
        return record

    def mark_final_model_content_deleted(self, case_id: str) -> None:
        record = self.current_model_binding(case_id)
        if not record:
            return
        now = _ts(self._clock())
        lifecycle_id = _id(
            "qqmcl", {"binding": record["binding_id"], "status": "DELETED", "at": now}
        )
        with self._connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO qq_model_candidate_lifecycle VALUES(?,?,?,?,?)",
                (
                    lifecycle_id,
                    record["binding_id"],
                    "DELETED",
                    "final_provider_acceptance_terminal",
                    now,
                ),
            )

    def model_counts(self, case_id: str | None = None) -> JsonObject:
        with self._connect() as c:
            if case_id is None:
                return {
                    "assist_request_count": c.execute(
                        "SELECT COUNT(*) FROM qq_model_assist_requests"
                    ).fetchone()[0],
                    "model_invocation_count": c.execute(
                        "SELECT COUNT(*) FROM qq_model_invocation_observations"
                    ).fetchone()[0],
                    "tool_result_count": c.execute(
                        "SELECT COUNT(*) FROM qq_model_tool_results"
                    ).fetchone()[0],
                    "candidate_count": c.execute(
                        "SELECT COUNT(*) FROM qq_model_candidate_bindings"
                    ).fetchone()[0],
                    "private_preview_count": c.execute(
                        "SELECT COUNT(*) FROM qq_model_private_previews"
                    ).fetchone()[0],
                }
            return {
                "assist_request_count": c.execute(
                    "SELECT COUNT(*) FROM qq_model_assist_requests WHERE case_id=?",
                    (case_id,),
                ).fetchone()[0],
                "model_invocation_count": c.execute(
                    "SELECT COUNT(*) FROM qq_model_invocation_observations o "
                    "JOIN qq_model_invocation_intents i USING(invocation_id) "
                    "JOIN qq_model_assist_requests r USING(assist_request_id) "
                    "WHERE r.case_id=?",
                    (case_id,),
                ).fetchone()[0],
                "tool_result_count": c.execute(
                    "SELECT COUNT(*) FROM qq_model_tool_results t "
                    "JOIN qq_model_assist_requests r USING(assist_request_id) "
                    "WHERE r.case_id=?",
                    (case_id,),
                ).fetchone()[0],
                "candidate_count": c.execute(
                    "SELECT COUNT(*) FROM qq_model_candidate_bindings WHERE case_id=?",
                    (case_id,),
                ).fetchone()[0],
                "private_preview_count": c.execute(
                    "SELECT COUNT(*) FROM qq_model_private_previews p "
                    "JOIN qq_model_assist_requests r USING(assist_request_id) "
                    "WHERE r.case_id=?",
                    (case_id,),
                ).fetchone()[0],
            }

    def build_model_acceptance_report(
        self,
        *,
        config: QQModelWorkflowConfig,
        binding: Mapping[str, Any],
        case_id: str,
        mode: str,
        qq_intake_ack_verified: bool,
        handler_private_workflow_verified: bool,
        live_model_contact_verified: bool,
        candidate_verification_verified: bool,
        group_approval_verified: bool,
        final_provider_accepted: bool,
        artifact_deletion_verified: bool,
        network_contacted: bool,
        external_write_attempted: bool,
        model_usage: Mapping[str, Any],
        failure_classification: str | None = None,
    ) -> JsonObject:
        counts = self.model_counts(case_id)
        with self._connect() as c:
            approval_decision_count = c.execute(
                "SELECT COUNT(*) FROM qq_handler_approval_decisions WHERE case_id=?",
                (case_id,),
            ).fetchone()[0]
        report = {
            "schema_id": QQ_MODEL_WORKFLOW_ACCEPTANCE_REPORT_SCHEMA_ID,
            "schema_version": "v1",
            "report_type": "weflow-qq-model-workflow-acceptance.v1",
            "report_id": _id(
                "qqmwr", {"mode": mode, "case": case_id, "binding": binding["handler_binding_id"]}
            ),
            "report_sha256": "0" * 64,
            "mode": mode,
            "qq_provider_mode": "fake" if mode == "offline-fake" else "qq-sandbox-live",
            "model_provider_mode": (
                "replay-fake" if mode == "offline-fake" else "openai-compatible-live"
            ),
            "app_id_hash": config.handler.app_id_hash,
            "tenant_id_hash": config.handler.tenant_id_hash,
            "group_openid_hash": config.handler.group_openid_hash,
            "handler_binding_id": binding["handler_binding_id"],
            "stage3_profile_sha256": config.stage3_profile_sha256,
            "qq_capability_profile_hash": config.qq_capability_profile_hash,
            "model_capability_profile_hash": config.model_capability_profile_hash,
            "case_count": 1,
            "acknowledgement_count": int(qq_intake_ack_verified),
            "notification_attempt_count": self.notification_attempt_count(
                case_id, str(binding["handler_binding_id"])
            ),
            **counts,
            "approval_decision_count": approval_decision_count,
            "final_reply_count": int(final_provider_accepted),
            "artifact_deletion_count": self.deleted_artifact_count(case_id),
            "model_usage": dict(model_usage),
            "failure_classification": failure_classification,
            "qq_intake_ack_verified": qq_intake_ack_verified,
            "handler_private_workflow_verified": handler_private_workflow_verified,
            "live_model_contact_verified": live_model_contact_verified,
            "candidate_verification_verified": candidate_verification_verified,
            "group_approval_verified": group_approval_verified,
            "final_provider_accepted": final_provider_accepted,
            "artifact_deletion_verified": artifact_deletion_verified,
            "network_contacted": network_contacted,
            "external_write_attempted": external_write_attempted,
            "customer_receipt_verified": False,
            "issue_resolution": False,
            "case_completion": False,
            "production_ready": False,
            "privacy": {
                "credential_persisted": False,
                "raw_qq_identity_persisted": False,
                "provider_event_persisted": False,
                "transcript_persisted": False,
                "issue_plaintext_in_report": False,
                "draft_plaintext_in_report": False,
                "prompt_plaintext_persisted": False,
                "provider_body_persisted": False,
                "unrestricted_tool_output_persisted": False,
            },
        }
        report["report_sha256"] = qq_model_workflow_report_sha256(report)
        validate_qq_model_workflow_acceptance_report(report, self._contract_root)
        return report


class QQModelHandlerWorkflowService(QQHandlerWorkflowService):
    def __init__(
        self,
        *,
        config: QQModelWorkflowConfig,
        binding: Mapping[str, Any],
        journal: SQLiteQQModelJournal,
        runtime: QQModelAssistRuntime,
        ordered_source_sha256s: Sequence[str],
    ) -> None:
        super().__init__(config=config.handler, binding=binding, journal=journal)
        self.model_config = config
        self.model_journal = journal
        self.runtime = runtime
        self.ordered_source_sha256s = tuple(ordered_source_sha256s)
        if len(self.ordered_source_sha256s) != 4:
            raise QQHandlerStateConflict("stage3_source_profile_invalid")

    def _assist_content(self, metadata: Mapping[str, Any]) -> str:
        if metadata["terminal_outcome"] != "response_ready":
            return (
                f"模型辅助已安全停止：{metadata['reason_code']}。"
                f"可继续用 WF-DRAFT {metadata['case_id']} "
                f"{metadata['workflow_version']} 换行提交人工草稿。"
            )
        candidate = self.model_journal.artifact_content(metadata["candidate_artifact_id"])
        return (
            f"模型草稿预览（仅私聊）：{candidate}\n"
            f"合成证据来源：{metadata['evidence_count']}；"
            f"模型调用：{metadata['provider_calls']}；"
            f"Token：{metadata['total_tokens']}；"
            f"估算成本 USD {metadata['estimated_cost']:.8f}\n"
            "群审批元数据（不得附带草稿正文）："
            f"WF-APPROVE {metadata['approval_request_id']} "
            f"{metadata['candidate_hash_prefix']} {metadata['workflow_version']}"
        )

    def _recover_persisted_assist(
        self,
        *,
        event: Mapping[str, Any],
        request: Mapping[str, Any],
        outcome: Mapping[str, Any] | None,
    ) -> QQPrivateWorkflowResponse | None:
        assist_request_id = str(request["assist_request_id"])
        model_binding = self.model_journal.candidate_binding_for_request(assist_request_id)
        if outcome is None and model_binding is None:
            return None
        terminal_outcome = str(outcome["terminal_outcome"]) if outcome else "response_ready"
        if terminal_outcome == "response_ready" and model_binding is None:
            raise QQHandlerStateConflict("recovery_model_candidate_binding_missing")
        context = self.model_journal.context_for_request(assist_request_id)
        if context is None and terminal_outcome == "response_ready":
            raise QQHandlerStateConflict("recovery_model_context_missing")
        budget = self.model_journal.latest_budget(assist_request_id)
        used = budget["used"]
        invocations = self.model_journal.invocation_observations_for_request(assist_request_id)
        projection = self.model_journal.case_projection(str(request["case_id"]))
        usage = {
            "available": not bool(budget["pessimistic_unknown_accounted"]),
            "provider_calls": int(used["provider_calls"]),
            "input_tokens": int(used["input_tokens"]),
            "output_tokens": int(used["output_tokens"]),
            "total_tokens": int(used["total_tokens"]),
            "estimated_cost": float(used["estimated_cost"]),
            "currency": "USD",
            "provider_latency_ms": sum(int(item["provider_latency_ms"]) for item in invocations),
            "end_to_end_latency_ms": int(used["wall_time_ms"]),
        }
        recovered_result: QQModelRuntimeResult | None = None
        if outcome is None and model_binding is not None:
            recovered_result = QQModelRuntimeResult(
                terminal_outcome="response_ready",
                reason_code="deterministic_candidate_verified",
                candidate_text=self.model_journal.artifact_content(
                    str(model_binding["candidate_artifact_id"])
                ),
                ordered_evidence_sha256s=tuple(
                    str(item) for item in model_binding["ordered_evidence_sha256s"]
                ),
                action_sha256=str(model_binding["action_sha256"]),
                invocation_evidence=invocations[-1] if invocations else None,
                budget=budget,
                usage_summary=usage,
            )
        candidate_artifact_id = (
            str(model_binding["candidate_artifact_id"]) if model_binding else None
        )
        metadata: JsonObject = {
            "case_id": request["case_id"],
            "workflow_version": int(projection["workflow_version"]),
            "terminal_outcome": terminal_outcome,
            "reason_code": (
                str(outcome["reason_code"]) if outcome else "deterministic_candidate_verified"
            ),
            "candidate_artifact_id": candidate_artifact_id,
            "approval_request_id": (
                model_binding["approval_request_id"] if model_binding else None
            ),
            "candidate_hash_prefix": (
                str(model_binding["candidate_sha256"])[:12] if model_binding else None
            ),
            "evidence_count": (
                len(model_binding["ordered_evidence_sha256s"])
                if model_binding
                else int(outcome["tool_count"])
            ),
            "provider_calls": usage["provider_calls"],
            "total_tokens": usage["total_tokens"],
            "estimated_cost": usage["estimated_cost"],
            "command": {
                "schema_id": QQ_MODEL_ASSIST_COMMAND_SCHEMA_ID,
                "schema_version": "v1",
                "command_id": _id(
                    "qqmac",
                    {
                        "source": event["message_id_hash"],
                        "case": request["case_id"],
                    },
                ),
                "surface": "c2c",
                "command": "assist",
                "tenant_id": request["tenant_id"],
                "case_id": request["case_id"],
                "case_revision_id": request["case_revision_id"],
                "handler_binding_id": self.binding["handler_binding_id"],
                "source_message_id_hash": event["message_id_hash"],
                "expected_version": request["expected_workflow_version"],
                "received_at": _ts(event["occurred_at"]),
            },
        }
        validate_qq_model_assist_command(metadata["command"], self.config.repository_root)
        response_content = self._assist_content(metadata)
        passive_intent = self.model_journal.create_passive_intent(
            case_id=str(request["case_id"]),
            binding=self.binding,
            source_message_id=str(event["message_id"]),
            response_kind="draft-preview",
            occurred_at=event["occurred_at"],
            content_artifact_id=candidate_artifact_id,
            content_sha256=_hash(response_content),
        )
        preview: JsonObject | None = None
        if model_binding is not None:
            preview = self.model_journal.create_private_preview(
                request=request,
                model_binding=model_binding,
                passive_intent=passive_intent,
                evidence_summary_sha256=canonical_sha256(
                    {"ordered_evidence_sha256s": list(model_binding["ordered_evidence_sha256s"])}
                ),
            )
        if outcome is None:
            if recovered_result is None or model_binding is None:
                raise QQHandlerStateConflict("recovery_model_outcome_incomplete")
            outcome = self.model_journal.create_outcome(
                request=request,
                result=recovered_result,
                candidate_binding_id=str(model_binding["binding_id"]),
                preview_id=str(preview["preview_id"]) if preview else None,
            )
        metadata.update(
            {
                "passive_intent": passive_intent,
                "assist_request_id": assist_request_id,
                "context_id": context["context_id"] if context else None,
                "outcome_id": outcome["outcome_id"],
                "model_candidate_binding_id": (
                    model_binding["binding_id"] if model_binding else None
                ),
                "private_preview_id": preview["preview_id"] if preview else None,
            }
        )
        _, persisted = self.model_journal.record_command_once(
            source_message_id_hash=str(event["message_id_hash"]),
            command_id=str(metadata["command"]["command_id"]),
            case_id=str(request["case_id"]),
            classification="private_assist",
            result=metadata,
        )
        return QQPrivateWorkflowResponse(
            duplicate=True,
            command=persisted["command"],
            passive_intent=persisted["passive_intent"],
            content=self._assist_content(persisted),
        )

    def handle_private_event(self, raw_event: Mapping[str, Any]) -> QQPrivateWorkflowResponse:
        data = raw_event.get("d")
        content = data.get("content") if isinstance(data, Mapping) else None
        if not isinstance(content, str) or not unicodedata.normalize(
            "NFKC", content
        ).strip().startswith("WF-ASSIST"):
            if isinstance(content, str) and unicodedata.normalize(
                "NFKC", content
            ).strip().startswith("WF-DRAFT"):
                event = self._private_event(raw_event)
                draft = parse_private_command(event["content"])
                if draft.command == "draft":
                    case = self.model_journal.case_projection(draft.case_id)
                    self.model_journal._authorize_case_row(
                        case, binding=self.binding, expected_version=draft.expected_version
                    )
                    assert draft.body is not None
                    normalize_private_content(draft.body, candidate=True)
            return super().handle_private_event(raw_event)

        event = self._private_event(raw_event)
        self.model_journal.observe_event_order(
            surface="c2c",
            handler_binding_id=str(self.binding["handler_binding_id"]),
            sequence=int(event["gateway_sequence"]),
            source_message_id_hash=str(event["message_id_hash"]),
        )
        stored = self._stored_command(str(event["message_id_hash"]))
        if stored:
            return QQPrivateWorkflowResponse(
                duplicate=True,
                command=stored["command"],
                passive_intent=stored["passive_intent"],
                content=self._assist_content(stored),
            )
        private = parse_assist_command(str(event["content"]))
        created, request = self.model_journal.create_assist_request(
            config=self.model_config,
            binding=self.binding,
            case_id=private.case_id,
            expected_version=private.expected_version,
            source_message_id_hash=str(event["message_id_hash"]),
        )
        existing_outcome = self.model_journal.outcome_for_request(request["assist_request_id"])
        if not created and existing_outcome is None:
            recovered_response = self._recover_persisted_assist(
                event=event, request=request, outcome=existing_outcome
            )
            if recovered_response is not None:
                return recovered_response
        elif not created:
            recovered_response = self._recover_persisted_assist(
                event=event, request=request, outcome=existing_outcome
            )
            if recovered_response is not None:
                return recovered_response
        context: JsonObject | None
        try:
            context, issue_view = self.model_journal.compile_context(
                config=self.model_config,
                request=request,
                ordered_source_sha256s=self.ordered_source_sha256s,
            )
        except QQHandlerAuthorizationDenied as error:
            context = None
            result = self.runtime.safe_stop(
                request=request,
                terminal_outcome="policy_denied",
                reason_code=str(error),
            )
        else:
            result = self.runtime.run(request=request, context=context, issue_view=issue_view)
        candidate_artifact_id: str | None = None
        approval_request_id: str | None = None
        candidate_hash_prefix: str | None = None
        model_binding: JsonObject | None = None
        projection = self.model_journal.case_projection(private.case_id)
        metadata: JsonObject
        if result.terminal_outcome == "response_ready":
            artifact, revision, approval, model_binding = self.model_journal.create_model_candidate(
                config=self.model_config,
                binding=self.binding,
                request=request,
                context=context,
                result=result,
            )
            candidate_artifact_id = str(artifact["artifact_id"])
            approval_request_id = str(approval["approval_request_id"])
            candidate_hash_prefix = str(approval["candidate_hash_prefix"])
            projection = self.model_journal.case_projection(private.case_id)
        outcome: JsonObject | None = None
        if result.terminal_outcome != "response_ready":
            outcome = self.model_journal.create_outcome(
                request=request,
                result=result,
                candidate_binding_id=None,
                preview_id=None,
            )
            projection = self.model_journal.case_projection(private.case_id)
        command_record = {
            "schema_id": QQ_MODEL_ASSIST_COMMAND_SCHEMA_ID,
            "schema_version": "v1",
            "command_id": _id(
                "qqmac", {"source": event["message_id_hash"], "case": private.case_id}
            ),
            "surface": "c2c",
            "command": "assist",
            "tenant_id": request["tenant_id"],
            "case_id": private.case_id,
            "case_revision_id": request["case_revision_id"],
            "handler_binding_id": self.binding["handler_binding_id"],
            "source_message_id_hash": event["message_id_hash"],
            "expected_version": private.expected_version,
            "received_at": _ts(event["occurred_at"]),
        }
        validate_qq_model_assist_command(command_record, self.config.repository_root)
        usage = result.usage_summary
        metadata = {
            "case_id": private.case_id,
            "workflow_version": projection["workflow_version"],
            "terminal_outcome": result.terminal_outcome,
            "reason_code": result.reason_code,
            "candidate_artifact_id": candidate_artifact_id,
            "approval_request_id": approval_request_id,
            "candidate_hash_prefix": candidate_hash_prefix,
            "evidence_count": len(result.ordered_evidence_sha256s),
            "provider_calls": usage["provider_calls"],
            "total_tokens": usage["total_tokens"],
            "estimated_cost": usage["estimated_cost"],
            "command": command_record,
        }
        response_content = self._assist_content(metadata)
        passive_intent = self.model_journal.create_passive_intent(
            case_id=private.case_id,
            binding=self.binding,
            source_message_id=str(event["message_id"]),
            response_kind="draft-preview",
            occurred_at=event["occurred_at"],
            content_artifact_id=candidate_artifact_id,
            content_sha256=_hash(response_content),
        )
        preview: JsonObject | None = None
        if model_binding:
            preview = self.model_journal.create_private_preview(
                request=request,
                model_binding=model_binding,
                passive_intent=passive_intent,
                evidence_summary_sha256=canonical_sha256(
                    {"ordered_evidence_sha256s": list(result.ordered_evidence_sha256s)}
                ),
            )
        if outcome is None:
            outcome = self.model_journal.create_outcome(
                request=request,
                result=result,
                candidate_binding_id=model_binding["binding_id"] if model_binding else None,
                preview_id=preview["preview_id"] if preview else None,
            )
        metadata.update(
            {
                "passive_intent": passive_intent,
                "assist_request_id": request["assist_request_id"],
                "context_id": context["context_id"] if context else None,
                "outcome_id": outcome["outcome_id"],
                "model_candidate_binding_id": (
                    model_binding["binding_id"] if model_binding else None
                ),
                "private_preview_id": preview["preview_id"] if preview else None,
            }
        )
        command_created, persisted = self.model_journal.record_command_once(
            source_message_id_hash=str(event["message_id_hash"]),
            command_id=str(command_record["command_id"]),
            case_id=private.case_id,
            classification="private_assist",
            result=metadata,
        )
        return QQPrivateWorkflowResponse(
            duplicate=not command_created,
            command=persisted["command"],
            passive_intent=persisted["passive_intent"],
            content=self._assist_content(persisted),
        )

    def handle_group_approval(self, raw_event: Mapping[str, Any]) -> QQGroupApprovalResponse:
        command, event = self._group_event(raw_event)
        self.model_journal.assert_model_approval_current(
            command.approval_request_id,
            binding=self.binding,
            expected_version=command.expected_version,
        )
        self.model_journal.observe_event_order(
            surface="group",
            handler_binding_id=str(self.binding["handler_binding_id"]),
            sequence=int(event["gateway_sequence"]),
            source_message_id_hash=_hash(str(event["message_id"])),
        )
        decision = self.model_journal.approve_request(
            binding=self.binding,
            command=command,
            member_openid=event["member_openid"],
            group_openid=event["group_openid"],
            source_message_id=event["message_id"],
            occurred_at=event["occurred_at"],
            identity_salt=self.config.identity_salt,
        )
        final_intent, content = self.model_journal.final_delivery_intent(
            decision, binding=self.binding
        )
        return QQGroupApprovalResponse(decision, final_intent, content)

    def execute_final_response(
        self, response: QQGroupApprovalResponse, *, transport: QQHandlerTransport
    ) -> JsonObject:
        result = super().execute_final_response(response, transport=transport)
        if result["provider_accepted"]:
            self.model_journal.mark_final_model_content_deleted(str(response.decision["case_id"]))
        return result


__all__ = [
    "QQModelAssistRuntime",
    "QQModelHandlerWorkflowService",
    "QQModelRuntimeResult",
    "QQModelWorkflowConfig",
    "QQ_STAGE3_MODEL_CAPABILITIES",
    "QQ_STAGE3_QQ_CAPABILITIES",
    "SQLiteQQModelJournal",
    "parse_assist_command",
    "render_model_candidate",
]
