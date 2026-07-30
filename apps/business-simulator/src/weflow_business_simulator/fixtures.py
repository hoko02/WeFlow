"""Load only declared local synthetic replay fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _find_repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "fixtures" / "replay").is_dir() and (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate
    raise RuntimeError("WeFlow repository root could not be located")


def load_replay_fixture(fixture_id: str, root: Path | None = None) -> dict[str, Any]:
    if not fixture_id or any(character in fixture_id for character in "/\\"):
        raise ValueError("invalid_fixture_id")
    path = (root or _find_repository_root()) / "fixtures" / "replay" / f"{fixture_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fixture_id") != fixture_id or payload.get("synthetic") is not True:
        raise ValueError("invalid_synthetic_fixture")
    return payload
