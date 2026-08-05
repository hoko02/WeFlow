## 1. Snapshot Contract

- [x] 1.1 Add the closed v1 `EvaluationSuiteSnapshot` schema and matching Python/TypeScript contract exports for suite identity, hashes, counts, capability flags, ordered task evidence, gates, dimensions, offline metrics, and observations; verify both packages accept one complete valid fixture and reject undeclared fields.
- [x] 1.2 Add semantic validation for canonical snapshot hashing, tenant/suite/report/result/source linkage, unique ordered task/result identities, aggregate counts, hard-gate precedence, and fixed offline capability flags; verify focused Python and TypeScript tests reject each mismatched invariant.
- [x] 1.3 Add cross-language valid/invalid snapshot fixtures covering foreign identity, detached hashes, duplicates, count mismatch, numeric quality after a failed gate, unsafe paths, raw/secret-like fields, authority, live-provider, customer-success, and external-write claims; verify parity and record the new schema fingerprint without changing retained evaluation fixture outcomes.

## 2. Canonical Report Reader

- [x] 2.1 Add a public read-only evaluation report boundary that resolves only `reports/change-6-evaluation-benchmark-core-acceptance.json`, rejects duplicate JSON keys and unsafe/out-of-repository paths, and supports an explicit injected report source for tests; verify missing, malformed, duplicate-key, and path-safety cases without creating a task store or file.
- [x] 2.2 Revalidate the report against the current `offline-seed.v1` manifest, source-bound tasks/oracles, report hashes, accepted/repeated-baseline flags, and the complete EvaluationCase/GraderResult/RunMetrics/EvaluationResult chain before projecting a snapshot; verify stale, tampered, detached, cross-task, and failed-integrity reports emit no partial snapshot.
- [x] 2.3 Build the deterministic content-addressed snapshot projection with bounded safe fields and stable task ordering; verify two reads are byte-equivalent, the 12 source/result links and aggregate counts match the canonical report, forbidden fields are absent, and report/workflow/effect files remain unchanged.

## 3. Tenant-Scoped Platform API

- [x] 3.1 Inject the evaluation report reader behind a small read-only Platform API protocol while keeping business workflow/runtime modules independent; verify existing health and route tests run with the boundary absent and evaluation-report availability does not affect foundation readiness.
- [x] 3.2 Implement only `GET /v1/evaluations/offline-seed.v1`, deriving tenant identity from `X-WeFlow-Synthetic-Actor`, rejecting query parameters and alternate selectors, and mapping absence/foreign access to `evaluation_report_not_found` and integrity failures to `evaluation_report_not_ready`; verify responses contain no path, foreign tenant, raw exception, or caller-supplied selector.
- [x] 3.3 Add Platform API integration/security tests for authorized, unknown-actor, foreign-tenant, missing, tampered, unsafe, query-selector, alternate-suite, and unsupported-method requests; verify the valid response satisfies the snapshot contract and every request leaves reports, Cases, workflows, approvals, deliveries, and effects unchanged.

## 4. Evaluation Console

- [x] 4.1 Add the TypeScript transport, runtime snapshot validation, and pure render-model mapping for loading, ready, not-found, identity-denied, and integrity-not-ready states; verify Node fixture tests never pass raw/unvalidated response content to the view.
- [x] 4.2 Add the Vue aggregate and selected-task evaluation view showing suite/report hashes, deterministic status, counts, offline capability flags, safe source/result links, hard gates, dimensions, observations, and offline counters; verify unsupported latency/token/cost/variance/customer receipt/resolution claims are explicitly unavailable rather than zero or successful.
- [x] 4.3 Add deterministic console render tests for all 12 task summaries, one selected task, failed-gate precedence, safe unavailable states, local-only delivery labeling, and forbidden unrestricted JSON/raw claims; verify lint, typecheck, tests, and the production Vite build pass without a new browser-test dependency.

## 5. Offline Acceptance and Documentation

- [x] 5.1 Add `python scripts/dev.py evaluation-console-acceptance` to exercise the canonical reader, tenant-scoped API, snapshot contract, render model, and production build twice offline; verify equal snapshots, matching hashes/counts/result IDs, zero network/model/provider use, and zero retained-state or external side effects.
- [x] 5.2 Add the missing, foreign, malformed, duplicate-key, tampered, unsafe, stale, detached, arbitrary-selector, and unsupported-claim acceptance matrix plus prior-report preservation; emit a redacted machine-readable report under the explicit repository report path only after every check passes.
- [x] 5.3 Run the repository check/lint, Python and TypeScript contract parity, focused and aggregate tests, secret hygiene, console acceptance, and strict OpenSpec validation; record exact verified metrics, limitations, report paths, and the next-stage gate in `docs/PROJECT_MEMORY.md` without claiming live or customer-verified capability.
