from pathlib import Path

import pytest
from weflow_control_kernel.qq_pairing import (
    QQPairingError,
    build_pairing_report,
    reject_pairing_configuration_for_ordinary_command,
    verify_pairing_report,
)

ROOT = Path(__file__).resolve().parents[2]


def test_ordinary_command_rejects_pairing_activation() -> None:
    with pytest.raises(ValueError):
        reject_pairing_configuration_for_ordinary_command(
            {"WEFLOW_QQ_SANDBOX_PAIRING_ID": "qqpair_" + "1" * 32}
        )


def test_fake_report_cannot_claim_live_or_leak_raw_values() -> None:
    completion = {
        "status": "COMPLETED",
        "pairing_id": "qqpair_" + "1" * 32,
        "app_id_hash": "a" * 64,
        "group_openid_hash": "b" * 64,
        "tenant_id_hash": "c" * 64,
        "reason_code": "pairing_exact_challenge_completed",
    }
    report = build_pairing_report(
        completion, mode="offline-fake", observed=1, rejected=0, contract_root=ROOT
    )
    report["qq_group_pairing_live_verified"] = True
    with pytest.raises(Exception):
        verify_pairing_report(report, expected_mode="offline-fake", contract_root=ROOT)
    unsafe = build_pairing_report(
        completion, mode="offline-fake", observed=1, rejected=0, contract_root=ROOT
    )
    unsafe["group_openid"] = "raw"
    with pytest.raises(QQPairingError):
        verify_pairing_report(unsafe, expected_mode="offline-fake", contract_root=ROOT)
