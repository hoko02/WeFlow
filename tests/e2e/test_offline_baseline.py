import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.py"


def run_dev(*arguments: str, expected: int) -> dict[str, object]:
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


def collect_offline_baseline() -> dict[str, object]:
    run_dev("down", expected=0)
    try:
        run_dev("up", "--mode", "offline", expected=0)
        return run_dev("health", expected=0)
    finally:
        run_dev("down", expected=0)


def test_repeated_offline_health_baselines_have_identical_deterministic_fields() -> None:
    first = collect_offline_baseline()
    second = collect_offline_baseline()

    assert first == second
    assert first["operational_ready"] is True
    assert first["business_workflow_implemented"] is False
    assert first["external_writes_enabled"] is False
    assert "pid" not in json.dumps(first, sort_keys=True).lower()
