from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_control_kernel.qq_pairing import (
    QQGroupPairingConfig,
    QQPairingActivationDenied,
    QQPairingEventRejected,
    SQLiteQQPairingJournal,
    create_pairing_challenge,
    normalize_pairing_event,
)

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def test_config_is_exact_read_only_and_repository_local(tmp_path: Path) -> None:
    env = {
        "WEFLOW_QQ_APP_ID": "app",
        "WEFLOW_QQ_CLIENT_SECRET": "secret",
        "WEFLOW_QQ_TENANT_ID": "tenant",
        "WEFLOW_QQ_CAPABILITIES": "qq.group_pair.read",
    }
    config = QQGroupPairingConfig.from_environment(
        confirm_live_pairing=True,
        store_path=".weflow/qq-sandbox.sqlite3",
        repository_root=tmp_path,
        environ=env,
    )
    assert config.safe_readiness()["qq_write_enabled"] is False
    with pytest.raises(QQPairingActivationDenied):
        QQGroupPairingConfig.from_environment(
            confirm_live_pairing=False,
            store_path=".weflow/qq-sandbox.sqlite3",
            repository_root=tmp_path,
            environ=env,
        )
    with pytest.raises(QQPairingActivationDenied):
        QQGroupPairingConfig.from_environment(
            confirm_live_pairing=True,
            store_path="../outside.sqlite3",
            repository_root=tmp_path,
            environ=env,
        )
    with pytest.raises(QQPairingActivationDenied):
        QQGroupPairingConfig.from_environment(
            confirm_live_pairing=True,
            store_path=".weflow/qq-sandbox.sqlite3",
            repository_root=tmp_path,
            environ={**env, "WEFLOW_QQ_SANDBOX_GROUP_OPENID": "caller-group"},
        )


def test_challenge_is_digest_only_and_exact_match(tmp_path: Path) -> None:
    config = QQGroupPairingConfig(
        "app", "secret", "tenant", tmp_path / ".weflow/qq-sandbox.sqlite3", tmp_path
    )
    challenge = create_pairing_challenge(
        config, clock=lambda: NOW, token_factory=lambda: "abcdefghijklmnopqrstuvwx"
    )
    journal = SQLiteQQPairingJournal(config.store_path, clock=lambda: NOW)
    journal.record_challenge(challenge.record)
    assert challenge.plaintext.startswith(
        "WFPAIR-"
    ) and challenge.plaintext not in config.store_path.read_bytes().decode("latin1")
    event = {
        "s": 1,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": "m1",
            "group_openid": "g1",
            "author": {"member_openid": "member"},
            "content": "@机器人 " + challenge.plaintext,
            "timestamp": "2026-08-10T00:00:00Z",
        },
    }
    observed = normalize_pairing_event(
        event,
        expected_plaintext=challenge.plaintext,
        now=NOW,
        deadline_at=str(challenge.record["deadline_at"]),
    )
    assert observed["group_openid_hash"] and "member" not in str(observed)
    with pytest.raises(QQPairingEventRejected):
        normalize_pairing_event(
            {**event, "t": "DIRECT_MESSAGE_CREATE"},
            expected_plaintext=challenge.plaintext,
            now=NOW,
            deadline_at=str(challenge.record["deadline_at"]),
        )
