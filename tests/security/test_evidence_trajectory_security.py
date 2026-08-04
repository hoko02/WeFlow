"""Fail-closed isolation checks for redacted Evidence Trajectories."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from weflow_contracts import ContractValidationError, content_hash, validate_evidence_chain

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "contracts" / "v1" / "semantic" / "evidence-trajectory.json"
JsonObject = dict[str, Any]


def _chain() -> JsonObject:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rehash_trajectory(trajectory: JsonObject) -> None:
    trajectory["root_sha256"] = content_hash(trajectory, without="root_sha256")


@pytest.mark.parametrize(
    "unsafe_case",
    (
        "raw_private_content",
        "secret_like_value",
        "customer_success_language",
        "caller_selected_authority",
        "foreign_reference",
        "undeclared_field",
        "detached_chain",
        "invalid_schema_version",
        "broken_causation",
        "duplicate_node",
        "out_of_order_node",
        "tampered_source_hash",
    ),
)
def test_unsafe_evidence_inputs_are_rejected_before_any_persistence(unsafe_case: str) -> None:
    fixture = deepcopy(_chain())
    artifact = fixture["artifact"]
    trajectory = fixture["trajectory"]
    report = fixture["report"]
    replay = fixture["replay_result"]

    if unsafe_case == "raw_private_content":
        report["raw_message"] = "private prompt material"
    elif unsafe_case == "secret_like_value":
        report["credential"] = "provider_token=not-a-real-secret"
    elif unsafe_case == "customer_success_language":
        report["outcome"] = "customer_resolved"
    elif unsafe_case == "caller_selected_authority":
        report["authority"] = "caller-selected-admin"
    elif unsafe_case == "foreign_reference":
        report["tenant_id"] = "tenant-foreign"
    elif unsafe_case == "undeclared_field":
        report["include_raw"] = True
    elif unsafe_case == "detached_chain":
        artifact["trajectory_id"] = "trajectory-detached"
    elif unsafe_case == "invalid_schema_version":
        trajectory["schema_version"] = "v2"
    elif unsafe_case == "broken_causation":
        trajectory["nodes"][1]["predecessor_node_id"] = None
        _rehash_trajectory(trajectory)
    elif unsafe_case == "duplicate_node":
        trajectory["nodes"][2]["node_id"] = trajectory["nodes"][1]["node_id"]
        _rehash_trajectory(trajectory)
    elif unsafe_case == "out_of_order_node":
        trajectory["nodes"][2]["sequence"] = 99
        _rehash_trajectory(trajectory)
    else:
        trajectory["nodes"][2]["content_sha256"] = "f" * 64
        _rehash_trajectory(trajectory)

    with pytest.raises(ContractValidationError):
        validate_evidence_chain(artifact, trajectory, report, replay, ROOT)
