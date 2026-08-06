import json
from collections.abc import Mapping
from dataclasses import dataclass

import pytest
from weflow_agent_runtime.live_provider import (
    MAX_RESPONSE_BYTES,
    OpenAICompatibleProvider,
    ProviderBoundaryError,
    ProviderTransportError,
    ProviderTurnInput,
    ReplayTurnProvider,
    TransportResponse,
)
from weflow_contracts.live import MODEL_ACTION_PROPOSAL_SCHEMA_ID


@dataclass(frozen=True, repr=False)
class Credential:
    value: str

    def authorization_header(self) -> str:
        return f"Bearer {self.value}"

    def __repr__(self) -> str:
        return "Credential(redacted)"


class FakeTransport:
    def __init__(
        self,
        response: TransportResponse | None = None,
        error: ProviderTransportError | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def send(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_ms: int,
    ) -> TransportResponse:
        self.calls.append(
            {"url": url, "headers": dict(headers), "body": body, "timeout_ms": timeout_ms}
        )
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def proposal(action_type: str = "read_crm") -> dict[str, object]:
    return {
        "schema_id": MODEL_ACTION_PROPOSAL_SCHEMA_ID,
        "schema_version": "v1",
        "action_type": action_type,
        "reason_code": None,
        "evidence_references": [],
        "draft": None,
    }


def response(
    proposal_payload: object,
    *,
    status: int = 200,
    headers: Mapping[str, str] | None = None,
    usage: object | None = None,
) -> TransportResponse:
    envelope = {
        "choices": [{"message": {"content": json.dumps(proposal_payload)}}],
        "usage": (
            usage
            if usage is not None
            else {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
        ),
    }
    return TransportResponse(
        status_code=status,
        headers=headers or {"x-request-id": "provider-request-secretless"},
        body=json.dumps(envelope).encode(),
        latency_ms=37,
    )


def turn(*, thinking_mode: str = "provider_default") -> ProviderTurnInput:
    return ProviderTurnInput(
        system_instructions=("Return JSON.",),
        user_content="UNTRUSTED_SYNTHETIC_DATA {}",
        max_output_tokens=200,
        request_timeout_ms=1_000,
        thinking_mode=thinking_mode,
    )


def provider(
    transport: FakeTransport, secret: str = "sentinel-live-secret"
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        endpoint="https://api.example.test/v1",
        model="synthetic-model-v1",
        auth=Credential(secret),
        transport=transport,
    )


def test_successful_structured_turn_captures_safe_usage_and_request_bounds() -> None:
    transport = FakeTransport(response(proposal()))
    result = provider(transport).propose(turn())

    assert result.status == "completed"
    assert result.proposal == proposal()
    assert result.total_tokens == 30
    assert result.usage_available is True
    assert result.live_contact is True
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["url"] == "https://api.example.test/v1/chat/completions"
    request = json.loads(call["body"])
    assert request["response_format"] == {"type": "json_object"}
    assert request["stream"] is False
    assert request["temperature"] == 0
    assert request["max_tokens"] == 200
    assert "thinking" not in request
    assert "sentinel-live-secret" not in json.dumps(result.__dict__)


def test_disabled_thinking_mode_is_explicit_in_provider_request() -> None:
    transport = FakeTransport(response(proposal()))

    result = provider(transport).propose(turn(thinking_mode="disabled"))

    assert result.status == "completed"
    request = json.loads(transport.calls[0]["body"])
    assert request["thinking"] == {"type": "disabled"}


def test_unknown_thinking_mode_is_denied_before_provider_contact() -> None:
    transport = FakeTransport(response(proposal()))

    with pytest.raises(ProviderBoundaryError, match="provider_turn_invalid"):
        provider(transport).propose(turn(thinking_mode="enabled"))
    assert transport.calls == []


@pytest.mark.parametrize(
    ("status_code", "expected_status", "classification", "retryable"),
    [
        (429, "observed_retryable_error", "provider_rate_limited", True),
        (503, "observed_retryable_error", "provider_unavailable", True),
        (401, "rejected", "provider_rejected", False),
    ],
)
def test_provider_statuses_map_to_closed_safe_outcomes(
    status_code: int,
    expected_status: str,
    classification: str,
    retryable: bool,
) -> None:
    raw_marker = "raw-provider-body-must-not-escape"
    transport = FakeTransport(
        TransportResponse(status_code, {}, raw_marker.encode(), latency_ms=12)
    )
    result = provider(transport).propose(turn())

    assert result.status == expected_status
    assert result.failure_classification == classification
    assert result.retryable is retryable
    assert raw_marker not in repr(result)


def test_timeout_is_outcome_unknown_and_never_retryable() -> None:
    result = provider(FakeTransport(error=ProviderTransportError(outcome_unknown=True))).propose(
        turn()
    )
    assert result.status == "provider_outcome_unknown"
    assert result.failure_classification == "provider_outcome_unknown"
    assert result.retryable is False


@pytest.mark.parametrize(
    "bad_payload",
    [
        {**proposal(), "target_state": "RESPONSE_READY"},
        {**proposal(), "arguments": {"customer_id": "chosen-by-model"}},
        {**proposal("response_candidate"), "draft": None},
    ],
)
def test_unknown_authority_arguments_and_invalid_drafts_are_malformed(
    bad_payload: dict[str, object],
) -> None:
    result = provider(FakeTransport(response(bad_payload))).propose(turn())
    assert result.status == "malformed_model_output"
    assert result.proposal is None


def test_missing_usage_and_excessive_response_fail_closed() -> None:
    missing_usage = response(proposal(), usage={})
    assert provider(FakeTransport(missing_usage)).propose(turn()).status == "malformed_model_output"

    oversized = TransportResponse(200, {}, b"x" * (MAX_RESPONSE_BYTES + 1), latency_ms=1)
    with pytest.raises(ProviderBoundaryError, match="provider_response_too_large"):
        provider(FakeTransport(oversized)).propose(turn())


def test_replay_turn_adapter_has_zero_network_and_model_contact() -> None:
    replay = ReplayTurnProvider([proposal("read_knowledge")])
    result = replay.propose(turn())
    assert result.proposal == proposal("read_knowledge")
    assert result.live_contact is False
    assert result.total_tokens == 0
    assert result.provider_latency_ms == 0
