from weflow_control_kernel.config import ConfigurationDenied, load_config


def test_default_configuration_is_offline_and_replay_only() -> None:
    config = load_config({})

    assert config.mode == "offline"
    assert config.provider_mode == "replay"
    assert not config.provider_allow_live
    assert not config.external_write_enabled
    assert not config.multi_agent_enabled


def test_live_provider_selection_is_denied_without_echoing_setting() -> None:
    try:
        load_config({"WEFLOW_PROVIDER_MODE": "a-real-provider"})
    except ConfigurationDenied as error:
        assert error.as_dict()["capability"] == "live_provider"
        assert "a-real-provider" not in str(error)
    else:
        raise AssertionError("Live provider configuration must be denied")


def test_credential_configuration_is_denied_without_echoing_value() -> None:
    try:
        load_config({"WEFLOW_PROVIDER_API_KEY": "not-a-real-secret"})
    except ConfigurationDenied as error:
        assert error.as_dict()["capability"] == "provider_credentials"
        assert "not-a-real-secret" not in str(error)
    else:
        raise AssertionError("Credential configuration must be denied")
