#!/usr/bin/env python
"""Cross-platform command surface for the WeFlow Change 4 local harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
CONTROL_KERNEL_SRC = ROOT / "packages" / "python" / "weflow-control-kernel" / "src"
CONTRACTS_SRC = ROOT / "packages" / "python" / "weflow-contracts" / "src"
TESTKIT_SRC = ROOT / "packages" / "python" / "weflow-testkit" / "src"
BUSINESS_SIMULATOR_SRC = ROOT / "apps" / "business-simulator" / "src"
AGENT_RUNTIME_SRC = ROOT / "apps" / "agent-runtime" / "src"
CONTROL_WORKER_SRC = ROOT / "apps" / "control-worker" / "src"
EXTENSION_SDK_SRC = ROOT / "packages" / "python" / "weflow-extension-sdk" / "src"
PLATFORM_API_SRC = ROOT / "apps" / "platform-api" / "src"
for source_directory in (
    SCRIPTS_DIRECTORY,
    CONTROL_KERNEL_SRC,
    CONTRACTS_SRC,
    TESTKIT_SRC,
    BUSINESS_SIMULATOR_SRC,
    AGENT_RUNTIME_SRC,
    CONTROL_WORKER_SRC,
    EXTENSION_SDK_SRC,
    PLATFORM_API_SRC,
):
    if str(source_directory) not in sys.path:
        sys.path.insert(0, str(source_directory))

from processes import runtime_report, start_services, stop_services  # noqa: E402
from weflow_control_kernel.config import ConfigurationDenied, load_config  # noqa: E402
from weflow_control_kernel.qq_sandbox import (  # noqa: E402
    QQActivationDenied,
    QQSandboxConfig,
    QQTransportError,
    reject_qq_configuration_for_ordinary_command,
)

REQUIRED_TOOLS = ("uv", "node", "pnpm", "git")


def _tool_status(tool: str) -> dict[str, object]:
    location = shutil.which(tool)
    return {"name": tool, "available": location is not None, "path": location}


def check_environment(environment: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    values = os.environ.copy() if environment is None else environment
    tools = [_tool_status(tool) for tool in REQUIRED_TOOLS]
    missing_tools = [tool["name"] for tool in tools if not tool["available"]]
    local_assets = {
        "workspace_manifest": (ROOT / "pyproject.toml").is_file(),
        "pnpm_workspace": (ROOT / "pnpm-workspace.yaml").is_file(),
        "contract_directory": (ROOT / "contracts" / "jsonschema" / "v1").is_dir(),
        "replay_fixture_directory": (ROOT / "fixtures" / "replay").is_dir(),
        "workflow_fixture_directory": (ROOT / "fixtures" / "workflow").is_dir(),
        "investigation_fixture_directory": (ROOT / "fixtures" / "investigation").is_dir(),
        "policy_approval_fixture": (
            ROOT / "fixtures" / "policy" / "api-503-policy-approval-delivery.json"
        ).is_file(),
    }
    try:
        config = load_config(values)
        denial = None
    except ConfigurationDenied as error:
        config = None
        denial = error.as_dict()

    ready = not missing_tools and all(local_assets.values()) and denial is None
    report = {
        "report_type": "weflow-environment-check.v1",
        "ready": ready,
        "mode": config.mode if config else "unknown",
        "tools": tools,
        "missing_tools": missing_tools,
        "local_assets": local_assets,
        "policy_denial": denial,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
    }
    return (0 if ready else 2), report


def _run(command: Sequence[str]) -> int:
    """Run a declared workspace command, including Windows .cmd shims."""

    resolved = list(command)
    executable = shutil.which(resolved[0])
    if executable:
        resolved[0] = executable
    use_shell = os.name == "nt" and Path(resolved[0]).suffix.lower() in {".bat", ".cmd"}
    try:
        completed = subprocess.run(resolved, cwd=ROOT, check=False, shell=use_shell)
    except FileNotFoundError:
        _print(
            {
                "report_type": "weflow-command-dispatch.v1",
                "command": command[0],
                "reason_code": "local_command_unavailable",
            }
        )
        return 2
    return completed.returncode


def _print(report: dict[str, object]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def command_check(_: argparse.Namespace) -> int:
    code, report = check_environment()
    _print(report)
    return code


def command_health(_: argparse.Namespace) -> int:
    report = runtime_report()
    _print(report)
    return 0 if report["operational_ready"] else 2


def command_contracts(_: argparse.Namespace) -> int:
    python_code = _run(["uv", "run", "pytest", "tests/contracts"])
    typescript_code = _run(["pnpm", "--filter", "@weflow/contracts", "test"])
    return python_code or typescript_code


def command_test(_: argparse.Namespace) -> int:
    python_code = _run(["uv", "run", "pytest"])
    typescript_code = _run(["pnpm", "test"])
    return python_code or typescript_code


def command_lint(_: argparse.Namespace) -> int:
    secret_code = _run([sys.executable, "scripts/scan_secrets.py"])
    python_code = _run(["uv", "run", "ruff", "check", "."])
    typescript_code = _run(["pnpm", "lint"])
    return secret_code or python_code or typescript_code


def command_typecheck(_: argparse.Namespace) -> int:
    return _run(["pnpm", "typecheck"])


def _write_acceptance_report(path_value: str, report: dict[str, object]) -> None:
    reports_directory = (ROOT / "reports").resolve()
    output_path = (ROOT / path_value).resolve()
    if reports_directory not in output_path.parents:
        raise ValueError("report_output_must_be_under_reports")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output_path.write_text(serialized + "\n", encoding="utf-8")


def command_case_intake_acceptance(arguments: argparse.Namespace) -> int:
    from case_intake_acceptance import run_case_intake_acceptance

    try:
        report = run_case_intake_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-change-1-acceptance.v1",
                "accepted": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(report)
    return 0


def command_durable_workflow_acceptance(arguments: argparse.Namespace) -> int:
    from durable_workflow_acceptance import run_durable_workflow_acceptance

    try:
        report = run_durable_workflow_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-change-2-durable-workflow-acceptance.v1",
                "accepted": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(report)
    return 0


def command_investigation_agent_acceptance(arguments: argparse.Namespace) -> int:
    from investigation_agent_acceptance import run_investigation_agent_acceptance

    try:
        report = run_investigation_agent_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-change-3-investigation-agent-acceptance.v1",
                "accepted": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(report)
    return 0


def command_policy_approval_acceptance(arguments: argparse.Namespace) -> int:
    from policy_approval_acceptance import run_policy_approval_acceptance

    try:
        report = run_policy_approval_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-change-4-policy-approval-acceptance.v1",
                "accepted": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(report)
    return 0


def command_evidence_trajectory_acceptance(arguments: argparse.Namespace) -> int:
    from evidence_trajectory_acceptance import run_evidence_trajectory_acceptance

    try:
        report = run_evidence_trajectory_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-change-5-evidence-trajectory-acceptance.v1",
                "accepted": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(report)
    return 0


def command_evaluation_benchmark_acceptance(arguments: argparse.Namespace) -> int:
    from evaluation_benchmark_acceptance import (
        BenchmarkValidationError,
        run_benchmark_core_acceptance,
    )

    try:
        report = run_benchmark_core_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (BenchmarkValidationError, RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-change-6-evaluation-benchmark-core-acceptance.v1",
                "accepted": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(report)
    return 0


def command_evaluation_console_acceptance(arguments: argparse.Namespace) -> int:
    from evaluation_console_acceptance import run_evaluation_console_acceptance

    try:
        report = run_evaluation_console_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (RuntimeError, ValueError):
        _print(
            {
                "report_type": "weflow-offline-evaluation-report-console-acceptance.v1",
                "accepted": False,
                "reason_code": "evaluation_console_acceptance_failed",
            }
        )
        return 2
    _print(report)
    return 0


def command_operator_case_timeline_acceptance(_: argparse.Namespace) -> int:
    from operator_case_timeline_acceptance import (
        publish_operator_case_timeline_acceptance,
        run_operator_case_timeline_acceptance,
    )

    try:
        report = run_operator_case_timeline_acceptance(ROOT)
        publish_operator_case_timeline_acceptance(ROOT, report)
    except (OSError, RuntimeError, ValueError):
        _print(
            {
                "report_type": "weflow-offline-operator-case-timeline-acceptance.v1",
                "accepted": False,
                "reason_code": "operator_case_timeline_acceptance_failed",
            }
        )
        return 2
    _print(report)
    return 0


def command_archive_evidence_check(_: argparse.Namespace) -> int:
    from reconcile_archive_evidence import EvidenceValidationError, validate_repository_evidence

    try:
        report = validate_repository_evidence(ROOT)
    except EvidenceValidationError as error:
        _print(
            {
                "report_type": "weflow-archive-evidence-check.v1",
                "passed": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(report)
    return 0


def command_reconciliation_verification(arguments: argparse.Namespace) -> int:
    from reconciliation_verification import run_aggregate_verification

    report = run_aggregate_verification(ROOT)
    if arguments.output:
        _write_acceptance_report(arguments.output, report)
    _print(report)
    return 0 if report["outcome"] == "passed" else 2


def command_qq_sandbox_offline_acceptance(arguments: argparse.Namespace) -> int:
    from qq_sandbox_acceptance import run_qq_sandbox_offline_acceptance

    try:
        report = run_qq_sandbox_offline_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (OSError, RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-qq-sandbox-offline-acceptance.v1",
                "accepted": False,
                "reason_code": str(error),
                "fake_transport_verified": False,
                "qq_sandbox_live_verified": False,
                "customer_receipt_verified": False,
            }
        )
        return 2
    _print(report)
    return 0


def command_qq_sandbox_acceptance_verify(arguments: argparse.Namespace) -> int:
    from qq_sandbox_acceptance import validate_qq_acceptance_report

    reports_directory = (ROOT / "reports").resolve()
    report_path = (ROOT / arguments.report).resolve()
    try:
        if reports_directory not in report_path.parents:
            raise ValueError("report_input_must_be_under_reports")
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("qq_acceptance_report_invalid")
        validate_qq_acceptance_report(payload, expected_mode=arguments.mode)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        _print(
            {
                "report_type": "weflow-qq-sandbox-acceptance-verification.v1",
                "verified": False,
                "reason_code": str(error),
            }
        )
        return 2
    _print(
        {
            "report_type": "weflow-qq-sandbox-acceptance-verification.v1",
            "verified": True,
            "mode": arguments.mode,
            "customer_receipt_verified": False,
            "case_completion": False,
        }
    )
    return 0


def _enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() not in {"", "0", "false", "no", "off"}


def command_qq_group_pairing(arguments: argparse.Namespace) -> int:
    from weflow_control_kernel.qq_pairing import (
        QQGroupPairingConfig,
        QQPairingActivationDenied,
        QQPairingError,
    )

    try:
        config = QQGroupPairingConfig.from_environment(
            confirm_live_pairing=arguments.confirm_live_qq_pairing,
            store_path=arguments.store,
            repository_root=ROOT,
            environ=os.environ,
            model_enabled=os.environ.get("WEFLOW_PROVIDER_MODE", "replay").lower() != "replay"
            or _enabled(os.environ.get("WEFLOW_PROVIDER_ALLOW_LIVE")),
            external_write_enabled=_enabled(os.environ.get("WEFLOW_EXTERNAL_WRITE_ENABLED")),
            multi_agent_enabled=_enabled(os.environ.get("WEFLOW_MULTI_AGENT_ENABLED")),
        )
    except QQPairingActivationDenied as error:
        _print(
            {
                "report_type": "weflow-qq-group-pairing-command.v1",
                "ready": False,
                "reason_code": error.reason_code,
                "network_contacted": False,
                "qq_write_attempted": False,
                "case_creation": False,
                "model_invocation": False,
            }
        )
        return 2
    readiness = config.safe_readiness()
    _print({"report_type": "weflow-qq-group-pairing-readiness.v1", **readiness})
    try:
        from weflow_control_worker.qq_pairing_runner import build_real_qq_pairing_runner

        runner = build_real_qq_pairing_runner(config=config, contract_root=ROOT)

        def announce_listening(challenge_text: str) -> None:
            _print(
                {
                    "report_type": "weflow-qq-group-pairing-challenge-display.v1",
                    "instruction": (
                        "\u5728\u552f\u4e00\u6d4b\u8bd5\u7fa4\u53d1\u9001\uff1a"
                        "@\u673a\u5668\u4eba " + challenge_text
                    ),
                    "deadline_seconds": 300,
                    "gateway_ready": True,
                    "persisted": False,
                }
            )

        report = asyncio.run(runner.run_one(on_listening=announce_listening))
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (OSError, RuntimeError, ValueError, QQPairingError, QQTransportError) as error:
        _print(
            {
                "report_type": "weflow-qq-group-pairing-live.v1",
                "accepted": False,
                "reason_code": getattr(error, "reason_code", "pairing_live_command_failed"),
                "qq_group_pairing_live_verified": False,
                "qq_write_attempted": False,
                "case_creation": False,
                "workflow_activation": False,
                "model_invocation": False,
            }
        )
        return 2
    _print(report)
    return 0 if report["accepted"] else 2


def command_qq_group_pairing_offline(arguments: argparse.Namespace) -> int:
    from qq_group_pairing_acceptance import run_qq_group_pairing_offline_acceptance

    try:
        report = run_qq_group_pairing_offline_acceptance(ROOT)
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (OSError, RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-qq-group-pairing-offline.v1",
                "accepted": False,
                "reason_code": getattr(error, "reason_code", "pairing_offline_acceptance_failed"),
            }
        )
        return 2
    _print(report)
    return 0


def command_qq_group_pairing_verify(arguments: argparse.Namespace) -> int:
    from weflow_control_kernel.qq_pairing import QQPairingError, verify_pairing_report

    try:
        report_path = (ROOT / arguments.report).resolve()
        if ROOT not in report_path.parents or report_path.parent != ROOT / "reports":
            raise QQPairingError("pairing_report_path_invalid")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        verify_pairing_report(report, expected_mode=arguments.mode, contract_root=ROOT)
    except (OSError, ValueError, QQPairingError) as error:
        _print(
            {
                "report_type": "weflow-qq-group-pairing-verification.v1",
                "passed": False,
                "reason_code": getattr(error, "reason_code", "pairing_report_invalid"),
                "stage1_verified": False,
            }
        )
        return 2
    _print(
        {
            "report_type": "weflow-qq-group-pairing-verification.v1",
            "passed": True,
            "report_sha256": report["report_sha256"],
            "qq_group_pairing_live_verified": report["qq_group_pairing_live_verified"],
            "stage1_verified": False,
        }
    )
    return 0


def command_qq_group_pairing_revoke(arguments: argparse.Namespace) -> int:
    from weflow_control_kernel.qq_pairing import QQPairingJournalError, SQLiteQQPairingJournal

    store_path = (ROOT / arguments.store).resolve()
    try:
        if (
            ROOT not in store_path.parents
            or store_path.name != "qq-sandbox.sqlite3"
            or store_path.parent.name != ".weflow"
        ):
            raise QQPairingJournalError("pairing_store_not_bounded")
        SQLiteQQPairingJournal(store_path).revoke(arguments.pairing_id)
    except (OSError, QQPairingJournalError) as error:
        _print(
            {
                "report_type": "weflow-qq-group-pairing-revoke.v1",
                "revoked": False,
                "reason_code": getattr(error, "reason_code", "pairing_revoke_failed"),
            }
        )
        return 2
    _print(
        {
            "report_type": "weflow-qq-group-pairing-revoke.v1",
            "revoked": True,
            "pairing_id": arguments.pairing_id,
            "qq_write_attempted": False,
        }
    )
    return 0


def command_qq_sandbox_intake_ack(arguments: argparse.Namespace) -> int:
    store_path = (ROOT / arguments.store).resolve()
    values = os.environ
    pairing_id = values.get("WEFLOW_QQ_SANDBOX_PAIRING_ID")
    selector_mode = "safe-pairing-id" if pairing_id else "direct-group"
    live_model_enabled = (
        values.get("WEFLOW_PROVIDER_MODE", "replay").strip().lower() != "replay"
        or _enabled(values.get("WEFLOW_PROVIDER_ALLOW_LIVE"))
        or "WEFLOW_PROVIDER_API_KEY" in values
        or "WEFLOW_LIVE_MODEL_API_KEY" in values
    )
    other_external_write_enabled = _enabled(
        values.get("WEFLOW_EXTERNAL_WRITE_ENABLED")
    ) or _enabled(values.get("WEFLOW_MULTI_AGENT_ENABLED"))
    try:
        from weflow_control_kernel.qq_pairing import resolve_stage1_pairing_environment

        if ROOT not in store_path.parents:
            raise QQActivationDenied("qq_store_path_outside_repository")
        values = resolve_stage1_pairing_environment(values, store_path=store_path)
        config = QQSandboxConfig.from_environment(
            confirm_live=arguments.confirm_live_qq,
            environ=values,
            live_model_enabled=live_model_enabled,
            other_external_write_enabled=other_external_write_enabled,
        )
    except (QQActivationDenied, ValueError) as error:
        _print(
            {
                "report_type": "weflow-qq-sandbox-command.v1",
                "ready": False,
                "reason_code": error.reason_code,
                "network_contacted": False,
                "external_write": False,
                "model_invocation": False,
            }
        )
        return 2
    readiness = config.safe_readiness()
    if arguments.readiness_only:
        report: dict[str, object] = {
            "report_type": "weflow-qq-stage1-precontact-readiness.v1",
            "selector_mode": selector_mode,
            "selector_resolved": True,
            "network_contacted": False,
            "case_creation": False,
            "qq_write_attempted": False,
            "stage1_verified": False,
            "readiness": readiness,
        }
        if pairing_id:
            report["pairing_id"] = pairing_id
        _print(report)
        return 0
    _print({"report_type": "weflow-qq-sandbox-readiness.v1", **readiness})
    try:
        from weflow_control_worker.qq_runner import build_real_qq_gateway_runner

        runner = build_real_qq_gateway_runner(
            config=config,
            store_path=store_path,
            contract_root=ROOT,
            verify_event_dedup=arguments.verify_live_event_dedup,
        )
        report = asyncio.run(runner.run_one()).report
        report["readiness"] = readiness
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (OSError, RuntimeError, ValueError, QQTransportError) as error:
        _print(
            {
                "report_type": "weflow-qq-sandbox-live-acceptance.v1",
                "accepted": False,
                "reason_code": getattr(error, "reason_code", "qq_live_command_failed"),
                "customer_receipt_verified": False,
                "case_completion": False,
                "model_invocation": False,
            }
        )
        return 2
    _print(report)
    return 0 if report["accepted"] else 2


def command_qq_handler_verify(arguments: argparse.Namespace) -> int:
    from weflow_contracts import (
        ContractValidationError,
        validate_qq_handler_acceptance_report,
    )

    reports_directory = (ROOT / "reports").resolve()
    report_path = (ROOT / arguments.report).resolve()
    try:
        if reports_directory not in report_path.parents:
            raise ValueError("handler_report_input_must_be_under_reports")
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("handler_acceptance_report_invalid")
        validate_qq_handler_acceptance_report(payload, ROOT)
        if payload["mode"] != arguments.mode:
            raise ValueError("handler_acceptance_report_mode_mismatch")
    except (ContractValidationError, OSError, ValueError, json.JSONDecodeError) as error:
        _print(
            {
                "report_type": "weflow-qq-handler-acceptance-verification.v1",
                "verified": False,
                "reason_code": str(error),
                "customer_receipt_verified": False,
                "issue_resolution": False,
                "case_completion": False,
                "production_ready": False,
            }
        )
        return 2
    _print(
        {
            "report_type": "weflow-qq-handler-acceptance-verification.v1",
            "verified": True,
            "mode": arguments.mode,
            "report_sha256": payload["report_sha256"],
            "dual_surface_binding_verified": payload["dual_surface_binding_verified"],
            "final_provider_accepted": payload["final_provider_accepted"],
            "customer_receipt_verified": False,
            "issue_resolution": False,
            "case_completion": False,
            "production_ready": False,
        }
    )
    return 0


def command_qq_handler_approval(arguments: argparse.Namespace) -> int:
    if arguments.offline_acceptance:
        from qq_handler_acceptance import run_qq_handler_offline_acceptance

        try:
            report = run_qq_handler_offline_acceptance(ROOT)
            if arguments.output:
                _write_acceptance_report(arguments.output, report)
        except (OSError, RuntimeError, ValueError) as error:
            _print(
                {
                    "report_type": "weflow-qq-handler-command.v1",
                    "ready": False,
                    "reason_code": str(error),
                    "network_contacted": False,
                    "external_write_attempted": False,
                    "model_invocation": False,
                }
            )
            return 2
        _print(report)
        return 0

    store_path = (ROOT / arguments.store).resolve()
    try:
        from weflow_control_kernel.qq_handler import (
            QQ_HANDLER_REVOCATION_CONFIRMATION,
            QQHandlerConfig,
            QQHandlerError,
        )
        from weflow_control_kernel.qq_pairing import resolve_stage1_pairing_environment

        values = resolve_stage1_pairing_environment(os.environ, store_path=store_path)
        config = QQHandlerConfig.from_environment(
            confirm_live_qq=arguments.confirm_live_qq,
            store_path=store_path,
            repository_root=ROOT,
            group_openid=values["WEFLOW_QQ_SANDBOX_GROUP_OPENID"],
            environ=values,
        )
        binding_id = arguments.handler_binding_id or values.get("WEFLOW_QQ_HANDLER_BINDING_ID")
        readiness = config.safe_readiness(handler_binding_id=binding_id)
        if arguments.readiness_only:
            _print(
                {
                    "report_type": "weflow-qq-handler-readiness.v1",
                    **readiness,
                    "selector_resolved": True,
                    "network_contacted": False,
                    "external_write_attempted": False,
                    "case_mutation": False,
                    "model_invocation": False,
                }
            )
            return 0

        from weflow_control_worker.qq_handler_runner import (
            PAIRING_CONFIRMATION,
            build_handler_journal,
            pair_live_handler,
            probe_live_c2c,
            probe_live_group_approval,
            run_live_handler_case,
        )

        if getattr(arguments, "revoke_handler_binding", False):
            journal = build_handler_journal(config)
            if not binding_id:
                raise QQHandlerError("handler_binding_id_required")
            report = journal.revoke_handler_binding(
                config=config,
                handler_binding_id=binding_id,
                operator_confirmation=input(
                    "Type "
                    f"{QQ_HANDLER_REVOCATION_CONFIRMATION} "
                    "to revoke this local handler binding: "
                ),
            )
        elif arguments.probe_c2c:
            report = asyncio.run(probe_live_c2c(config=config, display=_print))
        elif arguments.probe_group_approval:
            journal = build_handler_journal(config)
            if not binding_id:
                raise QQHandlerError("handler_binding_id_required")
            binding = journal.active_binding(binding_id)
            report = asyncio.run(
                probe_live_group_approval(
                    config=config,
                    binding=binding,
                    journal=journal,
                    display=_print,
                )
            )
        elif arguments.pair_handler:
            journal = build_handler_journal(config)
            report = asyncio.run(
                pair_live_handler(
                    config=config,
                    journal=journal,
                    display=_print,
                    confirm=lambda: input(
                        f"确认群与私聊挑战来自同一处理人后，输入 {PAIRING_CONFIRMATION}: "
                    ),
                )
            )
        else:
            journal = build_handler_journal(config)
            if not binding_id:
                raise QQHandlerError("handler_binding_id_required")
            binding = journal.active_binding(binding_id)
            report = asyncio.run(
                run_live_handler_case(
                    config=config,
                    binding=binding,
                    journal=journal,
                )
            )
        if arguments.output:
            _write_acceptance_report(arguments.output, report)
    except (EOFError, OSError, RuntimeError, ValueError) as error:
        _print(
            {
                "report_type": "weflow-qq-handler-command.v1",
                "ready": False,
                "reason_code": getattr(error, "reason_code", "qq_handler_command_failed"),
                "network_contacted": False,
                "external_write_attempted": False,
                "model_invocation": False,
                "production_ready": False,
            }
        )
        return 2
    _print(report)
    if getattr(arguments, "revoke_handler_binding", False):
        return 0 if report.get("revoked") is True else 2
    if arguments.probe_c2c:
        return 0 if report.get("pairing_matcher") == "accepted" else 2
    if arguments.probe_group_approval:
        return 0 if report.get("approval_matcher") == "accepted" else 2
    if arguments.pair_handler:
        return 0 if report["dual_surface_binding_verified"] else 2
    return 0 if report["final_provider_accepted"] else 2


def command_up(arguments: argparse.Namespace) -> int:
    report = start_services(arguments.mode)
    _print(report)
    return 0 if report.get("started") else 2


def command_down(_: argparse.Namespace) -> int:
    report = stop_services()
    _print(report)
    return 0 if report.get("stopped") else 2


def command_compose(arguments: argparse.Namespace) -> int:
    if shutil.which("docker") is None:
        _print(
            {
                "report_type": "weflow-compose.v1",
                "action": arguments.action,
                "started": False,
                "reason_code": "docker_unavailable",
            }
        )
        return 2
    command = ["docker", "compose", "-f", "deploy/compose/docker-compose.yml"]
    if arguments.action == "up":
        command.extend(["up", "--detach"])
    elif arguments.action == "status":
        command.append("ps")
    else:
        command.append("down")
    return _run(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser(
        "check", help="check safe offline development prerequisites"
    ).set_defaults(handler=command_check)
    subcommands.add_parser(
        "health", help="emit the redacted foundation health report"
    ).set_defaults(handler=command_health)
    subcommands.add_parser("contracts", help="run cross-language contract checks").set_defaults(
        handler=command_contracts
    )
    subcommands.add_parser("test", help="run Python and TypeScript checks").set_defaults(
        handler=command_test
    )
    subcommands.add_parser("lint", help="run Python and TypeScript linting").set_defaults(
        handler=command_lint
    )
    subcommands.add_parser("typecheck", help="run TypeScript type checks").set_defaults(
        handler=command_typecheck
    )

    case_intake = subcommands.add_parser(
        "case-intake-acceptance",
        help="run the offline synthetic Case intake acceptance sequence",
    )
    case_intake.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    case_intake.set_defaults(handler=command_case_intake_acceptance)

    durable_workflow = subcommands.add_parser(
        "durable-workflow-acceptance",
        help="run the offline deterministic durable-workflow acceptance sequence",
    )
    durable_workflow.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    durable_workflow.set_defaults(handler=command_durable_workflow_acceptance)

    investigation_agent = subcommands.add_parser(
        "investigation-agent-acceptance",
        help="run the offline API-503 replay-investigation acceptance sequence",
    )
    investigation_agent.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    investigation_agent.set_defaults(handler=command_investigation_agent_acceptance)

    policy_approval = subcommands.add_parser(
        "policy-approval-acceptance",
        help="run the offline API-503 policy/approval/local-delivery acceptance sequence",
    )
    policy_approval.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    policy_approval.set_defaults(handler=command_policy_approval_acceptance)

    evidence_trajectory = subcommands.add_parser(
        "evidence-trajectory-acceptance",
        help="run the offline evidence trajectory and verification replay acceptance sequence",
    )
    evidence_trajectory.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    evidence_trajectory.set_defaults(handler=command_evidence_trajectory_acceptance)
    evaluation_benchmark = subcommands.add_parser(
        "evaluation-benchmark-acceptance",
        help="run the offline deterministic 12-task evaluation benchmark core",
    )
    evaluation_benchmark.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    evaluation_benchmark.set_defaults(handler=command_evaluation_benchmark_acceptance)
    evaluation_console = subcommands.add_parser(
        "evaluation-console-acceptance",
        help="validate and render the fixed offline evaluation report without side effects",
    )
    evaluation_console.add_argument(
        "--output",
        default="reports/add-offline-evaluation-report-console-acceptance.json",
        help="repository-relative evidence path under reports/",
    )
    evaluation_console.set_defaults(handler=command_evaluation_console_acceptance)
    subcommands.add_parser(
        "operator-case-timeline-acceptance",
        help="build and validate the fixed offline Operator Case timeline",
    ).set_defaults(handler=command_operator_case_timeline_acceptance)
    subcommands.add_parser(
        "archive-evidence-check",
        help="validate redacted reconciliation evidence for archived Changes 4 and 5",
    ).set_defaults(handler=command_archive_evidence_check)
    reconciliation_verification = subcommands.add_parser(
        "reconciliation-verification",
        help="run the 900-second bounded offline aggregate verification suite",
    )
    reconciliation_verification.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    reconciliation_verification.set_defaults(handler=command_reconciliation_verification)
    from live_model_cli import configure_live_model_parser

    configure_live_model_parser(subcommands, root=ROOT, printer=_print)

    from qq_model_cli import configure_qq_model_parser

    configure_qq_model_parser(subcommands, root=ROOT, printer=_print)

    qq_pair = subcommands.add_parser(
        "qq-sandbox-pair-group",
        help="read-only first sandbox group pairing with an exact challenge",
    )
    qq_pair.add_argument(
        "--confirm-live-qq-pairing",
        action="store_true",
        help="confirm the bounded real QQ read-only pairing",
    )
    qq_pair.add_argument(
        "--store",
        default=".weflow/qq-sandbox.sqlite3",
        help="fixed repository-local private QQ journal",
    )
    qq_pair.add_argument("--output", help="optional repository-relative live report under reports/")
    qq_pair.set_defaults(handler=command_qq_group_pairing)

    qq_pair_offline = subcommands.add_parser(
        "qq-sandbox-pairing-offline-acceptance", help="run deterministic fake pairing acceptance"
    )
    qq_pair_offline.add_argument(
        "--output",
        default="reports/add-secure-qq-first-group-pairing-offline-acceptance.json",
        help="repository-relative report path",
    )
    qq_pair_offline.set_defaults(handler=command_qq_group_pairing_offline)

    qq_pair_verify = subcommands.add_parser(
        "qq-sandbox-pairing-verify", help="independently verify a pairing report"
    )
    qq_pair_verify.add_argument("--report", required=True)
    qq_pair_verify.add_argument(
        "--mode", choices=("offline-fake", "qq-sandbox-live"), required=True
    )
    qq_pair_verify.set_defaults(handler=command_qq_group_pairing_verify)

    qq_pair_revoke = subcommands.add_parser(
        "qq-sandbox-pairing-revoke", help="locally revoke a safe pairing ID"
    )
    qq_pair_revoke.add_argument("--pairing-id", required=True)
    qq_pair_revoke.add_argument("--store", default=".weflow/qq-sandbox.sqlite3")
    qq_pair_revoke.set_defaults(handler=command_qq_group_pairing_revoke)

    qq_offline = subcommands.add_parser(
        "qq-sandbox-offline-acceptance",
        help="run the deterministic QQ fake-transport acceptance and verifier",
    )
    qq_offline.add_argument(
        "--output",
        default="reports/add-qq-sandbox-intake-and-ack-offline-acceptance.json",
        help="repository-relative evidence path under reports/",
    )
    qq_offline.set_defaults(handler=command_qq_sandbox_offline_acceptance)
    qq_verify = subcommands.add_parser(
        "qq-sandbox-acceptance-verify",
        help="strictly verify one safe QQ offline or live acceptance report",
    )
    qq_verify.add_argument("--report", required=True, help="report path under reports/")
    qq_verify.add_argument("--mode", choices=("offline", "live", "live-dedup"), required=True)
    qq_verify.set_defaults(handler=command_qq_sandbox_acceptance_verify)

    qq_sandbox = subcommands.add_parser(
        "qq-sandbox-intake-ack",
        help="run one explicitly confirmed QQ sandbox group intake and fixed acknowledgement",
    )
    qq_sandbox.add_argument(
        "--confirm-live-qq",
        action="store_true",
        help="confirm the bounded real QQ sandbox read/write capability",
    )
    qq_sandbox.add_argument(
        "--readiness-only",
        action="store_true",
        help="resolve the selector and validate Stage 1 gates without network or writes",
    )
    qq_sandbox.add_argument(
        "--verify-live-event-dedup",
        action="store_true",
        help="replay the one observed provider event in memory and prove no duplicate effect",
    )
    qq_sandbox.add_argument(
        "--store",
        default=".weflow/qq-sandbox.sqlite3",
        help="repository-relative bounded QQ adapter journal path",
    )
    qq_sandbox.add_argument(
        "--output",
        help="optional repository-relative evidence path under reports/",
    )
    qq_sandbox.set_defaults(handler=command_qq_sandbox_intake_ack)

    qq_handler = subcommands.add_parser(
        "qq-sandbox-handler-approval",
        help="run the bounded private QQ handler approval-and-delivery sandbox flow",
    )
    qq_handler.add_argument(
        "--confirm-live-qq",
        action="store_true",
        help="confirm the exact bounded Stage 2 QQ capabilities",
    )
    phase = qq_handler.add_mutually_exclusive_group()
    phase.add_argument(
        "--readiness-only",
        action="store_true",
        help="validate configuration and Stage 1 selector without network or mutation",
    )
    phase.add_argument(
        "--pair-handler",
        action="store_true",
        help="observe the one-time group and C2C challenges, then confirm locally",
    )
    phase.add_argument(
        "--revoke-handler-binding",
        action="store_true",
        help="locally revoke one scope-matched binding without provider contact",
    )
    phase.add_argument(
        "--probe-c2c",
        action="store_true",
        help="observe one privacy-safe C2C event without binding, Case mutation, or writes",
    )
    phase.add_argument(
        "--probe-group-approval",
        action="store_true",
        help="observe one privacy-safe group approval event without mutation or writes",
    )
    phase.add_argument(
        "--offline-acceptance",
        action="store_true",
        help="run the deterministic fake-transport Stage 2 acceptance",
    )
    qq_handler.add_argument(
        "--handler-binding-id",
        help="safe qqhbind_ selector; defaults to WEFLOW_QQ_HANDLER_BINDING_ID",
    )
    qq_handler.add_argument("--store", default=".weflow/qq-sandbox.sqlite3")
    qq_handler.add_argument("--output", help="optional report path under reports/")
    qq_handler.set_defaults(handler=command_qq_handler_approval)

    qq_handler_verify = subcommands.add_parser(
        "qq-sandbox-handler-verify",
        help="independently verify a privacy-safe Stage 2 acceptance report",
    )
    qq_handler_verify.add_argument("--report", required=True)
    qq_handler_verify.add_argument(
        "--mode", choices=("offline-fake", "qq-sandbox-live"), required=True
    )
    qq_handler_verify.set_defaults(handler=command_qq_handler_verify)

    up = subcommands.add_parser("up", help="accept a local startup request")
    up.add_argument("--mode", choices=("offline", "service-boundary"), default="offline")
    up.set_defaults(handler=command_up)
    subcommands.add_parser("down", help="accept a local shutdown request").set_defaults(
        handler=command_down
    )

    compose = subcommands.add_parser("compose", help="accept a Docker Compose action")
    compose.add_argument("action", choices=("up", "down", "status"))
    compose.set_defaults(handler=command_compose)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    qq_commands = {
        "qq-sandbox-intake-ack",
        "qq-sandbox-pair-group",
        "qq-sandbox-handler-approval",
    }
    stage3_command = "qq-sandbox-live-model-workflow"
    if arguments.command != stage3_command and arguments.command not in qq_commands:
        try:
            from weflow_control_kernel.qq_handler import (
                reject_handler_configuration_for_other_commands,
            )
            from weflow_control_kernel.qq_model import (
                reject_model_configuration_for_other_commands,
            )
            from weflow_control_kernel.qq_pairing import (
                reject_pairing_configuration_for_ordinary_command,
            )

            reject_model_configuration_for_other_commands(
                os.environ,
                allow_isolated_live_credential=(
                    arguments.command == "live-model-evaluation-acceptance"
                ),
            )
            reject_handler_configuration_for_other_commands(os.environ)
            reject_pairing_configuration_for_ordinary_command(os.environ)
            reject_qq_configuration_for_ordinary_command(os.environ)
        except (QQActivationDenied, ValueError) as error:
            _print(
                {
                    "report_type": "weflow-command-dispatch.v1",
                    "command": arguments.command,
                    "reason_code": getattr(error, "reason_code", str(error)),
                    "network_contacted": False,
                    "external_write": False,
                    "model_invocation": False,
                }
            )
            return 2
    return int(arguments.handler(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
