"""Deterministic fixture-only synthetic IM intake adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from weflow_contracts import ContractValidationError, validate_inbound_message_event
from weflow_control_kernel.ledger import (
    CaseLedger,
    IntakeResult,
    SQLiteCaseLedger,
    SyntheticActorRegistry,
)

JsonObject = dict[str, Any]


def _find_repository_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "fixtures" / "intake").is_dir() and (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate
    raise RuntimeError("WeFlow repository root could not be located")


def load_intake_fixture(fixture_id: str, root: Path | None = None) -> JsonObject:
    """Load only a named checked-in synthetic intake fixture."""

    if not fixture_id or any(character in fixture_id for character in "/\\"):
        raise ValueError("invalid_fixture_id")
    path = (root or _find_repository_root()) / "fixtures" / "intake" / f"{fixture_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fixture_id") != fixture_id or payload.get("synthetic") is not True:
        raise ValueError("invalid_synthetic_fixture")
    return normalize_intake_fixture(payload, root=root)


def normalize_intake_fixture(
    fixture: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> JsonObject:
    """Return the safe actor/event shape consumed by the local Case ledger."""

    actor_id = fixture.get("actor_id")
    inbound_message = fixture.get("inbound_message")
    if not isinstance(actor_id, str) or not isinstance(inbound_message, Mapping):
        raise ValueError("invalid_synthetic_fixture")
    try:
        validate_inbound_message_event(inbound_message, root)
    except ContractValidationError as error:
        raise ValueError("invalid_synthetic_fixture") from error
    return {
        "fixture_id": fixture["fixture_id"],
        "actor_id": actor_id,
        "inbound_message": dict(inbound_message),
        "expected": dict(fixture.get("expected", {})),
    }


class SyntheticIntakeSimulator:
    """Fixture-only bridge to deterministic intake; it registers no external tool."""

    def __init__(
        self,
        registry: SyntheticActorRegistry | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        self.registry = registry or SyntheticActorRegistry.default()
        self.root = root

    def fixture_request(self, fixture_id: str) -> JsonObject:
        """Prepare one allowlisted synthetic fixture for an in-process boundary."""

        fixture = load_intake_fixture(fixture_id, self.root)
        self.registry.resolve(str(fixture["actor_id"]))
        return fixture

    def submit_fixture(self, ledger: CaseLedger, fixture_id: str) -> IntakeResult:
        fixture = self.fixture_request(fixture_id)
        tenant_id = self.registry.resolve(str(fixture["actor_id"]))
        return ledger.intake(
            fixture["inbound_message"],
            effective_tenant_id=tenant_id,
        )

    def export_snapshot(self, ledger: SQLiteCaseLedger, actor_id: str) -> JsonObject:
        return ledger.export_snapshot(self.registry.resolve(actor_id))
