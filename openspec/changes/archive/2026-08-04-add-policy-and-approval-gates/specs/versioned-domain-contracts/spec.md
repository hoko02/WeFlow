## MODIFIED Requirements

### Requirement: Canonical versioned domain schemas exist
WeFlow SHALL maintain language-neutral JSON Schema files under a versioned contract
directory. Each boundary object SHALL declare a stable schema identifier and
`schema_version`. Compatible v1 schemas SHALL cover retained boundary objects plus
ContextManifest, AgentAction, ToolRequest, ToolResult, ResponseCandidate,
VerifierOutcome, CapabilityGrant, PolicyDecision, AuthorizationBinding,
ApprovalRequest, ApprovalDecision, OutboundDeliveryIntent,
OutboundDeliveryObservation, and OutboundDeliveryCompletion. Each investigation and
authorization boundary SHALL have stable schema identity/version, tenant/Case/revision
linkage where applicable, forbid undeclared/raw fields, and validate in Python and
TypeScript.

#### Scenario: A valid contract fixture is consumed cross-language
- **WHEN** a valid `v1` fixture for each supported boundary object is validated by the
  Python and TypeScript contract packages
- **THEN** both packages SHALL accept the fixture under the same schema identifier and
  version

#### Scenario: A required version or schema identity is absent
- **WHEN** a boundary payload omits its declared schema identity or `schema_version`
- **THEN** both contract packages SHALL reject the payload with a deterministic
  validation result

#### Scenario: New Agent boundary fixtures validate cross-language
- **WHEN** valid and invalid replay Agent fixtures are consumed by both contract
  packages
- **THEN** both SHALL agree on acceptance and rejection while retained v1 fixtures
  remain valid

#### Scenario: New authorization and delivery fixtures validate cross-language
- **WHEN** valid and invalid Capability, Policy, AuthorizationBinding, approval, and
  outbound-delivery fixtures are consumed by both contract packages
- **THEN** both SHALL agree on acceptance and rejection while all retained v1 fixtures
  remain valid

### Requirement: Policy and approval bindings cannot be silently reused
PolicyDecision, CapabilityGrant, AuthorizationBinding, ApprovalRequest, and ApprovalDecision contracts SHALL bind their decision context to tenant, Case, Case
revision, workflow/checkpoint, requested action/resource/data classification, current
candidate hash, ordered evidence hashes, policy version/hash, capability grant
version/hash/status, creation time, and expiry where applicable. An approval decision
SHALL reference the approval request and exact authorization binding it decides.
Contract validation utilities SHALL classify an expired, revoked, foreign,
role/scope-mismatched, candidate/evidence/policy/grant-mismatched, or revision/
checkpoint-mismatched approval as not authorized for a later action.

#### Scenario: An approval becomes stale after a revision changes
- **WHEN** an approval decision bound to one Case revision or evidence hash is evaluated
  against a newer revision or different evidence hash
- **THEN** the validation utility SHALL classify the approval as stale and not
  authorized, and SHALL NOT emit a completion or external-write authorization result

#### Scenario: A policy or Capability Grant changes after approval
- **WHEN** an approval decision is evaluated with a different policy hash/version,
  Capability Grant hash/version/status, action, resource, data classification, or
  authorization binding
- **THEN** the validation utility SHALL classify it as unauthorized before a delivery
  intent can be created

## ADDED Requirements

### Requirement: Outbound delivery contracts are distinct, safe, and recoverable
WeFlow SHALL maintain OutboundDeliveryIntent, OutboundDeliveryObservation, and
OutboundDeliveryCompletion as distinct immutable tenant-scoped contracts rather
than aliases of ticket side-effect contracts. An intent SHALL bind Case/revision,
workflow/checkpoint, channel/conversation resource, candidate hash, authorization
binding hash, natural key, idempotency key, and safe evidence references. An
observation and completion SHALL reference that intent and expose only safe local
outcome identity/version/hash metadata; they SHALL represent unknown/conflicting
outcomes without representing a customer-success assertion.

#### Scenario: A valid fixture delivery recovery chain validates
- **WHEN** a fixture records one delivery intent, an unknown or present observation,
  and a reconciled completion for the same natural/idempotency key
- **THEN** both contract packages SHALL preserve the chain and reject a duplicate intent
  or an unauthorized completion

#### Scenario: A delivery contract contains raw or foreign authority data
- **WHEN** a delivery fixture contains raw message text, secret/credential data, a
  foreign tenant, mismatched binding, or detached intent reference
- **THEN** contract validation SHALL reject it before it can authorize or report a
  delivery
