## Context

Archived Change 3 produces one verified, evidence-bound `ResponseCandidate` and stops
at `RESPONSE_READY`. That state is deliberately not approval, delivery, customer
receipt, resolution, or completion. The current control kernel is the sole state
authority, but its actor registry derives only tenant identity, its approval contracts
do not bind policy/capability/role hashes, and its durable side-effect records are
ticket-specific. Change 4 adds one explicit, offline continuation for the named
API-503 fixture without changing the meaning of historical `RESPONSE_READY` replays.

The implementation remains local SQLite plus deterministic fixtures. Docker is not
available on the verification workstation; no result in this change may require Docker,
network access, a model key, enterprise credential, real WeCom/Tencent endpoint, or
real customer data.

## Goals / Non-Goals

**Goals:**

- Prove one verified candidate can produce at most one fixture-local IM delivery only
  after deterministic Capability, Policy, and human-approval gates all pass.
- Preserve tenant isolation, append-only Case/workflow facts, evidence lineage, stable
  idempotency, recovery, and repeated-run determinism.
- Bind authorization to exact Case/revision/workflow/checkpoint/candidate/evidence/
  policy/capability identities; expiry, revocation, or any binding mismatch denies
  delivery before an effect.
- Provide tenant-derived, fixture-role-bound approval observation/decision routes and
  redacted diagnostics that never expose candidate body, prompt, credentials, or raw
  fixture data.

**Non-Goals:**

- Live providers, real external writes, live approval systems, real WeCom/Tencent
  adapters, credentials, real customer data, generic RBAC administration, or a web
  approval console.
- Agent-issued grants, Agent approval, Agent delivery, Agent state selection, automatic
  policy changes, customer receipt, resolution, completion, knowledge publication, or
  multi-Agent coordination.
- General-purpose prompt-injection detection. This change tests only deterministic,
  fixture-classified unsafe instruction/secret/data-classification denials.

## Decisions

### 1. Use a deterministic, server-owned authorization chain

The control kernel SHALL create short-lived, fixture-owned Capability Grants and
evaluate a pure default-deny Policy Engine for `approval.request`, `approval.decide`,
and `outbound_delivery.execute`. The policy input is canonical and includes the
effective tenant, server-derived actor/role, action, resource scope, data
classification, remaining fixture budget, current checkpoint, and authorization
binding. Its append-only output has a stable decision identity, policy version, reason
code, and canonical hash.

The synthetic actor registry will be extended with a fixture-owned principal/role map;
the request header supplies only an actor identity and never an asserted tenant or
role. Grants are issued/revoked only by deterministic fixture setup/control code, not a
public API.

**Alternative considered:** accept an approval decision as the authorization source.
This is rejected because it cannot express grant expiry/revocation, scoped policy, or
default-deny behavior before the approval request and delivery effect.

### 2. Bind approval to an immutable authorization profile

Change 4 will add an `AuthorizationBinding`-style, content-addressed record that
contains the exact tenant, Case, revision, workflow/checkpoint, candidate hash, ordered
evidence hashes, policy decision hash/version, capability grant hash/version, delivery
resource, and expiry. `ApprovalRequest`, `ApprovalDecision`, and the delivery intent
all reference this binding hash. Existing v1 fixtures remain compatible; validators for
the Change 4 execution profile require every binding field and reject legacy or partial
approval records for an outbound action.

At decision time and again immediately before delivery intent persistence, the kernel
checks tenant, role, grant state/expiry, policy allow, current workflow version, and
every bound hash. Candidate, evidence, revision, policy, grant, or expiry changes make
an earlier approval unusable. Rejections and stale decisions are durable safe facts,
not privileges.

**Alternative considered:** add only optional fields to current approval schemas and
check an approval ID at delivery. This is rejected because an approval ID cannot prove
which security-relevant material was evaluated.

### 3. Add an explicit continuation rather than reinterpret old terminal replays

An archived Change 3 workflow stays at `RESPONSE_READY` unless a named Change 4
fixture/control action appends a durable policy-approval activation fact. After that
activation, only the control kernel may take these allowlisted transitions:

```text
RESPONSE_READY --policy allows request--> AWAITING_APPROVAL
AWAITING_APPROVAL --fresh valid approval + policy--> DELIVERING
DELIVERING --fixture delivery completion--> DELIVERY_RECORDED
DELIVERING --unknown/conflicting delivery result--> NEEDS_RECONCILIATION
AWAITING_APPROVAL --deny/reject/expiry/revocation--> WAITING_FOR_OPERATOR
```

`DELIVERY_RECORDED` is the bounded horizon for this increment: it records a local
adapter outcome only, never customer receipt, incident resolution, or Case completion.
The Agent has no state or authorization field. A missing activation, denied policy, or
stale approval produces no success transition and no effect.

**Alternative considered:** automatically recover every historical `RESPONSE_READY`
workflow into approval. This is rejected because it silently changes archived replay
semantics and could create new effects from old data.

### 4. Model fixture delivery as a distinct idempotent effect

The control kernel will add `OutboundDeliveryIntent`, `OutboundDeliveryObservation`,
and `OutboundDeliveryCompletion` records and tables rather than loosening the
ticket-specific `SideEffect*` contract. Their stable natural key is derived from tenant,
synthetic channel/conversation, Case/revision, candidate hash, and authorization
binding hash; their idempotency key is derived from the same immutable material.

The fixture-local IM adapter has only deterministic find/reconcile/execute behavior.
It emits safe identity/version/content-hash metadata; reports and observation APIs omit
the body, prompt, raw fixture payload, credentials, and unrestricted tool output.
Processing remains `persist intent -> reconcile natural key -> execute if absent ->
observe -> complete`. Unknown or conflicting outcomes enter reconciliation and do not
permit blind resend.

**Alternative considered:** generalize the existing ticket schema in place. This is
rejected because its effect kind and observation fields encode ticket semantics, and a
generalization would weaken retained Change 2 recovery guarantees.

### 5. Keep the API narrow and policy-checked at every write boundary

The Platform API will expose tenant-derived, read-only approval/delivery facts plus a
small decision endpoint. The decision endpoint accepts only an immutable request ID,
allowlisted approve/reject value, and expected workflow version; it derives the actor,
tenant, role, target binding, candidate, evidence, policy, and state from durable
records. Every write re-evaluates policy before appending a decision, intent, or
transition. Foreign/absent resources remain indistinguishable where existing APIs use
that pattern.

The Business Simulator provides the one API-503 authorization/delivery fixture,
deterministic clocks, grant expiry/revocation, policy-denial variants, and fault
profiles. Capability reports turn on only fixture approval and fixture outbound delivery
after acceptance passes; real-provider and real-external-write flags remain false.

### 6. Make negative paths and recovery first-class acceptance evidence

The acceptance runner will execute two equal baselines and fault/recovery variants
after policy decision, approval request, approval decision, delivery intent, execution,
lost response, observation, completion, and state-transition persistence. It reports
stable hashes/counts and proves exactly one fixture delivery in the happy path and zero
deliveries for all denied paths.

Deterministic negative fixtures cover cross-tenant actor, wrong role, absent/expired/
revoked grant, policy/data-classification/budget denial, unsafe instruction/secret
classification, rejected/expired approval, candidate/evidence/policy/grant mismatch,
duplicate decision, duplicate delivery, and unknown/conflicting delivery observation.

## Risks / Trade-offs

- **[Authorization profile expands contract surface]** → Keep the profile small,
  content-addressed, cross-language validated, and require it only for Change 4 actions
  while retained fixtures prove compatibility.
- **[Approval and delivery add many durable boundaries]** → Use append-only tables,
  fixed clocks, named fault points, and a single fixture before supporting another
  channel or live connector.
- **[State continuation could change old replay behavior]** → Require explicit,
  durable Change 4 activation; old `RESPONSE_READY` fixtures remain inert.
- **[Fixture delivery could be mistaken for production delivery]** → Use explicit
  capability flags, `fixture-local-im` naming, redacted reports, and forbid network/
  credential adapters at configuration and runtime boundaries.
- **[Prompt-injection scope may be overclaimed]** → Limit acceptance claims to the
  enumerated deterministic classified fixtures; do not claim general adversarial
  robustness.

## Migration Plan

1. Add schemas, fixtures, and Python/TypeScript compatibility checks without changing
   retained v1 acceptance results.
2. Apply additive SQLite tables, indexes, append-only triggers, and projection rebuild
   support. Existing ticket and investigation records remain untouched.
3. Register the Change 4 fixture policy, grants, roles, adapter, and explicit
   continuation activation. Existing `RESPONSE_READY` workflows receive no implicit
   activation or delivery.
4. Enable only the offline simulator/API acceptance path; capability reporting stays
   false until the acceptance baseline passes.
5. Roll back by disabling the Change 4 fixture activation/configuration. Durable facts
   are never deleted; pending/unknown delivery records recover or remain
   `NEEDS_RECONCILIATION`, never resend blindly.

## Open Questions

- None blocking this fixture-local increment. A future change must separately decide
  how authenticated production principals, real policy administration, and real
  delivery providers are introduced.
