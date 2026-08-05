#!/usr/bin/env python
"""Cross-platform command surface for the WeFlow Change 4 local harness."""

from __future__ import annotations

import argparse
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
EXTENSION_SDK_SRC = ROOT / "packages" / "python" / "weflow-extension-sdk" / "src"
PLATFORM_API_SRC = ROOT / "apps" / "platform-api" / "src"
for source_directory in (
    SCRIPTS_DIRECTORY,
    CONTROL_KERNEL_SRC,
    CONTRACTS_SRC,
    TESTKIT_SRC,
    BUSINESS_SIMULATOR_SRC,
    AGENT_RUNTIME_SRC,
    EXTENSION_SDK_SRC,
    PLATFORM_API_SRC,
):
    if str(source_directory) not in sys.path:
        sys.path.insert(0, str(source_directory))

from processes import runtime_report, start_services, stop_services  # noqa: E402
from weflow_control_kernel.config import ConfigurationDenied, load_config  # noqa: E402

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
    return int(arguments.handler(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
