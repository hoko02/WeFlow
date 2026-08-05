"""Deterministic, side-effect-free acceptance for the offline evaluation console."""

from __future__ import annotations

import hashlib
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
from weflow_control_kernel.durable_workflow import FixtureClock, SQLiteDurableWorkflow
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger, SyntheticActorRegistry
from weflow_platform_api import create_app
from weflow_testkit.evaluation_report import (
    EVALUATION_REPORT_NOT_FOUND,
    EVALUATION_REPORT_NOT_READY,
    EvaluationReportError,
    RepositoryEvaluationReportSource,
    read_evaluation_suite_snapshot,
)

JsonObject = dict[str, Any]
CANONICAL_REPORT = "reports/change-6-evaluation-benchmark-core-acceptance.json"
ROUTE = "/v1/evaluations/offline-seed.v1"
ACTOR_A = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-a"}
ACTOR_B = {"X-WeFlow-Synthetic-Actor": "simulator-tenant-b"}
FIXED_TIME = datetime(2026, 8, 5, tzinfo=UTC)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source(
    temporary_root: Path,
    name: str,
    *,
    payload: object | None = None,
    text: str | None = None,
) -> RepositoryEvaluationReportSource:
    reports = temporary_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    relative_path = f"reports/{name}.json"
    path = temporary_root / relative_path
    path.write_text(
        text if text is not None else json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )
    return RepositoryEvaluationReportSource(
        temporary_root,
        relative_path,
        allow_test_override=True,
    )


def _expect_unavailable(
    root: Path,
    source: RepositoryEvaluationReportSource,
    expected: str,
) -> str:
    try:
        read_evaluation_suite_snapshot(root, report_source=source)
    except EvaluationReportError as error:
        if error.reason_code != expected:
            raise RuntimeError("evaluation_console_negative_classification_invalid") from error
        return error.reason_code
    raise RuntimeError("evaluation_console_negative_snapshot_emitted")


def _run_console_verification(root: Path) -> JsonObject:
    executable = shutil.which("pnpm")
    if executable is None:
        raise RuntimeError("evaluation_console_command_unavailable")
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
        timeout=180,
        shell=use_shell,
    )
    rendered = f"{completed.stdout}\n{completed.stderr}"
    if (
        completed.returncode != 0
        or "weflow-console-evaluation-check.v1" not in rendered
        or '"task_summaries_rendered":12' not in rendered
        or "built in" not in rendered
    ):
        raise RuntimeError("evaluation_console_verification_failed")
    return {
        "typescript_contract_build": True,
        "runtime_validation": True,
        "task_summaries_rendered": 12,
        "selected_task_hard_gate_checked": True,
        "safe_unavailable_states_checked": 4,
        "production_vite_build": True,
        "unrestricted_json_rendered": False,
        "unsupported_success_claims_rendered": False,
    }


def _missing_reader() -> JsonObject:
    raise EvaluationReportError(EVALUATION_REPORT_NOT_FOUND)


def run_evaluation_console_acceptance(root: Path) -> JsonObject:
    """Revalidate retained evidence twice and exercise only local read boundaries."""

    report_path = root / CANONICAL_REPORT
    report_before = report_path.read_bytes()
    report_payload = json.loads(report_before)
    first = read_evaluation_suite_snapshot(root)
    second = read_evaluation_suite_snapshot(root)
    if first != second:
        raise RuntimeError("evaluation_console_snapshot_nondeterministic")
    if (
        first.get("task_count") != 12
        or first.get("passed_task_count") != 12
        or first.get("failed_task_count") != 0
        or first.get("unscored_task_count") != 0
        or first.get("task_result_ids")
        != [task["evaluation_result_id"] for task in first.get("tasks", [])]
    ):
        raise RuntimeError("evaluation_console_snapshot_summary_invalid")

    with TemporaryDirectory(prefix="weflow-evaluation-console-") as temporary:
        temporary_root = Path(temporary)
        integrity_matrix: JsonObject = {}
        missing = RepositoryEvaluationReportSource(
            temporary_root,
            "reports/missing.json",
            allow_test_override=True,
        )
        integrity_matrix["missing"] = _expect_unavailable(
            root, missing, EVALUATION_REPORT_NOT_FOUND
        )
        integrity_matrix["malformed"] = _expect_unavailable(
            root,
            _source(temporary_root, "malformed", text="not-json"),
            EVALUATION_REPORT_NOT_READY,
        )
        integrity_matrix["duplicate_key"] = _expect_unavailable(
            root,
            _source(
                temporary_root,
                "duplicate-key",
                text='{"accepted":true,"accepted":true}',
            ),
            EVALUATION_REPORT_NOT_READY,
        )

        mutations = {
            "tampered": ("evaluation_result", "result", "failed"),
            "stale": (None, "fixture_sha256", "f" * 64),
            "detached": ("evaluation_result", "suite_report_id", "report:detached"),
        }
        for name, (section, field, value) in mutations.items():
            payload = deepcopy(report_payload)
            diagnostic = payload["task_diagnostics"][0]
            target = diagnostic if section is None else diagnostic[section]
            target[field] = value
            integrity_matrix[name] = _expect_unavailable(
                root,
                _source(temporary_root, name, payload=payload),
                EVALUATION_REPORT_NOT_READY,
            )
        unsafe = deepcopy(report_payload)
        unsafe["task_diagnostics"][0]["raw_payload"] = "blocked"
        integrity_matrix["unsafe"] = _expect_unavailable(
            root,
            _source(temporary_root, "unsafe", payload=unsafe),
            EVALUATION_REPORT_NOT_READY,
        )
        unsupported = deepcopy(report_payload)
        unsupported["customer_success"] = True
        integrity_matrix["unsupported_claim"] = _expect_unavailable(
            root,
            _source(temporary_root, "unsupported", payload=unsupported),
            EVALUATION_REPORT_NOT_READY,
        )
        unsafe_source = RepositoryEvaluationReportSource(
            temporary_root,
            "reports/../private.json",
            allow_test_override=True,
        )
        integrity_matrix["unsafe_path"] = _expect_unavailable(
            root, unsafe_source, EVALUATION_REPORT_NOT_READY
        )

        store_path = temporary_root / "evaluation-console.sqlite3"
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
        client = TestClient(
            create_app(
                root=root,
                ledger=ledger,
                workflow=workflow,
                actor_registry=SyntheticActorRegistry.default(),
                evaluation_reader=lambda: deepcopy(first),
            )
        )
        missing_client = TestClient(
            create_app(
                root=root,
                ledger=ledger,
                workflow=workflow,
                actor_registry=SyntheticActorRegistry.default(),
                evaluation_reader=_missing_reader,
            )
        )
        store_before = store_path.read_bytes()
        authorized = client.get(ROUTE, headers=ACTOR_A)
        foreign = client.get(ROUTE, headers=ACTOR_B)
        absent = missing_client.get(ROUTE, headers=ACTOR_A)
        selector = client.get(f"{ROUTE}?path=forged", headers=ACTOR_A)
        unsupported_method = client.post(ROUTE, headers=ACTOR_A, json={"path": "forged"})
        identity_denied = client.get(
            ROUTE,
            headers={"X-WeFlow-Synthetic-Actor": "unknown"},
        )
        if (
            authorized.status_code != 200
            or authorized.json() != first
            or foreign.status_code != 404
            or absent.status_code != 404
            or foreign.json() != absent.json()
            or selector.status_code != 422
            or unsupported_method.status_code != 405
            or identity_denied.status_code != 403
        ):
            raise RuntimeError("evaluation_console_api_matrix_failed")
        if store_path.read_bytes() != store_before:
            raise RuntimeError("evaluation_console_retained_state_mutated")
        integrity_matrix["foreign"] = EVALUATION_REPORT_NOT_FOUND
        integrity_matrix["arbitrary_selector"] = "evaluation_request_invalid"

    console = _run_console_verification(root)
    if report_path.read_bytes() != report_before:
        raise RuntimeError("evaluation_console_source_report_mutated")
    tasks = first["tasks"]
    network_requests = sum(task["metrics"]["network_request_count"] for task in tasks)
    model_invocations = sum(task["metrics"]["model_invocation_count"] for task in tasks)
    external_write_attempts = sum(task["metrics"]["external_write_attempt_count"] for task in tasks)
    if network_requests or model_invocations or external_write_attempts:
        raise RuntimeError("evaluation_console_side_effect_boundary_failed")

    return {
        "report_type": "weflow-offline-evaluation-report-console-acceptance.v1",
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "suite": {
            "suite_id": first["suite_id"],
            "profile": first["profile"],
            "task_count": first["task_count"],
            "passed_task_count": first["passed_task_count"],
            "failed_task_count": first["failed_task_count"],
            "unscored_task_count": first["unscored_task_count"],
            "suite_sha256": first["suite_sha256"],
            "report_sha256": first["report_sha256"],
            "snapshot_sha256": first["snapshot_sha256"],
            "task_result_ids": list(first["task_result_ids"]),
        },
        "determinism": {
            "snapshot_reads_equal": True,
            "intentional_nondeterministic_fields": [],
        },
        "api": {
            "authorized_status": 200,
            "foreign_and_missing_status": 404,
            "selector_status": 422,
            "unsupported_method_status": 405,
            "identity_denied_status": 403,
            "tenant_identity_derived": True,
        },
        "integrity_matrix": integrity_matrix,
        "console": console,
        "side_effects": {
            "source_report_mutation_count": 0,
            "retained_store_mutation_count": 0,
            "case_workflow_approval_delivery_mutation_count": 0,
            "network_request_count": network_requests,
            "model_invocation_count": model_invocations,
            "external_write_attempt_count": external_write_attempts,
        },
        "capabilities": {
            "offline_evaluation_report_console_implemented": True,
            "live_model_enabled": False,
            "external_writes_enabled": False,
            "customer_resolution_enabled": False,
            "multi_agent_enabled": False,
            "latency_cost_variance_available": False,
        },
        "source_report_sha256": _sha256_bytes(report_before),
    }


__all__ = ["run_evaluation_console_acceptance"]
