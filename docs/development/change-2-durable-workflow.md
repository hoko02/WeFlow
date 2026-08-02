# Change 2 Durable Support Workflow Development Guide

Change 2 implements the smallest durable control path after the synthetic Change 1
Case intake. It is deliberately an offline, fixture-local reliability slice. It can
record and recover a local ticket handoff; it cannot investigate or resolve a customer
incident.

## Scope and safety boundary

Implemented in this change:

- Compatible `v1` contracts for workflow projections, checkpoints, commands,
  synthetic SLA policies, and local effect evidence.
- Additive SQLite workflow-journal tables with append-only guards, source rebuild,
  content-addressed linked snapshots, and one internal-only Case-state event port.
- A driver-neutral state reducer for `RECEIVED`, `TICKET_READY`, `PAUSED`,
  `WAITING_FOR_OPERATOR`, `NEEDS_RECONCILIATION`, and `CANCELLED`.
- Stable workflow activation by tenant/Case/revision/definition, immutable
  checkpoints, expected-versioned pause/resume/cancel commands, and a fixture clock.
- One deterministic local effect: ticket `find-or-create` followed by an
  expected-version `workflow-handoff`, both guarded by
  `intent → reconcile → execute → observe → complete` source facts.
- Offline recovery scans, named fault injection, narrow tenant-derived workflow
  observation/command routes, fixture-only simulator support, and an optional
  loopback-only Temporal service-boundary driver.

Not implemented:

- Agent/model invocation, prompt/context construction, investigation, CRM,
  monitoring, knowledge access, or customer enrichment.
- Approval, response candidate, outbound delivery, knowledge candidate, real
  provider, real ticketing API, Tencent/WeCom adapter, credential use, or external
  write executor.
- `RESPONSE_READY`, `RESOLVED`, `COMPLETED`, or any customer-success assertion.

`TICKET_READY` is a bounded local handoff fact only. It does not mean that a support
issue was diagnosed, fixed, communicated, or resolved.

## Local setup and verification

```powershell
uv sync --all-packages --all-groups
pnpm install --frozen-lockfile

python scripts/dev.py check
python scripts/dev.py contracts
python scripts/dev.py durable-workflow-acceptance --output reports/change-2-acceptance.json
python scripts/dev.py test
```

The Change 2 acceptance command is offline. It uses temporary SQLite stores, checked-in
fixtures, and an injected clock. It requires no network, Docker, model credential,
enterprise credential, customer data, or real connector.

## State machine and control ownership

Only deterministic workflow code can append a Change 2 Case-state event. There is no
HTTP route for generic Case mutation, event append, ticket mutation, approval, or
delivery.

| Current state | Durable fact or command | Next state | Meaning |
| --- | --- | --- | --- |
| `RECEIVED` | local ticket handoff completion | `TICKET_READY` | Fixture-local handoff known; not resolution. |
| `RECEIVED`, `TICKET_READY`, `WAITING_FOR_OPERATOR` | pause | `PAUSED` | Work stops; the prior safe state is checkpointed. |
| `PAUSED` | resume | checkpointed safe state | Continues only from the recorded state. |
| active state without unresolved effect | cancel | `CANCELLED` | Stops local control work. |
| unfinished active/paused state | synthetic SLA expiry | `WAITING_FOR_OPERATOR` | Local operator attention is required. |
| non-terminal state with unknown/conflicting effect | reconciliation required | `NEEDS_RECONCILIATION` | No blind retry or success claim. |
| `NEEDS_RECONCILIATION` | known reconciliation result | checkpointed safe state | Resumes only from source evidence. |

All other transitions, including resolution/completion states, fail closed. A cancel
command never bypasses an unresolved effect; it remains/reaches
`NEEDS_RECONCILIATION` until the local effect can be reconciled.

## Journal, recovery, and snapshot semantics

The Change 1 Case ledger remains the source for intake, Cases, revisions, and the
first three events. Change 2 adds immutable activation, run, command, checkpoint, SLA,
intent, observation, completion, and fixture-ticket source rows. Mutable workflow and
Case projections are rebuilt from those facts.

Workflow identity is derived from:

```text
(tenant_id, case_id, case_revision_id, workflow_definition_version)
```

An exact inbound retry cannot create a second activation, checkpoint chain, ticket
intent, or local ticket operation. A command is persisted before its transition. On a
fresh worker, recovery applies an uncheckpointed command against exactly its recorded
workflow version; duplicate command IDs return the existing result instead of creating
another transition.

`SQLiteDurableWorkflow.export_snapshot()` creates a content-addressed workflow snapshot
that embeds the unchanged Change 1 ledger snapshot and its hash. Restore is allowed
only into a fresh store, validates the journal, and replays workflow-originated Case
events from checkpoints. A legacy Change 1 ledger-only snapshot restores without
creating workflow work until an explicit recovery scan activates eligible `RECEIVED`
Cases.

## Fixture-local effect protocol

The ticket simulator is not a provider or external executor. It has no network client
and stores only synthetic identifiers, hashes, natural keys, and expected versions.

For each operation, the workflow persists a stable idempotency key and follows:

```text
intent recorded
  -> reconcile natural key/idempotency key
  -> execute only if absent
  -> observe and validate ticket identity/version
  -> persist completion
```

The local natural key is `tenant_id:case_id:case_revision_id`. The only allowed
operations are `find-or-create` and `workflow-handoff`. A lost response is reconciled
from the operation natural key before any retry. Unknown, stale-version, and conflicting
results move the workflow to `NEEDS_RECONCILIATION`; they never produce a success claim.

## Fault profiles and recovery operations

The deterministic profiles are:

- `activation`
- `checkpoint`
- `intent`
- `reconcile`
- `execute`
- `lost-response`
- `observation`
- `completion`
- `reconciliation-timeout`

Use a new `SQLiteCaseLedger` and `SQLiteDurableWorkflow` over the same store, then call
`recover_all()` or `recover_workflow(tenant_id, workflow_id)`. The acceptance command
does this for every declared interruption boundary and requires exactly two local ticket
operations after recovery: one create/find result and one handoff update.

## Narrow local API

All routes derive the effective tenant from `X-WeFlow-Synthetic-Actor`. Bodies cannot
choose a tenant, Case state, event type, ticket identifier, deadline, raw metadata, or
provider data.

| Route | Purpose | Safe outcomes |
| --- | --- | --- |
| `GET /v1/cases/{case_id}/workflow` | Tenant-scoped workflow projection. | `200`, or indistinguishable `404 workflow_not_found`. |
| `GET /v1/cases/{case_id}/workflow/checkpoints` | Canonical checkpoint history. | `200`, or indistinguishable `404`. |
| `POST /v1/cases/{case_id}/workflow/commands` | `pause`, `resume`, or `cancel` with `command_id` and expected version. | `200`, safe `409`, `422`, or `404`. |
| `GET /foundation/capabilities` | Capability truth. | Durable local workflow true; business workflow and external writes false. |

The command body has exactly these fields:

```json
{
  "command_id": "pause-fixture-001",
  "command_type": "pause",
  "expected_workflow_version": 0
}
```

Foreign and absent workflow reads both return `workflow_not_found`. Invalid data is not
echoed in errors.

## Service-boundary mode

The optional Temporal driver is an orchestration boundary only. It uses the same SQLite
journal/reducer, a fixed task queue, a bounded activity timeout, and only loopback
Temporal targets (`127.0.0.1`, `localhost`, or `::1`). It does not make Temporal history
the Case audit source and does not enable an external effect.

Run it only after the local Compose dependencies are intentionally started:

```powershell
python scripts/dev.py compose up
python scripts/dev.py up --mode service-boundary
uv run --package weflow-control-worker python -m weflow_control_worker.main --run-once
```

Docker/service-boundary evidence is optional in this change. A workstation without
Docker must report an explicit skip or unavailable condition, not a successful live
verification.

## Capability support matrix

| Capability | Change 2 status |
| --- | --- |
| Fixture-backed synthetic intake | Implemented from Change 1. |
| Durable local state/checkpoint/SLA/recovery | Implemented, offline and deterministic. |
| Fixture-local ticket handoff | Implemented; not an external write. |
| Temporal service-boundary driver | Implemented as an opt-in local boundary; live Docker verification remains environment-dependent. |
| Agent/model/provider | Disabled and unimplemented. |
| Approval/outbound delivery | Disabled and unimplemented. |
| Real enterprise connector/external write | Disabled and unimplemented. |
| Customer investigation or resolution | Unimplemented. |

## Next gate

The next change may introduce a bounded investigation Agent only through a new
OpenSpec proposal. It must preserve this journal/state-machine ownership, fixture-only
replay, tenant isolation, no-duplicate effect protocol, and the absence of approval or
external delivery until those capabilities receive their own explicitly verified
change.
