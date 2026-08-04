# idempotent-side-effect-recovery Specification

## Purpose
Define safe, reconstructable intent and reconciliation semantics for fixture-local
side effects without authorizing real external writes.

## Requirements

### Requirement: Each simulated side effect records an immutable intent before execution
Before a fixture-local ticket operation is attempted, the control kernel SHALL persist
a tenant-scoped immutable `SideEffectIntent` containing the Case, CaseRevision,
workflow/checkpoint reference, operation, natural key, intended-state hash, stable
idempotency key, safe evidence references, and correlation metadata. An intent identity
and idempotency key SHALL be deterministic for the same logical effect. No executor
shall run before the intent is durable.

#### Scenario: A worker stops immediately after intent persistence
- **WHEN** fault injection stops the worker after a ticket intent commits but before
  reconciliation or execution
- **THEN** a recovered worker SHALL find the same intent by stable identity, reconcile
  its natural key before executing, and SHALL not create a second intent or ticket

#### Scenario: Concurrent runners encounter the same logical effect
- **WHEN** two worker attempts for the same tenant, Case, revision, and operation race
  to process the same fixture-local ticket effect
- **THEN** durable uniqueness/claim rules SHALL yield one logical intent and one
  observable ticket outcome, while the non-winning attempt records or returns the
  durable result without a duplicate execution

### Requirement: The fixture-local ticket simulator supports natural-key reconciliation and expected-version updates
The only Change 2 effect executor SHALL be a deterministic local ticket simulator with
no network client or enterprise credential. It SHALL find or create one synthetic ticket
by natural key `tenant_id:case_id:case_revision_id`, then support a workflow-handoff
update only when the observed ticket version equals the intent's expected version. The
handoff update SHALL carry only a safe content hash/reference and SHALL return a new
observed version.

#### Scenario: Reconciliation finds a ticket created by an interrupted worker
- **WHEN** recovery reconciles a natural key after a prior worker created the synthetic
  ticket but lost its response
- **THEN** it SHALL observe the existing ticket identity/version, avoid another create,
  and persist a completion only after validating that observation against the intent

#### Scenario: An expected-version handoff update is repeated
- **WHEN** the same valid handoff update is retried with its original idempotency key
  after the ticket version has advanced from the first completion
- **THEN** the simulator and recovery journal SHALL return the original completed
  result rather than append a second update or treat the now-stale version as a new
  operation

### Requirement: Reconciliation is required for unknown, timeout, and conflict outcomes
The workflow SHALL reconcile by natural key before every new execution and after any
interruption, timeout, lost response, or ambiguous observation. It SHALL execute only
when reconciliation proves the intended effect absent. A timeout, conflicting ticket
identity, stale expected version not attributable to the same idempotency key, or
unreadable observation SHALL append a safe recovery fact and transition the workflow to
`NEEDS_RECONCILIATION`. It SHALL NOT blindly retry, mark the effect complete, or claim
a Case/customer outcome.

#### Scenario: Execution succeeds but its response is lost
- **WHEN** fault injection drops the simulator response after the ticket operation has
  taken effect but before the workflow persists its observation/completion
- **THEN** recovery SHALL reconcile the natural key, record the existing observed
  outcome exactly once, and SHALL not execute another ticket operation

#### Scenario: Reconciliation times out without an observable result
- **WHEN** the local simulator returns a deterministic timeout or unavailable outcome
  while the journal cannot prove whether the intended effect exists
- **THEN** the workflow SHALL record a payload-safe recovery reason, enter
  `NEEDS_RECONCILIATION`, and preserve the intent without executing again

#### Scenario: A conflicting version is observed
- **WHEN** a ticket handoff update observes a version different from the intent's
  expected version and cannot match it to the same completed idempotency key
- **THEN** the workflow SHALL reject the result as a conflict, append no completion,
  and require reconciliation before any later action

### Requirement: Completion evidence is append-only, safe, and cannot authorize a real write
After a reconciled local effect is validated, the control kernel SHALL append a
`SideEffectObservation` and `SideEffectCompletion` linked to the original intent,
workflow checkpoint, tenant, Case, revision, natural key, observed version, and safe
content hashes. These records SHALL be immutable and reconstructable after restart.
They SHALL not contain raw customer content, credentials, unrestricted tool output, or
an authorization to call a real provider.

#### Scenario: A completed effect is replayed after restart
- **WHEN** a fresh worker reconstructs a workflow whose ticket intent has a valid
  completion record
- **THEN** it SHALL treat that effect as complete, return the stored safe outcome, and
  make no simulator or external-provider call

#### Scenario: A real external effect is requested through the workflow
- **WHEN** a fixture or caller supplies a non-simulator provider, credential-like
  configuration, outbound operation, approval operation, or real delivery target
- **THEN** the effect boundary SHALL fail closed before intent execution, register no
  external executor, and produce no completion or customer-success record

### Requirement: Fixture-local outbound delivery has a distinct immutable recovery chain
Before a named fixture-local IM delivery is attempted, the control kernel SHALL persist
one tenant-scoped immutable OutboundDeliveryIntent containing Case, CaseRevision,
workflow/checkpoint, channel/conversation resource, candidate hash, authorization
binding hash, operation, natural key, stable idempotency key, safe evidence references,
and correlation metadata. It SHALL reconcile, execute, observe, and complete only that
same intent through distinct append-only delivery facts. Ticket `SideEffect*` records
and their natural keys SHALL remain unchanged.

#### Scenario: A worker stops immediately after delivery intent persistence
- **WHEN** fault injection stops a worker after an authorized delivery intent commits
  but before reconciliation or execution
- **THEN** recovery SHALL find the same intent by stable identity, reconcile before
  executing, and SHALL not create a second intent or delivery

#### Scenario: Delivery confirmation is lost after execution
- **WHEN** the fixture-local adapter has executed one natural-key operation but its
  response is lost
- **THEN** recovery SHALL observe/reconcile the existing local outcome and SHALL not
  execute a second delivery

#### Scenario: Delivery is unauthorized during recovery
- **WHEN** a recovered intent no longer has a current matching policy, Capability
  Grant, approval, candidate, evidence, or authorization binding
- **THEN** recovery SHALL append no execution or completion and SHALL preserve the
  existing immutable facts for safe handling
