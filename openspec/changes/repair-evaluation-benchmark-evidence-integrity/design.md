## Context

Benchmark core currently proves offline execution and report determinism, but its
fixture/policy reference files repeat task-declared hashes instead of resolving source
content. Some task adapters call private acceptance helpers and construct outcomes from
adapter branches. The result can be deterministic without being evidence of the actual
control-path state.

## Goals / Non-Goals

**Goals:**

- Content-address every resolved fixture and policy source used by a task.
- Make typed public offline observations the sole input to hard-gate grading.
- Preserve one isolated temporary store per task/attempt and bind every emitted
  evaluation record to the task, oracle, grading, metrics and suite report.
- Prove the guards with source-tampering, state-regression, isolation and linkage tests.

**Non-Goals:**

- No corpus expansion, live rerun, LLM judge, provider, credential, network, Docker,
  external write, customer data, API or multi-Agent capability.

## Decisions

### 1. A source manifest, not a mirror reference, owns input identity

Each task will contain safe relative paths to its allowed checked-in fixture and policy
source. The loader resolves paths below an allowlisted repository root, loads canonical
JSON, calculates SHA-256, and requires the declared task hash to match. A path escape,
missing source, non-object source, foreign identity or mismatch fails before a store is
created. Mirrored `fixture.json`/`policy.json` metadata is removed or derived only from
the resolved source. This detects source mutation; comparing two task-local declarations
does not.

### 2. Public typed observation adapters replace private acceptance helpers

Each retained offline control slice will expose a small benchmark-facing function that
receives the resolved task and fresh store path, executes its real fixture path, and
returns a safe `BenchmarkObservation`. It includes actual tenant, state/outcome,
evidence status, approval status, operation counts and tool count. The runner will not
call underscore-prefixed helpers and will not translate branch selection into an outcome.
Existing acceptance commands can delegate to the same public path.

### 3. Task isolation is structural

The runner creates one temporary SQLite store per record and passes it to exactly one
adapter call. It has no suite cache of accepted results. Adapters that do not need a
store still receive it and must not read another task's retained state. A test records
distinct paths and demonstrates that state from a prior task cannot affect another.

### 4. Runtime records close the contract chain

For every observation the runner materializes `EvaluationCase`, `GraderResult`,
`RunMetrics`, `EvaluationResult`, then the suite report. It validates all linked records
with `validate_benchmark_result`; `task_result_ids` contains the emitted
`EvaluationResult` IDs, not grader IDs. The acceptance report can retain redacted
diagnostics but cannot report success if this linkage is incomplete.

## Risks / Trade-offs

- [Existing scripts need a public adapter surface] → add thin wrappers around current
  tested controls, preserving acceptance-command behavior and fixture-only boundaries.
- [Canonical source paths could expose input location] → store only safe relative
  identities/hashes in reports; never serialize absolute paths or source content.
- [More record construction raises test cost] → keep record schemas compact and reuse
  canonical validator code; no new dependency or service is introduced.

## Migration Plan

1. Add source-manifest and typed-observation contracts with negative tests.
2. Refactor runner and local controls, then materialize linked result records.
3. Rebaseline the 12-task offline report and run strict validation.
4. Roll back by removing the new repair command/code only; no persisted production data
   or external state exists.
