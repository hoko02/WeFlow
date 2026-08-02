import pytest
from weflow_control_kernel.workflow_state import (
    CANCEL,
    CANCELLED,
    NEEDS_RECONCILIATION,
    PAUSE,
    PAUSED,
    RECEIVED,
    RECONCILIATION_COMPLETE,
    RECONCILIATION_REQUIRED,
    RESUME,
    SLA_EXPIRED,
    TICKET_HANDOFF_COMPLETE,
    TICKET_READY,
    WAITING_FOR_OPERATOR,
    WorkflowTransitionError,
    run_status,
    validate_transition,
)


@pytest.mark.parametrize(
    ("current", "kind", "target", "resume_state"),
    [
        (RECEIVED, TICKET_HANDOFF_COMPLETE, TICKET_READY, TICKET_READY),
        (RECEIVED, PAUSE, PAUSED, RECEIVED),
        (TICKET_READY, PAUSE, PAUSED, TICKET_READY),
        (WAITING_FOR_OPERATOR, PAUSE, PAUSED, WAITING_FOR_OPERATOR),
        (PAUSED, RESUME, RECEIVED, RECEIVED),
        (RECEIVED, SLA_EXPIRED, WAITING_FOR_OPERATOR, WAITING_FOR_OPERATOR),
        (RECEIVED, RECONCILIATION_REQUIRED, NEEDS_RECONCILIATION, RECEIVED),
        (
            NEEDS_RECONCILIATION,
            RECONCILIATION_COMPLETE,
            RECEIVED,
            RECEIVED,
        ),
        (RECEIVED, CANCEL, CANCELLED, CANCELLED),
    ],
)
def test_change_two_allows_only_declared_state_transitions(
    current: str,
    kind: str,
    target: str,
    resume_state: str,
) -> None:
    validate_transition(current, kind, target, resume_state=resume_state)


@pytest.mark.parametrize(
    ("current", "kind", "target", "resume_state", "unresolved_effect"),
    [
        (RECEIVED, TICKET_HANDOFF_COMPLETE, "RESOLVED", "RESOLVED", False),
        (TICKET_READY, TICKET_HANDOFF_COMPLETE, TICKET_READY, TICKET_READY, False),
        (PAUSED, RESUME, PAUSED, PAUSED, False),
        (NEEDS_RECONCILIATION, CANCEL, CANCELLED, CANCELLED, False),
        (RECEIVED, CANCEL, CANCELLED, CANCELLED, True),
        (CANCELLED, SLA_EXPIRED, WAITING_FOR_OPERATOR, WAITING_FOR_OPERATOR, False),
    ],
)
def test_change_two_rejects_resolution_and_unallowlisted_or_unsafe_transitions(
    current: str,
    kind: str,
    target: str,
    resume_state: str,
    unresolved_effect: bool,
) -> None:
    with pytest.raises(WorkflowTransitionError, match="workflow_"):
        validate_transition(
            current,
            kind,
            target,
            resume_state=resume_state,
            unresolved_effect=unresolved_effect,
        )


def test_run_status_never_turns_ticket_ready_into_customer_completion() -> None:
    assert run_status(TICKET_READY) == "active"
    assert run_status(PAUSED) == "paused"
    assert run_status(NEEDS_RECONCILIATION) == "blocked"
    assert run_status(CANCELLED) == "cancelled"
