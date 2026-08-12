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

### Requirement: QQ sandbox acknowledgement has a distinct immutable recovery chain
Before the bounded QQ executor is contacted, the control kernel SHALL persist one
tenant-scoped immutable QQAcknowledgementIntent containing the Case, CaseRevision,
source QQ message reference, configured group resource, fixed template hash, passive
reply deadline, operation, natural key, stable idempotency key, original provider
`msg_id`, deterministic positive reply `msg_seq`, safe evidence references, and
correlation metadata. It SHALL reconcile, execute, observe, and complete only that
same intent through distinct append-only QQ acknowledgement facts. Ticket SideEffect
and approved final OutboundDelivery records and their natural keys SHALL remain
unchanged.

#### Scenario: A worker stops immediately after acknowledgement intent persistence
- **WHEN** fault injection stops the worker after the QQ intent commits but before
  reconciliation or execution
- **THEN** recovery SHALL find the same intent, deadline, and provider deduplication
  tuple and SHALL not create a second intent or reply identity

#### Scenario: Concurrent runners encounter the same acknowledgement
- **WHEN** two workers race on the same tenant, Case revision, fixed template, and QQ
  source message
- **THEN** durable uniqueness/claim rules SHALL yield one logical intent and at most one
  provider-deduplicated acknowledgement outcome

### Requirement: QQ acknowledgement reconciliation is mandatory and truthful
The QQ recovery boundary SHALL reconcile local durable facts before every execution and
after interruption, timeout, disconnect, restart, lost response, duplicate response,
or conflict. It SHALL execute/retry only with the original `msg_id` and deterministic
`msg_seq`, only while the deadline and exact command capability remain valid. A
validated accepted or duplicate/present provider observation MAY append one immutable
completion. Unknown, unreadable, conflicting, unauthorized, or expired outcomes SHALL
append safe recovery evidence and remain incomplete; they MUST NOT generate a new
reply sequence, arbitrary resend, customer-receipt claim, final-delivery completion,
or Case/customer completion.

#### Scenario: Execution succeeds but its response is lost
- **WHEN** fault injection records that the fake provider accepted the original
  deduplication tuple but drops the response before observation/completion persistence
- **THEN** recovery SHALL reuse the same tuple, reconcile a present/duplicate result,
  and append at most one completion without a second logical send

#### Scenario: Reconciliation times out without proof
- **WHEN** neither local evidence nor the bounded provider response proves accepted,
  duplicate/present, absent-and-retryable, or conflicting state
- **THEN** recovery SHALL record an unknown safe reason, enter
  `NEEDS_RECONCILIATION`, and SHALL not blindly send or mark the acknowledgement
  complete

#### Scenario: Recovery observes an expired or unauthorized intent
- **WHEN** the passive reply deadline has elapsed or the exact QQ command capability,
  tenant/group mapping, template hash, or source binding no longer matches
- **THEN** recovery SHALL make no provider call, append no completion, and preserve the
  immutable intent for safe inspection

### Requirement: Active C2C notification SHALL use at-most-once transport execution

The system SHALL create a durable notification intent with a stable Case/binding natural key and SHALL make no more than one active provider transport attempt. Local reconciliation SHALL precede the attempt. A provider-accepted result may be recorded as accepted; a timeout, disconnect, or unknown outcome SHALL remain ambiguous and MUST NOT be retried or reported as delivered.

#### Scenario: Process restarts before transport attempt

- **WHEN** a durable intent exists with no recorded attempt
- **THEN** recovery may make the one allowed transport attempt after local reconciliation

#### Scenario: Process restarts after ambiguous transport

- **WHEN** an attempt was started but no authoritative provider outcome is known
- **THEN** recovery records `NOTIFICATION_UNKNOWN` and makes no second active C2C attempt

### Requirement: Passive C2C replies SHALL derive idempotency from the source event

Each private pull result, task response, draft preview, or rejection response SHALL use the current C2C source `msg_id`, a stable response-kind-specific `msg_seq`, and an idempotency key bound to the Case, binding, and workflow version. Execution SHALL respect the provider passive-reply window and count limit.

#### Scenario: Duplicate C2C event is delivered

- **WHEN** QQ delivers the same private command event more than once
- **THEN** the system produces one logical transition and at most one provider-visible reply for each response kind

#### Scenario: Passive window expires

- **WHEN** a private response cannot execute within the provider window
- **THEN** it expires safely and requires a new private command rather than an active-send fallback

### Requirement: Final group delivery SHALL reconcile against the approval source and decision

The final reply intent SHALL bind the exact approval decision, candidate artifact hash, group approval source `msg_id`, stable `msg_seq`, group, Case, and workflow version. Recovery SHALL check local intent/result state before any repeat and SHALL never switch to an active group send.

#### Scenario: Worker crashes after provider acceptance is recorded

- **WHEN** the final intent is replayed after restart
- **THEN** recovery observes the completed result and performs no transport call

#### Scenario: Final outcome is unknown

- **WHEN** transport returns an ambiguous outcome
- **THEN** the workflow records the uncertainty, attempts only safe reconciliation within the passive path, and does not claim delivery or completion

### Requirement: Recovery evidence SHALL distinguish provider acceptance from business completion

Intent, reconcile, execute, and complete records SHALL retain content-free evidence for each external write path. Provider acceptance MUST NOT set customer receipt, issue resolution, or Case completion.

#### Scenario: Acceptance report is built after final provider acceptance

- **WHEN** all live provider calls were accepted
- **THEN** the report may set the transport acceptance facts while receipt, resolution, and Case completion remain false
