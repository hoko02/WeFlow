from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_testkit.live_evaluation import canonical_sha256
from weflow_testkit.qq_model_profile import (
    QQ_STAGE3_BUDGET_PROFILE_ID,
    QQ_STAGE3_REQUIRED_MODEL_CAPABILITIES,
    QQ_STAGE3_REQUIRED_QQ_CAPABILITIES,
    QQModelProfileError,
    load_qq_model_profile,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 12, tzinfo=UTC)


def _copy_evals(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "evals", root / "evals")
    return root


def test_reviewed_stage3_profile_binds_exact_sources_capabilities_and_budget() -> None:
    loaded = load_qq_model_profile(ROOT, now=NOW)
    profile = loaded.profile
    assert tuple(profile["qq_capabilities"]) == QQ_STAGE3_REQUIRED_QQ_CAPABILITIES
    assert tuple(profile["model_capabilities"]) == QQ_STAGE3_REQUIRED_MODEL_CAPABILITIES
    assert profile["provider"] == {
        "mode": "openai-compatible",
        "model": "deepseek-v4-flash",
        "endpoint": "https://api.deepseek.com",
        "inference_mode": "disabled",
    }
    assert profile["case_budget"]["provider_call_limit"] == 6
    assert profile["case_budget"]["estimated_cost_limit"] == 0.5
    assert profile["budget_reference"]["budget_profile_id"] == QQ_STAGE3_BUDGET_PROFILE_ID
    assert loaded.budget_profile["estimated_cost_limit"] == 0.5
    assert loaded.suite.budget_profile["estimated_cost_limit"] == 0.02
    assert loaded.task_record["task"]["task_id"] == "grounded-response-ready"


def test_rehashed_unreviewed_stage3_budget_is_rejected_without_changing_evaluation(
    tmp_path: Path,
) -> None:
    root = _copy_evals(tmp_path)
    budget_path = root / "evals/qq-model/stage3-case-budget.v1.json"
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    budget["estimated_cost_limit"] = 0.51
    budget_path.write_text(json.dumps(budget), encoding="utf-8")

    profile_path = root / "evals/qq-model/stage3-api-503-profile.v1.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["budget_reference"]["sha256"] = canonical_sha256(budget)
    profile["case_budget"]["estimated_cost_limit"] = 0.51
    profile["profile_sha256"] = canonical_sha256(
        {key: value for key, value in profile.items() if key != "profile_sha256"}
    )
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    with pytest.raises(QQModelProfileError, match="stage3_budget_profile_invalid"):
        load_qq_model_profile(root, now=NOW)


def test_profile_rejects_duplicate_keys_before_source_or_secret_access(tmp_path: Path) -> None:
    root = _copy_evals(tmp_path)
    profile = root / "evals/qq-model/stage3-api-503-profile.v1.json"
    text = profile.read_text(encoding="utf-8")
    profile.write_text(text.replace("{", '{\n  "profile_id": "duplicate",', 1), encoding="utf-8")
    with pytest.raises(QQModelProfileError, match="stage3_profile_duplicate_key"):
        load_qq_model_profile(root, now=NOW)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (("provider", "endpoint", "http://127.0.0.1"), "stage3_profile_hash_mismatch"),
        (("provider", "model", "unreviewed-model"), "stage3_profile_hash_mismatch"),
        (("provider", "inference_mode", "provider_default"), "stage3_profile_hash_mismatch"),
        (("qq_capabilities", 0, "qq.arbitrary.send"), "stage3_profile_hash_mismatch"),
        (("model_capabilities", 0, "model.arbitrary.invoke"), "stage3_profile_hash_mismatch"),
    ],
)
def test_mutated_profile_fails_closed_before_client_construction(
    tmp_path: Path,
    mutation: tuple[str, str | int, str],
    reason: str,
) -> None:
    root = _copy_evals(tmp_path)
    path = root / "evals/qq-model/stage3-api-503-profile.v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    section, field, value = mutation
    payload[section][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QQModelProfileError, match=reason):
        load_qq_model_profile(root, now=NOW)


def test_profile_path_escape_and_stale_price_are_rejected() -> None:
    with pytest.raises(QQModelProfileError, match="stage3_profile_path_unsafe"):
        load_qq_model_profile(ROOT, profile_path="../outside.json", now=NOW)
    with pytest.raises(QQModelProfileError, match="live_price_profile_stale_or_mismatched"):
        load_qq_model_profile(ROOT, now=datetime(2026, 10, 1, tzinfo=UTC))
