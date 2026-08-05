# Change 6 Evaluation Benchmark Core Development Guide

`add-evaluation-benchmark-core` defines the first reproducible measurement layer over
the fixture-local API-503 reliability path. It is an offline, Replay-only benchmark;
it is not a live-model evaluation, provider integration, customer delivery, or customer
resolution claim.

## Supported profile

The supported suite is `offline-seed.v1` under `evals/suites/`. It contains exactly 12
ordered, tenant-scoped tasks under `evals/tasks/`, covering intake acceptance,
deduplication and ordering, workflow/SLA behavior, investigation recovery, policy and
approval denial, fixture-local delivery recovery, and evidence-lineage tampering.

Each task declares `fixture_source_id`, a repository-relative `fixture_source_path`, the
canonical JSON SHA-256, and the equivalent identity/path/hash for
`evals/sources/offline-policy.v1.json`. The loader resolves fixture paths only below
`fixtures/` and policy paths only below `evals/sources/`; it rejects path escapes,
missing or non-object JSON, duplicate keys, foreign identity/tenant, policy mismatch,
and source-hash mutation before any SQLite task store is created. Task-local
`fixture.json` and `policy.json` mirrors are forbidden and have been removed.

Each public offline adapter receives the resolved task, resolved fixture source and one
fresh temporary SQLite path. It returns only a closed `BenchmarkObservation`: actual
safe tenant, state/outcome, evidence/approval status, tool count, local-effect count and
fixed offline capability flags. The runner has no suite-level result cache, does not
call underscore-prefixed acceptance helpers, and does not invent an outcome outside the
returned observation.

The runner evaluates hard gates before quality: tenant/reference integrity, Replay-only
mode, zero external writes, expected local-effect count, approval binding where
applicable, evidence lineage, and expected safe outcome. Any failed applicable gate
produces `not_scored`; a weighted quality score can never offset it.

## Runtime evidence chain

Every task attempt materializes and semantically validates this chain before the suite
can be accepted:

```text
resolved source hashes ? EvaluationTask + Oracle ? BenchmarkObservation
? EvaluationCase ? GraderResult + RunMetrics ? EvaluationResult
? EvaluationSuiteReport
```

`EvaluationCase.input_hash` is the resolved fixture source hash. `EvaluationResult`
links the task/oracle hashes, hard-gate result, grader, metrics, suite report ID and
report hash. `EvaluationSuiteReport.task_result_ids` contains the emitted
`EvaluationResult` IDs, never grader IDs. Python and TypeScript reject detached report
links, source mismatch, cross-task records, duplicate result IDs, incomplete capability
flags and a numeric score after a hard-gate failure.

## Command and report

```powershell
python scripts/dev.py evaluation-benchmark-acceptance --output reports/change-6-evaluation-benchmark-core-acceptance.json
```

The command runs two equal offline baselines and writes only after the complete semantic
chain validates. The redacted report retains safe source paths/hashes, observations,
EvaluationCase/GraderResult/RunMetrics/EvaluationResult records, result IDs, suite hash,
fixed metrics and explicit capability flags. It requires no network, Docker, model key,
enterprise credential, live provider, public API, or external-write adapter.

`fixture_delivery_recorded` is only a fixture-local adapter record. It does not mean a
network send, provider acknowledgement, customer receipt, incident resolution, Case
completion, or permission for another effect.

## Limitations and next gate

This core still reports only 12 deterministic synthetic tasks and
`planned_live_runs=0`. Source binding proves which checked-in offline inputs were used;
it does not turn deterministic oracle scores into live-model or customer-outcome
claims. It does not establish the M1 target of 60 tasks, five repeated live runs,
cost/P95 claims, an LLM judge, an Operator Console evaluation screen, live trace export,
or multi-Agent benefit.

A future change may expand the corpus only after this repaired suite remains stable.
Live execution additionally requires provider, privacy/redaction and retention,
tenant/role authorization, independent grading, cost/safety budgets, rollout, rollback
and live safety evidence. No report, replay result or provider acknowledgement alone can
claim customer receipt or resolution.
