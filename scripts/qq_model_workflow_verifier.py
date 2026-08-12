"""Independent no-network verifier for bounded QQ plus model evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weflow_contracts import (
    QQ_MODEL_WORKFLOW_VERIFICATION_SCHEMA_ID,
    evaluation_canonical_sha256,
    qq_model_workflow_report_sha256,
    validate_payload,
    validate_qq_handler_approval_chain,
    validate_qq_handler_passive_reply_chain,
    validate_qq_model_lineage,
    validate_qq_model_workflow_acceptance_report,
    validate_qq_model_workflow_verification,
)
from weflow_control_kernel.qq_model import (
    QQ_STAGE3_MODEL_CAPABILITIES,
    QQ_STAGE3_QQ_CAPABILITIES,
)
from weflow_testkit.qq_model_profile import (
    load_qq_model_profile,
    qq_model_id_sha256,
    qq_model_provider_profile_sha256,
)

JsonObject = dict[str, Any]


class QQModelVerificationError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _require(value: bool, reason_code: str) -> None:
    if not value:
        raise QQModelVerificationError(reason_code)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_qq_model_workflow_evidence(
    *,
    root: Path,
    report: Mapping[str, Any],
    evidence: Mapping[str, Any],
    expected_mode: str,
    now: datetime | None = None,
) -> JsonObject:
    """Revalidate every durable content-free link without credentials or network."""

    validate_qq_model_workflow_acceptance_report(report, root)
    _require(report["mode"] == expected_mode, "stage3_report_mode_mismatch")
    loaded = load_qq_model_profile(root, now=now or datetime.now(UTC))
    profile = loaded.profile
    _require(
        report["stage3_profile_sha256"] == profile["profile_sha256"],
        "stage3_report_profile_mismatch",
    )
    _require(
        report["qq_capability_profile_hash"] == _hash("|".join(QQ_STAGE3_QQ_CAPABILITIES)),
        "stage3_report_qq_capabilities_mismatch",
    )
    _require(
        report["model_capability_profile_hash"] == _hash("|".join(QQ_STAGE3_MODEL_CAPABILITIES)),
        "stage3_report_model_capabilities_mismatch",
    )
    request = evidence["request"]
    context = evidence["context"]
    budget = evidence["budget"]
    invocation = evidence["invocation"]
    binding = evidence["binding"]
    preview = evidence["preview"]
    outcome = evidence["outcome"]
    validate_qq_model_lineage(
        request=request,
        context=context,
        budget=budget,
        invocation=invocation,
        binding=binding,
        preview=preview,
        outcome=outcome,
        root=root,
    )
    expected_sources = [item["sha256"] for item in profile["source_references"]]
    _require(
        context["source_profile_sha256"] == _canonical(profile["source_references"])
        and context["ordered_source_sha256s"] == expected_sources,
        "stage3_context_source_profile_mismatch",
    )
    _require(
        context["prompt_template_sha256"] == profile["prompt_reference"]["sha256"]
        and context["policy_profile_sha256"] == profile["policy_reference"]["sha256"]
        and context["budget_profile_sha256"] == profile["budget_reference"]["sha256"]
        and context["price_profile_sha256"] == profile["price_reference"]["profile_sha256"],
        "stage3_context_reviewed_profile_mismatch",
    )
    _require(
        context["provider_profile_sha256"] == qq_model_provider_profile_sha256(profile)
        and invocation["provider_profile_sha256"] == qq_model_provider_profile_sha256(profile)
        and invocation["model_id_sha256"] == qq_model_id_sha256(profile),
        "stage3_provider_binding_mismatch",
    )
    invocations = evidence["invocations"]
    _require(
        isinstance(invocations, list)
        and len(invocations) == report["model_invocation_count"]
        and invocation == invocations[-1],
        "stage3_invocation_count_or_terminal_mismatch",
    )
    for item in invocations:
        validate_payload(item, root)
        _require(
            item["assist_request_id"] == request["assist_request_id"]
            and item["context_sha256"] == context["context_sha256"],
            "stage3_invocation_lineage_mismatch",
        )
    action = evidence["action"]
    validate_payload(action, root)
    _require(
        action["tenant_id"] == request["tenant_id"]
        and action["case_id"] == request["case_id"]
        and action["context_manifest_id"] == context["context_id"]
        and action["action_sha256"] == binding["action_sha256"]
        and action["action_type"] == "response_candidate",
        "stage3_action_lineage_mismatch",
    )
    tools = evidence["tool_results"]
    _require(
        isinstance(tools, list)
        and len(tools) == 3
        and [item["tool_name"] for item in tools] == ["crm", "monitoring", "knowledge"]
        and [item["content_sha256"] for item in tools] == binding["ordered_evidence_sha256s"],
        "stage3_tool_lineage_mismatch",
    )
    for item in tools:
        validate_payload(item, root)
        _require(
            item["tenant_id"] == request["tenant_id"]
            and item["case_id"] == request["case_id"]
            and item["context_manifest_id"] == context["context_id"],
            "stage3_tool_scope_mismatch",
        )
    validate_qq_handler_approval_chain(
        evidence["approval_request"], [evidence["approval_decision"]], root
    )
    validate_qq_handler_passive_reply_chain(
        evidence["final_intent"], [evidence["final_result"]], root
    )
    _require(
        evidence["approval_request"]["approval_request_id"] == binding["approval_request_id"]
        and evidence["approval_decision"]["candidate_revision_id"]
        == binding["candidate_revision_id"]
        and evidence["final_intent"]["content_artifact_id"] == binding["candidate_artifact_id"],
        "stage3_approval_or_effect_lineage_mismatch",
    )
    _require(
        report["acknowledgement_count"] == evidence["acknowledgement_count"] == 1
        and report["notification_attempt_count"] == evidence["notification_count"] == 1,
        "stage3_qq_effect_count_mismatch",
    )
    _require(
        report["artifact_deletion_count"] == evidence["deletion_count"]
        and evidence["deletion_count"] >= 2
        and evidence["lifecycle_status"] == "DELETED",
        "stage3_deletion_evidence_incomplete",
    )
    used = budget["used"]
    usage = report["model_usage"]
    _require(
        all(
            usage[field] == used[field]
            for field in (
                "provider_calls",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "estimated_cost",
            )
        ),
        "stage3_usage_evidence_mismatch",
    )
    verified_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    verification = {
        "schema_id": QQ_MODEL_WORKFLOW_VERIFICATION_SCHEMA_ID,
        "schema_version": "v1",
        "report_type": "weflow-qq-model-workflow-verification.v1",
        "verification_id": "qqmwv_"
        + _hash(f"{report['report_id']}:{report['report_sha256']}")[:32],
        "report_id": report["report_id"],
        "report_sha256": report["report_sha256"],
        "mode": expected_mode,
        "verified": True,
        "reason_code": "offline_evidence_verified"
        if expected_mode == "offline-fake"
        else "integrated_live_evidence_verified",
        "network_contacted": False,
        "credential_required": False,
        "external_write_attempted": False,
        "model_invocation": False,
        "verified_at": verified_at,
        "verification_sha256": "0" * 64,
    }
    verification["verification_sha256"] = evaluation_canonical_sha256(
        verification, without="verification_sha256"
    )
    validate_qq_model_workflow_verification(verification, root)
    return verification


def verify_published_qq_model_reports(
    report: Mapping[str, Any],
    verification: Mapping[str, Any],
    *,
    expected_mode: str,
    root: Path,
) -> None:
    """Recheck two content-free published artifacts without network or credentials."""

    validate_qq_model_workflow_acceptance_report(report, root)
    validate_qq_model_workflow_verification(verification, root)
    if report.get("mode") != expected_mode or verification.get("mode") != expected_mode:
        raise QQModelVerificationError("stage3_published_mode_mismatch")
    expected_report_hash = qq_model_workflow_report_sha256(report)
    if report.get("report_sha256") != expected_report_hash:
        raise QQModelVerificationError("stage3_published_report_hash_mismatch")
    if (
        verification.get("report_id") != report.get("report_id")
        or verification.get("report_sha256") != expected_report_hash
        or verification.get("verified") is not True
        or verification.get("network_contacted") is not False
        or verification.get("credential_required") is not False
        or verification.get("external_write_attempted") is not False
        or verification.get("model_invocation") is not False
    ):
        raise QQModelVerificationError("stage3_published_verification_mismatch")
    verification_hash = evaluation_canonical_sha256(verification, without="verification_sha256")
    if verification.get("verification_sha256") != verification_hash:
        raise QQModelVerificationError("stage3_published_verification_hash_mismatch")


__all__ = [
    "QQModelVerificationError",
    "verify_published_qq_model_reports",
    "verify_qq_model_workflow_evidence",
]
