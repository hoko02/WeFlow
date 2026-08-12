from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_control_kernel.qq_sandbox import (
    QQEventRejected,
    QQSandboxConfig,
    normalize_qq_group_at_event,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 10, 0, 0, 1, tzinfo=UTC)
CONFIG = QQSandboxConfig(
    "fake-app", "not-a-real-secret", "fake-group", "fake-tenant", "fake-identity-salt"
)


def event() -> dict[str, object]:
    return {
        "op": 0,
        "s": 1,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "fake-message",
            "group_openid": "fake-group",
            "author": {"member_openid": "fake-member"},
            "message_type": 0,
            "content": "广告系统出现了API 503错误",
            "timestamp": "2026-08-10T00:00:00Z",
        },
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("message_type", 3),
        ("message_type", 7),
        ("ark_data", {"prompt": "structured card"}),
        ("msg_elements", [{"message_type": 102, "content": "chat history"}]),
    ),
)
def test_non_text_group_at_payload_is_rejected(field: str, value: object) -> None:
    raw = event()
    raw["d"][field] = value  # type: ignore[index]

    with pytest.raises(QQEventRejected, match="qq_non_text_unsupported"):
        normalize_qq_group_at_event(raw, CONFIG, received_at=NOW, contract_root=ROOT)


def test_official_plain_text_shape_is_accepted_and_raw_content_is_discarded() -> None:
    normalized = normalize_qq_group_at_event(event(), CONFIG, received_at=NOW, contract_root=ROOT)

    assert normalized["content_classification"] == "qq-private-hash"
    assert "广告系统" not in str(normalized)
