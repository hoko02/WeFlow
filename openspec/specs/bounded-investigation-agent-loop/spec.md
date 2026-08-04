# bounded-investigation-agent-loop Specification

## Purpose
Define the deterministic, replay-only investigation loop that may propose bounded
outcomes but cannot control workflow state or perform external effects.

## Requirements

### Requirement: A replay-only single Agent produces closed structured outcomes
The runtime SHALL run exactly one deterministic Replay Agent from a named synthetic
fixture and immutable Context Manifest. Each action SHALL validate as one of
`read_crm`, `read_monitoring`, `read_knowledge`, `needs_information`,
`needs_operator`, or `response_candidate`. It SHALL reject unknown fields, malformed
actions, direct state changes, approval, delivery, external writes, and completion
claims.

#### Scenario: A valid fixture completes bounded investigation
- **WHEN** a named API-503 replay fixture supplies a valid action transcript
- **THEN** the runtime SHALL persist ordered safe step facts and return only a
  schema-valid terminal outcome

#### Scenario: An action claims authority
- **WHEN** an Agent action requests a state change, approval, delivery, provider, or
  external write
- **THEN** the runtime SHALL fail closed and append no workflow transition or effect

### Requirement: Agent execution has deterministic duplicate, budget, and progress gates
The runtime SHALL use stable step identities and enforce fixture-defined action, tool,
and consecutive-no-progress limits outside the Agent. It SHALL return a safe terminal
outcome at a limit and SHALL not replay a completed step after restart.

#### Scenario: A transcript repeats without progress
- **WHEN** the same logical action recurs beyond the fixture limit
- **THEN** the runtime SHALL stop with `needs_operator` and preserve the prior durable
  facts
