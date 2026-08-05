"""Closed, source-linked contract for the fixed offline Operator Case view."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .validation import ContractValidationError, validate_payload

OPERATOR_CASE_SNAPSHOT_SCHEMA_ID = (
    "https://weflow.local/contracts/v1/operator-case-snapshot.schema.json"
)

PHASE_ORDER = (
    "intake",
    "case",
    "workflow",
    "investigation",
    "tools",
    "verification",
    "policy",
    "approval",
    "delivery",
    "replay",
)

SOURCE_PHASE = {
    "accepted_intake": "intake",
    "case_revision": "case",
    "case_event": "case",
    "workflow_activation": "workflow",
    "workflow_checkpoint": "workflow",
    "context_manifest": "investigation",
    "agent_step": "investigation",
    "tool_request": "tools",
    "tool_result": "tools",
    "evidence": "tools",
    "response_candidate": "verification",
    "verifier_outcome": "verification",
    "policy_activation": "policy",
    "capability_grant": "policy",
    "policy_decision": "policy",
    "authorization_binding": "policy",
    "approval_request": "approval",
    "approval_decision": "approval",
    "delivery_intent": "delivery",
    "delivery_completion": "delivery",
    "replay_result": "replay",
}

REQUIRED_SOURCE_KINDS = frozenset(SOURCE_PHASE)
HARD_GATE_SOURCE_KINDS = frozenset(
    {
        "verifier_outcome",
        "capability_grant",
        "policy_decision",
        "authorization_binding",
        "approval_decision",
    }
)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def operator_case_entry_id(
    *,
    sequence: int,
    source_kind: str,
    source_id: str,
    source_sha256: str,
) -> str:
    """Return the stable bounded identity for one source-linked entry."""

    digest = _sha256(
        {
            "sequence": sequence,
            "source_kind": source_kind,
            "source_id": source_id,
            "source_sha256": source_sha256,
        }
    )
    return f"operator_entry_{digest[:32]}"


def operator_case_snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    """Hash snapshot content without its two derived content-addressed identities."""

    material = {
        key: value
        for key, value in snapshot.items()
        if key not in {"operator_case_snapshot_id", "snapshot_sha256"}
    }
    return _sha256(material)


def finalize_operator_case_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with canonical snapshot hash and identity populated."""

    finalized = dict(snapshot)
    digest = operator_case_snapshot_sha256(finalized)
    finalized["operator_case_snapshot_id"] = f"operator_case_snapshot_{digest}"
    finalized["snapshot_sha256"] = digest
    return finalized


def _invalid(reason: str) -> None:
    raise ContractValidationError("operator-case-snapshot", reason)


def validate_operator_case_snapshot(
    snapshot: Mapping[str, Any], root: Any = None
) -> None:
    """Validate closed shape, causal order, counts, roots, and no-authority truth."""

    validate_payload(snapshot, root)
    if snapshot.get("schema_id") != OPERATOR_CASE_SNAPSHOT_SCHEMA_ID:
        _invalid("schema_identity_invalid")

    digest = operator_case_snapshot_sha256(snapshot)
    if snapshot.get("snapshot_sha256") != digest:
        _invalid("snapshot_sha256_mismatch")
    if snapshot.get("operator_case_snapshot_id") != f"operator_case_snapshot_{digest}":
        _invalid("snapshot_identity_mismatch")

    case = snapshot.get("case")
    source_report = snapshot.get("source_report")
    evidence = snapshot.get("evidence")
    replay = snapshot.get("replay")
    counts = snapshot.get("counts")
    timeline = snapshot.get("timeline")
    if not all(
        isinstance(item, Mapping)
        for item in (case, source_report, evidence, replay, counts)
    ) or not isinstance(timeline, list):
        _invalid("snapshot_sections_invalid")

    if (
        source_report.get("report_sha256") != replay.get("report_sha256")
        or evidence.get("root_sha256") != replay.get("recorded_root_sha256")
        or evidence.get("root_sha256") != replay.get("replayed_root_sha256")
    ):
        _invalid("source_root_mismatch")

    entry_ids: list[object] = []
    source_ids: list[object] = []
    source_kinds: list[str] = []
    prior_phase = -1
    prior_entry_id: str | None = None
    for sequence, value in enumerate(timeline, start=1):
        if not isinstance(value, Mapping):
            _invalid("timeline_entry_invalid")
        source_kind = value.get("source_kind")
        source_id = value.get("source_id")
        source_sha256 = value.get("source_sha256")
        if (
            not isinstance(source_kind, str)
            or source_kind not in SOURCE_PHASE
            or not isinstance(source_id, str)
            or not isinstance(source_sha256, str)
        ):
            _invalid("timeline_source_invalid")
        if value.get("sequence") != sequence:
            _invalid("timeline_sequence_invalid")
        if value.get("predecessor_entry_id") != prior_entry_id:
            _invalid("timeline_predecessor_invalid")
        if value.get("phase") != SOURCE_PHASE[source_kind]:
            _invalid("timeline_phase_invalid")
        phase = PHASE_ORDER.index(SOURCE_PHASE[source_kind])
        if phase < prior_phase:
            _invalid("timeline_phase_order_invalid")
        prior_phase = phase
        if source_id.split(":", 1)[0] != source_kind:
            _invalid("timeline_source_identity_invalid")
        expected_entry_id = operator_case_entry_id(
            sequence=sequence,
            source_kind=source_kind,
            source_id=source_id,
            source_sha256=source_sha256,
        )
        if value.get("entry_id") != expected_entry_id:
            _invalid("timeline_entry_identity_invalid")
        if source_kind in HARD_GATE_SOURCE_KINDS and value.get("gate_status") != "passed":
            _invalid("hard_gate_precedence_invalid")
        if (
            value.get("gate_status") == "failed"
            or value.get("result") == "blocked"
            or value.get("observation") in {"denied", "stale", "timeout"}
        ):
            _invalid("hard_gate_precedence_invalid")
        if value.get("recovery_status") != "not_required":
            _invalid("canonical_recovery_invalid")
        entry_ids.append(value.get("entry_id"))
        source_ids.append(source_id)
        source_kinds.append(source_kind)
        prior_entry_id = str(value.get("entry_id"))

    if len(entry_ids) != len(set(entry_ids)):
        _invalid("timeline_entry_duplicate")
    if len(source_ids) != len(set(source_ids)):
        _invalid("timeline_source_duplicate")
    if not REQUIRED_SOURCE_KINDS.issubset(source_kinds):
        _invalid("required_source_missing")
    if source_kinds[-1] != "replay_result":
        _invalid("replay_not_terminal")
    source_material = [
        {
            "source_kind": item["source_kind"],
            "source_id": item["source_id"],
            "source_sha256": item["source_sha256"],
        }
        for item in timeline[:-1]
    ]
    if evidence.get("timeline_source_sha256") != _sha256(source_material):
        _invalid("timeline_source_sha256_mismatch")

    expected_counts = {
        "timeline_entry_count": len(timeline),
        "case_event_count": source_kinds.count("accepted_intake")
        + source_kinds.count("case_event"),
        "case_revision_count": source_kinds.count("case_revision"),
        "workflow_checkpoint_count": source_kinds.count("workflow_checkpoint"),
        "agent_step_count": source_kinds.count("agent_step"),
        "tool_result_count": source_kinds.count("tool_result"),
        "fixture_delivery_effect_count": source_kinds.count("delivery_completion"),
        "evidence_node_count": len(timeline) - 1,
        "replay_result_count": source_kinds.count("replay_result"),
    }
    for field, expected in expected_counts.items():
        if counts.get(field) != expected:
            _invalid(f"{field}_mismatch")

    expected_revision_source = f"case_revision:{case.get('case_revision_id')}"
    expected_checkpoint_source = f"workflow_checkpoint:{case.get('latest_checkpoint_id')}"
    expected_replay_source = f"replay_result:{replay.get('replay_result_id')}"
    if (
        expected_revision_source not in source_ids
        or expected_checkpoint_source not in source_ids
        or source_ids[-1] != expected_replay_source
        or timeline[-1].get("source_sha256") != replay.get("result_sha256")
    ):
        _invalid("case_workflow_replay_link_mismatch")

    verifier_entries = [
        item for item in timeline if item.get("source_kind") == "verifier_outcome"
    ]
    policy_entries = [
        item for item in timeline if item.get("source_kind") == "policy_decision"
    ]
    approval_entries = [
        item for item in timeline if item.get("source_kind") == "approval_decision"
    ]
    delivery_entries = [
        item for item in timeline if item.get("source_kind") == "delivery_completion"
    ]
    if (
        len(verifier_entries) != 1
        or verifier_entries[0].get("observation") != "verified"
        or len(policy_entries) != 1
        or policy_entries[0].get("observation") != "allowed"
        or len(approval_entries) != 1
        or approval_entries[0].get("observation") != "approved"
        or len(delivery_entries) != 1
        or delivery_entries[0].get("observation") != "fixture_local_recorded"
    ):
        _invalid("canonical_gate_summary_invalid")
