from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    qq_handler_acceptance_report_sha256,
    validate_payload,
    validate_qq_customer_issue_artifact,
    validate_qq_handler_acceptance_report,
    validate_qq_handler_approval_chain,
    validate_qq_handler_binding,
    validate_qq_handler_command,
    validate_qq_handler_notification_chain,
    validate_qq_handler_passive_reply_chain,
    validate_qq_handler_response_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "fixtures/contracts/v1/semantic/qq-handler-approval-and-delivery.json").read_text(
        encoding="utf-8"
    )
)


def test_every_stage2_contract_round_trips_offline() -> None:
    for payload in FIXTURE.values():
        validate_payload(payload, ROOT)

    validate_qq_handler_binding(FIXTURE["binding"], ROOT)
    validate_qq_customer_issue_artifact(FIXTURE["issue_artifact"], ROOT)
    validate_qq_handler_response_artifact(FIXTURE["response_artifact"], ROOT)
    validate_qq_handler_command(FIXTURE["command"], ROOT)
    validate_qq_handler_notification_chain(
        FIXTURE["notification_intent"], [FIXTURE["notification_result"]], ROOT
    )
    validate_qq_handler_approval_chain(
        FIXTURE["approval_request"], [FIXTURE["approval_decision"]], ROOT
    )
    validate_qq_handler_passive_reply_chain(
        FIXTURE["passive_reply_intent"], [FIXTURE["passive_reply_result"]], ROOT
    )
    report = copy.deepcopy(FIXTURE["report"])
    report["report_sha256"] = qq_handler_acceptance_report_sha256(report)
    validate_qq_handler_acceptance_report(report, ROOT)


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("issue_artifact", "customer_issue", "private"),
        ("response_artifact", "candidate_text", "private"),
        ("command", "draft_preview", "private"),
        ("binding", "member_openid", "raw-private-id"),
        ("binding", "user_openid", "raw-private-id"),
        ("report", "raw_event", {"content": "private"}),
        ("report", "access_token", "secret"),
        ("notification_intent", "message", "unrestricted"),
    ],
)
def test_closed_metadata_contracts_reject_private_or_privileged_fields(
    target: str, field: str, value: object
) -> None:
    payload = copy.deepcopy(FIXTURE[target])
    payload[field] = value
    with pytest.raises(ContractValidationError):
        validate_payload(payload, ROOT)


def test_unknown_privileged_variants_fail_before_policy() -> None:
    command = copy.deepcopy(FIXTURE["command"])
    command["command"] = "send-arbitrary-message"
    with pytest.raises(ContractValidationError):
        validate_qq_handler_command(command, ROOT)

    notification = copy.deepcopy(FIXTURE["notification_intent"])
    notification["operation"] = "qq.c2c.send-arbitrary"
    with pytest.raises(ContractValidationError):
        validate_qq_handler_notification_chain(notification, [], ROOT)


def test_artifact_bounds_retention_and_terminal_deletion_are_semantic_gates() -> None:
    issue = copy.deepcopy(FIXTURE["issue_artifact"])
    issue["normalized_length"] = 1201
    with pytest.raises(ContractValidationError):
        validate_qq_customer_issue_artifact(issue, ROOT)

    issue = copy.deepcopy(FIXTURE["issue_artifact"])
    issue["expires_at"] = "2026-08-12T00:07:01Z"
    with pytest.raises(ContractValidationError, match="retention_exceeds_24_hours"):
        validate_qq_customer_issue_artifact(issue, ROOT)

    issue = copy.deepcopy(FIXTURE["issue_artifact"])
    issue["deletion_status"] = "DELETED"
    with pytest.raises(ContractValidationError, match="deletion_state_invalid"):
        validate_qq_customer_issue_artifact(issue, ROOT)


def test_at_most_once_notification_and_approval_are_closed_chains() -> None:
    with pytest.raises(ContractValidationError, match="multiple_attempts_forbidden"):
        validate_qq_handler_notification_chain(
            FIXTURE["notification_intent"],
            [FIXTURE["notification_result"], FIXTURE["notification_result"]],
            ROOT,
        )
    with pytest.raises(ContractValidationError, match="duplicate_decision"):
        validate_qq_handler_approval_chain(
            FIXTURE["approval_request"],
            [FIXTURE["approval_decision"], FIXTURE["approval_decision"]],
            ROOT,
        )


def test_provider_message_ids_are_opaque_bounded_strings() -> None:
    opaque_id = "opaque/QQ+C2C=message=="
    for target in ("command", "approval_decision", "passive_reply_intent"):
        payload = copy.deepcopy(FIXTURE[target])
        payload["source_message_id"] = opaque_id
        validate_payload(payload, ROOT)

    for invalid_id in ("", "line\nbreak", "x" * 257):
        payload = copy.deepcopy(FIXTURE["command"])
        payload["source_message_id"] = invalid_id
        with pytest.raises(ContractValidationError):
            validate_payload(payload, ROOT)
