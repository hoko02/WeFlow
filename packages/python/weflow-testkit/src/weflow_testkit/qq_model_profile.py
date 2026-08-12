"""Strict checked-in profile loading for the bounded QQ model workflow."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .live_evaluation import (
    LiveEvaluationValidationError,
    LoadedLiveSuite,
    canonical_sha256,
    load_live_pilot_suite,
)

JsonObject = dict[str, Any]

QQ_STAGE3_PROFILE_ID = "qq-stage3-api-503.v1"
QQ_STAGE3_PROFILE_PATH = "evals/qq-model/stage3-api-503-profile.v1.json"
QQ_STAGE3_REQUIRED_QQ_CAPABILITIES = (
    "qq.group_at.read",
    "qq.passive_ack.execute",
    "qq.c2c.read",
    "qq.c2c.notification.execute",
    "qq.c2c.passive_reply.execute",
    "qq.handler_approval.decide",
    "qq.final_reply.execute",
)
QQ_STAGE3_REQUIRED_MODEL_CAPABILITIES = (
    "model.proposal.invoke",
    "fixture.crm.read",
    "fixture.monitoring.read",
    "fixture.knowledge.read",
)
QQ_STAGE3_BUDGET_PROFILE_ID = "qq-stage3-case-budget.v1"
QQ_STAGE3_CASE_BUDGET = {
    "provider_call_limit": 6,
    "retry_limit": 1,
    "input_token_limit": 10_000,
    "output_token_limit": 4_000,
    "total_token_limit": 14_000,
    "wall_time_ms": 60_000,
    "request_timeout_ms": 15_000,
    "action_limit": 6,
    "tool_limit": 3,
    "no_progress_limit": 2,
    "estimated_cost_limit": 0.5,
    "currency": "USD",
}


class QQModelProfileError(ValueError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class LoadedQQModelProfile:
    profile: JsonObject
    suite: LoadedLiveSuite
    task_record: JsonObject
    budget_profile: JsonObject

    @property
    def profile_sha256(self) -> str:
        return str(self.profile["profile_sha256"])


def qq_model_id_sha256(profile: Mapping[str, Any]) -> str:
    return hashlib.sha256(str(profile["provider"]["model"]).encode("utf-8")).hexdigest()


def qq_model_provider_profile_sha256(profile: Mapping[str, Any]) -> str:
    provider = profile["provider"]
    host = urlsplit(str(provider["endpoint"])).hostname
    if not host:
        raise QQModelProfileError("stage3_provider_endpoint_invalid")
    material = {
        "provider_mode": provider["mode"],
        "endpoint_host_sha256": hashlib.sha256(host.encode("utf-8")).hexdigest(),
        "model_id_sha256": qq_model_id_sha256(profile),
        "price_profile_sha256": profile["price_reference"]["profile_sha256"],
    }
    return canonical_sha256(material)


def _duplicates(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise QQModelProfileError("stage3_profile_duplicate_key")
        result[key] = value
    return result


def _read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_duplicates)
    except QQModelProfileError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QQModelProfileError("stage3_profile_invalid") from error
    if not isinstance(value, dict):
        raise QQModelProfileError("stage3_profile_invalid")
    return value


def _resolve(root: Path, reference: Mapping[str, Any]) -> JsonObject:
    raw = reference.get("path")
    if not isinstance(raw, str) or "\\" in raw:
        raise QQModelProfileError("stage3_source_path_unsafe")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise QQModelProfileError("stage3_source_path_unsafe")
    resolved = (root / Path(*relative.parts)).resolve()
    allowed = (root / "evals").resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as error:
        raise QQModelProfileError("stage3_source_path_unsafe") from error
    payload = _read_json(resolved)
    expected = reference.get("file_sha256", reference.get("sha256"))
    if expected != canonical_sha256(payload):
        raise QQModelProfileError("stage3_source_hash_mismatch")
    return payload


def _exact_keys(payload: Mapping[str, Any], expected: set[str]) -> None:
    if set(payload) != expected:
        raise QQModelProfileError("stage3_profile_shape_invalid")


def load_qq_model_profile(
    root: Path,
    *,
    profile_path: str = QQ_STAGE3_PROFILE_PATH,
    now: datetime | None = None,
) -> LoadedQQModelProfile:
    """Validate all non-secret Stage 3 sources before endpoint or credential access."""

    repository_root = root.resolve()
    reference = {"path": profile_path}
    raw = reference["path"]
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise QQModelProfileError("stage3_profile_path_unsafe")
    profile_file = (repository_root / Path(*relative.parts)).resolve()
    allowed = (repository_root / "evals" / "qq-model").resolve()
    try:
        profile_file.relative_to(allowed)
    except ValueError as error:
        raise QQModelProfileError("stage3_profile_path_unsafe") from error
    profile = _read_json(profile_file)
    _exact_keys(
        profile,
        {
            "profile_id",
            "version",
            "classification",
            "tenant_resource",
            "selected_task_id",
            "suite_reference",
            "source_references",
            "prompt_reference",
            "policy_reference",
            "budget_reference",
            "price_reference",
            "provider",
            "qq_capabilities",
            "model_capabilities",
            "retention_seconds",
            "case_budget",
            "profile_sha256",
        },
    )
    if profile.get("profile_sha256") != canonical_sha256(
        {key: value for key, value in profile.items() if key != "profile_sha256"}
    ):
        raise QQModelProfileError("stage3_profile_hash_mismatch")
    if (
        profile.get("profile_id") != QQ_STAGE3_PROFILE_ID
        or profile.get("version") != "v1"
        or profile.get("classification") != "controlled-synthetic-qq"
        or profile.get("tenant_resource") != "current-paired-sandbox-tenant"
        or profile.get("selected_task_id") != "grounded-response-ready"
        or tuple(profile.get("qq_capabilities", ())) != QQ_STAGE3_REQUIRED_QQ_CAPABILITIES
        or tuple(profile.get("model_capabilities", ())) != QQ_STAGE3_REQUIRED_MODEL_CAPABILITIES
        or profile.get("retention_seconds") != 86_400
    ):
        raise QQModelProfileError("stage3_profile_scope_denied")
    for reference_value in (
        profile["suite_reference"],
        *profile["source_references"],
        profile["prompt_reference"],
        profile["policy_reference"],
        profile["price_reference"],
    ):
        _resolve(repository_root, reference_value)
    stage3_budget_profile = _resolve(repository_root, profile["budget_reference"])
    if stage3_budget_profile != {
        "budget_profile_id": QQ_STAGE3_BUDGET_PROFILE_ID,
        "version": "v1",
        **QQ_STAGE3_CASE_BUDGET,
        "thinking_mode": "disabled",
        "temperature": 0,
        "top_p": 1,
    }:
        raise QQModelProfileError("stage3_budget_profile_invalid")
    try:
        suite = load_live_pilot_suite(repository_root, now=now or datetime.now(UTC))
    except LiveEvaluationValidationError as error:
        raise QQModelProfileError(str(error)) from error
    selected = next(
        (
            record
            for record in suite.records
            if record["task"]["task_id"] == profile["selected_task_id"]
        ),
        None,
    )
    if selected is None:
        raise QQModelProfileError("stage3_task_missing")
    source_references = [selected["task"]["context_source"]]
    source_references.extend(
        selected["task"]["tool_sources"][tool] for tool in ("crm", "monitoring", "knowledge")
    )
    if source_references != profile["source_references"]:
        raise QQModelProfileError("stage3_source_binding_mismatch")
    if (
        selected["task"]["prompt_template"] != profile["prompt_reference"]
        or selected["task"]["policy_profile"] != profile["policy_reference"]
        or selected["task"]["price_profile"]
        != {
            key: profile["price_reference"][key]
            for key in ("price_profile_id", "path", "profile_sha256")
        }
    ):
        raise QQModelProfileError("stage3_profile_binding_mismatch")
    provider = profile["provider"]
    if (
        set(provider) != {"mode", "model", "endpoint", "inference_mode"}
        or provider["mode"] != "openai-compatible"
        or provider["model"] != suite.price_profile["model_pattern"]
        or provider["endpoint"] != "https://api.deepseek.com"
        or provider["inference_mode"] != stage3_budget_profile["thinking_mode"]
        or provider["inference_mode"] != "disabled"
        or profile["case_budget"] != QQ_STAGE3_CASE_BUDGET
    ):
        raise QQModelProfileError("stage3_provider_or_budget_mismatch")
    return LoadedQQModelProfile(
        profile,
        suite,
        dict(selected),
        dict(stage3_budget_profile),
    )


__all__ = [
    "LoadedQQModelProfile",
    "QQModelProfileError",
    "QQ_STAGE3_BUDGET_PROFILE_ID",
    "QQ_STAGE3_CASE_BUDGET",
    "QQ_STAGE3_PROFILE_ID",
    "QQ_STAGE3_PROFILE_PATH",
    "QQ_STAGE3_REQUIRED_MODEL_CAPABILITIES",
    "QQ_STAGE3_REQUIRED_QQ_CAPABILITIES",
    "load_qq_model_profile",
    "qq_model_id_sha256",
    "qq_model_provider_profile_sha256",
]
