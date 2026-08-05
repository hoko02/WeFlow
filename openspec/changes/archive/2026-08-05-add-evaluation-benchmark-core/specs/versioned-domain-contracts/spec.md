## ADDED Requirements

### Requirement: Benchmark-core contracts are versioned, payload-safe, and compatible
WeFlow SHALL maintain language-neutral v1 schemas for `EvaluationTask`,
`EvaluationOracle`, `GraderResult`, `RunMetrics`, and `EvaluationSuiteReport` alongside
the retained `EvaluationCase` and `EvaluationResult` schemas. Each benchmark boundary
SHALL declare stable schema identity/version, forbid undeclared fields, carry tenant,
suite/task/run, fixture/oracle, and SHA-256 linkage where applicable, and contain only
safe IDs, hashes, enumerations, counts, reason codes, and explicit capability flags.
The schemas SHALL reject raw customer/prompt/context/tool/adapter data, credentials,
caller-selected authority, external provider/delivery claims, customer receipt,
resolution, and Case-completion assertions.

#### Scenario: A valid benchmark task and result validate cross-language
- **WHEN** a valid offline benchmark-core task, oracle, grader result, metrics, suite
  report, and linked evaluation result fixture are consumed by Python and TypeScript
  validators
- **THEN** both packages SHALL accept the same schema identities and versions while all
  retained valid v1 fixtures remain valid

#### Scenario: A benchmark boundary contains unsafe or foreign data
- **WHEN** a benchmark contract has raw/secret-like content, an undeclared field, a
  caller-selected authority, a foreign tenant/reference, an invalid hash, or a
  customer-success or external-provider assertion
- **THEN** both validators SHALL reject the fixture before it can become a task input or
  report output

### Requirement: Benchmark-profile results are complete without breaking retained v1 fixtures
Existing `EvaluationCase` and `EvaluationResult` schemas SHALL evolve only additively.
Legacy v1 fixtures without the benchmark profile SHALL remain valid. When an
`EvaluationResult` declares the `benchmark-core.v1` profile, semantic validation SHALL
require safe linkage to its task and oracle hashes, named hard-gate results,
deterministic grader-result and metrics references, explicit offline/Replay/no-network/
no-model/no-external-write flags, and a canonical report reference. A failed hard gate
or oracle-integrity failure SHALL require `quality_score=not_scored`; a numeric quality
score SHALL be allowed only when every applicable hard gate passes.

#### Scenario: A retained foundation evaluation result is revalidated
- **WHEN** the retained v1 evaluation-case and evaluation-result fixtures are validated
  without a `benchmark-core.v1` profile
- **THEN** both language consumers SHALL preserve their existing acceptance result

#### Scenario: A benchmark-profile result is incomplete or mis-scored
- **WHEN** a `benchmark-core.v1` result omits a required safe linkage/flag, refers to a
  different task or oracle hash, reports a numeric quality score after a failed hard
  gate, or marks an external/customer-success claim as true
- **THEN** both language consumers SHALL reject it with a deterministic validation
  result
