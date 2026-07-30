import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def _run_dev(*arguments: str, expected: int) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(DEV), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert completed.returncode == expected, completed.stdout
    return json.loads(completed.stdout)


def test_offline_skeletons_restart_without_business_state_or_side_effects() -> None:
    _run_dev("down", expected=0)
    try:
        first_start = _run_dev("up", "--mode", "offline", expected=0)
        first_health = _run_dev("health", expected=0)
        stop = _run_dev("down", expected=0)
        stopped_health = _run_dev("health", expected=2)
        second_start = _run_dev("up", "--mode", "offline", expected=0)
        second_health = _run_dev("health", expected=0)

        assert first_start["started"] is True
        assert second_start["started"] is True
        assert stop["stopped"] is True
        assert stopped_health["operational_ready"] is False
        for report in (first_health, second_health):
            assert report["operational_ready"] is True
            assert report["business_workflow_implemented"] is False
            assert report["external_writes_enabled"] is False
            assert all(service["ready"] for service in report["services"])
            assert all(
                "no-business-workflow" in service["limitations"] for service in report["services"]
            )
    finally:
        _run_dev("down", expected=0)
