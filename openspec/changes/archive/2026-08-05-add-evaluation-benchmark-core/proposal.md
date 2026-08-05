## Why

Changes 0–5 prove one fixture-local API-503 path can be processed safely, recovered,
and explained, but the repository has no task corpus, grader, or runner that can
measure that result beyond a demonstration. An offline benchmark core is needed now
to turn the retained deterministic slices into a reproducible safety and quality
baseline before the project considers live providers, a broader corpus, a console demo,
or multi-Agent comparison.

## What Changes

- Introduce an offline, fixture-first evaluation benchmark capability with a canonical
  task-directory format, a deterministic suite manifest, and a 12-task seed suite
  assembled from the supported API-503 success, denial, validation, and recovery paths.
- Add deterministic, code-based hard-gate grading for tenant isolation, unauthorized
  delivery, duplicate side effects, approval binding, evidence lineage, and expected
  safe outcomes; calculate quality only after every applicable hard gate passes.
- Add redacted, machine-readable per-task diagnostics and suite reports with stable
  task/run identities, outcome and failure classification, relevant safe hashes/counts,
  and offline Replay metrics. The reports will distinguish a safe expected denial from
  a failed task and will not claim live-model cost, customer receipt, or resolution.
- Evolve the existing evaluation contracts additively so Python and TypeScript can
  validate task, oracle, grader-result, run-metrics, and evaluation-result boundaries
  while retaining all existing v1 fixtures.
- Expose a cross-platform `scripts/dev.py` command for the offline seed suite and add
  acceptance, negative-security, repeatability, and secret-hygiene coverage.

## Non-goals

- This change does not add a live model, network access, credentials, external write,
  live rerun, LLM judge, customer outcome, or multi-Agent execution.
- This change does not expand the corpus to the M1 target of 60 tasks, change Case or
  workflow state, or add a public evaluation API or Operator Console page.
- This change does not reinterpret retained fixture-local delivery as a customer send,
  receipt, resolution, or Case completion.

## Capabilities

### New Capabilities

- `offline-evaluation-benchmark`: Defines the offline task corpus, deterministic
  execution and grading boundary, redacted diagnostic/report outputs, and seed-suite
  acceptance requirements.

### Modified Capabilities

- `versioned-domain-contracts`: Adds compatible, payload-safe evaluation boundary
  contracts and cross-language fixture validation requirements.

## Impact

- Affected code: Python contracts/testkit and benchmark runner, `scripts/dev.py`,
  offline fixtures/evaluation tasks, and automated contract, unit, integration,
  security, repeatability, and end-to-end acceptance tests.
- Affected artifacts: additive v1 JSON Schema and TypeScript contract exports, new
  redacted machine-readable reports, a benchmark development guide, and project-memory
  facts after verification/archival.
- APIs and dependencies: no new network API, provider, credential, external connector,
  Docker requirement, or runtime dependency. Existing deterministic Replay and
  fixture-local SQLite paths remain the only executable sources.
