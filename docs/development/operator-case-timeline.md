# Offline Operator Case Timeline Development Guide

This vertical slice makes the existing synthetic API-503 Case evidence inspectable. It
does not add a mutable Case store, an approval action, a workflow command, a Replay
control, or any live provider behavior.

## Fixed surface

- Snapshot contract: `contracts/jsonschema/v1/operator-case-snapshot.schema.json`
- Canonical fixture: `fixtures/contracts/v1/semantic/operator-case-snapshot.json`
- Retained acceptance: `reports/add-offline-operator-case-timeline-acceptance.json`
- Read API: `GET /v1/operator/cases/api-503.v1`
- Synthetic actor: `X-WeFlow-Synthetic-Actor: simulator-tenant-a`

The route accepts no report, tenant, Case, path, or version selector. Tenant identity is
derived from the allowlisted actor. Missing and foreign evidence both return
`operator_case_not_found`; failed integrity returns `operator_case_not_ready`; an
unknown actor is denied before the report reader runs.

## Source and evidence flow

The acceptance command creates two fresh temporary SQLite stores and invokes the
public API-503 simulator path. The snapshot builder consumes only public ledger,
workflow, simulator, and evidence exports. It links 48 retained evidence nodes and one
terminal verification-Replay result into a contiguous 49-entry timeline:

```text
intake -> case -> workflow -> investigation -> tools -> verification
       -> policy -> approval -> delivery (fixture-local) -> replay (verification-only)
```

Every entry carries a stable sequence, predecessor, phase, source identity/hash,
transition or observation, gate/recovery status, and safe reason code. The canonical
reader rejects duplicate JSON keys, unsafe paths or fields, detached hashes and
predecessors, source/count/order mismatches, failed gates presented as success, and any
live, customer-success, or caller-authority claim.

## Console behavior

The Vue console fetches the single fixed route and completely validates the response,
including browser-side hashes, before rendering. Its states are `loading`, `ready`,
`not-found`, `identity-denied`, and `integrity-not-ready`. The ready view shows bounded
identity, counts, roots, the full ordered timeline, and one selected source-linked
detail. It never renders unrestricted JSON, HTML, raw exceptions, customer resolution,
approval authority, or a Replay control.

`DELIVERY_RECORDED (fixture-local)` means only that the deterministic fixture-local
delivery record exists. It does not prove provider acknowledgement, customer receipt,
incident resolution, Case completion, or permission for another side effect.

## Verification

Run the canonical offline acceptance with:

```powershell
python scripts/dev.py operator-case-timeline-acceptance
```

The command runs two equal source-backed baselines, the fixed reader/API/render paths,
18 negative scenarios, and the Web Console production build. It verifies zero default
store or retained-report mutation, duplicate natural or idempotency identities,
network/model/provider invocation, external-write attempt, or unauthorized effect. A
candidate report is re-read through the canonical reader before an atomic replacement;
failure preserves the prior report.

For development, the focused checks are:

```powershell
uv run pytest tests/contracts/test_operator_case_snapshot_contracts.py tests/unit/test_operator_case.py tests/unit/test_operator_case_report.py tests/integration/test_operator_case_api.py tests/e2e/test_operator_case_timeline_acceptance.py
pnpm --filter @weflow/web-console test
pnpm --filter @weflow/web-console build
openspec validate add-offline-operator-case-timeline --type change --strict
```

## Limits and next gate

The slice remains offline, synthetic, report-backed, and verification-Replay-only.
Network, models, real credentials, providers, external writes, customer data and
outcomes, Case completion, arbitrary Case selection, and multi-Agent coordination are
disabled or unimplemented.

Interactive Replay or fault controls require a separate approved OpenSpec change. That
change must define a closed command contract, tenant/role authorization, immutable run
identity, bounded fixture/fault selection, deterministic state ownership, budgets,
idempotency, audit evidence, cancellation/recovery behavior, and proof that observation
cannot mutate the source Case or grant approval, workflow, retry, or external-write
authority.
