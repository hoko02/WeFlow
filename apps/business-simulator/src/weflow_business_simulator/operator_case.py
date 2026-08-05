"""Public deterministic source boundary for the fixed offline Operator Case."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weflow_contracts import (
    OPERATOR_CASE_SNAPSHOT_SCHEMA_ID,
    SOURCE_PHASE,
    finalize_operator_case_snapshot,
    operator_case_entry_id,
    validate_checkpoint_sequence,
    validate_context_manifest,
    validate_evidence_chain,
    validate_generated_ledger_event,
    validate_operator_case_snapshot,
    validate_response_candidate,
    validate_revision_chain,
    validate_verifier_outcome,
    validate_workflow_projection,
)
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger

from .evidence import SyntheticEvidenceTrajectorySimulator

JsonObject = dict[str, Any]
FIXTURE_TIME = datetime(2026, 8, 4, tzinfo=UTC)
TENANT_ID = "tenant-alpha"
FIXTURE_ID = "api-503-policy-approval-delivery"
FIXTURE_SOURCE_PATH = "fixtures/policy/api-503-policy-approval-delivery.json"
RETAINED_REPORT_PATH = "reports/add-offline-operator-case-timeline-acceptance.json"


class OperatorCaseSourceError(ValueError):
    """Safe source integrity failure without payload, SQL, or filesystem detail."""


@dataclass(frozen=True)
class OperatorCaseSourceBundle:
    """Validated public records retained by one fresh deterministic source run."""

    fixture_sha256: str
    case_projection: JsonObject
    revisions: tuple[JsonObject, ...]
    events: tuple[JsonObject, ...]
    workflow_projection: JsonObject
    checkpoints: tuple[JsonObject, ...]
    investigation: JsonObject
    policy: JsonObject
    artifact: JsonObject
    trajectory: JsonObject
    evidence_report: JsonObject
    replay_result: JsonObject
    source_counts: JsonObject
    duplicate_natural_identity_count: int
    duplicate_idempotency_key_count: int


def _require_mapping(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        raise OperatorCaseSourceError("operator_case_source_invalid")
    return dict(value)


def _fixture_sha256(root: Path) -> str:
    path = root / FIXTURE_SOURCE_PATH
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise OperatorCaseSourceError("operator_case_fixture_not_ready") from error


def _validate_effect_identities(workflow: SQLiteDurableWorkflow) -> tuple[int, int]:
    """Inspect only the public export and discard its broad journal immediately."""

    exported = workflow.export_snapshot(TENANT_ID)
    journal = exported.get("workflow_journal")
    if not isinstance(journal, Mapping):
        raise OperatorCaseSourceError("operator_case_source_invalid")
    side_effects = journal.get("side_effect_intents")
    deliveries = journal.get("outbound_delivery_intents")
    if not isinstance(side_effects, list) or not isinstance(deliveries, list):
        raise OperatorCaseSourceError("operator_case_source_invalid")
    intents = [*side_effects, *deliveries]
    if not all(isinstance(item, Mapping) for item in intents):
        raise OperatorCaseSourceError("operator_case_source_invalid")
    natural_identities = [
        (str(item.get("operation")), str(item.get("natural_key"))) for item in intents
    ]
    idempotency_keys = [str(item.get("idempotency_key")) for item in intents]
    duplicate_natural = len(natural_identities) - len(set(natural_identities))
    duplicate_idempotency = len(idempotency_keys) - len(set(idempotency_keys))
    if duplicate_natural or duplicate_idempotency:
        raise OperatorCaseSourceError("operator_case_effect_identity_duplicate")
    return duplicate_natural, duplicate_idempotency


def run_operator_case_source(
    root: Path,
    store_path: Path,
) -> OperatorCaseSourceBundle:
    """Run the allowlisted path once in a caller-injected fresh SQLite store."""

    root = root.resolve()
    store_path = store_path.resolve()
    default_store = (root / ".weflow" / "case-ledger.sqlite3").resolve()
    if store_path == default_store or store_path.exists():
        raise OperatorCaseSourceError("operator_case_store_not_fresh")
    store_path.parent.mkdir(parents=True, exist_ok=True)

    ledger = SQLiteCaseLedger(
        store_path,
        clock=FixedClock(FIXTURE_TIME),
        contract_root=root,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXTURE_TIME),
        contract_root=root,
    )
    generated = SyntheticEvidenceTrajectorySimulator(root=root).authorized(ledger, workflow)
    if (
        generated.get("fixture_id") != FIXTURE_ID
        or generated.get("outcome") != "fixture_delivery_recorded"
        or generated.get("network_required") is not False
        or generated.get("model_invocation") is not False
        or generated.get("external_write") is not False
        or generated.get("customer_resolution") is not False
    ):
        raise OperatorCaseSourceError("operator_case_fixture_outcome_invalid")

    case_id = str(generated.get("case_id"))
    replayed = workflow.replay_evidence_trajectory(
        TENANT_ID, str(generated.get("trajectory_id"))
    )
    artifact = _require_mapping(replayed.get("artifact"))
    trajectory = _require_mapping(replayed.get("trajectory"))
    report = _require_mapping(replayed.get("report"))
    replay_result = _require_mapping(replayed.get("replay_result"))
    case_projection = _require_mapping(ledger.get_case_projection(TENANT_ID, case_id))
    revisions = tuple(ledger.list_case_revisions(TENANT_ID, case_id))
    events = tuple(ledger.list_case_events(TENANT_ID, case_id))
    workflow_projection = _require_mapping(
        workflow.get_workflow_for_case(TENANT_ID, case_id)
    )
    checkpoints_value = workflow.list_workflow_checkpoints_for_case(TENANT_ID, case_id)
    if checkpoints_value is None:
        raise OperatorCaseSourceError("operator_case_source_invalid")
    checkpoints = tuple(checkpoints_value)
    investigation = _require_mapping(
        workflow.investigation_facts_for_case(TENANT_ID, case_id)
    )
    policy = _require_mapping(workflow.policy_approval_facts_for_case(TENANT_ID, case_id))
    counts = _require_mapping(workflow.source_counts(TENANT_ID))

    validate_revision_chain(revisions)
    for event in events:
        validate_generated_ledger_event(event, root)
    validate_workflow_projection(workflow_projection, root)
    validate_checkpoint_sequence(checkpoints, root)
    validate_context_manifest(_require_mapping(investigation.get("context_manifest")), root)
    candidate = _require_mapping(investigation.get("response_candidate"))
    verifier = _require_mapping(investigation.get("verifier_outcome"))
    validate_response_candidate(candidate, root)
    validate_verifier_outcome(verifier, root)
    validate_evidence_chain(artifact, trajectory, report, replay_result, root)
    workflow.validate_projection_agreement()

    revision_id = str(case_projection.get("latest_case_revision_id"))
    workflow_id = str(workflow_projection.get("workflow_id"))
    linked = [
        case_projection.get("tenant_id") == TENANT_ID,
        case_projection.get("state") == "DELIVERY_RECORDED",
        len(revisions) == 1,
        revisions[0].get("case_revision_id") == revision_id,
        all(event.get("case_revision_id") == revision_id for event in events),
        workflow_projection.get("case_id") == case_id,
        workflow_projection.get("case_revision_id") == revision_id,
        workflow_projection.get("state") == "DELIVERY_RECORDED",
        all(checkpoint.get("workflow_id") == workflow_id for checkpoint in checkpoints),
        investigation.get("workflow_id") == workflow_id,
        policy.get("workflow_id") == workflow_id,
        policy.get("state") == "DELIVERY_RECORDED",
        policy.get("fixture_local") is True,
        policy.get("real_external_write") is False,
        policy.get("customer_resolution") is False,
        trajectory.get("case_id") == case_id,
        trajectory.get("case_revision_id") == revision_id,
        trajectory.get("workflow_id") == workflow_id,
        report.get("outcome") == "fixture_delivery_recorded",
        replay_result.get("verification_outcome") == "verified",
    ]
    if not all(linked):
        raise OperatorCaseSourceError("operator_case_source_link_invalid")

    required_counts = {
        "side_effect_intents": 2,
        "side_effect_completions": 2,
        "investigation_tool_results": 3,
        "policy_decisions": 1,
        "approval_decisions": 1,
        "outbound_delivery_intents": 1,
        "outbound_delivery_completions": 1,
        "fixture_delivery_operations": 1,
        "fixture_delivery_records": 1,
        "evidence_trajectories": 1,
        "evidence_reports": 1,
        "trajectory_replay_results": 1,
    }
    if any(int(counts.get(name, -1)) != expected for name, expected in required_counts.items()):
        raise OperatorCaseSourceError("operator_case_source_count_invalid")
    duplicate_natural, duplicate_idempotency = _validate_effect_identities(workflow)

    return OperatorCaseSourceBundle(
        fixture_sha256=_fixture_sha256(root),
        case_projection=case_projection,
        revisions=revisions,
        events=events,
        workflow_projection=workflow_projection,
        checkpoints=checkpoints,
        investigation=investigation,
        policy=policy,
        artifact=artifact,
        trajectory=trajectory,
        evidence_report=report,
        replay_result=replay_result,
        source_counts=counts,
        duplicate_natural_identity_count=duplicate_natural,
        duplicate_idempotency_key_count=duplicate_idempotency,
    )


def _entry_semantics(
    source_kind: str,
    *,
    checkpoint: Mapping[str, Any] | None = None,
    prior_checkpoint: Mapping[str, Any] | None = None,
) -> tuple[str | None, str | None, str, str, str, str, str]:
    from_state = None
    to_state = None
    observation = "recorded"
    result = "recorded"
    gate = "not_applicable"
    recovery = "not_required"
    reasons = {
        "accepted_intake": "accepted_intake",
        "case_revision": "revision_created",
        "case_event": "case_event_recorded",
        "workflow_activation": "workflow_activated",
        "workflow_checkpoint": "workflow_checkpoint_recorded",
        "context_manifest": "context_compiled",
        "agent_step": "agent_action_recorded",
        "tool_request": "tool_request_recorded",
        "tool_result": "tool_result_recorded",
        "evidence": "evidence_linked",
        "response_candidate": "candidate_proposed",
        "verifier_outcome": "evidence_complete",
        "policy_activation": "policy_activated",
        "capability_grant": "capability_active",
        "policy_decision": "fixture_policy_allowed",
        "authorization_binding": "authorization_bound",
        "approval_request": "approval_requested",
        "approval_decision": "fixture_approval_approved",
        "delivery_intent": "delivery_intent_recorded",
        "delivery_completion": "fixture_delivery_recorded",
        "replay_result": "verification_replay_verified",
    }
    if source_kind == "workflow_checkpoint" and checkpoint is not None:
        from_state = (
            None if prior_checkpoint is None else str(prior_checkpoint.get("current_state"))
        )
        to_state = str(checkpoint.get("current_state"))
    if source_kind == "accepted_intake":
        observation = "accepted"
    elif source_kind == "response_candidate":
        observation = "proposed"
    elif source_kind == "verifier_outcome":
        observation, result, gate = "verified", "passed", "passed"
    elif source_kind in {"capability_grant", "policy_decision", "authorization_binding"}:
        observation, result, gate = "allowed", "allowed", "passed"
    elif source_kind == "approval_decision":
        observation, result, gate = "approved", "approved", "passed"
    elif source_kind == "delivery_completion":
        observation, result = "fixture_local_recorded", "fixture_local_recorded"
        to_state = "DELIVERY_RECORDED"
    elif source_kind == "replay_result":
        observation, result, gate = "verified", "verified", "passed"
    return from_state, to_state, observation, result, gate, recovery, reasons[source_kind]


def build_operator_case_snapshot(
    source: OperatorCaseSourceBundle,
    root: Path,
) -> JsonObject:
    """Project one bounded content-addressed snapshot from validated source records."""

    nodes = source.trajectory.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise OperatorCaseSourceError("operator_case_source_invalid")
    checkpoint_by_id = {
        str(checkpoint["checkpoint_id"]): checkpoint for checkpoint in source.checkpoints
    }
    checkpoint_order = {
        str(checkpoint["checkpoint_id"]): index
        for index, checkpoint in enumerate(source.checkpoints)
    }
    timeline: list[JsonObject] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            raise OperatorCaseSourceError("operator_case_source_invalid")
        source_kind = str(node.get("source_kind"))
        source_id = str(node.get("source_id"))
        checkpoint = None
        prior_checkpoint = None
        if source_kind == "workflow_checkpoint":
            checkpoint_id = source_id.split(":", 1)[1]
            checkpoint = checkpoint_by_id.get(checkpoint_id)
            if checkpoint is None:
                raise OperatorCaseSourceError("operator_case_checkpoint_detached")
            index = checkpoint_order[checkpoint_id]
            prior_checkpoint = None if index == 0 else source.checkpoints[index - 1]
        semantics = _entry_semantics(
            source_kind,
            checkpoint=checkpoint,
            prior_checkpoint=prior_checkpoint,
        )
        sequence = len(timeline) + 1
        entry_id = operator_case_entry_id(
            sequence=sequence,
            source_kind=source_kind,
            source_id=source_id,
            source_sha256=str(node.get("content_sha256")),
        )
        timeline.append(
            {
                "sequence": sequence,
                "entry_id": entry_id,
                "predecessor_entry_id": None if not timeline else timeline[-1]["entry_id"],
                "phase": SOURCE_PHASE[source_kind],
                "source_kind": source_kind,
                "source_id": source_id,
                "source_sha256": node["content_sha256"],
                "classification": node["classification"],
                "from_state": semantics[0],
                "to_state": semantics[1],
                "observation": semantics[2],
                "result": semantics[3],
                "gate_status": semantics[4],
                "recovery_status": semantics[5],
                "reason_code": semantics[6],
            }
        )

    replay = source.replay_result
    replay_sequence = len(timeline) + 1
    replay_source_id = f"replay_result:{replay['replay_result_id']}"
    replay_entry_id = operator_case_entry_id(
        sequence=replay_sequence,
        source_kind="replay_result",
        source_id=replay_source_id,
        source_sha256=str(replay["result_sha256"]),
    )
    replay_semantics = _entry_semantics("replay_result")
    timeline.append(
        {
            "sequence": replay_sequence,
            "entry_id": replay_entry_id,
            "predecessor_entry_id": timeline[-1]["entry_id"],
            "phase": "replay",
            "source_kind": "replay_result",
            "source_id": replay_source_id,
            "source_sha256": replay["result_sha256"],
            "classification": "redacted",
            "from_state": None,
            "to_state": None,
            "observation": replay_semantics[2],
            "result": replay_semantics[3],
            "gate_status": replay_semantics[4],
            "recovery_status": replay_semantics[5],
            "reason_code": replay_semantics[6],
        }
    )

    source_kinds = [str(entry["source_kind"]) for entry in timeline]
    snapshot: JsonObject = {
        "schema_id": OPERATOR_CASE_SNAPSHOT_SCHEMA_ID,
        "schema_version": "v1",
        "operator_case_snapshot_id": "",
        "tenant_id": TENANT_ID,
        "fixture_id": FIXTURE_ID,
        "fixture_source_path": FIXTURE_SOURCE_PATH,
        "fixture_sha256": source.fixture_sha256,
        "case": {
            "case_id": source.case_projection["case_id"],
            "case_revision_id": source.case_projection["latest_case_revision_id"],
            "revision": source.case_projection["latest_revision"],
            "workflow_id": source.workflow_projection["workflow_id"],
            "workflow_version": source.workflow_projection["workflow_version"],
            "latest_checkpoint_id": source.workflow_projection["latest_checkpoint_id"],
        },
        "source_report": {
            "report_id": source.evidence_report["report_id"],
            "report_sha256": source.evidence_report["content_sha256"],
            "report_profile_id": source.evidence_report["report_profile_id"],
            "retained_report_path": RETAINED_REPORT_PATH,
        },
        "evidence": {
            "trajectory_id": source.trajectory["trajectory_id"],
            "root_sha256": source.trajectory["root_sha256"],
            "timeline_source_sha256": hashlib.sha256(
                json.dumps(
                    [
                        {
                            "source_kind": entry["source_kind"],
                            "source_id": entry["source_id"],
                            "source_sha256": entry["source_sha256"],
                        }
                        for entry in timeline[:-1]
                    ],
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "node_count": len(nodes),
        },
        "replay": {
            "replay_result_id": replay["replay_result_id"],
            "result_sha256": replay["result_sha256"],
            "report_sha256": replay["report_sha256"],
            "recorded_root_sha256": replay["recorded_root_sha256"],
            "replayed_root_sha256": replay["replayed_root_sha256"],
            "mode": replay["mode"],
            "verification_outcome": replay["verification_outcome"],
        },
        "current_state": "DELIVERY_RECORDED",
        "current_state_label": "DELIVERY_RECORDED (fixture-local)",
        "counts": {
            "timeline_entry_count": len(timeline),
            "case_event_count": len(source.events),
            "case_revision_count": len(source.revisions),
            "workflow_checkpoint_count": len(source.checkpoints),
            "agent_step_count": len(source.investigation["agent_steps"]),
            "tool_result_count": len(source.investigation["tool_evidence"]),
            "local_ticket_effect_count": int(source.source_counts["side_effect_completions"]),
            "fixture_delivery_effect_count": source_kinds.count("delivery_completion"),
            "evidence_node_count": len(nodes),
            "replay_result_count": 1,
        },
        "capabilities": {
            "offline": True,
            "synthetic": True,
            "replay_verification_only": True,
            "fixture_local_delivery": True,
            "network": False,
            "model": False,
            "live_provider": False,
            "external_write": False,
            "customer_receipt": False,
            "customer_resolution": False,
            "case_completion": False,
            "approval_authority": False,
            "workflow_authority": False,
            "retry_authority": False,
        },
        "timeline": timeline,
        "snapshot_sha256": "",
    }
    finalized = finalize_operator_case_snapshot(snapshot)
    validate_operator_case_snapshot(finalized, root)
    return finalized
