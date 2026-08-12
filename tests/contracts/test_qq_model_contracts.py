from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    evaluation_canonical_sha256,
    validate_payload,
    validate_qq_model_lineage,
    validate_qq_model_workflow_acceptance_report,
    validate_qq_model_workflow_readiness,
    validate_qq_model_workflow_verification,
)

ROOT = Path(__file__).resolve().parents[2]
VALID = json.loads(
    (ROOT / "fixtures/contracts/v1/semantic/qq-model-workflow.json").read_text(encoding="utf-8")
)
INVALID = json.loads(
    (ROOT / "fixtures/contracts/v1/invalid/qq-model-workflow-invalid-payloads.json").read_text(
        encoding="utf-8"
    )
)


def _lineage(fixture: dict[str, dict[str, object]]) -> tuple[dict[str, object], ...]:
    return tuple(
        fixture[name]
        for name in ("request", "context", "budget", "invocation", "binding", "preview", "outcome")
    )


def _rehash(payload: dict[str, object], field: str) -> None:
    payload[field] = evaluation_canonical_sha256(payload, without=field)


def test_every_stage3_fixture_is_closed_and_full_lineage_is_valid() -> None:
    for payload in VALID.values():
        validate_payload(payload, ROOT)
    validate_qq_model_workflow_readiness(VALID["readiness"], ROOT)
    validate_qq_model_lineage(
        request=VALID["request"],
        context=VALID["context"],
        budget=VALID["budget"],
        invocation=VALID["invocation"],
        binding=VALID["binding"],
        preview=VALID["preview"],
        outcome=VALID["outcome"],
        root=ROOT,
    )
    validate_qq_model_workflow_acceptance_report(VALID["report"], ROOT)
    validate_qq_model_workflow_verification(VALID["verification"], ROOT)


def test_unknown_privilege_and_private_content_shapes_fail_closed() -> None:
    for payload in INVALID.values():
        with pytest.raises(ContractValidationError):
            validate_payload(payload, ROOT)


def test_foreign_or_detached_lineage_fails_even_with_valid_self_hash() -> None:
    fixture = copy.deepcopy(VALID)
    fixture["binding"]["tenant_id"] = "tenant-foreign"
    _rehash(fixture["binding"], "binding_sha256")
    with pytest.raises(ContractValidationError, match="lineage_mismatch"):
        validate_qq_model_lineage(
            request=fixture["request"],
            context=fixture["context"],
            budget=fixture["budget"],
            invocation=fixture["invocation"],
            binding=fixture["binding"],
            preview=fixture["preview"],
            outcome=fixture["outcome"],
            root=ROOT,
        )

    fixture = copy.deepcopy(VALID)
    fixture["binding"]["invocation_evidence_sha256"] = "f" * 64
    _rehash(fixture["binding"], "binding_sha256")
    with pytest.raises(ContractValidationError, match="lineage_link_mismatch"):
        validate_qq_model_lineage(
            request=fixture["request"],
            context=fixture["context"],
            budget=fixture["budget"],
            invocation=fixture["invocation"],
            binding=fixture["binding"],
            preview=fixture["preview"],
            outcome=fixture["outcome"],
            root=ROOT,
        )


def test_fake_report_cannot_claim_live_or_customer_success() -> None:
    report = copy.deepcopy(VALID["report"])
    report["live_model_contact_verified"] = True
    _rehash(report, "report_sha256")
    with pytest.raises(ContractValidationError):
        validate_qq_model_workflow_acceptance_report(report, ROOT)

    report = copy.deepcopy(VALID["report"])
    report["customer_receipt_verified"] = True
    _rehash(report, "report_sha256")
    with pytest.raises(ContractValidationError):
        validate_qq_model_workflow_acceptance_report(report, ROOT)


def test_budget_missing_metrics_or_overuse_is_rejected() -> None:
    fixture = copy.deepcopy(VALID)
    del fixture["budget"]["used"]["estimated_cost"]
    _rehash(fixture["budget"], "budget_sha256")
    with pytest.raises(ContractValidationError):
        validate_payload(fixture["budget"], ROOT)

    fixture = copy.deepcopy(VALID)
    fixture["budget"]["used"]["provider_calls"] = 7
    _rehash(fixture["budget"], "budget_sha256")
    with pytest.raises(ContractValidationError, match="budget_exceeded"):
        validate_qq_model_lineage(
            request=fixture["request"],
            context=fixture["context"],
            budget=fixture["budget"],
            invocation=fixture["invocation"],
            binding=fixture["binding"],
            preview=fixture["preview"],
            outcome=fixture["outcome"],
            root=ROOT,
        )
