## ADDED Requirements

### Requirement: Benchmark runtime records are materially linked
The benchmark runtime SHALL emit benchmark-profile `EvaluationCase` and
`EvaluationResult` records for every graded task. Their tenant, suite/task, task/oracle
hashes, hard-gate result, capability flags and grader/metrics/report references SHALL
match the emitted records, and `EvaluationSuiteReport.task_result_ids` SHALL identify
the emitted EvaluationResult records.

#### Scenario: A runner emits a benchmark task result
- **WHEN** a safe offline task is graded successfully or fails a hard gate
- **THEN** Python and TypeScript-compatible runtime records SHALL retain one complete
  hash-bound evaluation chain and use `not_scored` for every failed applicable gate
