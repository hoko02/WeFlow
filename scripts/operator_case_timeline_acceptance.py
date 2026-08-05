"""Offline acceptance for the fixed, source-backed Operator Case timeline."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient
from weflow_business_simulator import (
    OperatorCaseSourceBundle,
    build_operator_case_snapshot,
    run_operator_case_source,
)
from weflow_contracts import validate_operator_case_snapshot
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app
from weflow_testkit import (
    CANONICAL_OPERATOR_CASE_REPORT_PATH,
    OPERATOR_CASE_NOT_FOUND,
    OPERATOR_CASE_NOT_READY,
    OperatorCaseReportError,
    RepositoryOperatorCaseReportSource,
    read_operator_case_snapshot,
)

JsonObject = dict[str, Any]
REPORT_TYPE = "weflow-offline-operator-case-timeline-acceptance.v1"
ROUTE = "/v1/operator/cases/api-503.v1"
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}
FIXED_TIME = datetime(2026, 8, 5, tzinfo=UTC)


def _bytes_or_none(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def _report_inventory(root: Path) -> dict[str, bytes]:
    reports = root / "reports"
    if not reports.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(reports.rglob("*"))
        if path.is_file()
    }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _acceptance_envelope(snapshot: JsonObject, negative_matrix: JsonObject) -> JsonObject:
    return {
        "report_type": REPORT_TYPE,
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "operator_case_snapshot": snapshot,
        "determinism": {
            "repeated_baseline_equal": True,
            "intentional_nondeterministic_fields": [],
        },
        "side_effect_counts": {
            "default_store_mutation_count": 0,
            "source_report_mutation_count": 0,
            "duplicate_natural_identity_count": 0,
            "duplicate_idempotency_key_count": 0,
            "network_request_count": 0,
            "model_invocation_count": 0,
            "provider_initialization_count": 0,
            "external_write_attempt_count": 0,
            "unauthorized_effect_count": 0,
        },
        "negative_matrix": negative_matrix,
        "capabilities": {
            "offline_operator_case_timeline_implemented": True,
            "fixture_local_delivery_only": True,
            "replay_verification_only": True,
            "live_provider_enabled": False,
            "external_writes_enabled": False,
            "customer_receipt_enabled": False,
            "customer_resolution_enabled": False,
            "business_workflow_complete": False,
            "multi_agent_enabled": False,
        },
    }


def _write_test_report(
    temporary_root: Path,
    name: str,
    *,
    payload: object | None = None,
    text: str | None = None,
) -> RepositoryOperatorCaseReportSource:
    reports = temporary_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    relative_path = f"reports/{name}.json"
    (temporary_root / relative_path).write_text(
        text if text is not None else json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )
    return RepositoryOperatorCaseReportSource(
        temporary_root,
        relative_path,
        allow_test_override=True,
    )


def _expect_unavailable(
    root: Path,
    source: RepositoryOperatorCaseReportSource,
    expected: str,
) -> str:
    try:
        read_operator_case_snapshot(root, report_source=source)
    except OperatorCaseReportError as error:
        if error.reason_code != expected:
            raise RuntimeError("operator_case_negative_classification_invalid") from error
        return error.reason_code
    raise RuntimeError("operator_case_negative_partial_snapshot_emitted")


def _timeline_entry(snapshot: JsonObject, source_kind: str) -> JsonObject:
    for value in snapshot["timeline"]:
        if value.get("source_kind") == source_kind:
            return value
    raise RuntimeError("operator_case_acceptance_fixture_invalid")


def _negative_snapshots(snapshot: JsonObject) -> dict[str, JsonObject]:
    mutations: dict[str, JsonObject] = {}

    detached_hash = deepcopy(snapshot)
    _timeline_entry(detached_hash, "tool_result")["source_sha256"] = "f" * 64
    mutations["detached_hash"] = detached_hash

    detached_predecessor = deepcopy(snapshot)
    detached_predecessor["timeline"][1]["predecessor_entry_id"] = "operator_entry_detached"
    mutations["detached_predecessor"] = detached_predecessor

    duplicate_source = deepcopy(snapshot)
    case_events = [
        item for item in duplicate_source["timeline"] if item["source_kind"] == "case_event"
    ]
    case_events[1]["source_id"] = case_events[0]["source_id"]
    mutations["duplicate_source"] = duplicate_source

    out_of_order = deepcopy(snapshot)
    out_of_order["timeline"][0], out_of_order["timeline"][1] = (
        out_of_order["timeline"][1],
        out_of_order["timeline"][0],
    )
    mutations["out_of_order_source"] = out_of_order

    count_mismatch = deepcopy(snapshot)
    count_mismatch["counts"]["timeline_entry_count"] += 1
    mutations["count_mismatch"] = count_mismatch

    stale_approval = deepcopy(snapshot)
    approval = _timeline_entry(stale_approval, "approval_decision")
    approval["observation"] = "stale"
    approval["reason_code"] = "stale_approval"
    mutations["stale_approval"] = stale_approval

    policy_denial = deepcopy(snapshot)
    policy = _timeline_entry(policy_denial, "policy_decision")
    policy["observation"] = "denied"
    policy["result"] = "blocked"
    policy["gate_status"] = "failed"
    policy["reason_code"] = "policy_denied"
    mutations["policy_denial"] = policy_denial

    recovery = deepcopy(snapshot)
    delivery = _timeline_entry(recovery, "delivery_completion")
    delivery["observation"] = "timeout"
    delivery["recovery_status"] = "recovered"
    delivery["reason_code"] = "restart_timeout_duplicate_completion"
    recovery["timeline"].insert(-1, deepcopy(delivery))
    recovery["counts"]["timeline_entry_count"] += 1
    recovery["counts"]["fixture_delivery_effect_count"] += 1
    recovery["counts"]["evidence_node_count"] += 1
    mutations["restart_timeout_duplicate_completion"] = recovery

    customer_success = deepcopy(snapshot)
    customer_success["capabilities"]["customer_resolution"] = True
    mutations["unsupported_customer_success"] = customer_success

    authority = deepcopy(snapshot)
    authority["capabilities"]["approval_authority"] = True
    mutations["unsupported_authority"] = authority
    return mutations


def _assert_source_mapping(snapshot: JsonObject, source: OperatorCaseSourceBundle) -> None:
    expected = [
        (node["source_kind"], node["source_id"], node["content_sha256"])
        for node in source.trajectory["nodes"]
    ]
    expected.append(
        (
            "replay_result",
            f"replay_result:{source.replay_result['replay_result_id']}",
            source.replay_result["result_sha256"],
        )
    )
    actual = [
        (entry["source_kind"], entry["source_id"], entry["source_sha256"])
        for entry in snapshot["timeline"]
    ]
    if actual != expected or len({entry[1] for entry in actual}) != len(actual):
        raise RuntimeError("operator_case_source_mapping_invalid")


def _api_matrix(root: Path, temporary_root: Path, snapshot: JsonObject) -> JsonObject:
    store_path = temporary_root / "operator-case-api.sqlite3"
    ledger = SQLiteCaseLedger(
        store_path,
        clock=FixedClock(FIXED_TIME),
        contract_root=root,
    )
    workflow = SQLiteDurableWorkflow(
        ledger,
        clock=FixtureClock(FIXED_TIME),
        contract_root=root,
    )

    def missing_reader() -> JsonObject:
        raise OperatorCaseReportError(OPERATOR_CASE_NOT_FOUND)

    common = {
        "root": root,
        "ledger": ledger,
        "workflow": workflow,
        "actor_registry": SyntheticActorRegistry.default(),
    }
    client = TestClient(
        create_app(**common, operator_case_reader=lambda: deepcopy(snapshot))
    )
    missing_client = TestClient(create_app(**common, operator_case_reader=missing_reader))
    store_before = store_path.read_bytes()
    authorized = client.get(ROUTE, headers=ACTOR_A)
    foreign = client.get(ROUTE, headers=ACTOR_B)
    missing = missing_client.get(ROUTE, headers=ACTOR_A)
    denied = client.get(ROUTE, headers={"X-WeFlow-Synthetic-Actor": "unknown"})
    selector = client.get(f"{ROUTE}?case=forged", headers=ACTOR_A)
    unsupported_method = client.post(ROUTE, headers=ACTOR_A, json={"case": "forged"})
    if (
        authorized.status_code != 200
        or authorized.json() != snapshot
        or foreign.status_code != 404
        or missing.status_code != 404
        or foreign.json() != missing.json()
        or denied.status_code != 403
        or selector.status_code != 422
        or unsupported_method.status_code != 405
        or store_path.read_bytes() != store_before
    ):
        raise RuntimeError("operator_case_api_matrix_failed")
    validate_operator_case_snapshot(authorized.json(), root)
    return {
        "missing": OPERATOR_CASE_NOT_FOUND,
        "foreign": OPERATOR_CASE_NOT_FOUND,
        "arbitrary_selector": "operator_case_request_invalid",
        "unsupported_method": "method_not_allowed",
    }


def _run_console_verification(root: Path) -> None:
    executable = shutil.which("pnpm")
    if executable is None:
        raise RuntimeError("operator_case_console_command_unavailable")
    command = [executable, "--filter", "@weflow/web-console", "test"]
    use_shell = os.name == "nt" and Path(executable).suffix.lower() in {".bat", ".cmd"}
    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
        shell=use_shell,
    )
    rendered = f"{completed.stdout}\n{completed.stderr}"
    required = (
        "weflow-console-operator-case-check.v1",
        '"timeline_entries_rendered":49',
        '"safe_surface_states_checked":5',
        "built in",
    )
    if completed.returncode != 0 or not all(value in rendered for value in required):
        raise RuntimeError("operator_case_console_verification_failed")


def run_operator_case_timeline_acceptance(root: Path) -> JsonObject:
    """Run two fresh baselines and all bounded read-only negative paths."""

    root = root.resolve()
    canonical_report = root / CANONICAL_OPERATOR_CASE_REPORT_PATH
    default_store = root / ".weflow" / "case-ledger.sqlite3"
    default_before = _bytes_or_none(default_store)
    reports_before = _report_inventory(root)

    with TemporaryDirectory(prefix="weflow-operator-case-") as temporary:
        temporary_root = Path(temporary)
        first_source = run_operator_case_source(root, temporary_root / "first.sqlite3")
        second_source = run_operator_case_source(root, temporary_root / "second.sqlite3")
        first = build_operator_case_snapshot(first_source, root)
        second = build_operator_case_snapshot(second_source, root)
        validate_operator_case_snapshot(first, root)
        validate_operator_case_snapshot(second, root)
        if _canonical_bytes(first) != _canonical_bytes(second):
            raise RuntimeError("operator_case_baseline_nondeterministic")
        _assert_source_mapping(first, first_source)
        _assert_source_mapping(second, second_source)
        if (
            first_source.duplicate_natural_identity_count
            or second_source.duplicate_natural_identity_count
            or first_source.duplicate_idempotency_key_count
            or second_source.duplicate_idempotency_key_count
        ):
            raise RuntimeError("operator_case_effect_identity_duplicate")

        negative_matrix = _api_matrix(root, temporary_root, first)
        missing_source = RepositoryOperatorCaseReportSource(
            temporary_root,
            "reports/absent.json",
            allow_test_override=True,
        )
        negative_matrix["missing"] = _expect_unavailable(
            root, missing_source, OPERATOR_CASE_NOT_FOUND
        )
        negative_matrix["malformed"] = _expect_unavailable(
            root,
            _write_test_report(temporary_root, "malformed", text="{"),
            OPERATOR_CASE_NOT_READY,
        )
        negative_matrix["duplicate_key"] = _expect_unavailable(
            root,
            _write_test_report(
                temporary_root,
                "duplicate-key",
                text='{"accepted":true,"accepted":true}',
            ),
            OPERATOR_CASE_NOT_READY,
        )
        unsafe_path = RepositoryOperatorCaseReportSource(
            temporary_root,
            "reports/../private.json",
            allow_test_override=True,
        )
        negative_matrix["unsafe_path"] = _expect_unavailable(
            root, unsafe_path, OPERATOR_CASE_NOT_READY
        )
        unsafe_envelope = _acceptance_envelope(first, {"seed": "blocked"})
        unsafe_envelope["raw_payload"] = "blocked"
        negative_matrix["unsafe_field"] = _expect_unavailable(
            root,
            _write_test_report(temporary_root, "unsafe-field", payload=unsafe_envelope),
            OPERATOR_CASE_NOT_READY,
        )
        for name, mutation in _negative_snapshots(first).items():
            negative_matrix[name] = _expect_unavailable(
                root,
                _write_test_report(
                    temporary_root,
                    name,
                    payload=_acceptance_envelope(mutation, {"seed": "not_ready"}),
                ),
                OPERATOR_CASE_NOT_READY,
            )

        candidate = _acceptance_envelope(first, negative_matrix)
        validated = read_operator_case_snapshot(
            root,
            report_source=_write_test_report(
                temporary_root,
                "candidate",
                payload=candidate,
            ),
        )
        if validated != first:
            raise RuntimeError("operator_case_canonical_reader_mismatch")
        _run_console_verification(root)

    if _bytes_or_none(default_store) != default_before:
        raise RuntimeError("operator_case_default_store_mutated")
    if _report_inventory(root) != reports_before:
        raise RuntimeError("operator_case_retained_report_mutated")
    if _bytes_or_none(canonical_report) != reports_before.get(
        CANONICAL_OPERATOR_CASE_REPORT_PATH
    ):
        raise RuntimeError("operator_case_prior_report_mutated")
    return candidate


def publish_operator_case_timeline_acceptance(root: Path, report: JsonObject) -> Path:
    """Validate a pending report and atomically replace only the canonical path."""

    root = root.resolve()
    output = root / CANONICAL_OPERATOR_CASE_REPORT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_name(f".{output.name}.{os.getpid()}.pending")
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        pending.write_text(serialized, encoding="utf-8")
        source = RepositoryOperatorCaseReportSource(
            root,
            pending.relative_to(root).as_posix(),
            allow_test_override=True,
        )
        read_operator_case_snapshot(root, report_source=source)
        os.replace(pending, output)
    finally:
        pending.unlink(missing_ok=True)
    return output


__all__ = [
    "publish_operator_case_timeline_acceptance",
    "run_operator_case_timeline_acceptance",
]
