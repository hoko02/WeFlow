## Context

The deterministic API-503 fixture already produces append-only Case events, immutable
revisions, workflow checkpoints, investigation actions and tool results, a verified
response candidate, policy and authorization facts, a hash-bound approval, one
fixture-local delivery chain, an Evidence Report, and verification replay. Platform API
can read those concerns through separate tenant-scoped routes, but the Web Console only
loads foundation health and the offline evaluation suite. The ignored default SQLite
store is not a canonical demo data source and may be empty, while the existing retained
acceptance reports summarize outcomes rather than expose one complete ordered Case
projection.

The operator view must therefore be generated from actual deterministic runtime facts,
not from browser-side joins, handcrafted expected values, task-local mirrors, or a read
that silently runs the workflow. It must remain useful on a fresh offline checkout and
must preserve the existing distinction between fixture-local delivery and a live
provider/customer outcome.

Stakeholders are a local support operator or interviewer inspecting the reliability
story, developers reviewing causal evidence, and security reviewers checking tenant,
authority, data-minimization, and no-side-effect boundaries.

## Goals / Non-Goals

**Goals:**

- Produce one deterministic, closed, content-addressed `OperatorCaseSnapshot` from two
  fresh executions of the allowlisted API-503 happy path through existing public
  control-kernel and simulator boundaries.
- Preserve a complete declared source chain from synthetic intake through local
  delivery, Evidence Report, and verification replay with stable order, identities,
  hashes, counts, state transitions, and capability flags.
- Serve only that canonical snapshot through a fixed, actor-derived, tenant-scoped,
  read-only route whose availability does not change foundation readiness.
- Render a clear Case timeline and selected bounded detail without raw payloads or
  authority/customer-success implications.
- Prove determinism, integrity, non-disclosure, prior-report preservation, and zero
  network/model/external-write/default-store mutation in machine-readable acceptance.

**Non-Goals:**

- Arbitrary Case discovery, pagination, search, caller-selected files/reports/tenants,
  or a general live operations backend.
- Browser approval decisions, workflow commands, Replay/fault controls, retries, or any
  mutation endpoint.
- Live models/providers, enterprise credentials, customer data, real delivery,
  resolution/completion, knowledge publication, multi-Agent behavior, or external
  writes.
- Corpus expansion, live evaluation metrics, PostgreSQL/Temporal migration, OTel UI,
  or a claim that the full business workflow is implemented.

## Decisions

### 1. Generate a retained snapshot report; do not seed the default runtime store

An explicit acceptance command will execute the existing allowlisted fixture twice in
separate temporary SQLite stores, revalidate the durable source records, compare the
two projections, and write a redacted canonical acceptance report only after every
check passes. The report will contain the validated operator snapshot and acceptance
evidence required to read it later. Normal API reads will never execute or repair the
workflow and will not create a SQLite store.

This keeps a fresh checkout demonstrable without treating ignored `.weflow` state as
source control. It also keeps report generation separate from report presentation.
Seeding `.weflow/case-ledger.sqlite3` during startup was rejected because startup would
become a hidden business mutation and local stale state could change the demo. Serving
a handwritten fixture was rejected because it would not prove the runtime chain.

### 2. Use one closed cross-language snapshot contract

`OperatorCaseSnapshot` will be an additive v1 JSON Schema consumed by Python and
TypeScript. The top level will bind schema/snapshot identity, tenant, fixed fixture,
Case/revision/workflow, current fixture state, source report and root hashes, aggregate
counts, and explicit offline capability flags. Ordered timeline entries will bind a
stable sequence and entry identity to an allowlisted source record type, source record
identity/hash, phase, state transition or bounded observation, result, and safe reason
code. Bounded detail sections will expose only IDs, hashes, classifications, counts,
fixed states/outcomes, and safe repository-relative source references.

Semantic validation will recompute the canonical snapshot hash, require unique
contiguous sequence and source identities, reconcile timeline/count summaries, enforce
tenant/Case/revision/workflow linkage, verify predecessor and source hashes, and make
failed authorization/evidence gates take precedence over any success-like label.
Undeclared fields, raw customer/prompt/tool/provider content, absolute or escaping
paths, credentials, caller authority, live-provider/customer-success flags, and
workflow/effect authority are forbidden.

An unrestricted generic event array was rejected because existing source records have
different trust and redaction semantics. The snapshot is an operator read model, not a
replacement source ledger or a new mutable domain aggregate.

### 3. Build the snapshot server-side from one consistent validated input

The reader will resolve only the canonical report path under `reports/`, reject
duplicate JSON keys and unsafe paths, validate the report envelope and full snapshot,
and return a copy through a small read protocol injected into Platform API. The browser
will not fan out across Case, checkpoint, investigation, approval, delivery, and
evidence routes because those calls could observe different versions and yield a
partial mixed projection.

The builder may reuse public validators and read-only export/fact methods, but it will
not query private SQLite tables or duplicate workflow transition logic. Existing
source routes and control ownership remain unchanged.

### 4. Expose one fixed tenant-derived route

Platform API will expose only `GET /v1/operator/cases/api-503.v1`. Tenant identity will
come from `X-WeFlow-Synthetic-Actor`; the caller cannot select a Case ID, tenant,
report, path, snapshot, or version through path/query/body values. Missing and foreign
snapshots will share `operator_case_not_found`; malformed, stale, detached, unsafe, or
failed-integrity evidence will return `operator_case_not_ready`. Unknown actors and
query parameters will use stable denied/invalid classifications. No POST/PUT/PATCH/
DELETE route will be added.

The evaluation report route remains independent. Absence of operator evidence will not
make `/health/ready` fail or change the truth of existing capability flags.

### 5. Validate before constructing a pure render model

The browser transport will accept only the fixed route and actor header. A complete
runtime validator will reject the entire response before a pure mapping function
produces `loading`, `ready`, `not-found`, `identity-denied`, or
`integrity-not-ready`. The ready model will render a phase timeline plus one selected
entry, source identities/hashes, gate and recovery annotations, evidence root, and
explicit capability limitations. It will not render unrestricted JSON, raw exceptions,
or server-supplied HTML.

The canonical current state will be labeled `DELIVERY_RECORDED (fixture-local)` and
never `resolved`, `completed`, `customer delivered`, or equivalent. Replay verification
is evidence validation only and cannot authorize a transition or effect.

### 6. Make acceptance the only publication path

`python scripts/dev.py operator-case-timeline-acceptance` will run the two fresh
baselines, contract and source-link validation, API/tenant matrix, renderer checks, and
production build. Its negative matrix will cover missing/foreign evidence, malformed
and duplicate-key JSON, unsafe paths/fields, detached hashes/predecessors, duplicate or
out-of-order source records, count mismatch, stale approval, policy denial presented as
authorized, timeout/restart recovery presented as duplicate completion, unsupported
customer-success authority, arbitrary selectors, and unsupported methods.

The command will compare the prior report and default runtime store bytes, publish the
machine-readable report only on complete success, and record zero network requests,
model invocations, provider initialization, external-write attempts, duplicate natural
or idempotency keys, and Case/workflow/effect mutations outside its temporary stores.

## Risks / Trade-offs

- **[Retained evidence can be mistaken for a live Case]** → Label every view and API
  capability as offline, synthetic, Replay-only, and report-backed; never expose live
  freshness language.
- **[The snapshot duplicates source facts]** → Keep the source ledgers authoritative,
  include only bounded operator fields, bind every entry to source identity/hash, and
  regenerate only through acceptance.
- **[Cross-source ordering can invent causality]** → Use an explicit allowlisted phase
  order plus source predecessor/event/checkpoint order; reject ambiguous, missing,
  duplicate, or conflicting links rather than guessing.
- **[A large contract becomes a raw ledger export]** → Cap fields and counts, use typed
  summaries, forbid arbitrary payload maps, and omit raw content even from tests and
  reports.
- **[A canonical happy path hides failures]** → Show gate/recovery evidence that exists
  in the source chain and test failure classifications in the negative matrix; add
  interactive Replay/fault scenarios only in a later change.
- **[Report drift can break normal startup]** → Keep the reader optional and readiness
  independent; return a safe unavailable state until explicit acceptance regenerates a
  valid report.

## Migration Plan

1. Add and validate the new contract and fixtures without changing retained schemas.
2. Add the builder and acceptance path; generate the canonical report only after two
   equal source-backed runs pass.
3. Add the optional reader and fixed API route, then the console transport/render view.
4. Run focused, aggregate, contract, secret-hygiene, production-build, acceptance, and
   strict OpenSpec checks before documenting verified facts.

Rollback removes the optional route/view/reader, generated report, and additive schema
exports. Existing source ledgers, workflow behavior, evaluation report, and default
runtime store require no data migration or rollback.

## Open Questions

No blocking product choices remain. Interactive Replay controls, a live/current Case
store, Case listing, and the 60-task corpus are deliberately separate future changes.
