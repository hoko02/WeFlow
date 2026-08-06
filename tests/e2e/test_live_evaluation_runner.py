import json
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from live_model_evaluation_acceptance import execute_live_suite, finalize_live_suite  # noqa: E402
from weflow_agent_runtime.live_provider import TransportResponse  # noqa: E402
from weflow_contracts.live import MODEL_ACTION_PROPOSAL_SCHEMA_ID  # noqa: E402
from weflow_testkit.live_evaluation import (  # noqa: E402
    LiveCredential,
    LiveEvaluationConfig,
    load_live_pilot_suite,
)
from weflow_testkit.live_grading import LiveEvaluationGradingError  # noqa: E402

NOW = datetime(2026, 8, 6, tzinfo=UTC)
SENTINEL = "runner-secret-sentinel"


def _proposal(
    action_type: str,
    *,
    reason_code: str | None = None,
    references: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_id": MODEL_ACTION_PROPOSAL_SCHEMA_ID,
        "schema_version": "v1",
        "action_type": action_type,
        "reason_code": reason_code,
        "evidence_references": references or [],
        "draft": (
            {
                "summary": "A synthetic API is intermittently returning HTTP 503.",
                "diagnosis": "Synthetic evidence indicates upstream queue saturation.",
                "next_steps": ["Continue the bounded synthetic observation window."],
                "risk": "medium",
            }
            if action_type == "response_candidate"
            else None
        ),
    }


class SuiteFakeTransport:
    def send(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_ms: int,
    ) -> TransportResponse:
        del url, timeout_ms
        assert headers["Authorization"] == f"Bearer {SENTINEL}"
        request = json.loads(body)
        assert request["thinking"] == {"type": "disabled"}
        system = request["messages"][0]["content"]
        assert "Read JSON example:" in system
        assert MODEL_ACTION_PROPOSAL_SCHEMA_ID in system
        user = json.loads(request["messages"][1]["content"])
        trusted = user["trusted_runtime"]
        references = list(trusted["current_evidence_references"])
        label = next(key for key in user if key.startswith("UNTRUSTED_"))
        observations = user[label]["tool_observations"]
        statuses = [item["observation"]["status"] for item in observations]
        source_ids = [item["observation"]["source_id"] for item in observations]
        if not references:
            proposal = _proposal("read_crm")
        elif "missing" in statuses:
            proposal = _proposal("needs_information", reason_code="missing_required_information")
        elif len(references) == 1:
            proposal = _proposal("read_monitoring")
        elif "conflicting" in statuses:
            proposal = _proposal("needs_operator", reason_code="conflicting_evidence")
        elif len(references) == 2:
            proposal = _proposal("read_knowledge")
        elif any("injection" in source_id for source_id in source_ids):
            proposal = _proposal("needs_operator", reason_code="policy_safe_stop")
        else:
            proposal = _proposal("response_candidate", references=references)
        envelope = {
            "choices": [{"message": {"content": json.dumps(proposal)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
        return TransportResponse(200, {}, json.dumps(envelope).encode(), 1)


def test_fake_transport_executes_all_30_but_cannot_replace_accepted_report(
    tmp_path: Path,
) -> None:
    suite = load_live_pilot_suite(ROOT, now=NOW)
    config = LiveEvaluationConfig(
        provider_mode="openai-compatible",
        endpoint="https://api.example.test/v1",
        endpoint_host_sha256="1" * 64,
        model="deepseek-v4-flash",
        model_id_sha256="2" * 64,
        provider_profile_id="openai-compatible.v1",
        provider_profile_sha256="3" * 64,
        price_profile_id=suite.price_profile["price_profile_id"],
        price_profile_sha256=suite.price_profile["profile_sha256"],
        credential_environment_variable="WEFLOW_LIVE_MODEL_API_KEY",
        budget_profile=dict(suite.budget_profile),
    )
    execution = execute_live_suite(
        root=ROOT,
        suite=suite,
        config=config,
        auth=LiveCredential(SENTINEL),
        transport=SuiteFakeTransport(),
    )
    assert len(execution["attempts"]) == 30
    assert len(execution["metrics"]) == 30
    assert execution["failures"] == []
    assert all(item["hard_gate_passed"] for item in execution["attempts"])
    assert execution["live_verification_eligible"] is False

    accepted = tmp_path / "accepted.json"
    verification = tmp_path / "verification.json"
    diagnostics = tmp_path / "diagnostics.json"
    accepted.write_text("prior-accepted-report\n", encoding="utf-8")
    with pytest.raises(LiveEvaluationGradingError, match="fake_transport"):
        finalize_live_suite(
            root=ROOT,
            suite=suite,
            config=config,
            execution=execution,
            output_path=accepted,
            verification_path=verification,
            diagnostics_path=diagnostics,
        )
    assert accepted.read_text(encoding="utf-8") == "prior-accepted-report\n"
    assert not verification.exists()
    rendered = diagnostics.read_text(encoding="utf-8")
    assert '"accepted": false' in rendered
    assert SENTINEL not in rendered
    diagnostic = json.loads(rendered)
    assert set(diagnostic["attempts"][0]["metrics"]) == {
        "invocation_count",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "provider_latency_ms",
    }
    assert "response_sha256" not in rendered
    assert "request_reference_sha256" not in rendered
