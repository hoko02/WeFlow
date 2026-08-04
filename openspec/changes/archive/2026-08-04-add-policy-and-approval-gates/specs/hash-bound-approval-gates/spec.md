## ADDED Requirements

### Requirement: Approval requests are control-created and bound to one authorization profile
Only the deterministic control kernel SHALL create an append-only approval request after
an explicit Change 4 continuation activation from `RESPONSE_READY` and a matching
allow policy decision. The request SHALL reference a canonical authorization binding
for tenant, Case, revision, workflow/checkpoint, candidate hash, ordered evidence
hashes, policy decision/version/hash, Capability Grant/version/hash, named fixture
delivery resource, and expiry. It SHALL not contain raw candidate content or accept
caller-selected tenant, role, candidate, evidence, policy, grant, state, or expiry.

#### Scenario: A verified candidate receives one approval request
- **WHEN** the named fixture has a matching verified candidate and current allow policy
  decision
- **THEN** the kernel SHALL persist one stable approval request and enter
  `AWAITING_APPROVAL` without delivering content

#### Scenario: A request is attempted without a valid authorization profile
- **WHEN** the policy is denied, the continuation is absent, or any required binding is
  missing or inconsistent
- **THEN** the kernel SHALL not create an approval request or transition to
  `AWAITING_APPROVAL`

### Requirement: Approval decisions derive tenant and role server-side
The approval decision API SHALL derive effective tenant and fixture-defined operator
role from the synthetic actor identity. It SHALL accept only an allowlisted approve or
reject value, immutable request identity, and expected workflow version; duplicate
submissions with identical content SHALL be idempotent and conflicting or stale
submissions SHALL fail closed. A decision SHALL be append-only and reference the exact
approval request and authorization binding.

#### Scenario: A scoped fixture approver accepts a current request
- **WHEN** a current tenant-matched operator with the required fixture role approves a
  request at its expected workflow version
- **THEN** the kernel SHALL persist one hash-bound approval decision and no delivery
  effect until the separate delivery gate runs

#### Scenario: A foreign or unprivileged actor submits a decision
- **WHEN** the actor maps to another tenant, lacks the approver role, or supplies a
  caller-selected role or target state
- **THEN** the API SHALL return a safe denial without revealing a foreign request or
  appending a decision, transition, intent, or effect

### Requirement: Stale approval is never usable for delivery
Immediately before delivery intent persistence, the control kernel SHALL revalidate the
approval decision against the current Case revision, workflow checkpoint/version,
candidate hash, ordered evidence hashes, policy hash/version, Capability Grant
hash/version/status, resource scope, data classification, and expiry. A rejection,
expiry, revocation, or any mismatch SHALL invalidate authorization and lead only to an
allowlisted safe non-success outcome.

#### Scenario: Candidate, evidence, policy, or grant changes after approval
- **WHEN** an otherwise approved request no longer matches any bound authorization
  material
- **THEN** delivery SHALL be denied with zero intent, adapter execution, or
  `DELIVERY_RECORDED` transition

#### Scenario: An approval expires before delivery recovery
- **WHEN** a worker restarts after an approval decision but after its expiry
- **THEN** recovery SHALL not resume delivery and SHALL preserve append-only approval
  facts without creating an effect
