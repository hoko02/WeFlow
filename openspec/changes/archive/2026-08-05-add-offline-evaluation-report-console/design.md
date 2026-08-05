## Context

The offline benchmark now writes one canonical, redacted acceptance report at
`reports/change-6-evaluation-benchmark-core-acceptance.json`. That report contains an
accepted 12-task `offline-seed.v1` suite, safe source paths and hashes, observations,
and the complete EvaluationCase/GraderResult/RunMetrics/EvaluationResult chain. The
runner validates the chain before writing, but there is no supported reader that
revalidates a retained report and no Platform API or Web Console surface for it.

The current Vue application fetches only foundation health and capability flags. The
Platform API already uses synthetic actor-derived tenant identity and non-disclosing
read behavior for Case, workflow, approval, delivery, and evidence routes. This change
extends that same local-only observation boundary to evaluation evidence without
making evaluation a workflow authority or a public file browser.

The primary stakeholders are a local operator or reviewer inspecting reproducible
portfolio evidence and a developer diagnosing a benchmark regression. The supported
environment remains offline, Replay-only, single-tenant synthetic data with no model,
credential, Docker, provider, external write, or customer outcome.

## Goals / Non-Goals

**Goals:**

- Revalidate the retained canonical report against the current suite, source-bound
  tasks/oracles, contract schemas, record links, report hashes, deterministic flags,
  and redaction rules before presentation.
- Derive one closed, content-addressed `EvaluationSuiteSnapshot` that Python and
  TypeScript accept identically and that contains only the fields needed by the API and
  console.
- Expose the snapshot through one fixed, tenant-derived, read-only loopback API route
  with stable non-disclosing error behavior.
- Render truthful suite and task evidence in Vue, including hard-gate precedence and
  explicit offline/no-live-metrics limitations.
- Provide a deterministic acceptance command covering valid, missing, foreign,
  tampered, unsafe, and detached report paths plus console rendering/build.

**Non-Goals:**

- No 60-task expansion, new scenario fixture, live rerun, model/LLM judge, token/cost/
  latency collection, P50/P95, holdout, or multi-Agent comparison.
- No Case list/timeline, Replay button, workflow command, approval decision, report
  upload/download, directory listing, arbitrary path, raw artifact, or unrestricted
  diagnostic export.
- No public deployment, network provider, enterprise identity, credential, database
  migration, external connector/write, customer receipt, resolution, or completion.
- The report endpoint does not run the benchmark, repair a report, replace a prior
  baseline, authorize a retry, or mutate workflow/evaluation state.

## Decisions

### 1. Serve a derived closed snapshot, not the acceptance JSON directly

The API will return a new additive v1 `EvaluationSuiteSnapshot`. It will carry stable
tenant/suite/profile/report identities and hashes, accepted/deterministic flags,
pass/fail/unscored counts, capability flags, and an ordered task array. Each task view
will contain only safe fixture/source/task/oracle/result identities and hashes, result
and failure classification, hard gates, quality dimensions, the existing offline
RunMetrics counters, and safe observation state/outcome facts. It will have
`additionalProperties=false` and its own canonical `snapshot_sha256`.

The snapshot intentionally omits raw source objects, prompts, context, tool/adapter
payloads, stack output, absolute paths, caller authority, credentials, external-
provider claims, and customer-success fields. Python will construct and validate it;
TypeScript will validate and consume the same shape.

Alternatives considered:

- Returning the full acceptance JSON was rejected because the top-level diagnostic
  envelope is broader than the UI contract and would make future safe report evolution
  a breaking console dependency.
- Copying the report into Vue static assets was rejected because it bypasses tenant
  identity, runtime integrity checks, and the Platform API observation boundary.

### 2. Use one allowlisted report repository with full validation before projection

A public benchmark report loader will resolve exactly the repository-relative
`reports/change-6-evaluation-benchmark-core-acceptance.json` path. Neither the HTTP
route nor the snapshot builder accepts a caller path, glob, suite directory, tenant, or
alternate report name. The loader will parse JSON with duplicate-key rejection and
will never follow an absolute path or path outside the repository reports directory.

Before deriving a snapshot it will reload the current `offline-seed.v1` manifest and
source-bound task/oracle records, validate the suite report, confirm accepted and equal
baseline flags, and semantically validate every EvaluationCase, GraderResult,
RunMetrics, EvaluationResult, source hash, result ID, and report link. It will also scan
the report/view for forbidden raw or secret-like fields. A read never runs adapters,
opens a task SQLite store, changes the report, or writes a replacement.

The Platform API will receive this reader through an injected evaluation-report
boundary so integration tests can use explicit temporary report paths internally while
the default application remains fixed to the canonical repository path. Keeping the
reader with the existing benchmark/testkit code is accepted for this local developer
console; business workflow code must not depend on or invoke it.

Alternatives considered:

- Trusting the checked-in report because Git tracks it was rejected; stale source
  hashes or detached record links must still fail at runtime.
- Regenerating a missing report on GET was rejected because a read endpoint must not
  execute a long benchmark or turn absence into a side effect.

### 3. Derive tenant identity and keep absent/foreign report reads indistinguishable

The fixed route will be `GET /v1/evaluations/offline-seed.v1`. It will reject query
parameters and use `X-WeFlow-Synthetic-Actor` with the existing actor registry. An
unknown actor remains a tenant-identity denial. If the valid report belongs to another
tenant, or no valid report exists for the effective tenant, the route returns the same
allowlisted `evaluation_report_not_found` response without revealing report identity,
path, hash, tenant, or validation details.

Malformed, duplicate-key, unsafe, or integrity-invalid canonical content returns a
generic `evaluation_report_not_ready` service error and never a partial snapshot or raw
exception. Platform API health/readiness remains independent: a missing evaluation
report makes only this optional evidence surface unavailable.

The route exposes no POST/PUT/PATCH/DELETE method. Snapshot/result identities are
evidence references only and cannot be passed to workflow, approval, delivery, or
external-effect code as authority.

### 4. Keep rendering pure, truthful, and failure-aware

The Vue application will split transport, snapshot validation, and display mapping.
Pure TypeScript functions will accept only a validated `EvaluationSuiteSnapshot` and
produce a render model for deterministic Node-based fixture tests. The page will show:

- suite identity, report/snapshot hash, accepted and repeated-baseline status;
- pass/fail/unscored counts and explicit offline/Replay/no-network/no-model/no-write
  flags;
- an ordered task list and selected-task hard gates, quality dimensions, source hashes,
  result/failure classification, observation facts, and existing counter metrics;
- stable loading, unavailable, identity-denied, and integrity-not-ready states.

The UI will label local fixture delivery as local-only and display latency, token, cost,
live-run variance, customer receipt, and resolution as unsupported rather than zero or
successful. It will not render arbitrary object keys or an unrestricted JSON dump.

Alternatives considered:

- Adding a client-side router and full Case Operator Console now was rejected as a
  broader change with separate list, demo-seeding, command, and evidence requirements.
- Adding a new browser-test framework was deferred; pure render-model fixture tests,
  TypeScript checks, an API integration test, and the production Vite build provide a
  bounded first acceptance surface without another dependency.

### 5. Acceptance is a read-only end-to-end evidence check

`python scripts/dev.py evaluation-console-acceptance` will use the canonical accepted
report and an injected local API boundary to produce a redacted machine-readable
report. It will prove one valid tenant receives a 12-task snapshot whose hashes, result
IDs, counts, hard gates, and deterministic flags match the source; a foreign tenant and
missing report are non-disclosing; tampered, unsafe, duplicate-key, or detached content
returns no snapshot; and no report, task store, workflow, approval, delivery, network,
model, or external-write state changes.

The aggregate repository checks will also run Python/TypeScript contract fixtures,
Platform API integration/security tests, the pure console render test, TypeScript
lint/typecheck, Vite build, secret hygiene, and strict OpenSpec validation. The
canonical acceptance output will live under `reports/` and be explicitly allowlisted
for repository evidence.

## Risks / Trade-offs

- **A checked-in report can become stale after fixture or task changes.** → Re-resolve
  current sources and record hashes on every snapshot load; fail closed rather than
  showing stale evidence.
- **The local Platform API gains a dependency on benchmark/testkit code.** → Keep it
  behind a small injected read-only boundary and prohibit any call from business
  workflow/runtime modules; revisit package extraction only when a second evaluation
  consumer exists.
- **The report is about 78 KB and task details can overwhelm the page.** → Return one
  bounded 12-task snapshot and render an aggregate plus one selected task, not an
  unrestricted tree.
- **Missing evidence could incorrectly make the whole application look unhealthy.** →
  Keep service readiness independent and expose an explicit optional-surface state.
- **Labels could imply live quality or customer success.** → Render fixed capability
  flags and unsupported metrics, test forbidden claims, and document the fixture-only
  meaning of every local effect.
- **The existing report may fail new validation during implementation.** → Treat that
  as evidence that design assumptions are invalid; update the change artifacts before
  altering report semantics or weakening validation.

## Migration Plan

1. Add the snapshot schema, Python/TypeScript validation, fixtures, and compatibility
   tests without changing existing report generation or retained fixtures.
2. Add the public canonical-report loader and deterministic snapshot builder with
   missing/tampered/unsafe/detached negative tests.
3. Add the injected Platform API boundary and fixed GET route; keep health/readiness and
   all existing routes unchanged.
4. Add the pure TypeScript render model and Vue evaluation view, retaining truthful
   foundation status and safe unavailable states.
5. Add the cross-platform acceptance command, canonical redacted evidence, docs, and
   full verification before archive.

Rollback removes the endpoint, UI view, command, and reader wiring while retaining the
published additive v1 schema, fixtures, canonical reports, and prior benchmark core.
There is no database migration or durable state to roll back.

## Open Questions

None block implementation. The exact visual layout may evolve during Apply provided
the snapshot fields, safe states, fixed route, and acceptance requirements remain
unchanged.
