from pathlib import Path

from weflow_contracts import validation

SCHEMA_ID = "https://weflow.local/contracts/v1/cache-test.schema.json"
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": SCHEMA_ID,
    "type": "object",
    "required": ["schema_id"],
    "properties": {"schema_id": {"const": SCHEMA_ID}},
    "additionalProperties": False,
}


def test_contract_validators_are_loaded_once_per_resolved_root(tmp_path: Path, monkeypatch) -> None:
    loaded_roots: list[Path] = []

    def load(root: Path) -> dict[str, dict[str, object]]:
        loaded_roots.append(root)
        return {SCHEMA_ID: SCHEMA}

    monkeypatch.setattr(validation, "load_contract_schemas", load)
    validation._contract_validators.cache_clear()
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    payload = {"schema_id": SCHEMA_ID}

    validation.validate_payload(payload, first_root)
    validation.validate_payload(payload, first_root)
    validation.validate_payload(payload, second_root)

    assert loaded_roots == [first_root.resolve(), second_root.resolve()]
    validation._contract_validators.cache_clear()
