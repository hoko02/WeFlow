"""Argparse registration for the dedicated live-model evaluation command."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from live_model_evaluation_acceptance import run_and_publish_live_acceptance, safe_reason
from weflow_testkit.live_evaluation import (
    load_live_credential,
    load_live_pilot_suite,
    parse_live_evaluation_config,
)

JsonPrinter = Callable[[dict[str, object]], None]


def _handler(arguments: argparse.Namespace, root: Path, printer: JsonPrinter) -> int:
    try:
        suite = load_live_pilot_suite(root)
        endpoint = arguments.endpoint or os.environ.get(
            "WEFLOW_LIVE_MODEL_ENDPOINT", "https://api.deepseek.com"
        )
        model = arguments.model or os.environ.get(
            "WEFLOW_LIVE_MODEL_MODEL", str(suite.price_profile["model_pattern"])
        )
        config = parse_live_evaluation_config(
            suite,
            confirm_live=arguments.confirm_live,
            endpoint=endpoint,
            model=model,
        )
        auth = load_live_credential(config, os.environ)
        report = run_and_publish_live_acceptance(
            root=root,
            suite=suite,
            config=config,
            auth=auth,
            output=arguments.output,
            verification_output=arguments.verification_output,
            diagnostics_output=arguments.diagnostics_output,
            retain_redacted_drafts=arguments.retain_redacted_drafts,
        )
    except (OSError, RuntimeError, ValueError) as error:
        printer(
            {
                "report_type": "weflow-live-model-evaluation-acceptance.v1",
                "accepted": False,
                "live_verified": False,
                "reason_code": safe_reason(error),
                "credential_persisted": False,
                "external_business_write_count": 0,
            }
        )
        return 2
    printer(
        {
            "report_type": "weflow-live-model-evaluation-acceptance.v1",
            "accepted": True,
            "live_verified": True,
            "evaluation_session_id": report["evaluation_session_id"],
            "attempt_count": report["attempt_count"],
            "grounded_happy_path_success_count": report["grounded_happy_path_success_count"],
            "report_sha256": report["report_sha256"],
            "estimated_cost": report["suite_aggregate"]["estimated_cost"],
            "currency": report["suite_aggregate"]["currency"],
            "credential_persisted": False,
            "external_business_write_count": 0,
            "limitations": report["limitations"],
        }
    )
    return 0


def configure_live_model_parser(subcommands: Any, *, root: Path, printer: JsonPrinter) -> None:
    command = subcommands.add_parser(
        "live-model-evaluation-acceptance",
        help="run the explicitly authorized 30-attempt synthetic live-model evaluation",
    )
    command.add_argument(
        "--confirm-live",
        action="store_true",
        help="explicitly authorize public provider/model contact and estimated cost",
    )
    command.add_argument(
        "--endpoint",
        help="public HTTPS OpenAI-compatible base URL; never written to reports",
    )
    command.add_argument(
        "--model", help="model identity matching the checked-in dated price profile"
    )
    command.add_argument(
        "--output",
        default="reports/add-bounded-live-model-evaluation-acceptance.json",
        help="accepted report path directly under reports/",
    )
    command.add_argument(
        "--verification-output",
        default="reports/add-bounded-live-model-evaluation-verification.json",
        help="safe per-attempt verification path directly under reports/",
    )
    command.add_argument(
        "--diagnostics-output",
        default="reports/add-bounded-live-model-evaluation-diagnostics.json",
        help="safe failure diagnostics path directly under reports/",
    )
    command.add_argument(
        "--retain-redacted-drafts",
        action="store_true",
        help="retain expiring redacted drafts under ignored .weflow diagnostics storage",
    )
    command.set_defaults(handler=lambda arguments: _handler(arguments, root, printer))


__all__ = ["configure_live_model_parser"]
