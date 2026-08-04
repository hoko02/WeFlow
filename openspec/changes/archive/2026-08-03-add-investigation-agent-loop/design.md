## Context

Change 2 has archived a deterministic, tenant-scoped workflow with append-only state,
checkpoints, synthetic SLA, and a fixture-local ticket handoff. Its `TICKET_READY`
state is a bounded handoff fact, not an investigation or customer outcome. The Agent
Runtime is currently replay-data only. This change introduces the smallest offline,
single-Agent execution slice that can turn an immutable workflow context and three
fixture-local read tools into an evidence-bound response candidate.

## Goals / Non-Goals

**Goals:**

- Keep workflow code as the sole owner of lifecycle state, retries, checkpoints, and
  completion; the Agent returns only schema-validated proposals.
- Produce an immutable Context Manifest from tenant/Case/revision, workflow checkpoint,
  synthetic environment snapshot, budget, and minimum evidence references.
- Run one deterministic Replay Agent through allowlisted read-only CRM, monitoring, and
  knowledge tools; persist safe tool/evidence/step facts with content hashes.
- Apply deterministic action, duplicate/no-progress, tenant, budget, evidence, and
  candidate verification gates before the control kernel may transition to
  `RESPONSE_READY`.
- Preserve offline replay, recovery, redaction, and no external effect guarantees.

**Non-Goals:**

- No live model, provider credential, network connector, real CRM/monitoring/knowledge
  service, approval, outbound delivery, knowledge publication, or multi-Agent runtime.
- No Agent authority to mutate Case state, call ticket write operations, approve, send a
  response, or claim customer resolution.
- No replacement of the Change 2 workflow journal, ticket reconciliation, or synthetic
  SLA semantics.

## Decisions

### 1. Replay Agent emits a closed action algebra

The Replay Adapter consumes only named fixture transcripts and emits one action at a
step: `read_crm`, `read_monitoring`, `read_knowledge`, `needs_information`,
`needs_operator`, or `response_candidate`. JSON Schema validation rejects unknown
fields, raw content, unbounded arguments, or an action inconsistent with the current
manifest. This proves the Agent/tool/control separation without nondeterministic model
or network behavior.

**Alternative:** enabling a live OpenAI-compatible adapter now would weaken the required
no-credential offline baseline and make replay evidence non-reproducible.

### 2. Context and tool results are immutable, hash-addressed evidence

The Context Compiler creates one content-addressed manifest per workflow checkpoint.
The Tool Gateway derives tenant and resource scope from that manifest, permits only
three named fixture reads, and turns each result into redacted Artifact/Evidence
metadata before returning a minimal result to the Agent. Raw fixture payloads never
enter prompts, logs, API responses, snapshots, or reports.

**Alternative:** passing full simulator payloads directly to the Agent would violate the
project evidence and data-minimization boundary.

### 3. The verifier, not the Agent, advances workflow state

A response candidate must bind tenant, Case/revision, workflow checkpoint, context
manifest, ordered evidence hashes, risk/next-step metadata, and a canonical candidate
hash. The deterministic verifier checks required evidence coverage, hash linkage,
redaction class, tenant consistency, action budget, and that the candidate does not
claim approval, delivery, resolution, or completion. Only a passed verifier outcome
allows the control kernel to append the next allowlisted state transition to
`RESPONSE_READY`; all other outcomes remain `TICKET_READY`, enter a safe waiting state,
or fail closed.

### 4. Recovery replays durable facts, never Agent authority

Each agent step, tool request/result, verifier outcome, and workflow transition is
append-only and causally tied to a checkpoint. Restart resumes from the latest durable
step/manifest and deduplicates by stable step/tool natural keys. Faults after action
selection, tool result persistence, candidate persistence, and verification must not
repeat a tool read beyond its recorded result or append another state event.

## Risks / Trade-offs

- [Replay can mask live model variability] → This change claims deterministic replay
  only; a later provider change requires separate credentials, cost, and variance gates.
- [Extending `TICKET_READY` changes Change 2's prior horizon] → New transitions are
  versioned workflow facts and retain all historic replay semantics.
- [Tool evidence becomes a prompt-exfiltration path] → Gateway allowlists schemas,
  redacts before persistence, and tests hostile/oversized tool results.
- [Candidate text may resemble a customer reply] → It is an unapproved internal
  candidate; no delivery executor or completion transition exists.

## Migration Plan

1. Add additive v1 schemas and retain every Change 0-2 fixture.
2. Add journal tables/projections and replay fixtures behind the existing offline mode.
3. Extend the reducer with only verifier-authorized candidate transitions and recovery
   scan support.
4. Run contract, unit, integration, security, recovery, and repeated offline acceptance
   checks. Rollback disables the new workflow definition while leaving append-only facts
   readable; no external side effect needs compensation.

## Open Questions

- The initial proposal fixes replay-only scope; a live provider remains a later change.
- The first fixture corpus will define required CRM, monitoring, and knowledge evidence
  for the API-503 candidate; it must not encode raw customer content.