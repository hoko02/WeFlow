"""Locate and load the canonical language-neutral JSON Schema files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def find_repository_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__).resolve()).resolve()
    for candidate in (current, *current.parents):
        schema_directory = candidate / "contracts" / "jsonschema" / "v1"
        if schema_directory.is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("WeFlow repository root could not be located")


def contract_schema_paths(root: Path | None = None) -> tuple[Path, ...]:
    directory = (root or find_repository_root()) / "contracts" / "jsonschema" / "v1"
    return tuple(sorted(directory.glob("*.schema.json")))


def load_contract_schemas(root: Path | None = None) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for path in contract_schema_paths(root):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise ValueError(f"Schema has no stable identifier: {path.name}")
        schemas[schema_id] = schema
    return schemas


def schema_fingerprints(root: Path | None = None) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for schema_id, schema in load_contract_schemas(root).items():
        canonical = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        fingerprints[schema_id] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return dict(sorted(fingerprints.items()))
