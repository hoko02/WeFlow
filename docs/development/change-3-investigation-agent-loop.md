# Change 3 Bounded Replay Investigation Agent Development Guide

`add-investigation-agent-loop` is the smallest investigation increment after the
archived Change 2 durable ticket handoff. It is archived as
`2026-08-03-add-investigation-agent-loop` after local offline verification.

The only supported vertical slice is the named synthetic API-503 investigation. It
starts from the retained `TICKET_READY` workflow fact, produces redacted evidence
references and a response candidate, and can reach `RESPONSE_READY` only after the
deterministic verifier accepts the complete evidence chain.

## Scope and safety boundary

Implemented:

- Additive v1 contracts for `ContextManifest`, `AgentAction`, `ToolRequest`,
  `ToolResult`, `ResponseCandidate`, and `VerifierOutcome`, with Python and
  TypeScript validation plus valid/invalid/retained fixture corpora.
- One deterministic Replay Agent. Its complete action algebra is `read_crm`,
  `read_monitoring`, `read_knowledge`, `needs_information`, `needs_operator`, and
  `response_candidate`.
- Immutable investigation activation, agent-step, tool request/result, candidate, and
  verifier source facts linked to the prior `TICKET_READY` checkpoint.
- A reducer-owned `TICKET_READY -> INVESTIGATING -> RESPONSE_READY` continuation.
  The candidate verifier, not the Agent, authorizes the second transition.
- Exactly three fixture-local, tenant-scoped, read-only tools: CRM, monitoring, and
  knowledge. They return only synthetic redaction classifications, stable IDs, and
  content hashes.
- Deterministic action, tool, and no-progress budgets; stable durable step identities;
  recovery after action, tool-result, candidate, and verifier persistence.
- A tenant-scoped, read-only investigation observation route and a content-addressed
  investigation-only inspection snapshot. Neither includes the Change 1 ledger
  payload or unrestricted tool output.

Not implemented:

- Live model/provider initialization, model credentials, network clients, or a
  multi-Agent coordinator.
- Tool writes, ticket writes, approval creation, outbound delivery, knowledge
  publication, or customer-resolution/completion claims.
- Any API route that asks an Agent to mutate Case state, grant permission, or send a
  message.

`RESPONSE_READY` means a verifier accepted a synthetic response candidate and its
required evidence references. It does not mean that text was approved, delivered,
observed by a customer, or that an incident was resolved.

## Local verification

```powershell
uv sync --all-packages --all-groups
pnpm install --frozen-lockfile

python scripts/dev.py check
python scripts/dev.py contracts
python scripts/dev.py investigation-agent-acceptance --output reports/change-3-acceptance.json
python scripts/dev.py test
```

The acceptance command creates temporary SQLite stores, uses fixed clocks and the
checked-in `api-503-investigation` transcript, runs two equal baselines, and injects
interruptions after `agent-action`, `tool-result`, `candidate`, and `verifier`
persistence. A passing report proves:

- `RESPONSE_READY` has three ordered evidence hashes and one verified candidate;
- all four recovery paths have four Agent steps, three tool results, one candidate,
  and one verifier outcome;
- no duplicate tool result or `RESPONSE_READY` transition is reported;
- no Docker, network, model credential, or enterprise credential is required.

The Business Simulator can run the same vertical slice without a pre-existing store:

```powershell
uv run --package weflow-business-simulator python -m weflow_business_simulator.main `
  --investigation-fixture api-503-investigation
```

The Agent Runtime command intentionally needs a tenant, Case, and existing local
`TICKET_READY` workflow. It fails closed when any scope is omitted:

```powershell
uv run --package weflow-agent-runtime python -m weflow_agent_runtime.main `
  --investigation-fixture api-503-investigation `
  --tenant-id tenant-alpha --case-id <existing-case-id> --store <local-store.sqlite3>
```

## Control ownership and state continuation

| Current state | Durable prerequisite | Next state | Authority |
| --- | --- | --- | --- |
| `TICKET_READY` | Valid immutable Context Manifest and investigation activation | `INVESTIGATING` | Control kernel only |
| `INVESTIGATING` | Complete ordered CRM, monitoring, knowledge evidence and a matching verified candidate | `RESPONSE_READY` | Deterministic verifier through control kernel |
| `INVESTIGATING` | `needs_information`, `needs_operator`, rejected candidate, no progress, or budget limit | `INVESTIGATING` | No success transition |

The Replay Agent has no target-state field and cannot call the control reducer directly.
Malformed actions, unknown fields, authority claims, foreign tenant links, unavailable
tools, and live-provider configuration fail before a workflow transition or external
effect. The retained Change 2 `TICKET_READY` behavior remains unchanged when no
investigation activation exists.

## Contracts, evidence, and tool gateway

The Context Compiler binds tenant, Case, revision, workflow, checkpoint, environment
snapshot hash, budgets, and evidence references. Each persisted action and tool record
links back to this manifest. The candidate binds the same identity chain, ordered
evidence hashes, a risk level, next step, and canonical candidate hash.

The fixture gateway has no HTTP client, credential, write method, approval adapter, or
delivery adapter. A successful read creates a `ToolRequest` plus `ToolResult` whose
only content reference is a synthetic `content_sha256`; raw CRM, monitoring, and
knowledge fixture bodies are neither loaded into prompts nor included in reports.

`SQLiteDurableWorkflow.export_investigation_inspection(tenant_id, case_id)` returns a
content-addressed, investigation-only inspection object. It is the safe snapshot for
reports and diagnostics. `export_snapshot()` remains the full journal-and-ledger
recovery snapshot and is not an observation payload.

## Narrow observation and diagnostics

All Platform API routes derive tenant scope from `X-WeFlow-Synthetic-Actor`.

| Route | Purpose | Safe outcomes |
| --- | --- | --- |
| `GET /v1/cases/{case_id}/workflow/investigation` | Redacted manifest, ordered action facts, evidence hashes, candidate, verifier outcome. | `200`, or indistinguishable `404 workflow_not_found`. |
| `GET /foundation/capabilities` | Capability truth. | Replay investigation and candidate verifier true; real provider, multi-Agent, writes, approval, delivery, and customer resolution false. |

The Web Console renders those capability flags as diagnostics only. It never displays a
candidate body, raw prompt, tool payload, credential, approval, or delivery control.

## Capability support matrix

| Capability | Change 3 status |
| --- | --- |
| Synthetic Case intake and durable local handoff | Implemented in Changes 1/2 and retained. |
| Single deterministic Replay investigation Agent | Implemented for the named API-503 fixture only. |
| Context Manifest and closed structured actions | Implemented and schema-validated. |
| CRM/monitoring/knowledge fixture reads | Implemented, tenant-scoped, read-only, redacted, and content-addressed. |
| Response candidate verifier and `RESPONSE_READY` | Implemented; not approval, delivery, or resolution. |
| Safe investigation inspection/report | Implemented; only IDs, state, hashes, counts, and redacted classifications. |
| Live provider or credentials | Disabled and denied. |
| Multi-Agent collaboration | Disabled and denied. |
| Real enterprise connector or external write | Disabled and denied. |
| Approval, outbound delivery, knowledge publication | Disabled and unimplemented. |
| Customer-success/resolution assertion | Disabled and unimplemented. |

## Verified environment limits

The core acceptance requires neither Docker nor Node. On the verified workstation,
Docker was unavailable, so service-boundary/Temporal behavior is not live-verified.
Node is installed and TypeScript contract plus Web Console checks run locally, but the
workspace-declared Node major version must still be verified on a conforming Node 24
environment before treating that front-end/toolchain combination as release evidence.

## Next-stage gate

A new OpenSpec change is required before enabling any policy or approval behavior. It
must retain the deterministic state/retry/effect owner, append-only Case/workflow/evidence
facts, tenant isolation, replay fixtures, and recovery baseline. The proposal must
introduce model-external capability/policy decisions, hash-bound approval invalidation,
and idempotent delivery intent/reconcile/execute/complete evidence. It must not enable
real external writes merely because a candidate reached `RESPONSE_READY`.