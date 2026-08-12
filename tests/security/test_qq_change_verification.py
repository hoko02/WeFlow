from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qq_sandbox_acceptance import validate_qq_acceptance_report  # noqa: E402

OFFLINE = ROOT / "reports" / "add-qq-sandbox-intake-and-ack-offline-acceptance.json"
VALIDATION = ROOT / "reports" / "add-qq-sandbox-intake-and-ack-openspec-validation.json"
VERIFICATION = ROOT / "reports" / "add-qq-sandbox-intake-and-ack-change-verification.json"


def test_qq_change_verification_is_source_backed_and_truthful() -> None:
    offline = json.loads(OFFLINE.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    verification = json.loads(VERIFICATION.read_text(encoding="utf-8"))

    validate_qq_acceptance_report(offline, expected_mode="offline")
    assert validation["summary"]["totals"] == {"failed": 0, "items": 1, "passed": 1}
    assert verification["verified"] is True
    assert verification["change_complete"] is False
    assert verification["pending_live_tasks"] == ["5.2", "5.3"]
    assert verification["fake_transport_verified"] is True
    assert verification["qq_sandbox_live_verified"] is False
    assert verification["customer_receipt_verified"] is False
    assert verification["case_completion"] is False
    assert verification["production_ready"] is False
    assert verification["tests"]["full_python_passed"] == 488
    assert verification["tests"]["qq_focused_passed"] == 89
    assert verification["checks"]["secret_hygiene_findings"] == 0
    assert verification["offline_acceptance"]["stable_report_sha256"] == hashlib.sha256(
        OFFLINE.read_bytes()
    ).hexdigest()


def test_qq_verification_reports_contain_no_private_runtime_values() -> None:
    rendered = OFFLINE.read_text(encoding="utf-8") + VERIFICATION.read_text(encoding="utf-8")
    for forbidden in (
        "广告系统出现了API 503错误",
        "group_openid",
        "member_openid",
        "access_token",
        "client_secret",
        "authorization",
        "AppSecret",
    ):
        assert forbidden not in rendered
