## ADDED Requirements

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
The ledger SHALL treat CaseRevision and BusinessEvent records as immutable source data.
It SHALL reject update/delete attempts on those records, enforce unique tenant-scoped
record identities and per-Case event indexes, and expose no public endpoint for an
arbitrary event append or caller-provided Case state.

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

### Requirement: The Case projection is derived and replayable from the ledger
The Case projection SHALL be a tenant-scoped read model derived from immutable source
records rather than an audit authority. A projection rebuild SHALL validate revision
predecessors, ordered event indexes, legal initial state transition, tenant references,
and event payload digests before producing the same Case state and timeline visible to
the API.

#### Scenario: A projection is rebuilt after a process restart
- **WHEN** an offline API/ledger process is restarted against an existing valid local
store
- **THEN** it SHALL rebuild or verify the projection from source records and return the
same Case/revision/event history; a retried original delivery SHALL still deduplicate
without an additional write

#### Scenario: Ledger history is internally inconsistent
- **WHEN** a rebuild encounters a broken revision predecessor, event index, tenant
reference, digest, or initial state transition
- **THEN** the affected store SHALL fail closed as not ready or invalid and SHALL not
manufacture a repaired history or customer-resolution result

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

### Requirement: Intake state has no external side effect or completion authority
This change's ledger writes SHALL be local synthetic persistence only. Intake SHALL NOT
start a workflow, initialize a model, create an external-write intent, invoke a
provider, request/decide approval, send a reply, or declare a Case/customer issue
complete.

#### Scenario: An accepted intake is inspected for prohibited behavior
- **WHEN** the accepted intake fixture and its telemetry/capability report are examined
- **THEN** the evidence SHALL show only local Case/Revision/Event state with replay
mode preserved and no external-write, approval, model, workflow-completion, or
customer-resolution assertion

