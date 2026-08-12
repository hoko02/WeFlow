from __future__ import annotations

from pathlib import Path

import pytest
from weflow_control_kernel.qq_handler import (
    QQ_HANDLER_REQUIRED_CAPABILITIES,
    QQHandlerActivationDenied,
    QQHandlerConfig,
)

ROOT = Path(__file__).resolve().parents[2]


def environment() -> dict[str, str]:
    return {
        "WEFLOW_QQ_APP_ID": "synthetic-app",
        "WEFLOW_QQ_CLIENT_SECRET": "not-a-real-secret",
        "WEFLOW_QQ_TENANT_ID": "synthetic-tenant",
        "WEFLOW_QQ_SANDBOX_PAIRING_ID": "qqpair_11111111111111111111111111111111",
        "WEFLOW_QQ_IDENTITY_SALT": "s" * 32,
        "WEFLOW_QQ_CAPABILITIES": ",".join(QQ_HANDLER_REQUIRED_CAPABILITIES),
    }


@pytest.mark.parametrize(
    ("key", "value", "reason"),
    [
        ("WEFLOW_PROVIDER_MODE", "live", "model_authority_denied"),
        ("WEFLOW_PROVIDER_API_KEY", "synthetic-secret", "unrelated_authority_denied"),
        ("WEFLOW_PROVIDER_ALLOW_LIVE", "1", "unrelated_authority_denied"),
        ("WEFLOW_EXTERNAL_WRITE_ENABLED", "1", "unrelated_authority_denied"),
        ("WEFLOW_MULTI_AGENT_ENABLED", "1", "unrelated_authority_denied"),
        ("WEFLOW_QQ_MAIL_ENABLED", "1", "unrelated_authority_denied"),
        ("WEFLOW_QQ_ATTACHMENT_ENABLED", "1", "unrelated_authority_denied"),
    ],
)
def test_stage2_rejects_model_generic_write_and_unrelated_authority(
    tmp_path: Path, key: str, value: str, reason: str
) -> None:
    values = environment()
    values[key] = value

    with pytest.raises(QQHandlerActivationDenied, match=reason):
        QQHandlerConfig.from_environment(
            confirm_live_qq=True,
            store_path=tmp_path / ".weflow" / "qq-sandbox.sqlite3",
            repository_root=tmp_path,
            group_openid="synthetic-group",
            environ=values,
        )
