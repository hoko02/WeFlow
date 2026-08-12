from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_qq_handler_workflow import (
    CASE_ID,
    c2c_event,
    group_event,
    pair_handler,
)
from weflow_control_kernel.qq_handler import (
    QQ_HANDLER_REQUIRED_CAPABILITIES,
    QQHandlerConfig,
    QQHandlerEventRejected,
    QQHandlerTransportError,
    begin_handler_pairing,
)
from weflow_control_kernel.qq_handler_service import QQHandlerWorkflowService
from weflow_control_worker.qq_handler_runner import (
    _LiveGateway,
    build_c2c_probe_observation,
    build_group_approval_probe_observation,
    normalize_live_customer_intake,
    pair_live_handler,
)

ROOT = Path(__file__).resolve().parents[2]


def config(tmp_path: Path) -> QQHandlerConfig:
    return QQHandlerConfig(
        app_id="synthetic-app",
        client_secret="not-a-real-secret",
        tenant_id="synthetic-tenant",
        stage1_pairing_id="qqpair_11111111111111111111111111111111",
        group_openid="bound-group",
        identity_salt="s" * 32,
        store_path=tmp_path / ".weflow" / "qq-sandbox.sqlite3",
        repository_root=ROOT,
        capabilities=QQ_HANDLER_REQUIRED_CAPABILITIES,
    )


def event(content: str = "@机器人 SYNTHETIC_ISSUE_API_503") -> dict[str, object]:
    return {
        "t": "GROUP_AT_MESSAGE_CREATE",
        "s": 10,
        "d": {
            "id": "synthetic-intake-message",
            "content": content,
            "timestamp": "2026-08-11T00:00:00Z",
            "group_openid": "bound-group",
            "author": {"member_openid": "customer-member", "nickname": "ignored"},
        },
    }


def test_live_intake_is_minimized_before_restricted_storage(tmp_path: Path) -> None:
    normalized = normalize_live_customer_intake(event(), config=config(tmp_path))

    assert normalized["content"] == "SYNTHETIC_ISSUE_API_503"
    assert normalized["case_id"].startswith("case_")
    assert normalized["case_revision_id"].startswith("qqrev_")
    assert "group_openid" not in normalized
    assert "author" not in normalized
    assert "raw_event" not in normalized


@pytest.mark.parametrize(
    "mutation, reason",
    [
        ({"group_openid": "foreign-group"}, "foreign_group"),
        ({"attachments": [{"id": "synthetic"}]}, "plain_text_required"),
        (
            {"content": "@机器人 WF-APPROVE qqhar_11111111111111111111111111111111 111111111111 1"},
            "command_not_issue",
        ),
    ],
)
def test_live_intake_rejects_foreign_rich_or_approval_events(
    tmp_path: Path, mutation: dict[str, object], reason: str
) -> None:
    payload = event()
    payload["d"].update(mutation)  # type: ignore[union-attr]

    with pytest.raises(QQHandlerEventRejected, match=reason):
        normalize_live_customer_intake(payload, config=config(tmp_path))


def test_pair_live_handler_recovers_confirmed_binding_without_network(
    tmp_path: Path,
) -> None:
    cfg, journal, _, binding = pair_handler(tmp_path)

    report = asyncio.run(
        pair_live_handler(
            config=cfg,
            journal=journal,
            display=lambda _payload: None,
            confirm=lambda: pytest.fail("recovery must not request another confirmation"),
        )
    )

    assert report["handler_binding_id"] == binding["handler_binding_id"]
    assert report["dual_surface_binding_verified"] is True
    assert report["notification_attempt_count"] == 0
    assert report["recovery_state"] == "reconciled"
    assert report["network_contacted"] is False


def test_c2c_probe_reports_only_presence_and_matcher_facts(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    tokens = iter(("g" * 32, "c" * 32))
    session = begin_handler_pairing(
        cfg,
        token_factory=lambda: next(tokens),
        contract_root=ROOT,
    )
    event = {
        "t": "C2C_MESSAGE_CREATE",
        "s": 101,
        "d": {
            "id": "synthetic/C2C+opaque=message==",
            "content": session.c2c.plaintext,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "author": {"user_openid": "synthetic-c2c-user"},
        },
    }

    report = build_c2c_probe_observation(
        event,
        config=cfg,
        challenge=session.c2c,
    )

    assert report["c2c_event_received"] is True
    assert report["has_user_openid"] is True
    assert report["has_message_id"] is True
    assert report["content_exact_probe"] is True
    assert report["pairing_matcher"] == "accepted"
    assert report["case_mutation"] is False
    assert report["provider_event_persisted"] is False
    serialized = json.dumps(report, sort_keys=True)
    assert "synthetic-c2c-user" not in serialized
    assert session.c2c.plaintext not in serialized
    assert "content" not in report
    assert "author" not in report
    assert report["external_write_attempted"] is False


def test_live_gateway_rejects_non_increasing_sequence_inside_one_connection(
    tmp_path: Path,
) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.frames = iter(
                (
                    {"op": 0, "t": "GROUP_AT_MESSAGE_CREATE", "s": 10, "d": {}},
                    {"op": 0, "t": "C2C_MESSAGE_CREATE", "s": 10, "d": {}},
                )
            )

        async def receive(self) -> dict[str, object]:
            return next(self.frames)

        async def send(self, _payload: object) -> None:
            return None

    async def exercise() -> None:
        gateway = _LiveGateway(config(tmp_path))
        gateway.connection = FakeConnection()

        first = await gateway.next_event()
        assert first["s"] == 10
        with pytest.raises(
            QQHandlerTransportError,
            match="qq_handler_gateway_sequence_out_of_order",
        ):
            await gateway.next_event()

    asyncio.run(exercise())


def test_live_gateway_captures_ready_session_before_events(tmp_path: Path) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.frames = iter(
                (
                    {
                        "op": 0,
                        "t": "READY",
                        "s": 1,
                        "d": {"session_id": "current-stage3-session"},
                    },
                    {"op": 0, "t": "GROUP_AT_MESSAGE_CREATE", "s": 2, "d": {}},
                )
            )

        async def receive(self) -> dict[str, object]:
            return next(self.frames)

        async def send(self, _payload: object) -> None:
            return None

    async def exercise() -> None:
        gateway = _LiveGateway(config(tmp_path))
        gateway.connection = FakeConnection()

        await gateway.wait_until_ready()
        assert gateway.session_id == "current-stage3-session"
        assert gateway.ready_sequence == 1
        assert (await gateway.next_event())["s"] == 2

    asyncio.run(exercise())


def test_group_approval_probe_reports_matchers_without_mutation_or_raw_values(
    tmp_path: Path,
) -> None:
    cfg, journal, clock, binding = pair_handler(tmp_path)
    journal.create_issue_artifact(
        binding=binding,
        case_id=CASE_ID,
        case_revision_id="case-revision-synthetic-1",
        source_message_id_hash="a" * 64,
        content="SYNTHETIC_ISSUE_API_503",
    )
    service = QQHandlerWorkflowService(config=cfg, binding=binding, journal=journal)
    service.handle_private_event(
        c2c_event(
            content=f"WF-ACCEPT {CASE_ID} 1",
            message_id="probe-accept",
            timestamp=clock(),
        )
    )
    draft = service.handle_private_event(
        c2c_event(
            content=f"WF-DRAFT {CASE_ID} 2\nSYNTHETIC_RESPONSE",
            message_id="probe-draft",
            timestamp=clock(),
        )
    )
    metadata = draft.content.split("WF-APPROVE ", 1)[1].split()
    event = group_event(
        content=f"WF-APPROVE {' '.join(metadata)}",
        message_id="probe-approval",
        timestamp=clock(),
    )

    report = build_group_approval_probe_observation(
        event,
        config=cfg,
        binding=binding,
        journal=journal,
    )

    assert report["approval_matcher"] == "accepted"
    assert report["paired_group_match"] is True
    assert report["bound_member_match"] is True
    assert report["current_request_match"] is True
    assert report["request_unexpired"] is True
    assert journal.safe_counts()["approval_decision_count"] == 0
    serialized = json.dumps(report, sort_keys=True)
    assert "member-raw-1" not in serialized
    assert "SYNTHETIC_RESPONSE" not in serialized
