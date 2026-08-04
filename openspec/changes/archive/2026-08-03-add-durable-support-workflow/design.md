## Context

Change 1 owns only fixture-backed inbound acceptance: it creates a stable Case,
Revision 1, and three immutable initial events, then leaves the Case in `RECEIVED`.
The current control worker is a health-only skeleton, and the SQLite ledger has no
durable workflow run, checkpoint, SLA deadline, or side-effect recovery record.

This change adds the minimum deterministic control-plane path after intake. Its
observable success boundary is intentionally narrow: a tenant-scoped Case can be
started or recovered, a fixture-local ticket handoff can be reconciled exactly once,
and the Case can reach `TICKET_READY` or a safe non-success state. It is not an
investigation, customer-resolution, approval, delivery, or Agent capability.

The primary stakeholders are contributors who need an offline, repeatable recovery
baseline and later changes that will consume a durable workflow rather than inventing
their own state, retries, or side-effect semantics. The implementation must work with
no network, Docker, model credential, enterprise credential, or customer data.

## Goals / Non-Goals

**Goals:**

- Make deterministic control code the exclusive owner of workflow lifecycle, legal
  Case transitions, synthetic SLA deadlines, retries, recovery, and the local
  side-effect protocol.
- Persist immutable workflow checkpoints and append-only control/effect evidence
  linked to tenant, Case, CaseRevision, correlation, and source-event identities.
- Use a fixture-local ticket simulator to prove `intent -> reconcile -> execute ->
  complete`, stable natural keys, idempotency, expected-version updates, and safe
  reconciliation after worker interruption or a lost response.
- Preserve offline determinism while adding a service-boundary Temporal driver that
  schedules the same deterministic control kernel rather than becoming the business
  audit authority.
- Keep all public surfaces narrow, tenant-scoped, safe-error-only, and incapable of
  arbitrary Case mutation or customer-completion claims.

**Non-Goals:**

- No Agent, model invocation, context/prompt construction, CRM/monitoring/knowledge
  reads, customer/SLA enrichment from external data, or response candidate.
- No approval, outbound delivery, knowledge candidate, real provider, real ticketing
  API, Tencent/WeCom connection, real credential, or external-write executor.
- No `RESPONSE_READY`, `RESOLVED`, `COMPLETED`, or assertion that a customer incident
  has been fixed. `TICKET_READY` means only that the fixture-local handoff is known.
- No replacement of the Change 1 inbound source ledger, no mutation of past source
  rows, and no production migration or rollout.

## Decisions

### 1. Keep business state deterministic and make Temporal a driver, not the ledger

The control kernel will define a pure workflow reducer plus storage-neutral ports for
workflow journal, timer, effect reconciliation, and ticket simulation. The reducer
accepts only durable facts and allowlisted commands; it returns an explicit next
checkpoint, append-only events, and effect work. It never consumes model output.

Offline acceptance will use a SQLite-backed deterministic workflow driver and an
injectable clock. A Temporal-backed control-worker driver will schedule equivalent
workflow/activity work only in explicit `service-boundary` mode. Both drivers use the
same reducer, identifiers, and journal contracts. Temporal history is operational
orchestration evidence, never the sole Case audit source; the local business and
workflow ledgers remain reconstructable without it.

**Why this choice:** offline recovery needs to be testable on the current Docker-free
workstation, while Temporal remains the intended service-boundary runtime. Keeping the
transition reducer outside either driver prevents two different definitions of
recovery behavior.

**Alternatives considered:** using Temporal history as the only durable state would
make the required offline path impossible and weaken append-only auditability. Using
only a bespoke SQLite loop would defer the service-boundary contract and make later
Temporal adoption a rewrite.

### 2. Introduce a constrained control state machine with no resolution transition

The Case projection stays derived from ordered immutable events. The workflow run has
a separate execution status, while the Case state may move only through this allowlist:

| Current Case state | Durable fact or command | Next Case state |
| --- | --- | --- |
| `RECEIVED` | simulated ticket handoff is reconciled complete | `TICKET_READY` |
| `RECEIVED` or `TICKET_READY` | valid pause command | `PAUSED` |
| `PAUSED` | valid resume command | checkpointed pre-pause state |
| non-terminal state without an unknown effect | valid cancel command | `CANCELLED` |
| active or paused state | synthetic SLA deadline expires before handoff is known | `WAITING_FOR_OPERATOR` |
| any state with an unknown or conflicting effect outcome | reconciliation is required | `NEEDS_RECONCILIATION` |
| `NEEDS_RECONCILIATION` | reconciliation proves the intended ticket state | checkpointed safe continuation state |

`PAUSED`, `WAITING_FOR_OPERATOR`, `NEEDS_RECONCILIATION`, and `CANCELLED` stop normal
progress. A cancel command must not bypass an unresolved intent; the workflow first
records/reconciles that intent or remains in `NEEDS_RECONCILIATION`. No caller supplies
a target Case state, event payload, tenant, or revision. A stable workflow identity is
derived from `(tenant_id, case_id, case_revision_id, workflow_definition_version)` and
only one active run is permitted for that identity.

**Why this choice:** it proves the durable control responsibilities needed by later
Agent work without pretending that the system has classified, investigated, or solved
an incident.

**Alternatives considered:** advancing through the full reference-architecture state
machine would require facts and decisions owned by later Agent/tool changes. A generic
state-transition API would violate the ledger's append-only and authorization
boundaries.

### 3. Store workflow facts append-only and derive all mutable views

The existing Case/Revision/inbound ledger remains immutable. The change adds an
append-only workflow journal for run activation, commands, checkpoints, SLA events,
effect phases, and recovery decisions. Workflow-originated Case-state events are
appended through one control-kernel-only ledger method; no HTTP route or simulator
payload can append an arbitrary event. Case and workflow projections are rebuilt from
their respective source records on startup.

Each checkpoint is immutable and contains only safe metadata: tenant, Case, revision,
workflow identity/version, monotonic checkpoint sequence, current and resume state,
deadline, pending/completed intent references, causal event reference, correlation,
and a canonical content hash. The checkpoint never contains raw message content,
credential material, unbounded tool output, or a model response.

Workflow activation is recorded transactionally after the initial Change 1 intake
commit. A recovery scan finds source Cases with an activation but no live/terminal
workflow record, then resumes their stable workflow identity. An exact inbound retry
does not create another activation, workflow run, state event, or ticket intent.

**Why this choice:** a distinct execution journal permits restart/recovery evidence
without mutating the Change 1 source history; derived projections avoid competing
authorities for state.

**Alternatives considered:** storing workflow progress only in process memory loses
interruption semantics. Updating a Case row in place makes replay and audit diverge.

### 4. Use a synthetic SLA policy and monotonic fixture clock

Each workflow activation snapshots a fixture-defined `SyntheticSlaPolicy` and derives
one deadline from the accepted Case timestamp. The injected clock, not wall-clock
ordering, drives deadline tests. Pausing a workflow does not extend or erase the
recorded deadline; expiration appends an SLA event and either leaves a known
`TICKET_READY` handoff intact or moves unfinished work to `WAITING_FOR_OPERATOR`.

The SLA record measures control progress only. It does not enrich customer data,
message a customer, escalate externally, or imply that an incident is resolved.

**Why this choice:** it makes timing and restart behavior reproducible while avoiding
an implicit policy decision about real customer contracts.

**Alternatives considered:** a real-time timer would make repeated-run evidence flaky;
pausing SLA by default would let a control command silently bypass the intended gate.

### 5. Treat the local ticket simulator as an effect boundary, not an external write

The only executable effect in this change is a deterministic, fixture-local ticket
simulator. It exposes no network client and is never registered as an external-write
executor. It supports `find-or-create` by natural key
`tenant_id:case_id:case_revision_id` and one expected-version handoff update carrying
only a content hash/reference.

Before every simulator call, the workflow persists an immutable `SideEffectIntent`
with the natural key, intended-state hash, stable idempotency key, operation,
Case/revision, causal checkpoint, and safe evidence references. It then reconciles by
natural key. It executes only if absent, observes the result, validates the returned
identity/version, and persists a completion. Duplicate calls return the existing
ticket; a stale expected version, unknown result, or inconsistent observation becomes
`NEEDS_RECONCILIATION` and never triggers a blind retry.

The phase transitions are:

```text
intent recorded -> reconcile observed/absent -> execute if absent
-> observe -> validate -> completion recorded
```

**Why this choice:** it tests the exact protocol later external adapters must obey
without making a network call or weakening the current fail-closed provider boundary.

**Alternatives considered:** a no-op effect cannot prove response-loss recovery.
Treating a local simulator call as automatically complete would hide the failure window
that the change is intended to validate.

### 6. Make recovery and fault injection first-class acceptance behavior

The runner will expose deterministic fault points after activation, checkpoint save,
intent persistence, reconciliation, simulator execution, observation, and completion
persistence. A fault stops the worker without synthesizing a result. A fresh worker
uses the same local store and performs recovery from checkpoints and natural keys.

Required recovery invariants are: exactly one active workflow identity per Case
revision; no duplicated simulated ticket or versioned update; no lost completed effect;
unknown result becomes reconciliation rather than retry; all rebuilt projections and
safe reports are deterministic. Timeout, restart, duplicate inbound, out-of-order
inbound, cross-tenant read, stale command, and unsupported provider paths remain
negative tests.

**Why this choice:** recovery needs proof at the durable boundary, not merely a retry
counter in memory.

**Alternatives considered:** injecting faults only around HTTP handlers would miss the
critical windows between intent, remote-like execution, observation, and completion.

### 7. Keep control/observation APIs narrow and tenant-derived

The Platform API may expose tenant-scoped workflow read/status and allowlisted
synthetic workflow commands, using a command identifier and expected workflow version.
The effective tenant comes from the existing synthetic actor mapping; request bodies
cannot choose tenant, Case state, event type, deadline, ticket identity, or raw
metadata. Commands are idempotent and are allowed only from the local simulator/test
surface in offline mode. A foreign Case/workflow remains indistinguishable from an
absent one.

The capability report gains a narrow durable-workflow flag only after acceptance
passes. `business_workflow_implemented` and `external_writes_enabled` remain `false`.
No approval, capability grant, model budget, or policy engine is added in this change;
the deterministic reducer and allowlisted synthetic boundary are the only authority.

**Why this choice:** later policy/approval changes can harden a small, explicit control
surface instead of replacing generic mutation endpoints.

**Alternatives considered:** postponing all command/observation boundaries would leave
recovery untestable end-to-end. Adding a broad operator CRUD API would expand authority
ahead of the Policy Engine change.

### 8. Evolve contracts and snapshots additively

New `v1` schemas cover `WorkflowCheckpoint`, `WorkflowCommand`,
`SyntheticSlaPolicy`, `SideEffectIntent`, `SideEffectObservation`, and
`SideEffectCompletion`. Existing Case, Revision, Projection, and BusinessEvent schemas
receive only compatible optional workflow references where required. Every new schema
and fixture is validated by both language packages; retained Change 0/1 fixtures stay
valid.

The existing Change 1 Case-ledger snapshot format remains readable as a ledger-only
snapshot. A new content-addressed workflow snapshot links the unchanged Case-ledger
snapshot hash to canonical workflow-journal records. Restoring a legacy ledger snapshot
creates no workflow work until a deterministic activation/recovery path records it.

**Why this choice:** it protects existing fixtures and avoids silently redefining a
published snapshot or `v1` consumer contract.

**Alternatives considered:** changing the existing snapshot shape in place would make
old fixture restore ambiguous. A new major contract version is not warranted because
the retained `v1` corpus remains compatible.

## Risks / Trade-offs

- [SQLite does not reproduce all Temporal scheduling/concurrency behavior] → The
  reducer, journal invariants, identifiers, and recovery tests are driver-neutral;
  Temporal service-boundary testing is explicit and reports an unavailable Docker
  environment as a skip, never as a pass.
- [A fixture-local ticket could be mistaken for a real enterprise action] → The
  contract, capability report, logs, tests, and documentation label it synthetic;
  no network client, credential, or external executor is registered.
- [The new state `TICKET_READY` could be mistaken for resolution] → It is defined as a
  local handoff only; all resolution/completion flags remain false and tests assert the
  absence of response, approval, delivery, and customer-success records.
- [Crash windows reveal a partially recorded effect] → Every phase has a durable
  record, recovery begins with reconciliation, and unknown observations fail closed to
  `NEEDS_RECONCILIATION`.
- [An operator command could bypass safety] → Commands are allowlisted, tenant-derived,
  version-checked, idempotent, and cannot directly set state; unresolved intents block
  cancellation and resume.
- [SLA deadlines introduce nondeterminism] → Fixture policy and injected monotonic time
  make deadlines reproducible; reports omit host timestamps and process identifiers.
- [Additive schemas or tables drift across components] → Contract parity, schema
  fingerprints, source-table immutability, rebuild tests, and additive SQLite migration
  checks are mandatory acceptance evidence.

## Migration Plan

1. Add contract schemas and retained/new cross-language fixtures before altering
   storage or routes. The compatibility command must pass first.
2. Add append-only workflow-journal, checkpoint, intent, observation, completion, and
   simulated-ticket tables through an additive SQLite migration. Existing Case 1
   source rows and the Change 1 snapshot format remain untouched.
3. Implement the driver-neutral reducer, deterministic offline driver, timer, and
   recovery scanner, then wire the Temporal control-worker driver behind explicit
   service-boundary configuration.
4. Add the narrow tenant-derived observation/command boundary and the simulator/testkit
   fixtures. Keep broad Case mutation, real adapters, approval, and outbound delivery
   absent.
5. Run contract, lint, unit, integration, recovery, offline acceptance, repeated-run,
   and optional service-boundary checks. Emit a redacted machine-readable Change 2
   report and archive only after strict OpenSpec validation passes.

There is no production deployment or data migration. Rollback stops local workers and
uses the existing ignored runtime store only after preserving any required local test
evidence. Code from before this change must fail closed against an unsupported
workflow-journal schema rather than ignore or mutate it.

## Open Questions

No blocking product or safety decisions remain for Apply. Implementation may choose
internal module names, SQLite table names, and Temporal task-queue names, provided it
preserves the state machine, identifiers, contracts, fault points, and offline/service-
boundary semantics above.
