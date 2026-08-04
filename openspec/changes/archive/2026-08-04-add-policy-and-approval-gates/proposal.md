## Why

Change 3 safely stops at an evidence-bound `RESPONSE_READY` candidate. The next
verifiable increment must prove that a candidate cannot become an outbound effect until
deterministic, model-external capability, policy, and human-approval gates authorize
one fixture-local delivery; a candidate alone must never grant that authority.

## What Changes

- Add deterministic, short-lived, tenant-scoped Capability Grants and a default-deny
  Policy Engine for approval request, approval decision, and fixture delivery actions.
- Bind every policy decision, approval request, approval decision, and delivery intent
  to the current Case/revision/workflow checkpoint plus canonical candidate, ordered
  evidence, policy, and capability hashes. Changes, expiry, revocation, foreign scope,
  wrong role, unsafe data classification, or budget denial invalidate authorization.
- Add an append-only, tenant-derived human-approval API with fixture-defined operator
  roles. Request payloads cannot select tenant, role, candidate, evidence, policy, or
  target state.
- Extend the durable reducer from `RESPONSE_READY` through approval and a
  fixture-local, idempotent IM delivery record. Delivery uses its own durable
  intent/reconcile/execute/observe/complete facts and ends only at
  `DELIVERY_RECORDED`, never resolution or completion.
- Add deterministic privacy/secret and prompt-injection negative fixtures at the
  delivery-policy boundary; only redacted, content-addressed delivery metadata appears
  in observation, logs, and reports.
- Preserve offline SQLite/replay operation and add recovery, repeated-baseline,
  authorization-denial, and no-duplicate-delivery acceptance evidence.

**Non-goals:** live providers, network delivery, real WeCom/Tencent adapters or
credentials, real customer data, customer receipt or resolution claims, knowledge
publication, generic RBAC administration, and multi-Agent behavior remain disabled.

## Capabilities

### New Capabilities

- `policy-capability-gates`: Deterministic, tenant-scoped capability validation and
  default-deny policy decisions for approval and fixture delivery actions.
- `hash-bound-approval-gates`: Immutable approval requests and decisions tied to the
  exact candidate, evidence, policy, capability, operator role, and expiry.
- `fixture-outbound-delivery`: A redacted, fixture-local IM delivery adapter with
  durable idempotency and recovery semantics.

### Modified Capabilities

- `versioned-domain-contracts`: Add compatible authorization, approval-binding, and
  outbound-delivery contracts plus cross-language fixture coverage.
- `case-event-ledger`: Allow only the control kernel to append canonical approval and
  fixture-delivery workflow facts.
- `durable-support-workflow`: Add allowlisted approval and delivery state continuation,
  checkpoints, recovery, and safe non-success outcomes.
- `idempotent-side-effect-recovery`: Extend immutable intent/reconcile/execute/
  observe/complete requirements to the distinct fixture delivery effect without
  weakening ticket semantics.
- `local-platform-dependencies`: Require complete policy, approval, delivery, and
  recovery acceptance in offline SQLite mode without Docker, network, or credentials.
- `safe-provider-runtime-boundary`: Permit only the control-kernel-owned fixture
  approval/delivery path while keeping Agents, live providers, and real external writes
  unable to authorize or execute effects.

## Impact

- Affected code: shared JSON Schema/Python/TypeScript contracts; control-kernel state,
  journal, policy, approval, and delivery adapters; Platform API; Business Simulator;
  truthful capability diagnostics; fixtures, fault injection, and acceptance reports.
- Affected data: additive append-only policy, grant, approval, delivery-intent,
  observation, completion, checkpoint, and Case-event records linked by stable hashes.
- Affected security boundaries: synthetic actor identity is extended to a fixture-owned
  operator-role registry; all authorization is derived server-side and evaluated before
  an effect. The Replay Agent remains proposal-only.
- No new runtime dependency, service, credential, or live connector is introduced;
  Docker/service-boundary verification remains explicitly optional and unverified.
