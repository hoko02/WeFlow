## Why

The archived benchmark core is safely offline and deterministic, but its task hashes are
self-consistent metadata rather than hashes of resolved source inputs; several adapters
also derive outcomes outside the returned control-path facts. That can let a changed
fixture or regressed state remain reported as a pass, which conflicts with WeFlow's
purpose of using reproducible evidence rather than a successful-looking demo.

## What Changes

- Bind every benchmark task to a resolved, checked-in fixture and policy source using
  canonical content hashes; reject missing, mismatched, foreign, or non-canonical
  sources before store creation.
- Replace private acceptance-helper calls and hard-coded outcomes with public,
  typed offline benchmark observations that expose the actual safe state, evidence,
  approval and local-effect facts required for grading.
- Enforce a fresh fixture-local SQLite execution context for every task and attempt;
  remove suite-level result reuse that bypasses a task's resolved store.
- Have the runner emit and semantically validate one `EvaluationCase` and
  `EvaluationResult` per task, linking them to the grader result, run metrics and
  suite report; the suite report will reference those actual result IDs.
- Add mutation, integrity, isolation and end-to-end lineage regressions, and retain a
  redacted re-baselined offline acceptance report.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `offline-evaluation-benchmark`: Require source-bound task inputs, public typed
  observations, per-task isolation, and end-to-end evaluation-record evidence.
- `versioned-domain-contracts`: Require benchmark-profile result records produced by
  the runner to satisfy their task/oracle/grader/metrics/report linkage.

## Impact

- Affected code: benchmark task loader/runner, the supported offline acceptance
  adapters, contract helpers, fixtures, testkit, and `scripts/dev.py` acceptance path.
- Affected data: evaluation task references will identify canonical source files and
  real hashes; reports gain safe evaluation-case/result records and result IDs.
- Safety: this remains Replay-only and fixture-only. It adds no model, credential,
  network client, Docker service, public API, customer data, external write, or
  multi-Agent capability.
