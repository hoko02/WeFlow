import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from qq_group_pairing_acceptance import run_qq_group_pairing_offline_acceptance  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_pairing_acceptance_is_stable_and_has_zero_effects() -> None:
    first = run_qq_group_pairing_offline_acceptance(ROOT)
    second = run_qq_group_pairing_offline_acceptance(ROOT)
    assert first == second
    assert first["accepted"] is True and first["fake_pairing_verified"] is True
    assert first["qq_group_pairing_live_verified"] is False
    assert all(
        first[field] is False
        for field in (
            "case_creation",
            "workflow_activation",
            "qq_write_attempted",
            "acknowledgement_sent",
            "model_invocation",
            "stage1_verified",
        )
    )
