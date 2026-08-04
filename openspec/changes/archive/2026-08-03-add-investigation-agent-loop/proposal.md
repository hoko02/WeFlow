## Why

Change 2 proves that WeFlow can durably own a synthetic Case through a local ticket
handoff, but it deliberately cannot investigate the API-503 incident or prepare a
customer-safe response. The next independently verifiable increment is a bounded
single-Agent investigation loop that consumes the durable workflow state, gathers only
fixture-local read evidence, and returns a structured response candidate without gaining
state, approval, delivery, or external-write authority.

## What Changes

- Add a deterministic replay-only single-Agent loop, immutable Context Manifest, and
  schema-validated structured actions with explicit terminal outcomes:
  `needs_information`, `needs_operator`, or `response_candidate`.
- Add a tenant-scoped, fixture-local Business Tool Gateway for CRM, monitoring, and
  knowledge reads. Tool results become redacted, content-addressed evidence references;
  the Agent never receives or persists raw customer payloads or unrestricted tool output.
- Add deterministic no-progress, duplicate-action, malformed-action, budget, tenant,
  evidence-completeness, and workflow-state gates. A deterministic verifier, not the
  Agent, may accept a response candidate and request the next allowed workflow
  transition to `RESPONSE_READY`.
- Extend the durable workflow from its bounded Change 2 handoff horizon through an
  allowlisted investigation/candidate path while preserving append-only journals,
  checkpoints, recovery, synthetic SLA behavior, and all no-duplicate-effect invariants.
- Add replay fixtures, negative security cases, fault/recovery coverage, cross-language
  contracts, offline acceptance evidence, and developer documentation for the new slice.

## Capabilities

### New Capabilities

- `bounded-investigation-agent-loop`: Replay-only single-Agent planning/execution with
  structured, non-authoritative outcomes and deterministic termination gates.
- `fixture-investigation-tool-gateway`: Tenant-scoped fixture-local CRM, monitoring,
  and knowledge reads that emit redacted, content-addressed evidence.
- `response-candidate-verification`: Deterministic validation of evidence-bound response
  candidates before the workflow may enter `RESPONSE_READY`.

### Modified Capabilities

- `durable-support-workflow`: Extend the allowlisted non-resolution state machine and
  checkpoint/recovery semantics for the Agent investigation and verified candidate path.
- `case-event-ledger`: Preserve append-only Case events while allowing only the
  control-kernel to record validated investigation/candidate workflow transitions.
- `versioned-domain-contracts`: Add compatible v1 contracts for context, Agent actions,
  tool requests/results, evidence, response candidates, and verifier outcomes.
- `safe-provider-runtime-boundary`: Permit only deterministic replay actions while
  preserving the fail-closed prohibition on live providers, external writes, and
  multi-agent coordination.
- `local-platform-dependencies`: Require offline deterministic Agent/tool replay,
  bounded fault profiles, and redacted diagnostic evidence.

## Impact

- Affected code boundaries: Agent Runtime, Control Kernel/Worker, Platform API workflow
  observation, Business Simulator, shared Python/TypeScript contracts, testkit,
  fixtures, reports, and the diagnostics console.
- Affected data boundaries: append-only Agent-step, tool, evidence, verifier, checkpoint,
  and workflow-transition facts linked to tenant, Case, revision, and correlation IDs.
- Affected interfaces: only loopback/testkit surfaces for workflow observation and
  synthetic replay control; no public generic mutation, approval, delivery, or provider
  API is introduced.
- Dependencies and safety: no network, Docker, model credential, enterprise credential,
  real connector, external-write executor, approval service, or multi-Agent runtime is
  enabled. The complete required acceptance path remains offline and deterministic.