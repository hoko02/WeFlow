# Offline Evaluation Report Console Development Guide

This vertical slice exposes the retained `offline-seed.v1` benchmark as a closed,
tenant-scoped, read-only snapshot and renders that snapshot in the local Vue console.
It does not rerun workflows, invoke a model, contact a provider, or perform an external
write.

## Fixed boundaries

- Canonical input: `reports/change-6-evaluation-benchmark-core-acceptance.json`
- API: `GET /v1/evaluations/offline-seed.v1`
- Synthetic observer header: `X-WeFlow-Synthetic-Actor: simulator-tenant-a`
- Acceptance output: `reports/add-offline-evaluation-report-console-acceptance.json`

The route accepts no report path, suite selector, or query parameter. Tenant identity is
derived from the allowlisted synthetic actor. A missing or foreign report returns the
same `404 evaluation_report_not_found` envelope. Unknown identity returns `403`, invalid
selectors return `422`, unsupported methods return `405`, and malformed or detached
evidence returns `503 evaluation_report_not_ready` without a partial snapshot.

The Platform API imports a reader protocol rather than benchmark internals. The reader
reloads the fixed report and current suite sources, rejects duplicate JSON keys and
unsafe paths, revalidates every retained EvaluationCase, GraderResult, RunMetrics, and
EvaluationResult link, then projects the closed `EvaluationSuiteSnapshot` contract.
Importing the API factory is side-effect free; the ASGI process entry point is
`weflow_platform_api.asgi:app`.

## Console behavior

The console validates the complete response before producing a render model. Its safe
states are `loading`, `ready`, `not-found`, `identity-denied`, and
`integrity-not-ready`. The ready view shows aggregate counts, content hashes, all 12
task summaries, one selected task, hard gates, scored dimensions, bounded observations,
and offline counters. It does not render unrestricted JSON or raw exceptions.

Latency, token use, cost, live-run variance, customer receipt, and incident resolution
are explicitly unavailable. Fixture-local delivery evidence is not a provider or
customer receipt.

## Local verification

Run from the repository root:

```powershell
python scripts/dev.py evaluation-console-acceptance
```

The command reads the canonical report twice, verifies byte-equivalent snapshots,
exercises the tenant/API and integrity matrices, runs the deterministic console checks
and production Vite build, and writes the acceptance report only after every check
passes. A failed run preserves any prior report.

To inspect the surface locally:

```powershell
python scripts/dev.py up --mode offline
python scripts/dev.py health
```

The console uses only loopback HTTP. Stop the local processes with
`python scripts/dev.py down`.

## Retained evidence and limitations

The accepted snapshot contains 12 passed tasks, zero failed tasks, and zero unscored
tasks. Its content identities are:

- Suite: `62683ba2880cd0ab9a96abc6f2f69cec6ca671c001b05de704f491afdd80be6b`
- Suite report: `a3ea07d5c88f8249de49006665630aa244720a531d3cc72ae4bef216ac6a1d11`
- Snapshot: `918a5959a6d5cb8046be8286b053391aceea9d7c65a2006724f8a1c59324c079`

These results are simulated and offline. They establish deterministic evidence
integrity and presentation only. Live models, real enterprise credentials, networked
providers, external writes, customer data, customer receipt/resolution, and multi-agent
coordination remain disabled. Enabling any of those capabilities requires a separate,
explicit OpenSpec change and its own acceptance evidence.
