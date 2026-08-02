## ADDED Requirements

### Requirement: An accepted Case revision has one durable workflow identity
The deterministic control kernel SHALL record a workflow activation after Change 1 has
atomically committed a new accepted Case and Revision 1. The activation SHALL use a
stable workflow identity derived from effective tenant, Case, CaseRevision, and
workflow-definition version. It SHALL create or resume at most one active workflow run
for that identity.
The activation and run records SHALL be tenant-scoped, append-only, correlated to the
accepted source event, and reconstructable after a worker restart. An inbound retry
MUST NOT create a second activation, run, checkpoint, state event, or effect intent.

#### Scenario: A newly accepted Case is activated once
- **WHEN** a valid first synthetic IM delivery has committed its Change 1 source
  records and the offline control worker processes the resulting activation
- **THEN** the worker SHALL create one stable workflow identity and an append-only
  activation/run record while the Case remains a non-successful workflow-owned Case

#### Scenario: Activation is recovered after a worker restart
- **WHEN** a worker stops after activation is durable but before it has recorded a
  later checkpoint and a fresh worker opens the same local store
- **THEN** recovery SHALL resume the same workflow identity from durable source facts
  without creating a duplicate Case, revision, activation, or run

#### Scenario: A duplicate inbound delivery arrives while a workflow exists
- **WHEN** the original accepted inbound envelope is delivered again after its workflow
  activation has been recorded
- **THEN** the intake result SHALL remain `deduplicated` and the workflow journal,
  Case state, checkpoint sequence, and simulated-effect counts SHALL remain unchanged

### Requirement: The durable workflow owns an allowlisted non-resolution state machine
The control kernel SHALL be the only component allowed to emit workflow-originated
Case-state events. It SHALL support only the following Change 2 transitions:
`RECEIVED -> TICKET_READY` after a simulated ticket handoff is reconciled complete;
`RECEIVED|TICKET_READY -> PAUSED`; `PAUSED ->` the checkpointed pre-pause state;
eligible non-terminal state `-> CANCELLED`; unfinished SLA work `->
WAITING_FOR_OPERATOR`; and any unknown/conflicting side-effect outcome `->
NEEDS_RECONCILIATION`. A reconciled known outcome SHALL return only to the
checkpointed safe continuation state. The workflow SHALL NOT emit `RESPONSE_READY`,
`RESOLVED`, `COMPLETED`, or any customer-success state in this change.

#### Scenario: A simulated handoff reaches the bounded success horizon
- **WHEN** the workflow has a valid durable checkpoint and the fixture-local ticket
  effect is reconciled and completed with matching tenant, natural key, and version
- **THEN** it SHALL append the allowed transition to `TICKET_READY` and SHALL not
  create a response, approval, delivery receipt, resolution, or completion claim

#### Scenario: An invalid state transition is requested
- **WHEN** a caller, fixture, or stale workflow record attempts to set an unallowlisted
  state, skip a required effect phase, or move from `CANCELLED` to an active state
- **THEN** the control kernel SHALL reject it with a safe reason code, append no forged
  Case event, and preserve the prior projection and workflow checkpoint

#### Scenario: An unknown effect outcome blocks normal progress
- **WHEN** an effect has an unknown result, conflicting natural-key observation, or
  stale expected version
- **THEN** the workflow SHALL append a reconciliation-required fact, enter
  `NEEDS_RECONCILIATION`, and SHALL NOT advance to `TICKET_READY` or retry blindly

### Requirement: Checkpoints and workflow commands are durable, scoped, and idempotent
Every workflow progress boundary SHALL persist an immutable `WorkflowCheckpoint` with
a monotonic sequence, Case/revision/workflow identity, current and resume state,
synthetic SLA deadline, pending/completed intent references, causation reference,
correlation metadata, and canonical content hash. The workflow SHALL accept only
allowlisted `pause`, `resume`, and `cancel` commands carrying a stable command identity
and expected workflow version. It SHALL derive tenant authority from the synthetic
actor boundary; no request may choose a tenant, target state, event type, ticket
identity, deadline, or arbitrary checkpoint content.

#### Scenario: Pause and resume preserve the checkpointed continuation
- **WHEN** a valid tenant-scoped pause command is accepted for an active workflow and a
  valid idempotent resume command is later accepted at the expected workflow version
- **THEN** the workflow SHALL append durable command/checkpoint facts, enter `PAUSED`,
  and resume only the saved non-terminal continuation state without duplicating an
  already completed effect

#### Scenario: A stale or foreign command is rejected without disclosure
- **WHEN** a command has a stale expected workflow version, duplicate command identity
  with different content, or an actor mapped to another tenant
- **THEN** the command boundary SHALL return an allowlisted safe failure, reveal no
  foreign workflow existence, and create no command, state, checkpoint, or effect
  record

#### Scenario: Cancellation cannot bypass reconciliation
- **WHEN** a cancel command reaches a workflow with an intent whose observed outcome
  is unknown
- **THEN** the workflow SHALL remain or enter `NEEDS_RECONCILIATION` and SHALL not mark
  the Case cancelled until the intent has a durable reconciled outcome

### Requirement: Synthetic SLA timing is deterministic and survives restart
The workflow SHALL snapshot a fixture-defined `SyntheticSlaPolicy` at activation and
derive a stable deadline from the accepted Case timestamp using an injectable monotonic
clock. Deadline processing SHALL append a safe SLA fact and preserve its deadline
across restart, pause, resume, and projection rebuild. A pause SHALL NOT erase or
extend a deadline. An SLA event SHALL NOT invoke a model, provider, approval, outbound
delivery, or customer escalation.

#### Scenario: An unfinished workflow reaches its synthetic SLA deadline
- **WHEN** the injected clock reaches the recorded deadline before the required
  simulated handoff is known complete
- **THEN** the workflow SHALL append one deadline fact, enter `WAITING_FOR_OPERATOR`,
  and create no external action or customer-resolution claim

#### Scenario: A deadline is rebuilt after worker interruption
- **WHEN** a worker stops before a scheduled deadline and a new worker restores the
  workflow from its durable journal with the same fixture clock
- **THEN** the restored workflow SHALL retain the original deadline and emit at most one
  deadline fact at the same deterministic point

### Requirement: Offline and service-boundary drivers preserve the same control semantics
The workflow reducer and journal contracts SHALL be independent of the runtime driver.
Offline mode SHALL run them with local SQLite and fixture time without Docker, network,
or model credentials. Explicit service-boundary mode SHALL use a Temporal control-worker
driver for the same identities, checkpoints, activities, and safe failure behavior;
Temporal history SHALL NOT be the only Case audit source. A missing Temporal dependency
MUST make only the service-boundary workflow not ready and MUST NOT fall back to a model,
network provider, or in-memory success path.

#### Scenario: Offline workflow acceptance runs without local services
- **WHEN** a contributor runs the Change 2 workflow fixtures in offline mode with Docker
  and network unavailable
- **THEN** the deterministic SQLite workflow driver SHALL produce the required
  checkpoints, projections, and recovery evidence without initializing Temporal,
  a model, or an enterprise client

#### Scenario: Temporal is unavailable in service-boundary mode
- **WHEN** the service-boundary control worker cannot reach its declared local Temporal
  dependency before the readiness deadline
- **THEN** it SHALL report a redacted not-ready diagnostic, execute no workflow effect,
  and leave the durable Case/workflow source state unchanged

### Requirement: The workflow remains a model-free and approval-free control slice
The workflow SHALL not initialize an Agent, model/provider client, approval service,
delivery adapter, real ticket adapter, or external-write executor. The deterministic
reducer is the only state/verifier authority for this change. Capability reporting SHALL
identify the narrow durable-workflow slice only after its acceptance passes while
retaining `business_workflow_implemented=false` and
`external_writes_enabled=false`.

#### Scenario: A fixture or caller requests an excluded capability
- **WHEN** a workflow command, replay fixture, or configuration requests model-driven
  action, approval, outbound delivery, a real provider, or a customer-completion
  result
- **THEN** the runtime SHALL fail closed with an allowlisted denial, initialize none of
  those components, and persist no state or effect that claims authorization or success
