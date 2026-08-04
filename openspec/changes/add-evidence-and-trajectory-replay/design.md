## Context

Changes 1–4 already persist tenant-scoped, append-only source facts for synthetic
intake, durable workflow checkpoints, Replay Agent investigation, evidence hashes,
verifier outcomes, default-deny policy, hash-bound approval, and one fixture-local
delivery record. These facts are individually inspectable, but they are not yet
assembled into a canonical trajectory that can explain why one run reached local
delivery recording, safely denied authorization, or recovered from an interruption.

The only supported input remains the checked-in synthetic API-503 fixture. The
verification workstation has no Docker, and core acceptance must continue to require
no network, model/enterprise credentials, live provider, or real external adapter.
The design therefore treats evidence reporting and replay as deterministic evidence
operations over existing durable facts—not as a new workflow driver or execution path.

## Goals / Non-Goals

**Goals:**

- Create an append-only, tenant-scoped, content-addressed evidence trajectory for the
  named API-503 path from accepted source facts through local delivery recording,
  authorization denial, or safe recovery.
- Create a redacted Evidence Report and Trajectory Replay Result with stable schema
  identities, canonical ordering, root hashes, explicit safe outcome/failure classes,
  and no raw business content.
- Make report persistence idempotent and replay read-only: replay validates a recorded
  trajectory against source facts without calling an Agent, tool, policy evaluator,
  approval recorder, delivery adapter, or workflow command.
- Verify two equal offline baselines and declared denial/recovery/tamper boundaries by
  one machine-readable Change 5 acceptance command.

**Non-Goals:**

- No live OpenTelemetry exporter, collector dependency, trace backend, network
  transport, provider, credential, real approval, real delivery, customer receipt,
  resolution/completion claim, knowledge publication, or multi-Agent runtime.
- No new Case state, workflow transition, authorization decision, budget, external
  effect, or mutation of a retained Case/workflow/evidence history.
- No general evaluation suite, LLM judge, 12-fixture expansion, live rerun semantics,
  or Operator Console redesign; later changes may consume these reports.

## Decisions

### 1. A trajectory is a canonical manifest over durable source facts

The control-kernel evidence reader SHALL construct one `EvidenceTrajectory` from a
single tenant, Case, revision, and workflow identity. Its ordered nodes reference only
stable source IDs, typed causal predecessors, content hashes, safe classifications, and
canonical sequence values. The manifest root hash covers the complete ordered node list
and report profile version.

This is preferred to storing a mutable trace tree or relying on a live OTel collector:
it is deterministic offline, independently verifiable, and keeps audit authority in the
existing append-only ledger/journal. A trace backend can later export from the same
manifest; it must not become the source of truth.

### 2. Artifact persistence is additive, idempotent, and redacted before hashing

`Artifact`, `EvidenceTrajectory`, `EvidenceReport`, and `TrajectoryReplayResult` use
compatible v1 contracts. Every persisted artifact is tenant-scoped and content-addressed
by canonical safe payload; its allowed metadata is schema-forbidden from carrying raw
customer text, prompt/context bodies, tool payloads, credentials, delivery content, or
caller-supplied authority. The report identity is derived from trajectory root, report
profile, and fixture/run identity, so an exact retry returns the existing artifact.

This is preferred to embedding raw source snapshots in reports or logs. Hashes and
redacted classifications retain audit/replay value without creating a second sensitive
storage channel.

### 3. Replay means verification, never re-execution

`trajectory-replay` loads one persisted manifest and re-resolves its declared source
facts in canonical order. It validates tenant, identity, causal links, hashes, and
outcome classification, then emits a `TrajectoryReplayResult` whose replayed root must
equal the recorded root. It performs no workflow command, effect reconciliation,
provider/model/tool request, policy evaluation, approval decision, or delivery call.

This deliberately excludes live rerun semantics. Re-executing a path would couple
observability to authority and can create duplicate work; live rerun needs a later,
separately gated change.

### 4. Reports classify operational evidence without customer-success language

The report profile permits only outcome classes such as `fixture_delivery_recorded`,
`authorization_denied`, `recovered_after_interruption`, `needs_reconciliation`, and
`lineage_invalid`. A `fixture_delivery_recorded` result is explicitly local-adapter
metadata; it never asserts message receipt, incident resolution, Case completion, or
customer success. Missing, foreign, tampered, duplicated, out-of-order, or unlinked
facts yield a redacted safe failure and no inferred gap-filling.

### 5. Observation is tenant-derived and replay remains local CLI/testkit work

A read-only tenant-derived API/inspection surface may return an already persisted
redacted report. It accepts no replay command or caller-selected Case, tenant,
trajectory node, raw field, report profile, or authority. The acceptance runner and
Business Simulator invoke replay internally against fixture-local SQLite only.

This keeps expensive/report-generating operations out of public routes and preserves
foreign-versus-absent non-disclosure.

## Risks / Trade-offs

- [Incomplete historical facts cannot form a full trajectory] → Fail closed with
  `lineage_invalid`; do not synthesize a missing node. The Change 5 acceptance scope is
  the named fixture generated under the current contracts.
- [Canonicalization drift between Python and TypeScript] → Share versioned JSON Schema,
  canonical SHA-256 rules, valid/invalid fixtures, and cross-language fingerprint
  checks before accepting a report.
- [Report fields reintroduce sensitive content] → Use `additionalProperties: false`,
  allowlisted safe field types, negative raw/secret fixture corpus, and secret-hygiene
  tests over reports and snapshots.
- [Artifact persistence is mistaken for workflow progress] → Keep report records in a
  separate additive evidence journal/table, omit them from the workflow reducer, and
  test that generation/replay leave Case state, checkpoint version, approval, and
  delivery counts unchanged.
- [A replay result is mistaken for live rerun] → Use explicit `verification_replay`
  mode and report flags `network_required=false`, `model_invocation=false`, and
  `external_write=false`; reject any live configuration.

## Migration Plan

1. Add compatible contracts and additive SQLite evidence-artifact/trajectory tables
   with append-only triggers and lookup indexes; existing Case/workflow histories and
   contract fixtures remain valid.
2. Add the deterministic source resolver, redacted report builder, read-only replay
   verifier, fixture-local inspection, and machine-readable acceptance command.
3. Enable the report only for the named API-503 success, denial, and recovery fixtures;
   do not backfill or rewrite stored history automatically.
4. Roll back by disabling Change 5 report generation/inspection and retaining the
   additive facts for audit. Because no Case/workflow state or external side effect is
   changed, no compensating business action is required.

## Open Questions

- None block the fixture-only slice. A future service-boundary/OpenTelemetry export,
  cross-fixture corpus, live rerun, benchmark, or real-provider trace is intentionally
  outside this Change and requires a new proposal.
