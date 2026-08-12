# case-event-ledger Specification

## Purpose
Define the deterministic, tenant-scoped, append-only Case ledger and replayable local snapshot boundary.
## Requirements
### Requirement: Accepted IM intake atomically creates immutable initial Case state
For a first accepted inbound delivery, deterministic control code SHALL atomically
create one stable Case, one immutable CaseRevision with revision value `1` and no
predecessor, and exactly three append-only BusinessEvents in per-Case event-index
order: `inbound.received.v1`, `case.revision-created.v1`, and
`case.state-transitioned.v1` to `RECEIVED`. Each generated record SHALL carry the
effective tenant, stable correlation metadata, and only safe/content-addressed event
metadata.

#### Scenario: A first synthetic delivery creates its initial ledger
- **WHEN** a valid new inbound delivery passes identity, duplicate, and sequence
validation
- **THEN** one transaction SHALL persist the Case, CaseRevision 1, and exactly the
three required ordered events, and the derived projection SHALL report `RECEIVED`

#### Scenario: Source persistence fails during intake
- **WHEN** an error or uniqueness conflict occurs before the initial intake transaction
commits
- **THEN** the ledger SHALL roll back without a partial Case, revision, event, receipt,
or projection and SHALL return a payload-safe failure result

### Requirement: Case revisions and business events are append-only source records
The ledger SHALL retain immutable CaseRevision and BusinessEvent records, reject
update/delete attempts, enforce unique tenant-scoped record identities and per-Case
event indexes, and expose no public endpoint for an arbitrary event append or
caller-provided Case state. Only the deterministic control-kernel workflow port may
append an allowlisted workflow-originated event, including investigation-started,
response-candidate-verified, policy-approval-activated, approval-requested,
approval-decided, delivery-intended, delivery-reconciled, and delivery-recorded events,
after it validates tenant, Case, revision, workflow identity, checkpoint causation,
predecessor state, authorization binding where required, and canonical payload digest.

#### Scenario: A mutation of a historical revision or event is attempted
- **WHEN** application code or a test attempts to update or delete a persisted
  CaseRevision or BusinessEvent through the ledger storage boundary
- **THEN** the operation SHALL fail with an append-only violation and the original
  record sequence SHALL remain unchanged

#### Scenario: A caller attempts to forge a later state or event
- **WHEN** a client submits a route or payload intended to append an arbitrary event or
  change a Case out of `RECEIVED`
- **THEN** the API SHALL not expose/accept that operation and SHALL not change the
  projection, ledger, approval state, or completion state

#### Scenario: The control kernel records an allowed workflow transition
- **WHEN** the durable workflow has a valid checkpoint and an allowlisted transition
  with matching tenant, Case, revision, causation, and predecessor state
- **THEN** the ledger SHALL append one canonical workflow-originated BusinessEvent at
  the next per-Case index and SHALL reject a duplicate, out-of-order, or invalid
  transition without changing the projection

#### Scenario: An Agent attempts to append a Case event
- **WHEN** an Agent result or API caller supplies an event or state payload
- **THEN** the ledger SHALL reject it and preserve the source timeline

#### Scenario: An approval route attempts to forge authorization or delivery facts
- **WHEN** an API caller supplies a tenant, role, candidate, evidence, policy, grant,
  target state, or delivery result instead of a permitted decision input
- **THEN** the ledger SHALL append no authorization or delivery event and preserve the
  source timeline

### Requirement: The Case projection is derived and replayable from the ledger
The Case projection SHALL be a tenant-scoped read model derived from immutable source
records rather than an audit authority. A projection rebuild SHALL validate revision
predecessors, ordered event indexes, legal initial state transition, legal
workflow-originated state transitions, tenant references, causation references, and
event payload digests before producing the same Case state and timeline visible to the
API.

#### Scenario: A projection is rebuilt after a process restart
- **WHEN** an offline API/ledger process is restarted against an existing valid local
  store
- **THEN** it SHALL rebuild or verify the projection from source records and return the
  same Case/revision/event history; a retried original delivery SHALL still deduplicate
  without an additional write

#### Scenario: Ledger history is internally inconsistent
- **WHEN** a rebuild encounters a broken revision predecessor, event index, tenant
  reference, digest, initial state transition, workflow causation, or workflow state
  transition
- **THEN** the affected store SHALL fail closed as not ready or invalid and SHALL not
  manufacture a repaired history or customer-resolution result

#### Scenario: A workflow journal is rebuilt after an interrupted transition
- **WHEN** a worker restarts after persisting a workflow checkpoint and its associated
  Case event sequence
- **THEN** the rebuilt Case and workflow projections SHALL agree on the latest legal
  state, checkpoint causation, and event index without appending a replacement event

### Requirement: Synthetic ledger snapshots are deterministic and non-destructive
The deterministic Business Simulator/testkit SHALL export a tenant-scoped snapshot of
source records in canonical order with a schema version and SHA-256 content hash.
Restore SHALL validate the hash and source invariants into a fresh local ledger store;
it SHALL not reset or rewrite an existing ledger and SHALL not generate new business
events.

#### Scenario: A valid tenant snapshot is restored into a fresh local store
- **WHEN** a test exports a valid tenant snapshot and restores it into a fresh offline
ledger store
- **THEN** the restored projection, Case/revision/event timelines, and snapshot hash
SHALL match the exported state deterministically

#### Scenario: A snapshot is tampered with or mixes tenants
- **WHEN** a snapshot hash does not match, records contain multiple tenants, or its
revision/event invariants are invalid
- **THEN** restore SHALL reject the snapshot without opening a partially populated
store or emitting a new event

### Requirement: Accepted QQ sandbox intake reuses the atomic Case ledger
For the first accepted server-normalized QQSandboxInboundEvent, the Case ledger SHALL
use the event's effective tenant, safe conversation/customer references, inbound
natural key, source content hash, and correlation metadata to create the same stable
Case, immutable CaseRevision 1, and exactly three ordered initial BusinessEvents
required for accepted IM intake. QQ source fields SHALL not weaken tenant-scoped reads,
append-only records, transaction rollback, projection replay, or deterministic
snapshot behavior.

#### Scenario: A first QQ mention creates the initial ledger
- **WHEN** a valid allowlisted QQ sandbox event passes identity, deduplication,
  sequence, and payload-safety validation
- **THEN** one transaction SHALL persist the receipt, Case, CaseRevision 1, and exactly
  the three required ordered events, and the projection SHALL report `RECEIVED`

#### Scenario: QQ source persistence fails
- **WHEN** an error or uniqueness conflict occurs before the QQ intake transaction
  commits
- **THEN** the ledger SHALL roll back without a partial receipt, Case, revision, event,
  projection, or acknowledgement intent

### Requirement: Intake state has no external side effect or completion authority
Inbound intake writes SHALL remain local payload-safe persistence. Once the initial
intake transaction commits, it SHALL be eligible for one durable, deterministic
workflow activation that records local workflow/checkpoint and simulated effect facts
through the control kernel. For an accepted QQ sandbox source only, the committed
intake MAY also cause creation of one distinct fixed QQ acknowledgement intent under
the dedicated command and capability gates; the intake transaction itself SHALL NOT
initialize a QQ executor or perform the send. Intake itself SHALL NOT initialize a
model, invoke a business/tool provider, request/decide approval, send a final reply,
execute any other real external write, or declare a Case/customer issue complete. The
existing workflow SHALL preserve Replay mode and its fixture-local ticket simulator.

#### Scenario: An accepted synthetic intake is inspected for prohibited behavior
- **WHEN** the accepted synthetic intake fixture and its telemetry/capability report are
  examined
- **THEN** the evidence SHALL show the initial local Case/Revision/Event state plus, if
  scheduled, a deterministic local workflow activation; it SHALL show no model, real
  external-write, approval, delivery, workflow-completion, or customer-resolution
  assertion

#### Scenario: An accepted QQ intake is inspected
- **WHEN** the accepted QQ sandbox intake and its durable facts are examined
- **THEN** the intake transaction SHALL contain only the initial local ledger and MAY
  be followed by one separately gated fixed acknowledgement recovery chain; it SHALL
  show no model, handler approval, final reply, other external write, Case completion,
  or customer-resolution assertion

#### Scenario: Intake is retried after workflow scheduling
- **WHEN** an exact inbound retry occurs after the original Case has a durable workflow
  activation, checkpoint, or QQ acknowledgement intent
- **THEN** the intake boundary SHALL return the original deduplicated result and SHALL
  not start another workflow, append another state event, create another simulated
  ticket intent, or create another QQ acknowledgement intent

### Requirement: Handler workflow transitions SHALL be append-only business events

The ledger SHALL append content-free events for dual binding activation/revocation/expiry, private pull, accept, candidate creation/replacement/rejection, approval request creation/invalidation, group approval decision, notification outcome, final delivery intent/result, and artifact deletion. Existing events, immutable binding records, and immutable Case revisions MUST NOT be rewritten.

#### Scenario: Candidate is replaced privately

- **WHEN** the bound handler submits a valid replacement
- **THEN** the ledger appends prior-request invalidation and new-candidate facts while retaining the earlier history

#### Scenario: Final write is accepted

- **WHEN** QQ accepts the passive group reply
- **THEN** the ledger appends provider-acceptance evidence without declaring customer receipt or resolution

#### Scenario: Operator revokes a stale dependent binding

- **WHEN** exact local confirmation and a matching current Stage 1 scope authorize revocation
- **THEN** the ledger appends one content-free terminal event while the immutable binding record remains unchanged

### Requirement: Ledger facts SHALL not disclose private content or raw QQ identity

Ledger events SHALL contain only stable internal identifiers, salted identity hashes or private locator references, artifact hashes, classifications, workflow versions, safe reason codes, provider outcome classes, and evidence links. They SHALL NOT contain credentials, raw `openid` values, source event bodies, customer issue text, candidate text, previews, or transcripts.

#### Scenario: C2C draft event is appended

- **WHEN** a private draft becomes current
- **THEN** the event records its artifact hash, length, classification, binding, Case revision, and workflow version without the draft body

### Requirement: Ledger ordering SHALL support deterministic replay

Every Stage 2 event SHALL carry a stable event identity, aggregate identity, expected prior workflow version, resulting version, correlation and causation references, and recorded-at metadata sufficient to replay duplicate, stale, replacement, approval, and recovery behavior offline.

#### Scenario: Duplicate provider event is replayed

- **WHEN** the same normalized C2C or group event is applied more than once
- **THEN** replay produces one logical transition and records the duplicate classification without a second side effect

#### Scenario: QQ reconnect resets the session-local sequence

- **WHEN** a new QQ WebSocket connection yields a new provider message whose session-local sequence
  equals or is lower than a sequence observed on an earlier connection
- **THEN** the transport enforces ordering only within the active connection, the ledger accepts the
  new natural key exactly once, and the conversation cursor remains a diagnostic high-water mark
  rather than an authorization or cross-session ordering gate
