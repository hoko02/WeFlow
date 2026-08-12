from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from weflow_contracts import ContractValidationError, validate_qq_handler_passive_reply_chain

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "fixtures/contracts/v1/semantic/qq-handler-approval-and-delivery.json").read_text(
        encoding="utf-8"
    )
)


def _group_nudge() -> dict[str, object]:
    intent = copy.deepcopy(FIXTURE["passive_reply_intent"])
    intent.update(
        {
            "surface": "group",
            "operation": "qq.final_reply.execute",
            "response_kind": "group-nudge",
            "reply_msg_seq": 2,
            "approval_decision_id": None,
        }
    )
    return intent


def test_group_nudge_has_one_cross_language_contract_shape() -> None:
    validate_qq_handler_passive_reply_chain(_group_nudge(), [], ROOT)


def test_group_nudge_cannot_reuse_final_delivery_sequence() -> None:
    intent = _group_nudge()
    intent["reply_msg_seq"] = 5
    with pytest.raises(ContractValidationError, match="response_shape_mismatch"):
        validate_qq_handler_passive_reply_chain(intent, [], ROOT)
