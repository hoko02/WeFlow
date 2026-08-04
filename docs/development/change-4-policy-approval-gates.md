# Change 4 Policy and Approval Gates Development Guide

`add-policy-and-approval-gates` is the narrow, fixture-only continuation after the
archived Replay investigation change. It is applied and locally verified; OpenSpec
sync/archive remains a separate finalization action.

## Supported vertical slice

The only supported path is `api-503-policy-approval-delivery`. It starts with the
existing deterministic API-503 replay result and stays entirely in local SQLite:

```text
TICKET_READY -> INVESTIGATING -> RESPONSE_READY
RESPONSE_READY --explicit fixture activation--> AWAITING_APPROVAL
AWAITING_APPROVAL --current approved binding--> DELIVERING
DELIVERING --local adapter completion--> DELIVERY_RECORDED
```

`RESPONSE_READY` remains inert during ordinary recovery. The explicit continuation is
control-kernel-only; there is no public route that activates policy, selects a grant,
selects a delivery resource, or changes a workflow target state.

`DELIVERY_RECORDED` means only that the named fixture-local adapter durably recorded one
local outcome. It is not a network request, customer receipt, incident resolution,
Case completion, or general outbound-delivery capability.

## Hard authorization boundary

The control kernel creates immutable, content-addressed records for one tenant, Case
revision, workflow/checkpoint, candidate hash, ordered evidence hashes, policy version
and hash, scoped Capability Grant, resource, data classification, budget, and expiry.
The Policy evaluator is default-deny. It rejects missing/foreign/expired/revoked grants,
wrong roles/scopes/resources, unsafe classifications, malformed expiry, and exhausted
budgets with stable redacted reason codes.

The synthetic actor header can select an allowlisted fixture actor ID only. The server
derives its tenant and role. Approval APIs reject request bodies containing tenant,
role, grant, policy, candidate, evidence, resource, target state, expiry, or delivery
fields.

The approval decision body has exactly these fields:

```json
{
  "approval_request_id": "approval_request_...",
  "decision": "approve",
  "expected_workflow_version": 9
}
```

The only accepted decision values are `approve` and `reject`. A matching duplicate is
idempotent; a conflicting duplicate, stale version, foreign actor, or wrong role fails
closed. Read routes are tenant-scoped and make foreign and absent workflows
indistinguishable.

| Route | Scope | Safe result |
| --- | --- | --- |
| `GET /v1/cases/{case_id}/workflow/approval` | Tenant derived from actor | Redacted authorization/approval facts, or `404 workflow_not_found`. |
| `POST /v1/cases/{case_id}/workflow/approval/decisions` | Tenant and approver role server-derived | Accepted/deduplicated projection, or safe `403`/`404`/`409`/`422`. |
| `GET /v1/cases/{case_id}/workflow/delivery` | Tenant derived from actor | Local-adapter metadata only; never a customer-success assertion. |

## Fixture-local delivery and recovery

The named adapter has no HTTP client, credentials, provider configuration, enterprise
connector, or customer-success behavior. It persists a separate
`intent -> reconcile -> execute -> observe -> complete` chain with stable natural and
idempotency keys. Its records are distinct from Change 2 ticket SideEffects.

Recovery covers interruptions after policy, approval request, approval decision,
delivery intent, execute, lost response, observation, completion, and final transition.
Unknown/conflicting local observations enter `NEEDS_RECONCILIATION`; the adapter does
not blindly resend. A revoked grant or stale authorization leads to a safe non-success
state with zero delivery intent and zero local delivery record.

## Local verification

```powershell
python scripts/dev.py check
python scripts/dev.py contracts
python scripts/dev.py policy-approval-acceptance --output reports/change-4-acceptance.json
python scripts/dev.py test
```

The acceptance report runs two equal baselines, all nine declared interruption points,
the unknown-outcome reconciliation boundary, and a revoked-grant denial. It records only redacted IDs/counts/state, fixture-local
flags, delivery effect counts, and explicit Node/Docker limitations.

The Business Simulator can run the same vertical slice without an existing store:

```powershell
uv run --package weflow-business-simulator python -m weflow_business_simulator.main `
  --policy-approval-fixture api-503-policy-approval-delivery
```

## Capability support matrix

| Capability | Status |
| --- | --- |
| Replay investigation and verified `RESPONSE_READY` | Implemented and retained from Change 3. |
| Explicit fixture continuation | Implemented; historical `RESPONSE_READY` recovery remains inert. |
| Scoped Capability Grant and default-deny policy | Implemented for the one named synthetic fixture. |
| Hash-bound approval request/decision | Implemented, append-only, tenant/role-derived, and idempotent. |
| Fixture-local outbound delivery | Implemented with local SQLite reconciliation and at-most-one record. |
| Real approval service or customer-facing outbound delivery | Disabled and unimplemented. |
| External writes, live providers, credentials, enterprise connectors | Disabled and unimplemented. |
| Customer receipt, resolution, completion, or knowledge publication | Disabled and unimplemented. |
| Multi-Agent collaboration | Disabled and unimplemented. |

## Environment limits and next gate

Core Change 4 acceptance needs neither Node nor Docker. Node is still required for the
TypeScript contract and Web Console checks. Docker is optional and unavailable on the
current verification workstation, so Temporal/service-boundary behavior is not
live-verified. No network, model credential, enterprise credential, or live connector
is used by this change.

A future OpenSpec change is required before any real approval provider or external
write. It must define real identity and credential ownership, provider-specific intent
reconciliation, durable operator authorization lifecycle, independent evidence/audit
retention, rollout/rollback controls, live safety tests, and an explicit prohibition on
claiming customer resolution from an adapter acknowledgement alone.