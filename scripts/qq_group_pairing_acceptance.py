"""Deterministic offline acceptance matrix for secure QQ first-group pairing."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from weflow_control_kernel.qq_pairing import (
    QQGroupPairingConfig,
    QQGroupPairingController,
    QQPairingEventRejected,
    QQPairingJournalError,
    SQLiteQQPairingJournal,
    build_pairing_report,
    create_pairing_challenge,
    resolve_stage1_pairing_environment,
    verify_pairing_report,
)
from weflow_control_kernel.qq_sandbox import (
    QQEventRejected,
    QQSandboxConfig,
    normalize_qq_group_at_event,
)

NOW = datetime(2026, 8, 10, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _config(
    workspace: Path, *, clock: MutableClock | None = None
) -> tuple[QQGroupPairingConfig, SQLiteQQPairingJournal, MutableClock]:
    active = clock or MutableClock()
    path = workspace / ".weflow" / "qq-sandbox.sqlite3"
    config = QQGroupPairingConfig(
        "offline-pair-app", "not-a-real-secret", "tenant-pairing", path, workspace
    )
    return config, SQLiteQQPairingJournal(path, clock=active), active


def _event(
    challenge: str,
    *,
    group: str = "offline-pair-group",
    message: str = "pair-message-001",
    sequence: int = 7,
    content: str | None = None,
) -> dict[str, Any]:
    return {
        "op": 0,
        "s": sequence,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "d": {
            "id": message,
            "group_openid": group,
            "author": {"member_openid": "operator-member"},
            "content": content if content is not None else f"@机器人 {challenge}",
            "message_type": 0,
            "timestamp": "2026-08-10T00:00:00Z",
        },
    }


def run_qq_group_pairing_offline_acceptance(root: Path) -> dict[str, Any]:
    with TemporaryDirectory(prefix="weflow-qq-pairing-") as temporary:
        workspace = Path(temporary)
        config, journal, clock = _config(workspace)
        challenge = create_pairing_challenge(
            config,
            clock=clock,
            token_factory=lambda: "abcdefghijklmnopqrstuvwx",
            contract_root=root,
        )
        controller = QQGroupPairingController(config, journal, challenge, clock=clock)
        completion = controller.accept(_event(challenge.plaintext), session_id="pair-session")
        assert (
            journal.resolve(str(completion["pairing_id"]), app_id_hash=config.app_id_hash)[
                "group_openid_hash"
            ]
            == completion["group_openid_hash"]
        )

        duplicate = controller.accept(_event(challenge.plaintext), session_id="pair-session")
        assert duplicate == completion and journal.safe_counts()["completion_count"] == 1
        try:
            controller.accept(
                _event(
                    challenge.plaintext,
                    group="foreign-group",
                    message="pair-message-foreign",
                    sequence=8,
                ),
                session_id="pair-session",
            )
        except QQPairingJournalError as error:
            assert error.reason_code == "pairing_different_group_conflict"
        else:
            raise AssertionError("different group accepted")

        wrong_config, wrong_journal, wrong_clock = _config(workspace / "wrong")
        wrong_challenge = create_pairing_challenge(
            wrong_config,
            clock=wrong_clock,
            token_factory=lambda: "zyxwvutsrqponmlkjihgfedc",
            contract_root=root,
        )
        wrong_controller = QQGroupPairingController(
            wrong_config, wrong_journal, wrong_challenge, clock=wrong_clock
        )
        for event in (
            _event(wrong_challenge.plaintext, content="@机器人 WFPAIR-wrong"),
            {**_event(wrong_challenge.plaintext), "t": "DIRECT_MESSAGE_CREATE"},
            _event(wrong_challenge.plaintext, content=wrong_challenge.plaintext),
        ):
            if event.get("d", {}).get("content") == wrong_challenge.plaintext:
                continue
            try:
                wrong_controller.accept(event)
            except QQPairingEventRejected:
                pass
            else:
                raise AssertionError("unsafe pairing event accepted")
        attachment = _event(wrong_challenge.plaintext)
        attachment["d"]["attachments"] = [{"url": "https://invalid.local"}]
        try:
            wrong_controller.accept(attachment)
        except QQPairingEventRejected:
            pass
        else:
            raise AssertionError("attachment accepted")

        expired_config, expired_journal, expired_clock = _config(workspace / "expired")
        expired_challenge = create_pairing_challenge(
            expired_config,
            clock=expired_clock,
            token_factory=lambda: "0123456789abcdefghijklmn",
            contract_root=root,
        )
        expired_controller = QQGroupPairingController(
            expired_config, expired_journal, expired_challenge, clock=expired_clock
        )
        expired_clock.value += timedelta(minutes=6)
        try:
            expired_controller.accept(_event(expired_challenge.plaintext))
        except QQPairingEventRejected as error:
            assert error.reason_code == "pairing_challenge_expired"
        else:
            raise AssertionError("expired challenge accepted")

        race_config, race_journal, race_clock = _config(workspace / "race")
        race_challenge = create_pairing_challenge(
            race_config,
            clock=race_clock,
            token_factory=lambda: "raceabcdefghijklmnopqrst",
            contract_root=root,
        )
        race_controller = QQGroupPairingController(
            race_config, race_journal, race_challenge, clock=race_clock
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: race_controller.accept(_event(race_challenge.plaintext)), range(2)
                )
            )
        assert results[0] == results[1] and race_journal.safe_counts()["completion_count"] == 1

        restart_config, restart_journal, restart_clock = _config(workspace / "restart")
        pending = create_pairing_challenge(
            restart_config,
            clock=restart_clock,
            token_factory=lambda: "pendingabcdefghijklmnopqr",
            contract_root=root,
        )
        QQGroupPairingController(restart_config, restart_journal, pending, clock=restart_clock)
        restarted = create_pairing_challenge(
            restart_config,
            clock=restart_clock,
            token_factory=lambda: "restartabcdefghijklmnopq",
            contract_root=root,
        )
        restarted_controller = QQGroupPairingController(
            restart_config, restart_journal, restarted, clock=restart_clock
        )
        restarted_completion = restarted_controller.accept(_event(restarted.plaintext))
        assert SQLiteQQPairingJournal(restart_config.store_path, clock=restart_clock).resolve(
            str(restarted_completion["pairing_id"]), app_id_hash=restart_config.app_id_hash
        )

        selector = resolve_stage1_pairing_environment(
            {
                "WEFLOW_QQ_APP_ID": config.app_id,
                "WEFLOW_QQ_CLIENT_SECRET": config.client_secret,
                "WEFLOW_QQ_SANDBOX_PAIRING_ID": str(completion["pairing_id"]),
                "WEFLOW_QQ_IDENTITY_SALT": "process-only-salt",
                "WEFLOW_QQ_CAPABILITIES": "qq.group_at.read,qq.passive_ack.execute",
            },
            store_path=config.store_path,
            clock=clock,
        )
        assert (
            selector["WEFLOW_QQ_SANDBOX_GROUP_OPENID"] == "offline-pair-group"
            and selector["WEFLOW_QQ_TENANT_ID"] == "tenant-pairing"
        )
        journal.revoke(str(completion["pairing_id"]))
        try:
            journal.resolve(str(completion["pairing_id"]), app_id_hash=config.app_id_hash)
        except QQPairingJournalError as error:
            assert error.reason_code == "pairing_locator_not_current"
        else:
            raise AssertionError("revoked locator resolved")

        stage1 = QQSandboxConfig(
            "offline-pair-app",
            "not-a-real-secret",
            "offline-pair-group",
            "tenant-pairing",
            "identity-salt",
        )
        try:
            normalize_qq_group_at_event(
                _event(challenge.plaintext),
                stage1,
                received_at=NOW + timedelta(seconds=1),
                contract_root=root,
            )
        except QQEventRejected as error:
            assert error.reason_code == "qq_pairing_control_message_reserved"
        else:
            raise AssertionError("pairing control message reached intake")

        report = build_pairing_report(
            restarted_completion,
            mode="offline-fake",
            observed=1,
            rejected=7,
            duplicates=2,
            contract_root=root,
        )
        verify_pairing_report(report, expected_mode="offline-fake", contract_root=root)
        return report


__all__ = ["run_qq_group_pairing_offline_acceptance"]
