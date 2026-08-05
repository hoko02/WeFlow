## Why

The repaired offline benchmark now produces a complete, redacted, hash-bound 12-task
evidence chain, but the Web Console still exposes only foundation capability status and
there is no supported API for an operator to inspect the accepted suite or a task's
hard-gate evidence. A narrow read-only console slice is needed now to turn the verified
machine report into reviewable product evidence before the project expands the corpus
or introduces any live execution.

## What Changes

- Add a public validator and read-model builder for the one canonical
  `offline-seed.v1` acceptance report. It will revalidate the suite hash, source-bound
  task/oracle records, EvaluationCase/GraderResult/RunMetrics/EvaluationResult links,
  result IDs, determinism flags, and redaction boundary before returning a view.
- Add a fixed, loopback-only Platform API read endpoint for the supported suite. The
  effective tenant will be derived from an allowlisted synthetic observer; callers
  cannot select a filesystem path, report file, tenant, or arbitrary suite.
- Add a Vue evaluation view that renders aggregate pass/fail/unscored counts, repeated
  baseline status, capability flags, and per-task hard gates, quality dimensions,
  failure classification, safe source references, hashes, and offline metrics from the
  validated read model.
- Add a versioned `EvaluationSuiteSnapshot` boundary contract with Python and
  TypeScript validation, retained valid/invalid fixtures, and compatibility coverage.
- Add an offline acceptance command and automated API, security, rendering, build, and
  end-to-end checks for the report-present, missing, tampered, unsafe, and foreign-
  tenant paths. Update the console/benchmark guide and retain a machine-readable
  acceptance report.

## Non-goals

- This change does not expand the corpus beyond 12 tasks, add live-model runs, an LLM
  judge, token/cost/latency or P50/P95 claims, customer outcomes, or multi-Agent
  comparison.
- This change does not add a Case list or timeline, Replay controls, workflow commands,
  approval decisions, arbitrary report browsing/download, raw artifact export, network
  provider, credential, external write, or public deployment.
- An evaluation snapshot remains read-only evidence. It cannot authorize a workflow
  transition, approval, delivery, retry, external effect, customer-receipt claim, or
  incident-resolution claim.

## Capabilities

### New Capabilities

- `offline-evaluation-report-console`: Defines validated canonical-report loading, a
  tenant-derived read-only Platform API, safe suite/task presentation, unavailable and
  integrity-failure behavior, and deterministic offline console acceptance.

### Modified Capabilities

- `versioned-domain-contracts`: Adds the payload-safe `EvaluationSuiteSnapshot`
  boundary and cross-language compatibility/semantic validation requirements.

## Impact

- Affected code: benchmark validation/read-model code in the Python contracts/testkit,
  Platform API route wiring, TypeScript contract exports, Vue console components and
  pure render-model utilities, and `scripts/dev.py` command dispatch.
- Affected contracts and data: one additive v1 JSON Schema plus valid, invalid, and
  semantic fixtures. The existing canonical acceptance report remains the source and
  is not rewritten by a read request.
- Security boundary: synthetic actor-derived tenant scope, one allowlisted suite and
  repository-relative report path, full validation before presentation, non-disclosing
  absent/foreign behavior, and no caller-selected path or authority.
- Verification and docs: contract, unit, integration, security, console-render/build,
  end-to-end acceptance, secret-hygiene, and strict OpenSpec checks; development guide,
  project-memory update after verification, and a redacted machine-readable report.
- Dependencies and runtime: no new provider, credential, network dependency, Docker
  requirement, external connector, database migration, or external-write capability.
