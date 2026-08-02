"""Pure, allowlisted state transitions for Change 2 durable workflows."""

from __future__ import annotations

from collections.abc import Iterable

WORKFLOW_DEFINITION_VERSION = "durable-support-workflow.v1"

RECEIVED = "RECEIVED"
TICKET_READY = "TICKET_READY"
PAUSED = "PAUSED"
WAITING_FOR_OPERATOR = "WAITING_FOR_OPERATOR"
NEEDS_RECONCILIATION = "NEEDS_RECONCILIATION"
CANCELLED = "CANCELLED"

WORKFLOW_STATES = frozenset(
    {
        RECEIVED,
        TICKET_READY,
        PAUSED,
        WAITING_FOR_OPERATOR,
        NEEDS_RECONCILIATION,
        CANCELLED,
    }
)
TERMINAL_STATES = frozenset({TICKET_READY, CANCELLED})
NORMAL_PROGRESS_STATES = frozenset({RECEIVED})

TICKET_HANDOFF_COMPLETE = "ticket-handoff-complete"
PAUSE = "pause"
RESUME = "resume"
CANCEL = "cancel"
SLA_EXPIRED = "sla-expired"
RECONCILIATION_REQUIRED = "reconciliation-required"
RECONCILIATION_COMPLETE = "reconciliation-complete"

WORKFLOW_TRANSITION_KINDS = frozenset(
    {
        TICKET_HANDOFF_COMPLETE,
        PAUSE,
        RESUME,
        CANCEL,
        SLA_EXPIRED,
        RECONCILIATION_REQUIRED,
        RECONCILIATION_COMPLETE,
    }
)


class WorkflowTransitionError(ValueError):
    """A payload-safe transition denial for a deterministic workflow."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def is_terminal(state: str) -> bool:
    return state in TERMINAL_STATES


def run_status(state: str) -> str:
    """Return the derived execution status without making a business-success claim."""

    if state == PAUSED:
        return "paused"
    if state == NEEDS_RECONCILIATION:
        return "blocked"
    if state == CANCELLED:
        return "cancelled"
    return "active"


def allowed_targets(
    current_state: str,
    transition_kind: str,
    *,
    resume_state: str | None = None,
    unresolved_effect: bool = False,
) -> frozenset[str]:
    """Return precisely the legal target states for one durable fact or command."""

    if current_state not in WORKFLOW_STATES or transition_kind not in WORKFLOW_TRANSITION_KINDS:
        return frozenset()
    if transition_kind == TICKET_HANDOFF_COMPLETE:
        return frozenset({TICKET_READY}) if current_state == RECEIVED else frozenset()
    if transition_kind == PAUSE:
        return (
            frozenset({PAUSED})
            if current_state in {RECEIVED, TICKET_READY, WAITING_FOR_OPERATOR}
            else frozenset()
        )
    if transition_kind == RESUME:
        if current_state != PAUSED or resume_state not in WORKFLOW_STATES - {PAUSED, CANCELLED}:
            return frozenset()
        return frozenset({resume_state})
    if transition_kind == CANCEL:
        if unresolved_effect or current_state in {CANCELLED, NEEDS_RECONCILIATION}:
            return frozenset()
        return frozenset({CANCELLED})
    if transition_kind == SLA_EXPIRED:
        return (
            frozenset({WAITING_FOR_OPERATOR})
            if current_state not in TERMINAL_STATES | {NEEDS_RECONCILIATION}
            else frozenset()
        )
    if transition_kind == RECONCILIATION_REQUIRED:
        return (
            frozenset({NEEDS_RECONCILIATION})
            if current_state not in TERMINAL_STATES
            else frozenset()
        )
    if transition_kind == RECONCILIATION_COMPLETE:
        if current_state != NEEDS_RECONCILIATION or resume_state not in WORKFLOW_STATES - {
            PAUSED,
            NEEDS_RECONCILIATION,
            CANCELLED,
        }:
            return frozenset()
        return frozenset({resume_state})
    return frozenset()


def validate_transition(
    current_state: str,
    transition_kind: str,
    next_state: str,
    *,
    resume_state: str | None = None,
    unresolved_effect: bool = False,
) -> None:
    """Reject every non-Change-2 transition before an event can be appended."""

    if current_state not in WORKFLOW_STATES or next_state not in WORKFLOW_STATES:
        raise WorkflowTransitionError("workflow_state_not_allowlisted")
    if next_state not in allowed_targets(
        current_state,
        transition_kind,
        resume_state=resume_state,
        unresolved_effect=unresolved_effect,
    ):
        raise WorkflowTransitionError("workflow_transition_not_allowed")


def assert_known_states(states: Iterable[str]) -> None:
    if any(state not in WORKFLOW_STATES for state in states):
        raise WorkflowTransitionError("workflow_state_not_allowlisted")
