"""Read-only canonical report source for the fixed offline Operator Case."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from weflow_contracts import ContractValidationError, validate_operator_case_snapshot

JsonObject = dict[str, Any]
CANONICAL_OPERATOR_CASE_REPORT_PATH: Final = (
    "reports/add-offline-operator-case-timeline-acceptance.json"
)
OPERATOR_CASE_NOT_FOUND: Final = "operator_case_not_found"
OPERATOR_CASE_NOT_READY: Final = "operator_case_not_ready"

_ENVELOPE_KEYS = {
    "accepted",
    "capabilities",
    "determinism",
    "docker_required",
    "model_credentials_required",
    "negative_matrix",
    "network_required",
    "offline",
    "operator_case_snapshot",
    "report_type",
    "side_effect_counts",
}
_EXPECTED_CAPABILITIES = {
    "offline_operator_case_timeline_implemented": True,
    "fixture_local_delivery_only": True,
    "replay_verification_only": True,
    "live_provider_enabled": False,
    "external_writes_enabled": False,
    "customer_receipt_enabled": False,
    "customer_resolution_enabled": False,
    "business_workflow_complete": False,
    "multi_agent_enabled": False,
}
_ZERO_COUNT_KEYS = {
    "default_store_mutation_count",
    "source_report_mutation_count",
    "duplicate_natural_identity_count",
    "duplicate_idempotency_key_count",
    "network_request_count",
    "model_invocation_count",
    "provider_initialization_count",
    "external_write_attempt_count",
    "unauthorized_effect_count",
}
_FORBIDDEN_KEYS = {
    "adapter_payload",
    "caller_authority",
    "caller_role",
    "credential",
    "customer_resolved",
    "customer_success",
    "private_prompt",
    "provider_acknowledged",
    "provider_token",
    "raw_message",
    "raw_payload",
    "stack",
    "tool_output",
    "traceback",
}


class OperatorCaseReportError(ValueError):
    """Allowlisted unavailable state with no source value or path disclosure."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _safe_report_path(relative_path: object) -> PurePosixPath:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
    pure = PurePosixPath(relative_path)
    if (
        pure.is_absolute()
        or not pure.parts
        or pure.parts[0] != "reports"
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
    return pure


@dataclass(frozen=True)
class RepositoryOperatorCaseReportSource:
    """Repository-bounded report reader; alternate reports require explicit test opt-in."""

    root: Path
    relative_path: str = CANONICAL_OPERATOR_CASE_REPORT_PATH
    allow_test_override: bool = False

    def read_text(self) -> str:
        pure = _safe_report_path(self.relative_path)
        if (
            not self.allow_test_override
            and pure.as_posix() != CANONICAL_OPERATOR_CASE_REPORT_PATH
        ):
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
        reports_root = (self.root / "reports").resolve()
        path = (self.root / Path(*pure.parts)).resolve()
        try:
            path.relative_to(reports_root)
        except ValueError as error:
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY) from error
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_FOUND) from error
        except (OSError, UnicodeError) as error:
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY) from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    loaded: JsonObject = {}
    for key, value in pairs:
        if key in loaded:
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
        loaded[key] = value
    return loaded


def _parse_report(text: str) -> JsonObject:
    try:
        loaded = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except OperatorCaseReportError:
        raise
    except (json.JSONDecodeError, TypeError, UnicodeError) as error:
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY) from error
    if not isinstance(loaded, dict):
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
    return loaded


def _contains_unsafe_field(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized.startswith("raw_") or normalized in _FORBIDDEN_KEYS:
                return True
            if _contains_unsafe_field(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_unsafe_field(item) for item in value)
    return False


def _validate_acceptance_envelope(report: JsonObject) -> JsonObject:
    if set(report) != _ENVELOPE_KEYS or _contains_unsafe_field(report):
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
    counts = report.get("side_effect_counts")
    negative_matrix = report.get("negative_matrix")
    snapshot = report.get("operator_case_snapshot")
    if (
        report.get("report_type")
        != "weflow-offline-operator-case-timeline-acceptance.v1"
        or report.get("accepted") is not True
        or report.get("offline") is not True
        or report.get("docker_required") is not False
        or report.get("network_required") is not False
        or report.get("model_credentials_required") is not False
        or report.get("capabilities") != _EXPECTED_CAPABILITIES
        or report.get("determinism")
        != {
            "repeated_baseline_equal": True,
            "intentional_nondeterministic_fields": [],
        }
        or not isinstance(counts, Mapping)
        or set(counts) != _ZERO_COUNT_KEYS
        or any(value != 0 for value in counts.values())
        or not isinstance(negative_matrix, Mapping)
        or not negative_matrix
        or not isinstance(snapshot, Mapping)
    ):
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
    if not all(
        isinstance(name, str)
        and name
        and isinstance(reason, str)
        and reason
        for name, reason in negative_matrix.items()
    ):
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
    return dict(snapshot)


def read_operator_case_snapshot(
    root: Path,
    *,
    report_source: RepositoryOperatorCaseReportSource | None = None,
) -> JsonObject:
    """Return one fully validated snapshot or a stable safe unavailable reason."""

    source = report_source or RepositoryOperatorCaseReportSource(root)
    try:
        acceptance = _parse_report(source.read_text())
        snapshot = _validate_acceptance_envelope(acceptance)
        validate_operator_case_snapshot(snapshot, root)
        if (
            snapshot.get("tenant_id") != "tenant-alpha"
            or snapshot.get("fixture_id") != "api-503-policy-approval-delivery"
            or snapshot.get("source_report", {}).get("retained_report_path")
            != CANONICAL_OPERATOR_CASE_REPORT_PATH
        ):
            raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY)
        return json.loads(json.dumps(snapshot, sort_keys=True, separators=(",", ":")))
    except OperatorCaseReportError:
        raise
    except (ContractValidationError, KeyError, TypeError, ValueError) as error:
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_READY) from error
