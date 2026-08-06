"""Command-local provider boundary for bounded live-model evaluation."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin

from weflow_contracts.live import validate_model_action_proposal

JsonObject = dict[str, Any]
MAX_REQUEST_BYTES = 128_000
MAX_RESPONSE_BYTES = 65_536


class ProviderBoundaryError(RuntimeError):
    """A safe provider-boundary error without request, response, or credentials."""


class ProviderTransportError(RuntimeError):
    """A redacted transport failure with explicit outcome certainty."""

    def __init__(self, *, outcome_unknown: bool) -> None:
        super().__init__("provider_transport_failed")
        self.outcome_unknown = outcome_unknown


class AuthorizationCredential(Protocol):
    def authorization_header(self) -> str: ...


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    latency_ms: int


class OpenAICompatibleTransport(Protocol):
    def send(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_ms: int,
    ) -> TransportResponse: ...


@dataclass(frozen=True)
class ProviderTurnInput:
    system_instructions: tuple[str, ...]
    user_content: str
    max_output_tokens: int
    request_timeout_ms: int
    thinking_mode: str = "provider_default"
    temperature: float = 0
    top_p: float = 1


@dataclass(frozen=True)
class ProviderTurnResult:
    status: str
    proposal: JsonObject | None
    request_reference_sha256: str | None
    response_sha256: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    usage_available: bool
    provider_latency_ms: int
    failure_classification: str | None
    retryable: bool
    live_contact: bool


class AgentTurnProvider(Protocol):
    def propose(self, turn: ProviderTurnInput) -> ProviderTurnResult: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class UrllibJsonTransport:
    """Small stdlib transport that never follows redirects."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    @staticmethod
    def _bounded_read(response: Any) -> bytes:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ProviderBoundaryError("provider_response_too_large")
        return body

    def send(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_ms: int,
    ) -> TransportResponse:
        request = urllib.request.Request(
            url,
            data=body,
            headers=dict(headers),
            method="POST",
        )
        started = time.monotonic()
        try:
            with self._opener.open(request, timeout=timeout_ms / 1000) as response:
                payload = self._bounded_read(response)
                return TransportResponse(
                    status_code=int(response.status),
                    headers=dict(response.headers.items()),
                    body=payload,
                    latency_ms=max(0, round((time.monotonic() - started) * 1000)),
                )
        except urllib.error.HTTPError as error:
            payload = self._bounded_read(error)
            return TransportResponse(
                status_code=int(error.code),
                headers=dict(error.headers.items()) if error.headers else {},
                body=payload,
                latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            )
        except TimeoutError as error:
            raise ProviderTransportError(outcome_unknown=True) from error
        except urllib.error.URLError as error:
            raise ProviderTransportError(outcome_unknown=True) from error


def _json_no_duplicates(raw: str) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def _safe_usage(payload: object) -> tuple[int, int, int, bool]:
    if not isinstance(payload, Mapping):
        return 0, 0, 0, False
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0, 0, False
    values = (usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens"))
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        return 0, 0, 0, False
    input_tokens, output_tokens, total_tokens = values
    if total_tokens != input_tokens + output_tokens:
        return 0, 0, 0, False
    return input_tokens, output_tokens, total_tokens, True


class OpenAICompatibleProvider:
    """One OpenAI-compatible chat-completions adapter with no raw logging."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        auth: AuthorizationCredential,
        transport: OpenAICompatibleTransport,
    ) -> None:
        self._url = urljoin(endpoint.rstrip("/") + "/", "chat/completions")
        self._model = model
        self._credential = auth
        self._transport = transport

    @staticmethod
    def _failure_result(
        *,
        status: str,
        classification: str,
        latency_ms: int,
        response_sha256: str | None,
        request_reference_sha256: str | None,
        usage: tuple[int, int, int, bool] = (0, 0, 0, False),
        retryable: bool = False,
    ) -> ProviderTurnResult:
        input_tokens, output_tokens, total_tokens, available = usage
        return ProviderTurnResult(
            status=status,
            proposal=None,
            request_reference_sha256=request_reference_sha256,
            response_sha256=response_sha256,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            usage_available=available,
            provider_latency_ms=latency_ms,
            failure_classification=classification,
            retryable=retryable,
            live_contact=True,
        )

    def propose(self, turn: ProviderTurnInput) -> ProviderTurnResult:
        if (
            not turn.system_instructions
            or not turn.user_content
            or turn.max_output_tokens < 1
            or turn.request_timeout_ms < 1
            or turn.thinking_mode not in {"provider_default", "disabled"}
        ):
            raise ProviderBoundaryError("provider_turn_invalid")
        request_payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "\n".join(turn.system_instructions)},
                {"role": "user", "content": turn.user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": turn.temperature,
            "top_p": turn.top_p,
            "max_tokens": turn.max_output_tokens,
            "stream": False,
        }
        if turn.thinking_mode == "disabled":
            request_payload["thinking"] = {"type": "disabled"}
        body = json.dumps(
            request_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise ProviderBoundaryError("provider_request_too_large")
        try:
            response = self._transport.send(
                url=self._url,
                headers={
                    "Authorization": self._credential.authorization_header(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body=body,
                timeout_ms=turn.request_timeout_ms,
            )
        except ProviderTransportError as error:
            classification = (
                "provider_outcome_unknown" if error.outcome_unknown else "provider_unavailable"
            )
            status = (
                "provider_outcome_unknown" if error.outcome_unknown else "observed_retryable_error"
            )
            return self._failure_result(
                status=status,
                classification=classification,
                latency_ms=turn.request_timeout_ms,
                response_sha256=None,
                request_reference_sha256=None,
                retryable=not error.outcome_unknown,
            )
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise ProviderBoundaryError("provider_response_too_large")
        response_hash = hashlib.sha256(response.body).hexdigest()
        request_reference = response.headers.get("x-request-id") or response.headers.get(
            "X-Request-Id"
        )
        request_hash = (
            hashlib.sha256(request_reference.encode("utf-8")).hexdigest()
            if request_reference
            else None
        )
        try:
            envelope = _json_no_duplicates(response.body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            envelope = None
        usage = _safe_usage(envelope)
        if response.status_code in {429}:
            return self._failure_result(
                status="observed_retryable_error",
                classification="provider_rate_limited",
                latency_ms=response.latency_ms,
                response_sha256=response_hash,
                request_reference_sha256=request_hash,
                usage=usage,
                retryable=True,
            )
        if response.status_code in {500, 502, 503, 504}:
            return self._failure_result(
                status="observed_retryable_error",
                classification="provider_unavailable",
                latency_ms=response.latency_ms,
                response_sha256=response_hash,
                request_reference_sha256=request_hash,
                usage=usage,
                retryable=True,
            )
        if response.status_code < 200 or response.status_code >= 300:
            return self._failure_result(
                status="rejected",
                classification="provider_rejected",
                latency_ms=response.latency_ms,
                response_sha256=response_hash,
                request_reference_sha256=request_hash,
                usage=usage,
            )
        try:
            if not isinstance(envelope, Mapping):
                raise ValueError("provider_envelope_invalid")
            choices = envelope.get("choices")
            if (
                not isinstance(choices, Sequence)
                or isinstance(choices, (str, bytes))
                or len(choices) != 1
            ):
                raise ValueError("provider_choices_invalid")
            choice = choices[0]
            message = choice.get("message") if isinstance(choice, Mapping) else None
            content = message.get("content") if isinstance(message, Mapping) else None
            if not isinstance(content, str) or len(content) > MAX_RESPONSE_BYTES:
                raise ValueError("provider_content_invalid")
            proposal = _json_no_duplicates(content)
            if not isinstance(proposal, dict):
                raise ValueError("provider_proposal_invalid")
            validate_model_action_proposal(proposal)
            if not usage[3]:
                raise ValueError("provider_usage_missing")
        except (ValueError, json.JSONDecodeError):
            return self._failure_result(
                status="malformed_model_output",
                classification="malformed_model_output",
                latency_ms=response.latency_ms,
                response_sha256=response_hash,
                request_reference_sha256=request_hash,
                usage=usage,
            )
        return ProviderTurnResult(
            status="completed",
            proposal=proposal,
            request_reference_sha256=request_hash,
            response_sha256=response_hash,
            input_tokens=usage[0],
            output_tokens=usage[1],
            total_tokens=usage[2],
            usage_available=True,
            provider_latency_ms=response.latency_ms,
            failure_classification=None,
            retryable=False,
            live_contact=True,
        )


class ReplayTurnProvider:
    """Deterministic provider-neutral adapter with zero network/model contact."""

    def __init__(self, proposals: Sequence[Mapping[str, Any]]) -> None:
        self._proposals = tuple(dict(item) for item in proposals)
        self._index = 0

    def propose(self, turn: ProviderTurnInput) -> ProviderTurnResult:
        del turn
        if self._index >= len(self._proposals):
            raise ProviderBoundaryError("replay_turns_exhausted")
        proposal = self._proposals[self._index]
        self._index += 1
        validate_model_action_proposal(proposal)
        return ProviderTurnResult(
            status="completed",
            proposal=proposal,
            request_reference_sha256=None,
            response_sha256=hashlib.sha256(
                json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            usage_available=False,
            provider_latency_ms=0,
            failure_classification=None,
            retryable=False,
            live_contact=False,
        )


__all__ = [
    "AgentTurnProvider",
    "AuthorizationCredential",
    "OpenAICompatibleProvider",
    "OpenAICompatibleTransport",
    "ProviderBoundaryError",
    "ProviderTransportError",
    "ProviderTurnInput",
    "ProviderTurnResult",
    "ReplayTurnProvider",
    "TransportResponse",
    "UrllibJsonTransport",
]
