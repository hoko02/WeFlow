"""Argparse registration for the dedicated bounded QQ-plus-model workflow."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qq_model_workflow_acceptance import run_qq_model_workflow_offline_acceptance
from qq_model_workflow_verifier import verify_published_qq_model_reports
from weflow_testkit.qq_model_profile import QQ_STAGE3_PROFILE_PATH

JsonObject = dict[str, Any]
JsonPrinter = Callable[[dict[str, object]], None]
_SAFE_REASON = re.compile(r"^[a-z0-9._:-]{1,120}$")


def _reason(error: BaseException) -> str:
    value = getattr(error, "reason_code", None) or str(error)
    return (
        value
        if isinstance(value, str) and _SAFE_REASON.fullmatch(value)
        else "stage3_command_failed"
    )


def _report_path(root: Path, value: str) -> Path:
    reports = (root / "reports").resolve()
    candidate = (root / value).resolve()
    if candidate.parent != reports or candidate.suffix != ".json":
        raise ValueError("stage3_report_path_invalid")
    return candidate


def _publish(root: Path, value: str, payload: JsonObject) -> None:
    path = _report_path(root, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _command(arguments: argparse.Namespace, root: Path, printer: JsonPrinter) -> int:
    try:
        if arguments.offline_fake:
            report, verification = run_qq_model_workflow_offline_acceptance(root)
            _publish(root, arguments.output, report)
            _publish(root, arguments.verification_output, verification)
        else:
            from weflow_control_worker.qq_model_runner import (
                prepare_stage3_preflight,
                recover_completed_live_stage3_reports,
                run_live_stage3_case,
            )

            if arguments.recover_completed_case:
                report, verification = recover_completed_live_stage3_reports(
                    root=root,
                    store_path=arguments.store,
                    confirm_live_qq=arguments.confirm_live_qq,
                    confirm_live_model=arguments.confirm_live_model,
                    pairing_id=arguments.pairing_id,
                    handler_binding_id=arguments.handler_binding_id,
                    endpoint=arguments.provider_endpoint,
                    model=arguments.provider_model,
                    profile_path=arguments.profile,
                    case_id=arguments.recover_completed_case,
                )
                _publish(root, arguments.output, report)
                _publish(root, arguments.verification_output, verification)
            elif arguments.readiness_only:
                prepared = prepare_stage3_preflight(
                    root=root,
                    store_path=arguments.store,
                    confirm_live_qq=arguments.confirm_live_qq,
                    confirm_live_model=arguments.confirm_live_model,
                    pairing_id=arguments.pairing_id,
                    handler_binding_id=arguments.handler_binding_id,
                    endpoint=arguments.provider_endpoint,
                    model=arguments.provider_model,
                    profile_path=arguments.profile,
                )
                printer(prepared.readiness)
                return 0
            else:
                report, verification = run_live_stage3_case(
                    root=root,
                    store_path=arguments.store,
                    confirm_live_qq=arguments.confirm_live_qq,
                    confirm_live_model=arguments.confirm_live_model,
                    pairing_id=arguments.pairing_id,
                    handler_binding_id=arguments.handler_binding_id,
                    endpoint=arguments.provider_endpoint,
                    model=arguments.provider_model,
                    profile_path=arguments.profile,
                    diagnostic=printer,
                )
                _publish(root, arguments.output, report)
                _publish(root, arguments.verification_output, verification)
    except (OSError, RuntimeError, ValueError) as error:
        printer(
            {
                "report_type": "weflow-qq-model-workflow-command.v1",
                "ready": False,
                "reason_code": _reason(error),
                "network_contacted": bool(getattr(error, "network_contacted", False)),
                "model_invocation": bool(getattr(error, "model_invocation", False)),
                "case_mutation": bool(getattr(error, "case_mutation", False)),
                "external_write_attempted": bool(getattr(error, "external_write_attempted", False)),
                "production_ready": False,
            }
        )
        return 2
    printer(report)
    return 0


def _verify(arguments: argparse.Namespace, root: Path, printer: JsonPrinter) -> int:
    try:
        report = json.loads(_report_path(root, arguments.report).read_text(encoding="utf-8"))
        verification = json.loads(
            _report_path(root, arguments.verification).read_text(encoding="utf-8")
        )
        if not isinstance(report, dict) or not isinstance(verification, dict):
            raise ValueError("stage3_published_report_invalid")
        verify_published_qq_model_reports(
            report,
            verification,
            expected_mode=arguments.mode,
            root=root,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        printer(
            {
                "report_type": "weflow-qq-model-workflow-verification-command.v1",
                "verified": False,
                "reason_code": _reason(error),
                "network_contacted": False,
                "credential_required": False,
                "external_write_attempted": False,
                "model_invocation": False,
            }
        )
        return 2
    printer(verification)
    return 0


def configure_qq_model_parser(subcommands: Any, *, root: Path, printer: JsonPrinter) -> None:
    command = subcommands.add_parser(
        "qq-sandbox-live-model-workflow",
        help="run the explicit bounded Stage 3 QQ-plus-model workflow",
    )
    command.add_argument("--confirm-live-qq", action="store_true")
    command.add_argument("--confirm-live-model", action="store_true")
    phase = command.add_mutually_exclusive_group()
    phase.add_argument("--readiness-only", action="store_true")
    phase.add_argument("--offline-fake", action="store_true")
    phase.add_argument("--recover-completed-case", metavar="CASE_ID")
    command.add_argument("--pairing-id")
    command.add_argument("--handler-binding-id")
    command.add_argument("--provider-endpoint")
    command.add_argument("--provider-model")
    command.add_argument("--profile", default=QQ_STAGE3_PROFILE_PATH)
    command.add_argument("--store", default=".weflow/qq-sandbox.sqlite3")
    command.add_argument(
        "--output",
        default="reports/enable-bounded-live-model-in-qq-workflow-acceptance.json",
    )
    command.add_argument(
        "--verification-output",
        default="reports/enable-bounded-live-model-in-qq-workflow-verification.json",
    )
    command.set_defaults(handler=lambda arguments: _command(arguments, root, printer))

    verify = subcommands.add_parser(
        "qq-sandbox-live-model-workflow-verify",
        help="independently verify the two content-free Stage 3 artifacts",
    )
    verify.add_argument("--report", required=True)
    verify.add_argument("--verification", required=True)
    verify.add_argument(
        "--mode", choices=("offline-fake", "qq-model-integrated-live"), required=True
    )
    verify.set_defaults(handler=lambda arguments: _verify(arguments, root, printer))


__all__ = ["configure_qq_model_parser"]
