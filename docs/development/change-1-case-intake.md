# Change 1 Synthetic Case Intake Development Guide

Change 1 implements the smallest verifiable business record slice for the API-503 support scenario. It accepts only checked-in synthetic IM envelopes, derives a tenant from a fixture-only actor header, creates an immutable Case revision and three ledger events, and exposes tenant-scoped reads. It does not resolve an incident or contact a real customer.

## Scope and safety boundary

Implemented:

- Canonical `v1` schemas for `InboundMessageEvent` and `CaseProjection`.
- A deterministic SQLite Case ledger with immutable source records and a derived projection.
- Exact retry deduplication, conflicting replay rejection, and contiguous conversation-sequence enforcement.
- Fixture-only synthetic IM intake and tenant-scoped Case, revision, and event reads.
- Content-addressed single-tenant snapshot export and fresh-store restore.
- A local capability report that declares only `synthetic_case_intake_implemented=true`.

Not implemented:

- Real Tencent/WeCom, CRM, ticketing, delivery, customer lookup, model, workflow, approval, or external-write behavior.
- Any claim that an API-503 incident was investigated, fixed, replied to, or resolved.
- Generic Case mutation, append-event, state-transition, reset, or cross-tenant administrative routes.

The runtime accepts no raw message body or prompt. Tracked fixtures contain opaque synthetic identifiers and content hashes only. A request field not allowed by the inbound schema is rejected with an allowlisted reason code and is never echoed.

## Local setup and verification

```powershell
uv sync --all-packages --all-groups
pnpm install --frozen-lockfile

python scripts/dev.py check
python scripts/dev.py contracts
python scripts/dev.py case-intake-acceptance --output reports/change-1-acceptance.json
python scripts/dev.py test
```

The acceptance command is offline. It uses temporary SQLite stores and the checked-in fixture corpus; it requires no Docker, network, model credential, or enterprise credential. The optional report path must be repository-relative and under `reports/`.

## Narrow API surface

All routes are loopback-only through the local Platform API. The only synthetic actor identity input is the `X-WeFlow-Synthetic-Actor` request header. The registry maps allowlisted synthetic actors to tenants; the payload's `tenant_id` must agree with that derived tenant.

| Route | Purpose | Safe outcomes |
| --- | --- | --- |
| `POST /v1/synthetic-im/intake` | Submit one canonical synthetic IM envelope. | `201 accepted`, `200 deduplicated`, or an allowlisted error. |
| `GET /v1/cases/{case_id}` | Read a tenant-scoped derived Case projection. | `200` or indistinguishable `404 case_not_found`. |
| `GET /v1/cases/{case_id}/revisions` | Read immutable Case revisions for the effective tenant. | `200`, `404`, or safe `503`. |
| `GET /v1/cases/{case_id}/events` | Read ordered ledger events for the effective tenant. | `200`, `404`, or safe `503`. |
| `GET /foundation/capabilities` | Report the narrow implemented capability. | Synthetic intake true; business workflow and external writes false. |

No route exposes a generic append, state change, reset, or administrative read path. Unknown actors and tenant mismatches return `tenant_identity_mismatch`. Foreign and absent Case reads intentionally produce the same `case_not_found` response.

## Fixture sequence and deterministic ledger behavior

The fixture corpus is under `fixtures/intake/`:

1. `api-503-first-delivery` creates one Case, revision `1`, and exactly these event types: `inbound.received.v1`, `case.revision-created.v1`, and `case.state-transitioned.v1`.
2. `api-503-duplicate-delivery` has the same delivery natural key and logical fingerprint, so it returns `deduplicated` without writing another source record.
3. `api-503-out-of-order` has a sequence gap and returns `inbound_out_of_order` without partial state.

The Business Simulator is fixture-only. Its adapter validates named fixture files, resolves the synthetic actor through the allowlist, prepares the in-process API request, and exports a tenant snapshot. It registers no enterprise integration or model tool.

The SQLite ledger is the source of truth. It validates the tenant claim before opening the atomic intake transaction, persists source records behind update/delete guards, and rebuilds the Case projection from immutable records on startup. A conflicting reuse of a delivery key returns `inbound_event_conflict`; a late or gapped sequence returns `inbound_out_of_order`.

## Snapshot semantics

`SQLiteCaseLedger.export_snapshot()` emits one tenant's source records plus a canonical `content_sha256`. Restore is allowed only into a fresh file path. Restore verifies the content hash, schema shape, tenant scope, source integrity, and reconstructed projection before it replaces the target. The acceptance command restores a snapshot, replays the original delivery, and compares deterministic results.

The report contains only fixture names, HTTP outcomes, source counts, the snapshot hash, and capability booleans. It does not include a Case identifier, actor identifier, customer identifier, sender identifier, raw content, prompt, or provider output.

## Next gate

Change 2 may add deterministic workflow routing only after it specifies revision creation rules, evidence requirements, approval gates, replay/fault acceptance criteria, and the unchanged no-external-write default. It must build on this ledger rather than grant state changes or permissions to a model.
