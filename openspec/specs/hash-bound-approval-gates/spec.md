# hash-bound-approval-gates Specification

## Purpose
Define deterministic, hash-bound approval requests and decisions for the named fixture-only continuation.
## Requirements
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

### Requirement: Approval requests SHALL bind the exact private candidate and workflow state

An `ApprovalRequest` SHALL bind the candidate artifact hash, normalized candidate hash, customer-issue artifact hash, Case and immutable revision, active dual-surface binding, policy/capability decisions, workflow version, creation time, and expiry. For a model-assisted candidate it SHALL additionally bind the handler-authored assist request, Context Manifest, model invocation/observation, normalized action, provider/prompt/price profiles, ordered evidence and claim references, verifier result, and budget state. Its group-safe representation SHALL contain only request identity, unambiguous hash prefix, and expected version.

#### Scenario: Private human draft creates an approval request

- **WHEN** deterministic verification succeeds for a bound-handler `WF-DRAFT`
- **THEN** the system stores the full content-free human binding and returns only bounded preview plus group-safe approval metadata to the bound handler in C2C

#### Scenario: Private model candidate creates an approval request

- **WHEN** deterministic verification succeeds for the bound handler's current assist request and complete model/evidence provenance
- **THEN** the system stores the full content-free model binding and returns only bounded preview/evidence summary plus group-safe approval metadata to that handler in C2C

#### Scenario: Group member requests candidate plaintext

- **WHEN** a group command attempts to retrieve an approval preview, model evidence summary, or draft body
- **THEN** the request is denied without disclosing whether restricted content exists

### Requirement: Approval decisions SHALL require the linked group identity and exact current binding

An `ApprovalDecision` SHALL be accepted only when the group event author matches the `member_openid` side of the same active binding whose C2C `user_openid` either created the human candidate or authored the assist request for the model candidate, and every request-bound candidate/provenance hash, Case revision, policy/capability/profile, evidence, verifier, budget, workflow version, retention state, and expiry still matches. The robot, candidate, model, provider role, tool output, customer, or another user MUST NOT approve.

#### Scenario: Correct handler approves exact metadata

- **WHEN** the linked group identity submits the current request ID, hash prefix, and expected version for its private current candidate
- **THEN** exactly one content-free approval decision is recorded

#### Scenario: Different group member copies approval metadata

- **WHEN** any unbound member submits otherwise valid metadata
- **THEN** the command is rejected and final delivery remains unauthorized

#### Scenario: Model lineage changes after preview

- **WHEN** invocation, Context, evidence, verifier, budget, provider/profile, assist request, candidate, or workflow state no longer matches the approval request
- **THEN** the approval is stale and no final delivery intent or QQ transport attempt occurs

### Requirement: Changes SHALL invalidate approval authority atomically

Candidate replacement, rejection, expiry, Case revision change, handler-binding change, or workflow-version change SHALL invalidate all prior requests and decisions before any final write can begin.

#### Scenario: Candidate is edited after approval

- **WHEN** a replacement is accepted after a decision was recorded but before final execution
- **THEN** the decision cannot authorize delivery and a fresh approval request and decision are required
