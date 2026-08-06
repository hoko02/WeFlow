from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_testkit.live_evaluation import (
    LIVE_TASK_IDS,
    LiveEvaluationValidationError,
    canonical_sha256,
    load_live_pilot_suite,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 6, tzinfo=UTC)


def _copy_live_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "evals", root / "evals")
    shutil.copytree(ROOT / "contracts", root / "contracts")
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    return root


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rehash_task(root: Path, task_id: str) -> None:
    suite_path = root / "evals" / "suites" / "live-pilot.v1.json"
    suite = _read(suite_path)
    reference = next(item for item in suite["tasks"] if item["task_id"] == task_id)
    task = _read(root / reference["path"])
    reference["sha256"] = canonical_sha256(task)
    _write(suite_path, suite)


def test_live_pilot_loads_exactly_six_tasks_and_thirty_attempts() -> None:
    loaded = load_live_pilot_suite(ROOT, now=NOW)

    assert tuple(record["task"]["task_id"] for record in loaded.records) == LIVE_TASK_IDS
    assert len(loaded.records) == 6
    assert len(loaded.attempt_ids) == len(set(loaded.attempt_ids)) == 30
    assert all(record["task"]["attempt_count"] == 5 for record in loaded.records)
    assert loaded.price_profile["model_pattern"] == "deepseek-v4-flash"
    assert loaded.budget_profile["thinking_mode"] == "disabled"


def test_live_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    root = _copy_live_tree(tmp_path)
    suite_path = root / "evals" / "suites" / "live-pilot.v1.json"
    raw = suite_path.read_text(encoding="utf-8")
    suite_path.write_text(raw.replace("{", '{\n  "suite_id": "duplicate",', 1))

    with pytest.raises(LiveEvaluationValidationError, match="duplicate_key"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_path_escape_before_store_creation(tmp_path: Path) -> None:
    root = _copy_live_tree(tmp_path)
    suite_path = root / "evals" / "suites" / "live-pilot.v1.json"
    suite = _read(suite_path)
    suite["tasks"][0]["path"] = "../outside/task.json"
    _write(suite_path, suite)

    with pytest.raises(LiveEvaluationValidationError, match="path_unsafe"):
        load_live_pilot_suite(root, now=NOW)
    assert not tuple(root.rglob("*.sqlite3"))


def test_live_loader_rejects_source_hash_mutation(tmp_path: Path) -> None:
    root = _copy_live_tree(tmp_path)
    source_path = root / "evals" / "live" / "sources" / "crm-grounded.v1.json"
    source = _read(source_path)
    source["summary"] = "Mutated synthetic summary."
    _write(source_path, source)

    with pytest.raises(LiveEvaluationValidationError, match="hash_mismatch"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_secret_like_source_before_hash_comparison(
    tmp_path: Path,
) -> None:
    root = _copy_live_tree(tmp_path)
    source_path = root / "evals" / "live" / "sources" / "crm-grounded.v1.json"
    source = _read(source_path)
    source["summary"] = "sk-" + "unit-test-secret-sentinel"
    _write(source_path, source)

    with pytest.raises(LiveEvaluationValidationError, match="secret_like"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_private_tool_classification_even_when_rehashed(
    tmp_path: Path,
) -> None:
    root = _copy_live_tree(tmp_path)
    source_path = root / "evals" / "live" / "sources" / "knowledge-grounded.v1.json"
    source = _read(source_path)
    source["classification"] = "private"
    _write(source_path, source)
    source_hash = canonical_sha256(source)
    task_ids = (
        "grounded-response-ready",
        "missing-information",
        "conflicting-evidence",
        "tool-timeout",
        "budget-exhaustion",
    )
    for task_id in task_ids:
        task_path = root / "evals" / "live" / "tasks" / task_id / "task.json"
        task = _read(task_path)
        task["tool_sources"]["knowledge"]["sha256"] = source_hash
        _write(task_path, task)
        _rehash_task(root, task_id)

    with pytest.raises(LiveEvaluationValidationError, match="tool_source_invalid"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_task_selected_budget_even_when_rehashed(
    tmp_path: Path,
) -> None:
    root = _copy_live_tree(tmp_path)
    task_id = "budget-exhaustion"
    task_path = root / "evals" / "live" / "tasks" / task_id / "task.json"
    task = _read(task_path)
    task["provider_call_limit"] = 100
    _write(task_path, task)
    _rehash_task(root, task_id)

    with pytest.raises(LiveEvaluationValidationError, match="task_invalid"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_task_selected_endpoint_even_when_rehashed(tmp_path: Path) -> None:
    root = _copy_live_tree(tmp_path)
    task_id = "grounded-response-ready"
    task_path = root / "evals" / "live" / "tasks" / task_id / "task.json"
    task = _read(task_path)
    task["endpoint"] = "https://fixture.example"
    _write(task_path, task)
    _rehash_task(root, task_id)

    with pytest.raises(LiveEvaluationValidationError, match="task_invalid"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_cross_tenant_task_even_when_rehashed(tmp_path: Path) -> None:
    root = _copy_live_tree(tmp_path)
    task_id = "missing-information"
    task_path = root / "evals" / "live" / "tasks" / task_id / "task.json"
    task = _read(task_path)
    task["tenant_id"] = "tenant-foreign"
    _write(task_path, task)
    _rehash_task(root, task_id)

    with pytest.raises(LiveEvaluationValidationError, match="task_invalid"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_detached_oracle_even_when_links_are_rehashed(
    tmp_path: Path,
) -> None:
    root = _copy_live_tree(tmp_path)
    task_id = "tool-timeout"
    oracle_path = root / "evals" / "live" / "tasks" / task_id / "oracle.json"
    task_path = root / "evals" / "live" / "tasks" / task_id / "task.json"
    oracle = _read(oracle_path)
    oracle["task_id"] = "another-task"
    _write(oracle_path, oracle)
    task = _read(task_path)
    task["oracle_sha256"] = canonical_sha256(oracle)
    _write(task_path, task)
    _rehash_task(root, task_id)

    with pytest.raises(LiveEvaluationValidationError, match="oracle_invalid"):
        load_live_pilot_suite(root, now=NOW)


def test_live_loader_rejects_stale_price_profile() -> None:
    with pytest.raises(LiveEvaluationValidationError, match="stale_or_mismatched"):
        load_live_pilot_suite(ROOT, now=datetime(2026, 10, 1, tzinfo=UTC))
