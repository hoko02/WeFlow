"""Keep secrets and raw private content out of local foundation diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_KEY = re.compile(r"(api[_-]?key|token|secret|password|credential|authorization)", re.I)
_PRIVATE_CONTENT_KEY = re.compile(
    r"(customer|payload|tool[_-]?output|message|body|error|exception|traceback)", re.I
)
_CONNECTION_STRING = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s,;]+", re.I)
_ASSIGNMENT = re.compile(
    r"(?P<key>api[_-]?key|token|secret|password|credential|authorization)\s*[:=]\s*[^\s,;]+",
    re.I,
)


def redact_text(value: str) -> str:
    without_connections = _CONNECTION_STRING.sub("[REDACTED_CONNECTION]", value)
    return _ASSIGNMENT.sub(lambda match: f"{match.group('key')}=[REDACTED]", without_connections)


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        if _SENSITIVE_KEY.search(key) or _PRIVATE_CONTENT_KEY.search(key):
            redacted[key] = "[REDACTED]"
        elif isinstance(item, Mapping):
            redacted[key] = redact_mapping(item)
        elif isinstance(item, list):
            redacted[key] = [
                redact_mapping(entry)
                if isinstance(entry, Mapping)
                else redact_text(entry)
                if isinstance(entry, str)
                else entry
                for entry in item
            ]
        elif isinstance(item, str):
            redacted[key] = redact_text(item)
        else:
            redacted[key] = item
    return redacted


def structured_event(
    event_name: str,
    *,
    service: str,
    mode: str,
    correlation_id: str | None = None,
    **attributes: Any,
) -> dict[str, Any]:
    """Build a safe, JSON-serializable local observability event."""

    return {
        "event_name": event_name,
        "service": service,
        "mode": mode,
        "correlation_id": correlation_id,
        "resource": {
            "service.name": service,
            "service.version": "0.1.0",
            "deployment.environment.name": "local",
        },
        "trace": {"weflow.correlation_id": correlation_id},
        "attributes": redact_mapping(attributes),
    }


def failure_evidence(
    *,
    service: str,
    mode: str,
    component: str,
    reason_code: str,
    correlation_id: str,
    raw_error: str | None = None,
    raw_tool_output: str | None = None,
) -> dict[str, Any]:
    """Record only safe timeout/error evidence, never raw diagnostics."""

    return structured_event(
        "weflow.dependency.failure",
        service=service,
        mode=mode,
        correlation_id=correlation_id,
        component=component,
        reason_code=reason_code,
        error_detail=raw_error,
        tool_output=raw_tool_output,
    )
