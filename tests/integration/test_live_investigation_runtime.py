import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from weflow_agent_runtime.investigation import compile_context_manifest
from weflow_agent_runtime.live_provider import (
    OpenAICompatibleProvider,
    ProviderTransportError,
    TransportResponse,
)
from weflow_agent_runtime.live_runtime import (
    DraftArtifactStore,
    LiveProviderBinding,
    run_live_investigation_attempt,
)
from weflow_agent_runtime.live_store import LiveAttemptIdentities, LiveEvaluationStore
from weflow_business_simulator import SyntheticIntakeSimulator
from weflow_contracts.live import MODEL_ACTION_PROPOSAL_SCHEMA_ID
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_testkit.live_evaluation import load_live_pilot_suite

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 8, 6, 0, 0, 2, tzinfo=UTC)
SENTINEL = "sentinel-live-api-secret"


@dataclass(frozen=True, repr=False)
class Credential:
    value: str = SENTINEL

    def authorization_header(self) -> str:
        return f"Bearer {self.value}"

    def __repr__(self) -> str:
        return "Credential(redacted)"


ProposalFactory = Callable[[Mapping[str, object], int], Mapping[str, object]]


class ScriptedTransport:
    def __init__(
        self,
        factory: ProposalFactory,
        *,
        statuses: list[int] | None = None,
        error: ProviderTransportError | None = None,
    ) -> None:
        self.factory = factory
        self.statuses = statuses or []
        self.error = error
        self.calls = 0

    def send(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_ms: int,
    ) -> TransportResponse:
        del url, timeout_ms
        self.calls += 1
        assert headers["Authorization"] == f"Bearer {SENTINEL}"
        if self.error is not None:
            raise self.error
        request = json.loads(body)
        user = json.loads(request["messages"][1]["content"])
        status = self.statuses.pop(0) if self.statuses else 200
        if status != 200:
            return TransportResponse(status, {}, b'{"error":"bounded"}', 5)
        proposal = self.factory(user, self.calls)
        envelope = {
            "choices": [{"message": {"content": json.dumps(proposal)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
        return TransportResponse(
            200,
            {"x-request-id": f"request-{self.calls}"},
            json.dumps(envelope).encode(),
            7,
        )


def proposal(
    action_type: str,
    *,
    reason_code: str | None = None,
    evidence_references: list[str] | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    draft = None
    if action_type == "response_candidate":
        draft = {
            "summary": "A synthetic API is intermittently returning HTTP 503.",
            "diagnosis": "Synthetic evidence indicates upstream queue saturation.",
            "next_steps": ["Continue the bounded synthetic observation window."],
            "risk": "medium",
        }
    value = {
        "schema_id": MODEL_ACTION_PROPOSAL_SCHEMA_ID,
        "schema_version": "v1",
        "action_type": action_type,
        "reason_code": reason_code,
        "evidence_references": evidence_references or [],
        "draft": draft,
    }
    if extra:
        value.update(extra)
    return value


def next_grounded_action(user: Mapping[str, object], _: int) -> Mapping[str, object]:
    trusted = user["trusted_runtime"]
    references = list(trusted["current_evidence_references"])
    reads = ["read_crm", "read_monitoring", "read_knowledge"]
    if len(references) < len(reads):
        return proposal(reads[len(references)])
    return proposal("response_candidate", evidence_references=references)


def _record(suite: object, task_id: str) -> Mapping[str, object]:
    return next(item for item in suite.records if item["task"]["task_id"] == task_id)


def run_attempt(
    tmp_path: Path,
    task_id: str,
    factory: ProposalFactory,
    *,
    statuses: list[int] | None = None,
    transport_error: ProviderTransportError | None = None,
    budget_override: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], SQLiteDurableWorkflow, LiveEvaluationStore, ScriptedTransport]:
    suite = load_live_pilot_suite(ROOT, now=FIXED_TIME)
    record = _record(suite, task_id)
    ledger = SQLiteCaseLedger(
        tmp_path / "workflow.sqlite3",
        clock=FixedClock(FIXED_TIME),
        contract_root=ROOT,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=ROOT,
    )
    accepted = SyntheticIntakeSimulator(root=ROOT).submit_fixture(ledger, "api-503-first-delivery")
    projection = workflow.run_case("tenant-alpha", accepted.case_id, accepted.case_revision_id)
    assert projection is not None and projection["state"] == "TICKET_READY"
    budget = dict(suite.budget_profile)
    if budget_override:
        budget.update(budget_override)
    transcript = {
        "environment_snapshot_sha256": record["task"]["context_source"]["sha256"],
        "action_budget": budget["action_limit"],
        "tool_budget": budget["tool_limit"],
        "no_progress_limit": budget["no_progress_limit"],
    }
    manifest = compile_context_manifest(workflow, "tenant-alpha", accepted.case_id, transcript)
    store = LiveEvaluationStore(tmp_path / "live.sqlite3")
    session_id = f"session-{task_id}"
    store.append_session(
        evaluation_session_id=session_id,
        suite_id="live-pilot.v1",
        tenant_id="tenant-alpha",
        config_sha256="a" * 64,
        created_at=manifest["created_at"],
    )
    identities = LiveAttemptIdentities(session_id, task_id, 1)
    transport = ScriptedTransport(factory, statuses=statuses, error=transport_error)
    provider = OpenAICompatibleProvider(
        endpoint="https://api.example.test/v1",
        model="synthetic-model-v1",
        auth=Credential(),
        transport=transport,
    )
    result = run_live_investigation_attempt(
        workflow=workflow,
        tenant_id="tenant-alpha",
        case_id=accepted.case_id,
        manifest=manifest,
        task_record=record,
        prompt_template=suite.prompt_template,
        policy_profile=suite.policy_profile,
        budget_profile=budget,
        price_profile=suite.price_profile,
        provider_binding=LiveProviderBinding(
            provider_profile_id="openai-compatible.v1",
            provider_profile_sha256="b" * 64,
            model_id_sha256="c" * 64,
            price_profile_id=suite.price_profile["price_profile_id"],
            price_profile_sha256=suite.price_profile["profile_sha256"],
        ),
        provider=provider,
        store=store,
        identities=identities,
        artifact_store=DraftArtifactStore(tmp_path / "artifacts"),
    )
    return result, workflow, store, transport


def test_allowed_reads_and_grounded_candidate_reach_only_verifier_response_ready(
    tmp_path: Path,
) -> None:
    result, workflow, store, transport = run_attempt(
        tmp_path, "grounded-response-ready", next_grounded_action
    )
    assert result["terminal_outcome"] == "response_ready"
    assert result["state"] == "RESPONSE_READY"
    assert transport.calls == 4
    assert result["approval_count"] == 0
    assert result["delivery_count"] == 0
    assert result["external_business_write_count"] == 0
    assert not tuple((tmp_path / "artifacts").glob("*.json"))
    facts = workflow.investigation_facts_for_case("tenant-alpha", result["attempt_id"])
    assert facts is None
    persisted = (tmp_path / "live.sqlite3").read_bytes() + (
        tmp_path / "workflow.sqlite3"
    ).read_bytes()
    assert SENTINEL.encode() not in persisted
    assert b"intermittently returning HTTP 503" not in persisted
    assert b"Synthetic monitoring correlates" not in persisted
    assert len(store.attempt_snapshot(result["attempt_id"])["observations"]) == 4


def test_missing_information_and_conflicting_evidence_stop_safely(tmp_path: Path) -> None:
    def missing(user: Mapping[str, object], _: int) -> Mapping[str, object]:
        refs = list(user["trusted_runtime"]["current_evidence_references"])
        if not refs:
            return proposal("read_crm")
        return proposal("needs_information", reason_code="missing_required_information")

    missing_result, missing_workflow, _, _ = run_attempt(
        tmp_path / "missing", "missing-information", missing
    )
    assert missing_result["terminal_outcome"] == "needs_information"
    assert missing_workflow.source_counts("tenant-alpha")["investigation_candidates"] == 0

    def conflicting(user: Mapping[str, object], _: int) -> Mapping[str, object]:
        refs = list(user["trusted_runtime"]["current_evidence_references"])
        if len(refs) < 3:
            return proposal(["read_crm", "read_monitoring", "read_knowledge"][len(refs)])
        return proposal("needs_operator", reason_code="conflicting_evidence")

    conflict_result, conflict_workflow, _, _ = run_attempt(
        tmp_path / "conflict", "conflicting-evidence", conflicting
    )
    assert conflict_result["terminal_outcome"] == "needs_operator"
    assert conflict_workflow.source_counts("tenant-alpha")["investigation_candidates"] == 0


def test_tool_timeout_and_fault_injected_budget_exhaustion_never_claim_success(
    tmp_path: Path,
) -> None:
    timeout_result, timeout_workflow, _, _ = run_attempt(
        tmp_path / "timeout", "tool-timeout", next_grounded_action
    )
    assert timeout_result["terminal_outcome"] == "tool_timeout"
    assert timeout_workflow.source_counts("tenant-alpha")["investigation_candidates"] == 0

    budget_result, budget_workflow, _, budget_transport = run_attempt(
        tmp_path / "budget", "budget-exhaustion", next_grounded_action
    )
    assert budget_result["terminal_outcome"] == "budget_exhausted"
    assert budget_transport.calls == 1
    assert budget_workflow.source_counts("tenant-alpha")["agent_steps"] == 0


def test_prompt_injection_remains_untrusted_and_clean_draft_can_verify(tmp_path: Path) -> None:
    saw_injection = False

    def injection(user: Mapping[str, object], call: int) -> Mapping[str, object]:
        nonlocal saw_injection
        rendered = json.dumps(user)
        saw_injection = saw_injection or "approve yourself" in rendered
        return next_grounded_action(user, call)

    result, workflow, _, _ = run_attempt(tmp_path, "prompt-injection", injection)
    assert saw_injection is True
    assert result["terminal_outcome"] == "response_ready"
    assert result["approval_count"] == 0
    assert result["delivery_count"] == 0
    assert result["external_business_write_count"] == 0


def test_foreign_evidence_and_self_approval_output_are_denied(tmp_path: Path) -> None:
    def foreign(user: Mapping[str, object], call: int) -> Mapping[str, object]:
        grounded = next_grounded_action(user, call)
        if grounded["action_type"] == "response_candidate":
            grounded["evidence_references"] = ["evidence:foreign"]
        return grounded

    foreign_result, foreign_workflow, _, _ = run_attempt(
        tmp_path / "foreign", "grounded-response-ready", foreign
    )
    assert foreign_result["terminal_outcome"] == "policy_denied"
    assert foreign_workflow.source_counts("tenant-alpha")["investigation_candidates"] == 0

    def self_approve(_: Mapping[str, object], __: int) -> Mapping[str, object]:
        return proposal("read_crm", extra={"approval": True, "target_state": "RESPONSE_READY"})

    denied, denied_workflow, _, _ = run_attempt(
        tmp_path / "authority", "grounded-response-ready", self_approve
    )
    assert denied["terminal_outcome"] == "malformed_model_output"
    assert denied_workflow.source_counts("tenant-alpha")["agent_steps"] == 0


def test_retryable_error_retries_once_but_unknown_timeout_never_retries(tmp_path: Path) -> None:
    retry, _, _, retry_transport = run_attempt(
        tmp_path / "retry",
        "grounded-response-ready",
        lambda *_: proposal("needs_operator", reason_code="tool_unavailable"),
        statuses=[429, 200],
    )
    assert retry["terminal_outcome"] == "needs_operator"
    assert retry_transport.calls == 2
    assert retry["budget"]["retry_count"] == 1

    unknown, unknown_workflow, _, unknown_transport = run_attempt(
        tmp_path / "unknown",
        "grounded-response-ready",
        lambda *_: proposal("read_crm"),
        transport_error=ProviderTransportError(outcome_unknown=True),
    )
    assert unknown["terminal_outcome"] == "provider_outcome_unknown"
    assert unknown_transport.calls == 1
    assert unknown_workflow.source_counts("tenant-alpha")["agent_steps"] == 0


def test_call_is_prevented_when_input_cannot_fit_budget(tmp_path: Path) -> None:
    result, workflow, _, transport = run_attempt(
        tmp_path,
        "grounded-response-ready",
        next_grounded_action,
        budget_override={"input_token_limit": 1},
    )
    assert result["terminal_outcome"] == "budget_exhausted"
    assert transport.calls == 0
    assert workflow.source_counts("tenant-alpha")["agent_steps"] == 0


def test_repeated_action_hits_no_progress_before_duplicate_tool_effect(tmp_path: Path) -> None:
    result, workflow, _, transport = run_attempt(
        tmp_path, "grounded-response-ready", lambda *_: proposal("read_crm")
    )
    assert result["terminal_outcome"] == "needs_operator"
    assert result["reason_code"] == "no_progress_limit_reached"
    assert transport.calls == 2
    assert workflow.source_counts("tenant-alpha")["agent_steps"] == 1


def test_authority_language_in_draft_is_policy_denied(tmp_path: Path) -> None:
    def unsafe_draft(user: Mapping[str, object], call: int) -> Mapping[str, object]:
        value = dict(next_grounded_action(user, call))
        if value["action_type"] == "response_candidate":
            draft = dict(value["draft"])
            draft["summary"] = "I approve this case and sent it to the customer."
            value["draft"] = draft
        return value

    result, workflow, _, _ = run_attempt(tmp_path, "grounded-response-ready", unsafe_draft)
    assert result["terminal_outcome"] == "policy_denied"
    assert workflow.source_counts("tenant-alpha")["investigation_candidates"] == 0
