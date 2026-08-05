# offline-evaluation-benchmark Specification

## Purpose

Define the deterministic, Replay-only offline benchmark corpus, execution gates, grading, reporting, and acceptance evidence for WeFlow.

## Requirements

### Requirement: A canonical offline seed task corpus exists
The repository SHALL maintain a versioned offline evaluation task directory under
`evals/tasks/<task-id>/` and a deterministic suite manifest under `evals/suites/`.
Each task SHALL have a unique stable task identity, a required task definition and
oracle, safe references and SHA-256 hashes for its synthetic fixture/environment and
policy inputs, and an optional declared fault profile. A task or oracle SHALL NOT carry
raw customer text, prompt/context content, unrestricted tool or adapter output,
credential, caller-selected authority, or undeclared field. The
`offline-seed.v1` suite SHALL select exactly 12 unique API-503 fixture-local tasks that
cover successful processing, expected denial, validation failure, duplicate or
out-of-order input, and recovery behavior.

#### Scenario: The offline seed suite is loaded
- **WHEN** the suite loader reads the checked-in `offline-seed.v1` manifest and all
  referenced task directories
- **THEN** it SHALL accept exactly 12 unique, hash-valid task/oracle/fixture references
  and preserve their declared deterministic order

#### Scenario: A task attempts an unsafe or mismatched reference
- **WHEN** a task has a duplicate identity, a missing/foreign/hash-mismatched reference,
  raw or secret-like field, caller-selected authority, or unsupported fault name
- **THEN** the loader SHALL return only a redacted task-validation failure before it
  initializes a task store, workflow, provider, or side effect

### Requirement: The benchmark runner is isolated, Replay-only, and deterministic
The benchmark runner SHALL validate each selected task before execution, create a fresh
temporary fixture-local SQLite store for each task and deterministic attempt, execute
only its named Replay/control/simulator path, collect safe observations, and remove the
temporary store after collection. It SHALL not initialize a network client, live model,
credential, Docker service, real provider, external executor, multi-Agent coordinator,
or public API. It SHALL not mutate retained fixture evidence or treat an evaluation
result as a policy decision, approval, workflow command, delivery completion, customer
receipt, resolution, or Case completion.

#### Scenario: A task is executed twice from unchanged inputs
- **WHEN** the complete offline seed suite executes twice with unchanged checked-in
  inputs and deterministic attempt indices
- **THEN** both executions SHALL produce equal canonical per-task results and suite
  report hashes, with `offline=true`, `replay=true`, `network=false`, `model=false`,
  and `external_write=false`

#### Scenario: A live or external execution mode is requested
- **WHEN** benchmark configuration, task input, or a referenced fixture requests a live
  provider, credential, network destination, external-write adapter, Docker service,
  or multi-Agent execution
- **THEN** the runner SHALL deny the request before store initialization or contact and
  emit only a redacted configuration failure

### Requirement: Safety and integrity gates precede quality scoring
For every task, the deterministic grader SHALL evaluate effective tenant and reference
consistency, Replay/offline execution, unauthorized external-write absence, expected
local side-effect count and idempotency identity, current hash-bound approval where a
fixture-local delivery is expected, complete hash-valid evidence lineage, and the
oracle's expected safe outcome or state. These conditions are hard gates. A task with
any failed applicable hard gate SHALL be `failed`, SHALL have `quality_score` equal to
`not_scored`, and SHALL contribute no weighted quality score to a passing suite.

#### Scenario: A hard gate is violated
- **WHEN** an executed task has a tenant mismatch, unauthorized or duplicate side
  effect, stale approval, missing/tampered lineage, unexpected state/outcome, or
  non-Replay execution flag
- **THEN** the grader SHALL record the failed named gate and safe failure classification,
  mark the task failed and unscored, and SHALL NOT let another quality dimension offset
  the violation

#### Scenario: An expected policy denial is observed safely
- **WHEN** a task oracle requires a revoked-grant or stale-approval denial with zero
  local delivery intent and completion records
- **THEN** the grader SHALL mark the task passed only if that denial, zero-effect count,
  tenant boundary, and evidence requirements all satisfy their hard gates

### Requirement: Quality dimensions are deterministic and oracle-bound
Only after all applicable hard gates pass, the code-based grader SHALL derive a numeric
quality score from oracle-declared outcome correctness, evidence grounding, recovery
semantics, and bounded tool/budget efficiency. Every result SHALL retain the exact
oracle hash and named dimension outcomes. A model or LLM judge SHALL NOT execute in
this profile and SHALL NOT alter hard-gate or quality outcomes.

#### Scenario: A valid task reaches its expected local outcome
- **WHEN** a task's safe observations match its hash-bound oracle and all hard gates
  pass
- **THEN** the result SHALL include deterministic dimension outcomes and a numeric
  quality score bound to that oracle hash

#### Scenario: The oracle changes after task loading
- **WHEN** a task result is evaluated with a different, tampered, or hash-mismatched
  oracle
- **THEN** the runner SHALL fail the task with a redacted oracle-integrity
  classification and SHALL not report a numeric quality score

### Requirement: Benchmark diagnostics and reports are redacted and machine-readable
The runner SHALL emit a per-task diagnostic and aggregate suite report containing only
stable suite/task/run identities, safe fixture/task/oracle/report hashes, named
hard-gate and deterministic-dimension statuses, safe outcome/failure classifications,
aggregate counts, deterministic Replay metrics, and explicit capability/environment
flags. A report SHALL omit raw input, prompt, context, tool/adapter payload, credential,
customer identity details, caller-supplied authority, network/provider claim, customer
receipt, incident resolution, Case completion, or unrestricted stack output. Reports
SHALL be written only to an explicit output path and SHALL have a canonical content hash
over their stable safe representation.

#### Scenario: A caller writes an accepted seed-suite report
- **WHEN** the offline acceptance command is invoked with a valid explicit output path
- **THEN** it SHALL write a redacted report that identifies all 12 task results, their
  gate/dimension summaries, aggregate pass/fail/unscored counts, and a canonical report
  hash without exposing protected content

#### Scenario: Report construction receives unsafe content
- **WHEN** diagnostic or report construction sees a raw, secret-like, foreign, detached,
  undeclared, or customer-success field
- **THEN** it SHALL reject the affected result with a redacted classification and SHALL
  NOT write a report that exposes the unsafe value

### Requirement: Offline seed-suite acceptance is independently reproducible
The cross-platform development command surface SHALL provide an offline benchmark-core
acceptance command that runs the complete seed suite twice, compares canonical outputs,
and emits a redacted machine-readable acceptance report. Acceptance SHALL require all
12 tasks to satisfy their oracle, all hard gates to pass, no duplicate local effect,
and equal repeated baselines. The command SHALL run without network, Docker, model
credentials, enterprise credentials, or a live provider. A correct safe denial counts
as a passed task only under its declared denial oracle; it SHALL not be represented as a
successful customer delivery or resolution.

#### Scenario: Offline benchmark-core acceptance succeeds
- **WHEN** the supported suite, fixtures, and deterministic execution paths are
  unchanged on an offline workstation
- **THEN** the acceptance command SHALL produce a report with 12 expected task passes,
  zero hard-gate failures, zero unauthorized external-write attempts, zero duplicate
  local effects, and equal repeated canonical baselines

#### Scenario: A declared recovery or validation path regresses
- **WHEN** an intake ordering path, worker/recovery boundary, timeout/lost-response
  path, policy denial, stale approval, duplicate-delivery guard, or evidence-lineage
  validation path no longer satisfies its task oracle
- **THEN** the acceptance command SHALL fail with a redacted per-task classification and
  SHALL NOT replace a prior accepted baseline
