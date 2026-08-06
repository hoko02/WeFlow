from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from weflow_testkit.live_evaluation import (
    LIVE_CREDENTIAL_ENVIRONMENT_VARIABLE,
    LiveConfigurationDenied,
    load_live_credential,
    load_live_pilot_suite,
    parse_live_evaluation_config,
    validate_public_https_endpoint,
    validate_same_origin_redirect,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 6, tzinfo=UTC)


def _suite():
    return load_live_pilot_suite(ROOT, now=NOW)


def _public_resolver(_host: str, _port: int) -> tuple[str, ...]:
    return ("1.1.1.1",)


def test_valid_live_config_is_operator_controlled_and_publicly_redacted() -> None:
    config = parse_live_evaluation_config(
        _suite(),
        confirm_live=True,
        endpoint="https://api.deepseek.com",
        model="deepseek-v4-flash",
        resolver=_public_resolver,
    )

    assert config.endpoint == "https://api.deepseek.com"
    assert config.model == "deepseek-v4-flash"
    assert config.budget_profile["temperature"] == 0
    assert "endpoint" not in config.public_dict()
    assert "model" not in config.public_dict()
    assert "credential" not in str(config.public_dict()).lower()


def test_missing_confirmation_fails_before_dns_or_credential_access() -> None:
    calls: list[str] = []

    def resolver(host: str, _port: int) -> tuple[str, ...]:
        calls.append(host)
        return ("1.1.1.1",)

    with pytest.raises(LiveConfigurationDenied, match="explicit_confirmation_required"):
        parse_live_evaluation_config(
            _suite(),
            confirm_live=False,
            endpoint="https://api.deepseek.com",
            model="deepseek-v4-flash",
            resolver=resolver,
        )
    assert calls == []


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://api.deepseek.com",
        "https://user:pass@api.deepseek.com",
        "https://api.deepseek.com?target=other",
        "https://127.0.0.1",
        "https://api.deepseek.com:8443",
    ),
)
def test_unsafe_endpoint_shapes_fail_before_dns(endpoint: str) -> None:
    calls: list[str] = []

    def resolver(host: str, _port: int) -> tuple[str, ...]:
        calls.append(host)
        return ("1.1.1.1",)

    with pytest.raises(LiveConfigurationDenied):
        validate_public_https_endpoint(endpoint, resolver=resolver)
    assert calls == []


def test_private_resolved_address_is_denied() -> None:
    with pytest.raises(LiveConfigurationDenied, match="address_not_public"):
        validate_public_https_endpoint(
            "https://api.deepseek.com", resolver=lambda _host, _port: ("10.0.0.4",)
        )


def test_fixture_cannot_expand_model_beyond_price_profile() -> None:
    calls: list[str] = []
    with pytest.raises(LiveConfigurationDenied, match="model_price_profile_mismatch"):
        parse_live_evaluation_config(
            _suite(),
            confirm_live=True,
            endpoint="https://api.deepseek.com",
            model="fixture-selected-model",
            resolver=lambda host, _port: calls.append(host) or ("1.1.1.1",),
        )
    assert calls == []


def test_cross_origin_redirect_is_denied_but_same_origin_path_is_allowed() -> None:
    assert (
        validate_same_origin_redirect(
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
            resolver=_public_resolver,
        )
        == "https://api.deepseek.com/v1"
    )
    with pytest.raises(LiveConfigurationDenied, match="cross_origin_redirect_denied"):
        validate_same_origin_redirect(
            "https://api.deepseek.com",
            "https://other.example/v1",
            resolver=_public_resolver,
        )


def test_credential_is_loaded_only_after_config_and_never_repr_echoed() -> None:
    config = parse_live_evaluation_config(
        _suite(),
        confirm_live=True,
        endpoint="https://api.deepseek.com",
        model="deepseek-v4-flash",
        resolver=_public_resolver,
    )
    sentinel = "unit-test-live-credential-sentinel"
    auth = load_live_credential(config, {LIVE_CREDENTIAL_ENVIRONMENT_VARIABLE: sentinel})

    assert repr(auth) == "LiveCredential(redacted)"
    assert sentinel not in repr(auth)
    assert auth.authorization_header().endswith(sentinel)


def test_missing_credential_error_never_echoes_environment_values() -> None:
    config = parse_live_evaluation_config(
        _suite(),
        confirm_live=True,
        endpoint="https://api.deepseek.com",
        model="deepseek-v4-flash",
        resolver=_public_resolver,
    )
    with pytest.raises(LiveConfigurationDenied, match="credential_missing") as error:
        load_live_credential(config, {})
    assert "api.deepseek.com" not in str(error.value)
