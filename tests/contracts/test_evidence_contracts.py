# ruff: noqa: E501
import json
from copy import deepcopy
from pathlib import Path

import pytest
from weflow_contracts import (
    ContractValidationError,
    content_hash,
    validate_evidence_chain,
    validate_evidence_report,
    validate_evidence_trajectory,
    validate_trajectory_replay_result,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "fixtures" / "contracts" / "v1"


def _chain() -> dict[str, dict[str, object]]:
    return json.loads((FIXTURE_ROOT / "semantic" / "evidence-trajectory.json").read_text())


def test_redacted_evidence_chain_is_contract_valid_and_hash_bound() -> None:
    fixture = _chain()
    validate_evidence_chain(
        fixture["artifact"],
        fixture["trajectory"],
        fixture["report"],
        fixture["replay_result"],
        ROOT,
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "raw_payload",
        "foreign_tenant",
        "duplicate_node",
        "out_of_order",
        "customer_success",
        "tampered_hash",
    ),
)
def test_unsafe_or_detached_evidence_chain_is_rejected(mutation: str) -> None:
    fixture = deepcopy(_chain())
    if mutation == "raw_payload":
        fixture["report"]["raw_message"] = "not-allowed"
    elif mutation == "foreign_tenant":
        fixture["report"]["tenant_id"] = "tenant-foreign"
    elif mutation == "duplicate_node":
        fixture["trajectory"]["nodes"][2]["node_id"] = "node-01"
    elif mutation == "out_of_order":
        fixture["trajectory"]["nodes"][2]["sequence"] = 8
    elif mutation == "customer_success":
        fixture["report"]["outcome"] = "customer_resolved"
    else:
        fixture["trajectory"]["root_sha256"] = "f" * 64

    with pytest.raises(ContractValidationError):
        validate_evidence_chain(
            fixture["artifact"],
            fixture["trajectory"],
            fixture["report"],
            fixture["replay_result"],
            ROOT,
        )


def test_replay_result_requires_matching_root_and_report_hash() -> None:
    fixture = _chain()
    replay = deepcopy(fixture["replay_result"])
    replay["replayed_root_sha256"] = "f" * 64
    replay["result_sha256"] = content_hash(replay, without="result_sha256")
    with pytest.raises(ContractValidationError, match="replay_root_mismatch"):
        validate_trajectory_replay_result(
            replay,
            ROOT,
            trajectory=fixture["trajectory"],
            report=fixture["report"],
        )

    report = deepcopy(fixture["report"])
    report["content_sha256"] = "f" * 64
    with pytest.raises(ContractValidationError, match="content_sha256_mismatch"):
        validate_evidence_report(report, ROOT, trajectory=fixture["trajectory"])

    trajectory = deepcopy(fixture["trajectory"])
    trajectory["nodes"][1]["predecessor_node_id"] = None
    trajectory["root_sha256"] = content_hash(trajectory, without="root_sha256")
    with pytest.raises(ContractValidationError, match="causal_predecessor_invalid"):
        validate_evidence_trajectory(trajectory, ROOT)
