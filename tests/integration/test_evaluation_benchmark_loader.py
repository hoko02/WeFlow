from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import weflow_testkit.evaluation_benchmark as benchmark
from weflow_contracts.evaluation import canonical_sha256
from weflow_testkit.evaluation_benchmark import (
    BenchmarkValidationError,
    load_offline_seed_suite,
)

ROOT = Path(__file__).resolve().parents[2]


def _isolated_root(tmp_path: Path) -> Path:
    isolated = tmp_path / "repo"
    for name in ("contracts", "evals", "fixtures"):
        shutil.copytree(ROOT / name, isolated / name)
    return isolated


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assert_pre_store_failure(
    root: Path, monkeypatch: pytest.MonkeyPatch, reason_code: str
) -> None:
    connection_attempts: list[Path] = []

    def unexpected_connect(path: Path) -> None:
        connection_attempts.append(path)
        raise AssertionError("task_store_created_before_source_validation")

    monkeypatch.setattr(benchmark.sqlite3, "connect", unexpected_connect)
    with pytest.raises(BenchmarkValidationError, match=reason_code):
        benchmark.run_offline_seed_suite(root)
    assert connection_attempts == []


def test_seed_tasks_bind_safe_fixture_and_policy_sources() -> None:
    suite, records = load_offline_seed_suite(ROOT)

    assert suite["profile"] == "benchmark-core.v1"
    for record in records:
        task = record["task"]
        assert record["fixture"]["fixture_id"] == task["fixture_source_id"]
        assert canonical_sha256(record["fixture"]) == task["fixture_sha256"]
        assert record["policy"]["policy_id"] == task["policy_source_id"]
        assert canonical_sha256(record["policy"]) == task["policy_sha256"]
        assert record["fixture_source_path"] == task["fixture_source_path"]
        assert record["policy_source_path"] == task["policy_source_path"]
        assert not Path(record["fixture_source_path"]).is_absolute()
        assert ".." not in Path(record["fixture_source_path"]).parts


def test_changed_fixture_source_fails_before_store_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated = _isolated_root(tmp_path)
    source = isolated / "fixtures" / "intake" / "api-503-first-delivery.json"
    value = json.loads(source.read_text(encoding="utf-8"))
    value["synthetic_mutation"] = True
    _write_json(source, value)

    _assert_pre_store_failure(isolated, monkeypatch, "benchmark_source_hash_mismatch")


def test_source_path_escape_fails_before_store_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated = _isolated_root(tmp_path)
    task_path = isolated / "evals" / "tasks" / "intake-accepted" / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["fixture_source_path"] = "fixtures/../evals/sources/offline-policy.v1.json"
    _write_json(task_path, task)

    _assert_pre_store_failure(isolated, monkeypatch, "benchmark_source_path_unsafe")


def test_missing_source_fails_before_store_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated = _isolated_root(tmp_path)
    task_path = isolated / "evals" / "tasks" / "intake-accepted" / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["fixture_source_path"] = "fixtures/intake/missing.json"
    _write_json(task_path, task)

    _assert_pre_store_failure(isolated, monkeypatch, "benchmark_source_invalid")


def test_task_local_mirror_fails_before_store_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated = _isolated_root(tmp_path)
    mirror = isolated / "evals" / "tasks" / "intake-accepted" / "fixture.json"
    _write_json(mirror, {"fixture_id": "self-consistent-mirror"})

    _assert_pre_store_failure(
        isolated, monkeypatch, "benchmark_task_local_mirror_forbidden"
    )
