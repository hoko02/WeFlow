from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from weflow_control_kernel.qq_model import (
    QQ_STAGE3_MODEL_CAPABILITIES,
    QQ_STAGE3_QQ_CAPABILITIES,
    QQModelActivationDenied,
)
from weflow_control_worker import qq_model_runner as runner

ROOT = Path(__file__).resolve().parents[2]
PAIRING_ID = "qqpair_" + "3" * 32
BINDING_ID = "qqhbind_" + "4" * 32
APP_ID = "stage3-public-app"
TENANT_ID = "stage3-tenant"
GROUP_OPENID = "stage3-group"
SECRETS = {
    "WEFLOW_QQ_CLIENT_SECRET",
    "WEFLOW_QQ_IDENTITY_SALT",
    "WEFLOW_LIVE_MODEL_API_KEY",
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RecordingEnvironment(dict[str, str]):
    def __init__(self, *args: object, fail_on_secret: bool = False, **kwargs: str) -> None:
        super().__init__(*args, **kwargs)
        self.events: list[str] = []
        self.fail_on_secret = fail_on_secret

    def get(self, key: str, default: str | None = None) -> str | None:
        self.events.append(key)
        if self.fail_on_secret and key in SECRETS:
            raise AssertionError("secret_read_during_preflight")
        return super().get(key, default)


class FakeJournal:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def active_binding(self, handler_binding_id: str) -> dict[str, str]:
        assert handler_binding_id == BINDING_ID
        return {
            "handler_binding_id": BINDING_ID,
            "app_id_hash": _hash(APP_ID),
            "tenant_id_hash": _hash(TENANT_ID),
            "group_openid_hash": _hash(GROUP_OPENID),
            "stage1_pairing_id": PAIRING_ID,
        }


def _environment(*, include_secrets: bool, fail_on_secret: bool = False) -> RecordingEnvironment:
    values = RecordingEnvironment(
        {
            "WEFLOW_QQ_APP_ID": APP_ID,
            "WEFLOW_QQ_SANDBOX_PAIRING_ID": PAIRING_ID,
            "WEFLOW_QQ_HANDLER_BINDING_ID": BINDING_ID,
            "WEFLOW_QQ_CAPABILITIES": ",".join(QQ_STAGE3_QQ_CAPABILITIES),
            "WEFLOW_QQ_MODEL_CAPABILITIES": ",".join(QQ_STAGE3_MODEL_CAPABILITIES),
            "WEFLOW_PROVIDER_MODE": "openai-compatible",
        },
        fail_on_secret=fail_on_secret,
    )
    if include_secrets:
        values.update(
            {
                "WEFLOW_QQ_CLIENT_SECRET": "not-a-real-secret",
                "WEFLOW_QQ_IDENTITY_SALT": "identity-salt-never-rendered-123456",
                "WEFLOW_LIVE_MODEL_API_KEY": "not-a-real-secret",
            }
        )
    return values


@pytest.fixture(autouse=True)
def _selectors(monkeypatch):
    def resolve(_values, *, store_path):
        del store_path
        return {
            "WEFLOW_QQ_TENANT_ID": TENANT_ID,
            "WEFLOW_QQ_SANDBOX_GROUP_OPENID": GROUP_OPENID,
        }

    monkeypatch.setattr(runner, "resolve_stage1_pairing_environment", resolve)
    monkeypatch.setattr(runner, "SQLiteQQHandlerJournal", FakeJournal)


def test_readiness_preflight_never_reads_provider_credentials() -> None:
    values = _environment(include_secrets=False, fail_on_secret=True)
    prepared = runner.prepare_stage3_preflight(
        root=ROOT,
        store_path=".weflow/qq-sandbox.sqlite3",
        confirm_live_qq=True,
        confirm_live_model=True,
        pairing_id=None,
        handler_binding_id=None,
        endpoint=None,
        model=None,
        profile_path="evals/qq-model/stage3-api-503-profile.v1.json",
        environ=values,
    )
    assert prepared.readiness["ready"] is True
    assert prepared.readiness["network_contacted"] is False
    assert prepared.readiness["model_invocation"] is False
    assert prepared.readiness["case_mutation"] is False
    assert prepared.readiness["external_write_attempted"] is False
    assert prepared.live_config.budget_profile["estimated_cost_limit"] == 0.5
    assert prepared.loaded_profile.budget_profile["estimated_cost_limit"] == 0.5
    assert prepared.loaded_profile.suite.budget_profile["estimated_cost_limit"] == 0.02
    assert not SECRETS.intersection(values.events)


def test_activation_resolves_public_endpoint_before_any_secret_read() -> None:
    values = _environment(include_secrets=True)

    def resolve(_host: str, _port: int):
        values.events.append("dns_resolved")
        return ("93.184.216.34",)

    active = runner.activate_stage3(
        root=ROOT,
        store_path=".weflow/qq-sandbox.sqlite3",
        confirm_live_qq=True,
        confirm_live_model=True,
        pairing_id=None,
        handler_binding_id=None,
        endpoint=None,
        model=None,
        profile_path="evals/qq-model/stage3-api-503-profile.v1.json",
        environ=values,
        resolver=resolve,
    )
    first_secret = min(values.events.index(name) for name in SECRETS)
    assert values.events.index("dns_resolved") < first_secret
    rendered = repr(active)
    assert "not-a-real-secret" not in rendered


def test_expanded_capability_fails_before_dns_or_secret_read() -> None:
    values = _environment(include_secrets=True, fail_on_secret=True)
    values["WEFLOW_QQ_MODEL_CAPABILITIES"] += ",model.unrestricted.invoke"
    dns_called = False

    def resolve(_host: str, _port: int):
        nonlocal dns_called
        dns_called = True
        return ("93.184.216.34",)

    with pytest.raises(QQModelActivationDenied, match="stage3_model_capability_scope_denied"):
        runner.activate_stage3(
            root=ROOT,
            store_path=".weflow/qq-sandbox.sqlite3",
            confirm_live_qq=True,
            confirm_live_model=True,
            pairing_id=None,
            handler_binding_id=None,
            endpoint=None,
            model=None,
            profile_path="evals/qq-model/stage3-api-503-profile.v1.json",
            environ=values,
            resolver=resolve,
        )
    assert dns_called is False
    assert not SECRETS.intersection(values.events)


def test_completed_case_recovery_uses_integrated_mode_without_activation(monkeypatch) -> None:
    built: dict[str, object] = {}
    prepared = SimpleNamespace(
        root=ROOT,
        store_path=ROOT / ".weflow" / "qq-sandbox.sqlite3",
        model_config=SimpleNamespace(
            handler=SimpleNamespace(tenant_id=TENANT_ID),
            stage3_profile_sha256="a" * 64,
        ),
        binding={"handler_binding_id": BINDING_ID},
    )
    evidence = {
        "request": {
            "case_id": "case_123",
            "tenant_id": TENANT_ID,
            "handler_binding_id": BINDING_ID,
            "stage3_profile_sha256": "a" * 64,
        },
        "binding": {"handler_binding_id": BINDING_ID},
        "outcome": {"terminal_outcome": "response_ready", "private_preview_id": "preview"},
        "preview": {"preview_id": "preview"},
        "approval_decision": {"decision": "approved"},
        "final_result": {"status": "accepted", "provider_accepted": True},
        "acknowledgement_count": 1,
        "notification_count": 1,
        "deletion_count": 2,
        "lifecycle_status": "DELETED",
        "invocations": [
            {
                "status": "completed",
                "response_sha256": "b" * 64,
                "provider_latency_ms": 7,
                "usage": {"total_tokens": 11},
            }
        ],
        "budget": {
            "used": {
                "provider_calls": 1,
                "input_tokens": 8,
                "output_tokens": 3,
                "total_tokens": 11,
                "estimated_cost": 0.00001,
                "wall_time_ms": 9,
            }
        },
    }

    class RecoveryJournal:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def model_evidence_for_case(self, case_id: str):
            assert case_id == "case_123"
            return evidence

        def case_projection(self, case_id: str):
            assert case_id == "case_123"
            return {
                "handler_binding_id": BINDING_ID,
                "status": "FINAL_ACCEPTED",
            }

        def build_model_acceptance_report(self, **kwargs: object):
            built.update(kwargs)
            return {"mode": kwargs["mode"], "report_id": "report"}

    monkeypatch.setattr(runner, "prepare_stage3_preflight", lambda **_kwargs: prepared)
    monkeypatch.setattr(runner, "SQLiteQQModelJournal", RecoveryJournal)
    monkeypatch.setitem(
        sys.modules,
        "qq_model_workflow_verifier",
        SimpleNamespace(
            verify_qq_model_workflow_evidence=lambda **kwargs: {
                "mode": kwargs["expected_mode"],
                "verified": True,
            }
        ),
    )
    report, verification = runner.recover_completed_live_stage3_reports(
        root=ROOT,
        store_path=".weflow/qq-sandbox.sqlite3",
        confirm_live_qq=True,
        confirm_live_model=True,
        pairing_id=PAIRING_ID,
        handler_binding_id=BINDING_ID,
        endpoint=None,
        model=None,
        profile_path="evals/qq-model/stage3-api-503-profile.v1.json",
        case_id="case_123",
    )
    assert report["mode"] == "qq-model-integrated-live"
    assert verification == {"mode": "qq-model-integrated-live", "verified": True}
    assert built["network_contacted"] is True
    assert built["external_write_attempted"] is True
    assert built["model_usage"]["total_tokens"] == 11


def test_completed_case_recovery_rejects_fake_zero_usage(monkeypatch) -> None:
    prepared = SimpleNamespace(
        root=ROOT,
        store_path=ROOT / ".weflow" / "qq-sandbox.sqlite3",
        model_config=SimpleNamespace(
            handler=SimpleNamespace(tenant_id=TENANT_ID),
            stage3_profile_sha256="a" * 64,
        ),
        binding={"handler_binding_id": BINDING_ID},
    )
    evidence = {
        "request": {
            "case_id": "case_123",
            "tenant_id": TENANT_ID,
            "handler_binding_id": BINDING_ID,
            "stage3_profile_sha256": "a" * 64,
        },
        "binding": {"handler_binding_id": BINDING_ID},
        "outcome": {"terminal_outcome": "response_ready", "private_preview_id": "preview"},
        "preview": {"preview_id": "preview"},
        "approval_decision": {"decision": "approved"},
        "final_result": {"status": "accepted", "provider_accepted": True},
        "acknowledgement_count": 1,
        "notification_count": 1,
        "deletion_count": 2,
        "lifecycle_status": "DELETED",
        "invocations": [
            {
                "status": "completed",
                "response_sha256": "b" * 64,
                "provider_latency_ms": 0,
                "usage": {"total_tokens": 0},
            }
        ],
    }

    class FakeEvidenceJournal:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def model_evidence_for_case(self, _case_id: str):
            return evidence

        def case_projection(self, _case_id: str):
            return {
                "handler_binding_id": BINDING_ID,
                "status": "FINAL_ACCEPTED",
            }

    monkeypatch.setattr(runner, "prepare_stage3_preflight", lambda **_kwargs: prepared)
    monkeypatch.setattr(runner, "SQLiteQQModelJournal", FakeEvidenceJournal)
    monkeypatch.setitem(
        sys.modules,
        "qq_model_workflow_verifier",
        SimpleNamespace(
            verify_qq_model_workflow_evidence=lambda **_kwargs: pytest.fail(
                "fake_evidence_reached_verifier"
            )
        ),
    )
    with pytest.raises(
        runner.QQHandlerStateConflict, match="stage3_completed_case_evidence_incomplete"
    ):
        runner.recover_completed_live_stage3_reports(
            root=ROOT,
            store_path=".weflow/qq-sandbox.sqlite3",
            confirm_live_qq=True,
            confirm_live_model=True,
            pairing_id=PAIRING_ID,
            handler_binding_id=BINDING_ID,
            endpoint=None,
            model=None,
            profile_path="evals/qq-model/stage3-api-503-profile.v1.json",
            case_id="case_123",
        )
