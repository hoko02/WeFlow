from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_control_kernel.ledger import FixedClock, SQLiteCaseLedger
from weflow_control_kernel.qq_sandbox import (
    QQSandboxConfig,
    QQSandboxIntakeService,
    SQLiteQQSandboxJournal,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 10, 0, 0, 1, tzinfo=UTC)


def _config() -> QQSandboxConfig:
    return QQSandboxConfig(
        app_id="qq-app-sandbox",
        client_secret="not-a-real-secret",
        group_openid="qq-group-sandbox",
        tenant_id="tenant-alpha",
        identity_salt="process-only-identity-salt",
    )


def _event() -> dict[str, object]:
    return {
        "op": 0,
        "t": "GROUP_AT_MESSAGE_CREATE",
        "s": 42,
        "d": {
            "id": "qq-message-concurrent-001",
            "group_openid": "qq-group-sandbox",
            "author": {"member_openid": "qq-member-customer"},
            "content": "广告系统出现了API 503错误",
            "timestamp": "2026-08-10T00:00:00Z",
        },
    }


def _service(path: Path):
    clock = FixedClock(NOW)
    ledger = SQLiteCaseLedger(path, clock=clock, contract_root=ROOT)
    journal = SQLiteQQSandboxJournal(path, clock=clock, contract_root=ROOT)
    return (
        ledger,
        journal,
        QQSandboxIntakeService(
            ledger,
            journal,
            _config(),
            clock=clock,
            contract_root=ROOT,
        ),
    )


def test_concurrent_qq_consumers_create_one_case_and_one_intent(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.sqlite3"
    ledger, journal, service = _service(path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.accept(_event()), range(2)))

    assert sorted(result.intake.disposition for result in results) == [
        "accepted",
        "deduplicated",
    ]
    assert len({result.intake.case_id for result in results}) == 1
    assert len({result.intent["intent_id"] for result in results}) == 1
    assert ledger.source_counts("tenant-alpha")["cases"] == 1
    assert journal.safe_counts("tenant-alpha")["acknowledgement_intent_count"] == 1


def test_qq_source_failure_rolls_back_without_case_cursor_or_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rollback.sqlite3"
    ledger, journal, service = _service(path)

    def fail_projection(*_args, **_kwargs):
        raise RuntimeError("injected-projection-failure")

    monkeypatch.setattr(ledger, "_projection_from_records", fail_projection)
    with pytest.raises(RuntimeError, match="injected-projection-failure"):
        service.accept(_event())

    assert ledger.source_counts("tenant-alpha") == {
        "inbound_receipts": 0,
        "cases": 0,
        "case_revisions": 0,
        "business_events": 0,
        "case_projection": 0,
    }
    assert journal.safe_counts("tenant-alpha") == {
        "gateway_cursor_count": 0,
        "acknowledgement_intent_count": 0,
        "acknowledgement_observation_count": 0,
        "acknowledgement_completion_count": 0,
    }


def test_qq_case_reads_remain_tenant_scoped_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "tenant.sqlite3"
    ledger, _, service = _service(path)
    accepted = service.accept(_event())

    restarted = SQLiteCaseLedger(path, clock=FixedClock(NOW), contract_root=ROOT)
    assert restarted.get_case_projection("tenant-alpha", accepted.intake.case_id) is not None
    assert restarted.get_case_projection("tenant-bravo", accepted.intake.case_id) is None
    assert restarted.list_case_revisions("tenant-bravo", accepted.intake.case_id) == []
    assert restarted.list_case_events("tenant-bravo", accepted.intake.case_id) == []
