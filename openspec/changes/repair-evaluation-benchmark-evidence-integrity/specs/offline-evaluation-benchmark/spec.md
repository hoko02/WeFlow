## ADDED Requirements

### Requirement: Benchmark task inputs are resolved and content-addressed
The benchmark loader SHALL resolve every task fixture and policy reference to an
allowlisted checked-in source file, canonicalize its JSON object, and require its
declared SHA-256 and safe identity to match the resolved source before it creates a
task store. It SHALL reject task-local mirror metadata, path escapes, missing,
non-canonical, foreign or hash-mismatched sources with a redacted failure.

#### Scenario: A referenced fixture source changes
- **WHEN** a task's referenced source fixture no longer hashes to its declared value
- **THEN** loading SHALL fail before adapter execution or SQLite store creation

### Requirement: Benchmark observations are public, typed and task-isolated
The runner SHALL invoke only public offline benchmark adapters which receive one fresh
temporary store and return the actual safe tenant, state/outcome, evidence, approval,
tool-count and local-effect facts. It SHALL not call private acceptance helpers, reuse
a cached suite result, or construct an outcome independently of the returned observation.

#### Scenario: A control path returns an unexpected state
- **WHEN** an adapter returns a safe state or outcome different from its task oracle
- **THEN** the expected-outcome hard gate SHALL fail and the task SHALL be failed and
  `not_scored`

### Requirement: Runtime results form a complete evaluation evidence chain
For each executed task the runner SHALL materialize and semantically validate linked
`EvaluationCase`, `GraderResult`, `RunMetrics`, and `EvaluationResult` records before
including the evaluation-result ID in the suite report. An incomplete, mismatched or
cross-task link SHALL fail the task and prevent accepted-suite output.

#### Scenario: A suite result link is detached
- **WHEN** an EvaluationResult does not link to the emitted task, oracle, grader,
  metrics or suite report hash
- **THEN** validation SHALL reject the task result and the acceptance command SHALL not
  replace a prior accepted report
