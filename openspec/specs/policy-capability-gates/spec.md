# policy-capability-gates Specification

## Purpose
Define deterministic fixture-owned Capability Grants and default-deny policy authorization.

## Requirements

### Requirement: Fixture-owned Capability Grants are scoped, short-lived, and fail closed
Only deterministic fixture setup or the control kernel SHALL issue, revoke, or expire a
tenant-scoped Capability Grant. A grant SHALL bind one synthetic subject to allowlisted
`approval.request`, `approval.decide`, or `outbound_delivery.execute` action scope,
the named fixture resource scope, permitted data classifications, issuance/expiry, a
stable version, and a canonical hash. An API caller, Agent, replay transcript, or
request body SHALL NOT choose a tenant, role, scope, grant status, or grant hash.

#### Scenario: An active scoped grant authorizes policy evaluation
- **WHEN** the named API-503 fixture presents a current grant for the effective tenant,
  synthetic subject, action, resource, and data classification
- **THEN** the deterministic policy evaluator SHALL be able to consider the request
  without treating the grant itself as an approval or delivery authorization

#### Scenario: A missing, foreign, expired, or revoked grant is supplied
- **WHEN** a requested approval or delivery action has no matching current fixture-owned
  grant
- **THEN** the evaluator SHALL deny it with a redacted stable reason and append no
  approval, delivery intent, state transition, or effect

### Requirement: Policy decisions are deterministic, content-addressed, and default-deny
The Policy Engine SHALL evaluate a canonical input containing the effective tenant,
server-derived subject/role, requested action, fixture resource, data classification,
remaining budget, current Case/revision/workflow/checkpoint, candidate hash, ordered
evidence hashes, policy version, and Capability Grant hash. It SHALL persist one
append-only, content-addressed allow/deny `PolicyDecision` with a stable reason code;
an unspecified rule or malformed input SHALL deny.

#### Scenario: The named fixture satisfies the outbound policy
- **WHEN** all fixture-defined tenant, role, grant, resource, classification, budget,
  candidate, and evidence checks match
- **THEN** repeated evaluation SHALL produce the same allow decision identity and
  policy-decision hash without an effect

#### Scenario: Unsafe classification, budget, or instruction evidence reaches policy
- **WHEN** fixture input is classified as secret, raw/private, untrusted instruction,
  over-budget, or otherwise not allowlisted for the requested action
- **THEN** the Policy Engine SHALL produce a deny decision and SHALL not create an
  approval request, delivery intent, or customer-success claim

### Requirement: Authorization observations disclose only safe binding metadata
Policy and Capability facts SHALL expose only stable identifiers, versions, hashes,
allow/deny status, safe reason codes, and redacted classifications. They SHALL NOT
persist or expose raw candidate body, prompt, private fixture payload, credential,
unrestricted tool output, or an asserted role supplied by a caller.

#### Scenario: A denied policy decision is inspected
- **WHEN** a tenant-scoped observation or acceptance report includes a denied policy
  decision
- **THEN** it SHALL contain only safe metadata and SHALL not disclose protected content
  or foreign-tenant existence
