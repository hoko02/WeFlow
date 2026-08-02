## Why

Change 1 proves that a synthetic enterprise-IM delivery can become an immutable,
tenant-scoped `RECEIVED` Case, but it deliberately stops there. There is no durable
owner for post-intake work, no restart-safe progress record, no SLA timer, and no
way to prove that a future side effect is reconciled rather than duplicated after a
worker interruption or lost response.

Change 2 establishes the smallest deterministic control-plane vertical that can own
that work safely. It must be independently verifiable offline before an Agent,
approval, outbound delivery, or real enterprise integration is allowed to depend on
it.

## What Changes

- Add a deterministic, tenant-scoped durable support-workflow runtime that starts or
  resumes from an accepted Case revision and owns only allowlisted lifecycle
  transitions, pause/resume/cancel commands, checkpoint persistence, and synthetic
  SLA timing.
- Define an append-only workflow timeline and rebuildable workflow projection that
  remains separate from the immutable inbound source ledger while preserving the
  Case/revision/event lineage already established by Change 1.
- Add a fixture-local, deterministic ticket-effect simulator and a generic
  `intent -> reconcile -> execute -> complete` journal. It will prove natural-key
  reconciliation, stable idempotency, expected-version handling, and
  `NEEDS_RECONCILIATION` behavior without registering an external-write executor or
  contacting a provider.
- Add injected interruption, timeout, and response-loss fault points around workflow
  checkpointing and each side-effect phase. Recovery will restart from durable state
  and must neither duplicate the simulated ticket nor manufacture a successful
  customer outcome.
- Extend compatible `v1` contracts and fixtures for workflow checkpoints,
  deterministic SLA policy/deadline records, workflow commands, side-effect intent
  and reconciliation evidence, and safe recovery outcomes. Retained Change 0/1
  fixtures remain valid in Python and TypeScript.
- Expose only narrow, loopback/testkit workflow observation and control surfaces;
  preserve actor-derived tenant isolation, append-only source history, replay-only
  provider selection, redacted reports, and truthful capability reporting.
- Add offline acceptance, recovery, security, and repeated-run evidence plus updated
  developer documentation. The final report will distinguish this implemented
  control-plane slice from the still-unimplemented end-to-end support workflow.

## Capabilities

### New Capabilities

- `durable-support-workflow`: Deterministic, tenant-scoped workflow lifecycle,
  checkpoints, synthetic SLA deadlines, controlled pause/resume/cancel behavior, and
  restart-safe recovery from an accepted Case revision.
- `idempotent-side-effect-recovery`: Fixture-local side-effect intents, natural-key
  reconciliation, idempotent simulated ticket execution, expected-version handling,
  and fail-closed recovery for unknown outcomes.

### Modified Capabilities

- `case-event-ledger`: Permit an accepted Case to be safely handed to the durable
  workflow while retaining immutable source records, derived projections, and the
  prohibition on arbitrary client state mutation or customer-completion claims.
- `versioned-domain-contracts`: Add compatible workflow, checkpoint, SLA, intent,
  reconciliation, and recovery boundary objects plus their cross-language fixture
  corpus without breaking retained `v1` consumers.
- `local-platform-dependencies`: Require deterministic offline workflow-fault and
  recovery profiles, with redacted evidence and no fallback to a model, network, or
  real provider.

## Impact

- Affected code boundaries: `apps/control-worker`, `apps/platform-api`,
  `apps/business-simulator`, shared Python/TypeScript contracts,
  `weflow-control-kernel`, testkit, fixtures, recovery/e2e/security tests, and
  `scripts/dev.py`.
- Affected data boundaries: the local SQLite runtime gains append-only workflow and
  side-effect-journal records linked to Case and revision identities. All tracked
  fixtures and reports remain synthetic, content-addressed, and free of raw customer
  content, credentials, or unrestricted tool output.
- Affected interfaces: loopback-only observation/control APIs or in-process testkit
  surfaces for workflow status, safe commands, and recovery evidence; there is no
  generic Case mutation API and no externally reachable ticket, approval, or delivery
  endpoint.
- Verification: retained cross-language contract compatibility, deterministic offline
  acceptance, worker interruption and lost-response fault tests, tenant-isolation and
  no-external-write negative tests, repeated-run baselines, and a machine-readable
  Change 2 acceptance report.

## Non-Goals

- Do not add an Agent, model invocation, live/replay provider adapter expansion,
  prompt/context compiler, CRM/monitoring/knowledge investigation, or response
  candidate generation.
- Do not add approval, outbound IM delivery, knowledge publication, customer lookup,
  real Tencent/WeCom or enterprise connectors, production credentials, or any real
  external write.
- Do not declare a Case/customer incident resolved, complete the full support
  workflow, enable multi-agent coordination, or weaken tenant, evidence, or
  append-only invariants.
