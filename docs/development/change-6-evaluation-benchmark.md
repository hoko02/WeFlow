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

Each task contains only safe task/oracle metadata and fixture/policy identity hashes.
It must not contain raw customer messages, prompts, unrestricted tool results,
credentials, caller-selected authority, or external-provider configuration.

The runner executes only existing deterministic fixture paths in temporary SQLite
stores. It evaluates hard gates before quality: tenant/reference integrity, Replay-only
mode, zero external writes, expected local-effect count, approval binding where
applicable, evidence lineage, and expected safe outcome. Any failed hard gate produces
`not_scored`; a weighted quality score can never offset it.

## Command and report

```powershell
python scripts/dev.py evaluation-benchmark-acceptance --output reports/change-6-evaluation-benchmark-core-acceptance.json
```

The command runs two equal offline baselines and emits a redacted report. It includes
the suite hash, per-task task/oracle hashes, named gate/dimension results, safe counts,
deterministic metrics, and explicit capability flags. It requires no network, Docker,
model key, enterprise credential, live provider, public API, or external-write adapter.

`fixture_delivery_recorded` is only a fixture-local adapter record. It does not mean a
network send, provider acknowledgement, customer receipt, incident resolution, Case
completion, or permission for another effect.

## Limitations and next gate

This core reports 12 deterministic synthetic tasks and `planned_live_runs=0`. It does
not establish the M1 completion target of 60 tasks, five repeated live runs, cost/P95
claims, an LLM judge, an Operator Console evaluation screen, live trace export, or
multi-Agent benefit. A future change may expand the corpus only after this suite remains
stable; live execution additionally requires provider, privacy, retention, rollout,
rollback, and independent safety controls.
