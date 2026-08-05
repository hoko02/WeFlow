## Context

The retained Changes 0–5 provide deterministic, fixture-local evidence for one
API-503 path: intake, workflow/ticket recovery, replay investigation, policy and
approval-gated local delivery, and evidence-trajectory verification. The repository
does not yet have an `evals/` task corpus, an oracle/grader boundary, or a command that
compares outcomes across those paths. The existing v1 `EvaluationCase` and
`EvaluationResult` schemas are intentionally minimal foundation contracts.

This change creates the measurement layer for the existing offline path. It is owned by
deterministic code, uses only checked-in synthetic data and temporary local SQLite
stores, and remains outside the customer-facing workflow/API surface. Stakeholders are
the reliability-harness developer and an evaluator reviewing reproducible evidence.

## Goals / Non-Goals

**Goals:**

- Define a versioned, machine-validatable 12-task offline seed suite over the existing
  API-503 success, expected-denial, validation, and recovery behavior.
- Make task loading, execution, grading, and report construction deterministic,
  redacted, tenant-scoped, and independently repeatable.
- Gate quality scoring behind non-negotiable safety and integrity checks, so an
  unauthorized action, duplicate local effect, stale approval, tenant violation, or
  incomplete evidence can never be offset by a weighted score.
- Produce a single cross-platform command and a stable, machine-readable diagnostic
  report suitable for later corpus expansion and console consumption.

**Non-Goals:**

- No live model/provider, network access, credential, external executor, public API,
  Operator Console page, or LLM judge is introduced.
- No Case/workflow state is mutated outside a per-run temporary fixture store; no
  benchmark result grants policy/approval authority or claims customer receipt,
  incident resolution, or Case completion.
- The M1 60-task corpus, five live repetitions, and multi-Agent comparison remain
  subsequent changes once this core has an accepted deterministic baseline.

## Decisions

### 1. A JSON-only task directory is the canonical source of evaluation input

Each task will live under `evals/tasks/<task-id>/` and contain a required
`task.json` and `oracle.json`, plus required safe fixture/environment and policy
reference files and an optional `faults.json`. `evals/suites/offline-seed.v1.json`
will list exactly 12 unique task identities and their expected offline profile.
Task files contain only synthetic fixture identities, hashes, permitted fault names,
and expectation metadata; they do not duplicate raw customer text, prompts, tool output,
credentials, or local-adapter payloads.

JSON is chosen over YAML for the initial core because the repository already validates
JSON Schema in Python and TypeScript and canonical JSON hashing avoids a new parser and
serialization ambiguity. The task directory remains extensible by later contract
versions.

The seed suite will cover accepted/deduplicated/out-of-order intake, bounded
investigation, SLA/operator-safe handling, ticket and delivery lost-response recovery,
revoked-grant and stale-approval denial, duplicate-side-effect prevention, and tampered
evidence lineage. An expected safe denial is a passing evaluation result only when its
oracle-required denial and zero-effect assertions both hold.

### 2. The runner has a four-stage deterministic boundary

`scripts/dev.py evaluation-benchmark-acceptance` will invoke a Python benchmark runner
that performs the following per suite execution:

```text
validate task + oracle + referenced fixture hashes
  -> create isolated temporary SQLite fixture store per task/run
  -> execute named Replay-only path with declared fault injection
  -> collect redacted observations -> code graders -> canonical report
```

The runner does not call a network client, model, Docker service, external adapter, or
public API. It selects only existing fixture-local control paths and deletes temporary
run stores after collecting safe records. All output identities derive from the suite,
task, fixture, and deterministic attempt index; canonical reports carry no wall-clock,
absolute-path, PID, raw payload, or randomly generated field. The acceptance command
runs the complete suite twice and compares canonical report hashes and per-task results.

Using the existing execution paths rather than simulating their outputs keeps the
benchmark tied to actual policy, recovery, and evidence behavior. Isolated stores avoid
cross-task history and prevent a benchmark run from changing retained fixture evidence.

### 3. Hard gates are evaluated before deterministic quality dimensions

The runner will produce one named result for every required hard gate: effective tenant
and referenced identity consistency; Replay/offline execution; absence of an
unauthorized external write; exact expected local side-effect count and idempotency
identity; valid current approval binding where local delivery is expected; complete,
hash-matching evidence lineage; and the oracle's expected safe outcome/state.

If any applicable hard gate fails, the task result is `failed`, its quality score is
`not_scored`, and the suite cannot report overall success. If all gates pass, code-only
quality dimensions from the oracle evaluate outcome correctness, evidence grounding,
recovery semantics, and declared budget/tool-count efficiency. These dimensions are
deterministic and use safe IDs, hashes, counts, and reason codes only.

An LLM judge was considered for response usefulness, but is excluded because it would
make the core non-deterministic, require model provenance and isolation controls, and
could not override the safety gates in any case.

### 4. Contracts evolve additively under an explicit benchmark profile

New v1 JSON Schema objects will model `EvaluationTask`, `EvaluationOracle`,
`GraderResult`, `RunMetrics`, and `EvaluationSuiteReport`. They will have stable schema
IDs/versions, tenant/task/suite/run linkage where applicable, fixed enumerations, and
`additionalProperties: false`.

`EvaluationCase` and `EvaluationResult` retain their current valid v1 shape. Additive
benchmark fields are optional for legacy fixtures but become required through a
`benchmark-core.v1` profile validation path for results emitted by this runner. Python
and TypeScript semantic validation will enforce cross-object hashes and the rule that a
failed hard gate cannot have a numeric quality score. This avoids silently breaking
retained Change 0 fixtures while making benchmark-produced results complete.

### 5. Reports are redacted evidence, not workflow or provider evidence

The per-task diagnostic and aggregate suite report will contain only stable task/run
IDs, fixture IDs/hashes, task/oracle/report hashes, hard-gate statuses, safe outcome or
failure classifications, aggregate counts, deterministic metrics, and explicit flags
for `offline=true`, `replay=true`, `network=false`, `model=false`, and
`external_write=false`. A local fixture-delivery record is described only by its safe
identity/count and is never presented as a send, provider acknowledgement, customer
receipt, resolution, or completion.

Reports are written only when the caller supplies the existing-style `--output` path;
the acceptance path will produce the canonical redacted report under `reports/` for
review. Invalid task input produces a redacted validation failure and does not initialize
a task store or persist a partial successful report.

## Risks / Trade-offs

- **A 12-task seed may look like M1-scale coverage.** → The report and documentation
  SHALL label it `benchmark-core` and expose `planned_live_runs=0`; 60-task and live
  claims remain explicitly unavailable.
- **Existing fixture helpers may couple tasks to test internals.** → Put task loading,
  observations, graders, and canonical serialization in a dedicated benchmark package;
  call supported control/simulator interfaces rather than asserting private state.
- **Synthetic fixture data could leak into diagnostics.** → Validate report objects and
  task files against denylisted raw/secret fields; test malformed and secret-like input
  before any output is written.
- **A flawed oracle could create a misleading pass.** → Hash-bind each result to its
  oracle, test tampered/mismatched oracle references, and require reviewable per-gate
  results rather than a score alone.
- **Repeated execution can leave durable contamination.** → Use a fresh temporary
  SQLite store per task/attempt, verify no retained store mutation, and clean up only
  the resolved temporary path after collection.

## Migration Plan

1. Add schemas, Python/TypeScript exports, valid/invalid/semantic fixtures, and
   compatibility tests before adding task execution.
2. Add the task loader, isolated Replay-only runner, deterministic graders, and seed
   task/suite files; preserve all existing acceptance commands unchanged.
3. Add the `dev.py` acceptance command, redacted report generation, repeatability,
   fault, and negative-security tests; document the supported offline profile and
   limitations.
4. Run the full offline quality gates and strict OpenSpec validation before archival.

No deployed database, API, provider configuration, or durable migration is required.
Rollback disables the new command and removes the new task/runner code before release;
already-published contract schemas and canonical reports are retained rather than
rewritten. A failed benchmark run is a reportable evaluation outcome, not an authority
to retry an external effect.

## Open Questions

- None block the core proposal. The exact task IDs and oracle weights will be reviewed
  with the seed-suite manifest, provided they preserve the required 12-task category
  coverage and all hard-gate semantics above.
