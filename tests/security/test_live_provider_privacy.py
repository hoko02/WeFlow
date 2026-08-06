import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from weflow_agent_runtime.live_provider import (
    OpenAICompatibleProvider,
    ProviderTurnInput,
    TransportResponse,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from live_model_evaluation_acceptance import safe_reason  # noqa: E402

SENTINEL = "sentinel-provider-secret-value"
RAW = "sentinel-raw-provider-body"


@dataclass(frozen=True, repr=False)
class Credential:
    value: str

    def authorization_header(self) -> str:
        return f"Bearer {self.value}"

    def __repr__(self) -> str:
        return "Credential(redacted)"


class ErrorBodyTransport:
    def send(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_ms: int,
    ) -> TransportResponse:
        del url, body, timeout_ms
        assert headers["Authorization"] == f"Bearer {SENTINEL}"
        return TransportResponse(503, {}, f"{RAW}:{SENTINEL}".encode(), 4)


def test_secret_and_raw_provider_body_never_escape_result_exception_or_logs(caplog) -> None:
    auth = Credential(SENTINEL)
    provider = OpenAICompatibleProvider(
        endpoint="https://api.example.test/v1",
        model="synthetic-model-v1",
        auth=auth,
        transport=ErrorBodyTransport(),
    )
    result = provider.propose(
        ProviderTurnInput(
            system_instructions=("Return JSON.",),
            user_content=json.dumps({"classification": "untrusted_synthetic"}),
            max_output_tokens=100,
            request_timeout_ms=1_000,
        )
    )
    rendered = repr(result) + repr(auth) + caplog.text

    assert result.status == "observed_retryable_error"
    assert result.failure_classification == "provider_unavailable"
    assert SENTINEL not in rendered
    assert RAW not in rendered
    assert safe_reason(ValueError(f"unsafe:{SENTINEL}")) == "live_evaluation_failed"
