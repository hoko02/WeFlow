"""Safe source loading and command-scoped configuration for live-model evaluation."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from weflow_contracts.live import validate_provider_price_profile

JsonObject = dict[str, Any]
AddressResolver = Callable[[str, int], Sequence[str]]

LIVE_SUITE_ID = "live-pilot.v1"
LIVE_TASK_IDS = (
    "grounded-response-ready",
    "missing-information",
    "conflicting-evidence",
    "prompt-injection",
    "tool-timeout",
    "budget-exhaustion",
)
LIVE_CREDENTIAL_ENVIRONMENT_VARIABLE = "WEFLOW_LIVE_MODEL_API_KEY"
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SECRET_KEY_MARKERS = (
    "api_key",
    "access_token",
    "auth_token",
    "provider_token",
    "secret",
    "password",
    "credential",
    "authorization_header",
    "raw_provider_body",
)
_SECRET_VALUE_RE = re.compile(r"(?:\bBearer\s+[A-Za-z0-9._-]+|\bsk-[A-Za-z0-9_-]{8,})")
_ALLOWED_TASK_KINDS = frozenset(
    {
        "grounded_response_ready",
        "missing_information",
        "conflicting_evidence",
        "prompt_injection",
        "tool_timeout",
        "budget_exhaustion",
    }
)
_ALLOWED_OUTCOMES = frozenset(
    {
        "response_ready",
        "needs_information",
        "needs_operator",
        "tool_timeout",
        "budget_exhausted",
        "malformed_model_output",
        "policy_denied",
        "provider_outcome_unknown",
    }
)


class LiveEvaluationValidationError(ValueError):
    """A redacted pre-contact source/configuration failure."""


class LiveConfigurationDenied(ValueError):
    """Command-scoped denial that never includes operator or credential values."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"live_evaluation_denied:{reason_code}")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    loaded: JsonObject = {}
    for key, value in pairs:
        if key in loaded:
            raise LiveEvaluationValidationError("live_input_duplicate_key")
        loaded[key] = value
    return loaded


def _load_json(path: Path) -> JsonObject:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LiveEvaluationValidationError("live_input_invalid") from error
    if not isinstance(payload, dict):
        raise LiveEvaluationValidationError("live_input_invalid")
    return payload


def _safe_tree(value: object, *, depth: int = 0) -> None:
    if depth > 8:
        raise LiveEvaluationValidationError("live_input_excessive")
    if isinstance(value, Mapping):
        if len(value) > 32:
            raise LiveEvaluationValidationError("live_input_excessive")
        for key, item in value.items():
            if not isinstance(key, str) or any(
                marker in key.lower() for marker in _SECRET_KEY_MARKERS
            ):
                raise LiveEvaluationValidationError("live_input_secret_like")
            _safe_tree(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 32:
            raise LiveEvaluationValidationError("live_input_excessive")
        for item in value:
            _safe_tree(item, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 1600:
            raise LiveEvaluationValidationError("live_input_excessive")
        if _SECRET_VALUE_RE.search(value):
            raise LiveEvaluationValidationError("live_input_secret_like")


def _safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value:
        raise LiveEvaluationValidationError("live_source_path_unsafe")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise LiveEvaluationValidationError("live_source_path_unsafe")
    return path


def _resolve_json(
    root: Path,
    reference: Mapping[str, Any],
    *,
    allowed_root: str = "evals/live",
    hash_field: str = "sha256",
) -> JsonObject:
    path = _safe_relative_path(reference.get("path"))
    allowed = (root / allowed_root).resolve()
    resolved = (root / Path(*path.parts)).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as error:
        raise LiveEvaluationValidationError("live_source_path_unsafe") from error
    payload = _load_json(resolved)
    _safe_tree(payload)
    expected_hash = reference.get(hash_field)
    if not isinstance(expected_hash, str) or canonical_sha256(payload) != expected_hash:
        raise LiveEvaluationValidationError("live_source_hash_mismatch")
    return payload


def _require_exact_keys(payload: Mapping[str, Any], keys: set[str], reason: str) -> None:
    if set(payload) != keys:
        raise LiveEvaluationValidationError(reason)


def _validate_prompt(prompt: JsonObject, reference: Mapping[str, Any]) -> None:
    _require_exact_keys(
        prompt,
        {
            "prompt_template_id",
            "version",
            "classification",
            "system_instructions",
            "untrusted_data_label",
            "output_schema_id",
            "max_prompt_characters",
            "max_history_items",
        },
        "live_prompt_invalid",
    )
    if (
        prompt.get("prompt_template_id") != reference.get("prompt_template_id")
        or prompt.get("classification") != "synthetic"
        or prompt.get("untrusted_data_label") != "UNTRUSTED_SYNTHETIC_DATA"
        or not isinstance(prompt.get("system_instructions"), list)
        or not prompt["system_instructions"]
        or not isinstance(prompt.get("max_prompt_characters"), int)
        or not 1 <= prompt["max_prompt_characters"] <= 16000
        or not isinstance(prompt.get("max_history_items"), int)
        or not 1 <= prompt["max_history_items"] <= 12
    ):
        raise LiveEvaluationValidationError("live_prompt_invalid")


def _validate_policy(policy: JsonObject, reference: Mapping[str, Any]) -> None:
    _require_exact_keys(
        policy,
        {
            "policy_profile_id",
            "version",
            "tenant_id",
            "classification",
            "allowed_actions",
            "allowed_tools",
            "external_business_write",
            "approval",
            "delivery",
            "knowledge_publication",
            "multi_agent",
        },
        "live_policy_invalid",
    )
    if (
        policy.get("policy_profile_id") != reference.get("policy_profile_id")
        or policy.get("tenant_id") != "tenant-alpha"
        or policy.get("classification") != "synthetic"
        or policy.get("allowed_tools") != ["crm", "monitoring", "knowledge"]
        or any(
            policy.get(field) is not False
            for field in (
                "external_business_write",
                "approval",
                "delivery",
                "knowledge_publication",
                "multi_agent",
            )
        )
    ):
        raise LiveEvaluationValidationError("live_policy_invalid")


def _validate_budget(budget: JsonObject, reference: Mapping[str, Any]) -> None:
    keys = {
        "budget_profile_id",
        "version",
        "provider_call_limit",
        "retry_limit",
        "input_token_limit",
        "output_token_limit",
        "total_token_limit",
        "wall_time_ms",
        "request_timeout_ms",
        "action_limit",
        "tool_limit",
        "no_progress_limit",
        "estimated_cost_limit",
        "currency",
        "thinking_mode",
        "temperature",
        "top_p",
    }
    _require_exact_keys(budget, keys, "live_budget_invalid")
    positive = keys - {
        "budget_profile_id",
        "version",
        "currency",
        "thinking_mode",
        "temperature",
        "top_p",
        "retry_limit",
    }
    if (
        budget.get("budget_profile_id") != reference.get("budget_profile_id")
        or any(
            isinstance(budget.get(field), bool)
            or not isinstance(budget.get(field), (int, float))
            or budget[field] <= 0
            for field in positive
        )
        or budget.get("retry_limit") != 1
        or budget.get("thinking_mode") != "disabled"
        or budget.get("temperature") != 0
        or budget.get("top_p") != 1
        or budget.get("total_token_limit")
        != budget.get("input_token_limit") + budget.get("output_token_limit")
        or budget.get("request_timeout_ms") > budget.get("wall_time_ms")
        or budget.get("currency") != "USD"
    ):
        raise LiveEvaluationValidationError("live_budget_invalid")


def _validate_tool_source(source: JsonObject, reference: Mapping[str, Any], tool: str) -> None:
    _require_exact_keys(
        source,
        {
            "source_id",
            "version",
            "tenant_id",
            "tool_name",
            "classification",
            "status",
            "summary",
            "facts",
        },
        "live_tool_source_invalid",
    )
    if (
        source.get("source_id") != reference.get("source_id")
        or source.get("tenant_id") != "tenant-alpha"
        or source.get("tool_name") != tool
        or source.get("classification") != "untrusted_synthetic"
        or source.get("status") not in {"available", "missing", "conflicting", "timed_out"}
        or not isinstance(source.get("summary"), str)
        or not isinstance(source.get("facts"), list)
    ):
        raise LiveEvaluationValidationError("live_tool_source_invalid")


def _validate_context_source(source: JsonObject, reference: Mapping[str, Any]) -> None:
    _require_exact_keys(
        source,
        {
            "source_id",
            "version",
            "tenant_id",
            "classification",
            "incident_summary",
            "customer_visible_scope",
            "required_evidence",
        },
        "live_context_source_invalid",
    )
    if (
        source.get("source_id") != reference.get("source_id")
        or source.get("tenant_id") != "tenant-alpha"
        or source.get("classification") != "untrusted_synthetic"
        or source.get("required_evidence") != ["crm", "monitoring", "knowledge"]
    ):
        raise LiveEvaluationValidationError("live_context_source_invalid")


def _validate_oracle(oracle: JsonObject, task: JsonObject) -> None:
    _require_exact_keys(
        oracle,
        {
            "oracle_id",
            "task_id",
            "tenant_id",
            "expected_outcomes",
            "required_hard_gates",
            "quality_weights",
        },
        "live_oracle_invalid",
    )
    weights = oracle.get("quality_weights")
    if (
        oracle.get("task_id") != task.get("task_id")
        or oracle.get("tenant_id") != task.get("tenant_id")
        or oracle.get("expected_outcomes") != task.get("allowed_outcomes")
        or not isinstance(oracle.get("required_hard_gates"), list)
        or len(oracle["required_hard_gates"]) != len(set(oracle["required_hard_gates"]))
        or not isinstance(weights, Mapping)
        or sum(weights.values()) != 100
    ):
        raise LiveEvaluationValidationError("live_oracle_invalid")


@dataclass(frozen=True)
class LoadedLiveSuite:
    suite: JsonObject
    records: tuple[JsonObject, ...]
    prompt_template: JsonObject
    policy_profile: JsonObject
    budget_profile: JsonObject
    price_profile: JsonObject
    suite_sha256: str
    attempt_ids: tuple[str, ...]


def load_live_pilot_suite(
    root: Path,
    suite_name: str = "live-pilot.v1.json",
    *,
    now: datetime | None = None,
) -> LoadedLiveSuite:
    """Validate all checked-in live sources before credentials, DNS, or SQLite."""

    suite = _load_json(root / "evals" / "suites" / suite_name)
    _safe_tree(suite)
    _require_exact_keys(
        suite,
        {
            "suite_id",
            "profile",
            "task_count",
            "attempts_per_task",
            "tasks",
            "prompt_template",
            "policy_profile",
            "budget_profile",
            "price_profile",
        },
        "live_suite_invalid",
    )
    tasks = suite.get("tasks")
    if (
        suite.get("suite_id") != LIVE_SUITE_ID
        or suite.get("profile") != LIVE_SUITE_ID
        or suite.get("task_count") != 6
        or suite.get("attempts_per_task") != 5
        or not isinstance(tasks, list)
        or tuple(item.get("task_id") for item in tasks if isinstance(item, Mapping))
        != LIVE_TASK_IDS
    ):
        raise LiveEvaluationValidationError("live_suite_invalid")

    prompt = _resolve_json(root, suite["prompt_template"])
    policy = _resolve_json(root, suite["policy_profile"])
    budget = _resolve_json(root, suite["budget_profile"])
    price_reference = suite["price_profile"]
    price = _resolve_json(root, price_reference, hash_field="file_sha256")
    _validate_prompt(prompt, suite["prompt_template"])
    _validate_policy(policy, suite["policy_profile"])
    _validate_budget(budget, suite["budget_profile"])
    try:
        validate_provider_price_profile(price, root)
    except ValueError as error:
        raise LiveEvaluationValidationError("live_price_profile_invalid") from error
    current = now or datetime.now(UTC)
    effective = datetime.fromisoformat(str(price["effective_at"]).replace("Z", "+00:00"))
    expires = datetime.fromisoformat(str(price["expires_at"]).replace("Z", "+00:00"))
    if (
        price.get("price_profile_id") != price_reference.get("price_profile_id")
        or price.get("profile_sha256") != price_reference.get("profile_sha256")
        or not effective <= current < expires
    ):
        raise LiveEvaluationValidationError("live_price_profile_stale_or_mismatched")

    task_keys = {
        "task_id",
        "suite_id",
        "tenant_id",
        "context_source",
        "prompt_template",
        "policy_profile",
        "budget_profile",
        "price_profile",
        "attempt_count",
        "task_kind",
        "tool_sources",
        "oracle_path",
        "oracle_sha256",
        "fault_profile",
        "allowed_outcomes",
    }
    records: list[JsonObject] = []
    attempt_ids: list[str] = []
    for task_reference in tasks:
        if not isinstance(task_reference, Mapping):
            raise LiveEvaluationValidationError("live_task_reference_invalid")
        task = _resolve_json(root, task_reference)
        _require_exact_keys(task, task_keys, "live_task_invalid")
        task_id = task_reference["task_id"]
        if (
            task.get("task_id") != task_id
            or task.get("suite_id") != LIVE_SUITE_ID
            or task.get("tenant_id") != "tenant-alpha"
            or task.get("task_kind") not in _ALLOWED_TASK_KINDS
            or task.get("attempt_count") != 5
            or not isinstance(task.get("allowed_outcomes"), list)
            or not task["allowed_outcomes"]
            or not set(task["allowed_outcomes"]).issubset(_ALLOWED_OUTCOMES)
            or task.get("prompt_template") != suite["prompt_template"]
            or task.get("policy_profile") != suite["policy_profile"]
            or task.get("budget_profile") != suite["budget_profile"]
            or task.get("price_profile")
            != {key: price_reference[key] for key in ("price_profile_id", "path", "profile_sha256")}
        ):
            raise LiveEvaluationValidationError("live_task_invalid")
        context = _resolve_json(root, task["context_source"])
        _validate_context_source(context, task["context_source"])
        tool_references = task.get("tool_sources")
        if not isinstance(tool_references, Mapping) or set(tool_references) != {
            "crm",
            "monitoring",
            "knowledge",
        }:
            raise LiveEvaluationValidationError("live_task_tool_sources_invalid")
        tools: JsonObject = {}
        for tool in ("crm", "monitoring", "knowledge"):
            reference = tool_references[tool]
            source = _resolve_json(root, reference)
            _validate_tool_source(source, reference, tool)
            tools[tool] = source
        oracle_reference = {"path": task["oracle_path"], "sha256": task["oracle_sha256"]}
        oracle = _resolve_json(root, oracle_reference)
        _validate_oracle(oracle, task)
        task_attempt_ids = tuple(f"{task_id}:attempt-{index}" for index in range(1, 6))
        attempt_ids.extend(task_attempt_ids)
        records.append(
            {
                "task": task,
                "oracle": oracle,
                "context": context,
                "tools": tools,
                "attempt_ids": task_attempt_ids,
            }
        )
    if len(records) != 6 or len(attempt_ids) != 30 or len(set(attempt_ids)) != 30:
        raise LiveEvaluationValidationError("live_attempt_identity_invalid")
    return LoadedLiveSuite(
        suite=suite,
        records=tuple(records),
        prompt_template=prompt,
        policy_profile=policy,
        budget_profile=budget,
        price_profile=price,
        suite_sha256=canonical_sha256(suite),
        attempt_ids=tuple(attempt_ids),
    )


def _resolve_host(host: str, port: int) -> Sequence[str]:
    return tuple(
        sorted(
            {str(item[4][0]) for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        )
    )


def validate_public_https_endpoint(
    endpoint: str,
    *,
    resolver: AddressResolver = _resolve_host,
) -> tuple[str, str]:
    """Return normalized endpoint and host hash only for a public HTTPS authority."""

    try:
        parsed = urlsplit(endpoint)
        port = parsed.port or 443
    except ValueError as error:
        raise LiveConfigurationDenied("endpoint_invalid") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port != 443
        or ".." in PurePosixPath(parsed.path or "/").parts
    ):
        raise LiveConfigurationDenied("endpoint_not_public_https")
    host = parsed.hostname.lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise LiveConfigurationDenied("endpoint_ip_literal_denied")
    try:
        addresses = tuple(resolver(host, port))
    except OSError as error:
        raise LiveConfigurationDenied("endpoint_resolution_failed") from error
    if not addresses:
        raise LiveConfigurationDenied("endpoint_resolution_failed")
    try:
        parsed_addresses = tuple(ipaddress.ip_address(address) for address in addresses)
    except ValueError as error:
        raise LiveConfigurationDenied("endpoint_resolution_invalid") from error
    if any(not address.is_global for address in parsed_addresses):
        raise LiveConfigurationDenied("endpoint_address_not_public")
    normalized = f"https://{host}{'' if parsed.path in ('', '/') else parsed.path.rstrip('/')}"
    return normalized, hashlib.sha256(host.encode("utf-8")).hexdigest()


def validate_same_origin_redirect(
    original_endpoint: str,
    redirect_target: str,
    *,
    resolver: AddressResolver = _resolve_host,
) -> str:
    original, _ = validate_public_https_endpoint(original_endpoint, resolver=resolver)
    target, _ = validate_public_https_endpoint(redirect_target, resolver=resolver)
    if urlsplit(original).netloc != urlsplit(target).netloc:
        raise LiveConfigurationDenied("cross_origin_redirect_denied")
    return target


@dataclass(frozen=True)
class LiveEvaluationConfig:
    provider_mode: str
    endpoint: str
    endpoint_host_sha256: str
    model: str
    model_id_sha256: str
    provider_profile_id: str
    provider_profile_sha256: str
    price_profile_id: str
    price_profile_sha256: str
    credential_environment_variable: str
    budget_profile: JsonObject

    def public_dict(self) -> JsonObject:
        public = asdict(self)
        public.pop("endpoint")
        public.pop("model")
        public.pop("credential_environment_variable")
        return public


@dataclass(frozen=True, repr=False)
class LiveCredential:
    _value: str

    def authorization_header(self) -> str:
        return f"Bearer {self._value}"

    def __repr__(self) -> str:
        return "LiveCredential(redacted)"


def parse_live_evaluation_config(
    suite: LoadedLiveSuite,
    *,
    confirm_live: bool,
    endpoint: str,
    model: str,
    provider_mode: str = "openai-compatible",
    resolver: AddressResolver = _resolve_host,
) -> LiveEvaluationConfig:
    """Parse operator-controlled settings without reading a credential."""

    if confirm_live is not True:
        raise LiveConfigurationDenied("explicit_confirmation_required")
    if provider_mode != "openai-compatible":
        raise LiveConfigurationDenied("provider_mode_unsupported")
    if not isinstance(model, str) or not _MODEL_RE.fullmatch(model):
        raise LiveConfigurationDenied("model_invalid")
    if suite.price_profile.get("model_pattern") != model:
        raise LiveConfigurationDenied("model_price_profile_mismatch")
    normalized_endpoint, host_hash = validate_public_https_endpoint(endpoint, resolver=resolver)
    provider_material = {
        "provider_mode": provider_mode,
        "endpoint_host_sha256": host_hash,
        "model_id_sha256": hashlib.sha256(model.encode("utf-8")).hexdigest(),
        "price_profile_sha256": suite.price_profile["profile_sha256"],
    }
    return LiveEvaluationConfig(
        provider_mode=provider_mode,
        endpoint=normalized_endpoint,
        endpoint_host_sha256=host_hash,
        model=model,
        model_id_sha256=provider_material["model_id_sha256"],
        provider_profile_id=str(suite.price_profile["provider_profile_id"]),
        provider_profile_sha256=canonical_sha256(provider_material),
        price_profile_id=str(suite.price_profile["price_profile_id"]),
        price_profile_sha256=str(suite.price_profile["profile_sha256"]),
        credential_environment_variable=LIVE_CREDENTIAL_ENVIRONMENT_VARIABLE,
        budget_profile=dict(suite.budget_profile),
    )


def load_live_credential(
    config: LiveEvaluationConfig,
    environment: Mapping[str, str],
) -> LiveCredential:
    """Load the environment-only secret after all non-secret preflight gates pass."""

    value = environment.get(config.credential_environment_variable)
    if not isinstance(value, str) or not value.strip():
        raise LiveConfigurationDenied("credential_missing")
    return LiveCredential(value.strip())


__all__ = [
    "LIVE_CREDENTIAL_ENVIRONMENT_VARIABLE",
    "LIVE_SUITE_ID",
    "LIVE_TASK_IDS",
    "LiveConfigurationDenied",
    "LiveCredential",
    "LiveEvaluationConfig",
    "LiveEvaluationValidationError",
    "LoadedLiveSuite",
    "canonical_sha256",
    "load_live_credential",
    "load_live_pilot_suite",
    "parse_live_evaluation_config",
    "validate_public_https_endpoint",
    "validate_same_origin_redirect",
]
