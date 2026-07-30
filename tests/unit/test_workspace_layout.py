from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_workspace_declares_required_boundaries() -> None:
    required_files = (
        "pyproject.toml",
        "package.json",
        "pnpm-workspace.yaml",
        "scripts/dev.py",
        "apps/platform-api/pyproject.toml",
        "apps/control-worker/pyproject.toml",
        "apps/agent-runtime/pyproject.toml",
        "apps/business-simulator/pyproject.toml",
        "apps/web-console/package.json",
        "packages/python/weflow-contracts/pyproject.toml",
        "packages/typescript/weflow-contracts/package.json",
    )

    missing = [path for path in required_files if not (ROOT / path).is_file()]
    assert not missing, f"Missing required workspace files: {', '.join(missing)}"


def test_local_configuration_defaults_to_replay_only() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "WEFLOW_MODE=offline" in example
    assert "WEFLOW_PROVIDER_MODE=replay" in example
    assert "WEFLOW_PROVIDER_ALLOW_LIVE=false" in example
    assert "WEFLOW_EXTERNAL_WRITE_ENABLED=false" in example
    assert "WEFLOW_MULTI_AGENT_ENABLED=false" in example
