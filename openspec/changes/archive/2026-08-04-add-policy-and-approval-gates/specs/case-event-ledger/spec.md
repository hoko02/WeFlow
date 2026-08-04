## MODIFIED Requirements

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
