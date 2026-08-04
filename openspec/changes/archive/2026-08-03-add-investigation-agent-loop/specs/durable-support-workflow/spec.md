## MODIFIED Requirements

### Requirement: The durable workflow owns an allowlisted non-resolution state machine
The control kernel SHALL remain the only component that emits workflow-originated Case-state events. In addition to retained Change 2 transitions, it SHALL permit TICKET_READY to INVESTIGATING only after a durable replay investigation activation and INVESTIGATING to RESPONSE_READY only after a matching deterministic verifier outcome. The Agent SHALL not select a target state. The workflow SHALL NOT emit approval, delivery, RESOLVED, COMPLETED, or customer-success states.

#### Scenario: A verified candidate advances the workflow
- **WHEN** a replay investigation has a durable checkpoint and a matching verified candidate outcome
- **THEN** the control kernel SHALL append one RESPONSE_READY transition and checkpoint it

#### Scenario: An unverified candidate is returned
- **WHEN** the Agent returns needs_information, needs_operator, or a rejected candidate
- **THEN** the workflow SHALL remain in or enter an allowlisted safe non-success state without a response-ready transition