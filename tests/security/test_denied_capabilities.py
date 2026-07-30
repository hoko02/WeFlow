from pathlib import Path

import pytest
from weflow_control_kernel.config import ConfigurationDenied, load_config
from weflow_control_kernel.status import build_service_status

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("environment", "capability"),
    [
        ({"WEFLOW_PROVIDER_MODE": "live-provider"}, "live_provider"),
        ({"WEFLOW_PROVIDER_API_KEY": "not-a-real-secret"}, "provider_credentials"),
        ({"WEFLOW_EXTERNAL_WRITE_ENABLED": "true"}, "external_write"),
        ({"WEFLOW_MULTI_AGENT_ENABLED": "true"}, "multi_agent"),
    ],
)
def test_each_forbidden_capability_fails_closed_before_runtime_start(
    environment: dict[str, str], capability: str
) -> None:
    with pytest.raises(ConfigurationDenied) as error:
        load_config(environment)

    assert error.value.as_dict()["capability"] == capability
    status = build_service_status("agent-runtime", environment=environment, root=ROOT)
    assert status["ready"] is False
    assert status["state"] == "configuration-denied"
    assert status["policy_denial"]["capability"] == capability
    assert "not-a-real-secret" not in str(status)
