import json
from pathlib import Path

import pytest
from weflow_contracts.qq_pairing import (
    validate_qq_group_pairing_acceptance_report,
    validate_qq_group_pairing_chain,
)
from weflow_contracts.validation import ContractValidationError

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "fixtures/contracts/v1/semantic/qq-group-pairing.json").read_text(encoding="utf-8")
)


def test_pairing_contract_chain_and_report_are_valid() -> None:
    validate_qq_group_pairing_chain(FIXTURE["challenge"], [FIXTURE["completion"]], ROOT)
    validate_qq_group_pairing_acceptance_report(FIXTURE["report"], ROOT)


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("challenge", "challenge_plaintext", "WFPAIR-forbidden"),
        ("completion", "group_openid", "raw-group"),
        ("completion", "tenant_id", "tenant-foreign"),
        ("report", "qq_group_pairing_live_verified", True),
        ("report", "stage1_verified", True),
    ],
)
def test_pairing_contracts_fail_closed(target: str, field: str, value: object) -> None:
    payload = json.loads(json.dumps(FIXTURE))
    payload[target][field] = value
    with pytest.raises(ContractValidationError):
        if target == "report":
            validate_qq_group_pairing_acceptance_report(payload["report"], ROOT)
        else:
            validate_qq_group_pairing_chain(payload["challenge"], [payload["completion"]], ROOT)
