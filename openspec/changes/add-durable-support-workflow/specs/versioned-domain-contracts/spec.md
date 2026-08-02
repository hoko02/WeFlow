## MODIFIED Requirements

### Requirement: Canonical versioned domain schemas exist
WeFlow SHALL maintain language-neutral JSON Schema files under a versioned contract
directory. Each boundary object SHALL declare a stable schema identifier and
`schema_version`. The compatible initial version SHALL cover InboundMessageEvent, Case,
CaseRevision, CaseProjection, BusinessEvent, Artifact, EvidenceReference,
CapabilityGrant, PolicyDecision, ApprovalRequest, ApprovalDecision, ReplayRequest,
ReplayResult, EvaluationCase, EvaluationResult, ExternalWriteIntent,
WorkflowProjection, WorkflowCheckpoint, WorkflowCommand, SyntheticSlaPolicy,
SideEffectIntent, SideEffectObservation, and SideEffectCompletion.

#### Scenario: A valid contract fixture is consumed cross-language
- **WHEN** a valid `v1` fixture for each supported boundary object is validated by the
  Python and TypeScript contract packages
- **THEN** both packages SHALL accept the fixture under the same schema identifier and
  version

#### Scenario: A required version or schema identity is absent
- **WHEN** a boundary payload omits its declared schema identity or `schema_version`
- **THEN** both contract packages SHALL reject the payload with a deterministic
  validation result

## ADDED Requirements

### Requirement: Workflow control contracts are tenant-bound, immutable, and payload-safe
WorkflowProjection, WorkflowCheckpoint, WorkflowCommand, and SyntheticSlaPolicy SHALL
identify effective tenant, Case, CaseRevision, stable workflow identity/version, and
safe correlation/timing metadata. A checkpoint SHALL have a monotonic sequence and
canonical content hash. A command SHALL have a stable command identity, allowlisted
command type, and expected workflow version, and SHALL NOT contain a caller-selected
target state, tenant, raw customer content, secret, credential, provider configuration,
or unrestricted tool output.

#### Scenario: A valid workflow checkpoint and command validate cross-language
- **WHEN** a synthetic fixture contains a checkpoint, an allowlisted version-checked
  command, and a fixture-defined SLA policy with all required safe references
- **THEN** Python and TypeScript validators SHALL accept the same `v1` payloads without
  requiring model, provider, or customer data

#### Scenario: A workflow command attempts arbitrary authority
- **WHEN** a workflow command fixture supplies another tenant, a direct Case state,
  raw message content, credential-like data, an unallowlisted command type, or omits
  its expected workflow version
- **THEN** both validators SHALL reject it before it can authorize a transition or
  effect

### Requirement: Side-effect recovery contracts distinguish intent, observation, and completion
SideEffectIntent, SideEffectObservation, and SideEffectCompletion SHALL be distinct,
immutable tenant-scoped records. An intent SHALL carry the stable natural key,
idempotency key, intended-state hash, Case/revision, causal checkpoint, operation, and
safe evidence references. An observation and completion SHALL reference that intent and
record only safe outcome identity/version/hash metadata. The schemas SHALL represent an
unknown or conflicting observation without representing it as complete or authorized
for an external provider.

#### Scenario: An interrupted ticket operation is represented without duplication
- **WHEN** a fixture records one ticket intent, an unknown observation, and a later
  reconciled observation/completion for the same idempotency key
- **THEN** validation SHALL retain the phase order and identity references without
  producing a second intent or an external-write authorization

#### Scenario: A completion is detached from its intent or tenant
- **WHEN** an observation or completion has a missing intent reference, a different
  tenant/Case/revision, an invalid version, or raw provider output
- **THEN** contract validation SHALL reject the fixture as an invalid recovery boundary

### Requirement: Workflow contract evolution preserves existing v1 safety fixtures
The contract compatibility command SHALL validate the new workflow/recovery corpus
alongside every retained Change 0/1 valid, invalid, duplicate-delivery, out-of-order,
cross-tenant, and stale-approval fixture. New workflow fields SHALL be additive for
retained `v1` consumers; a required-field or semantic incompatibility MUST use a new
major-version contract directory.

#### Scenario: A workflow contract edit breaks a retained fixture
- **WHEN** a proposed `v1` workflow/recovery schema edit causes any retained valid
  fixture to fail in either language consumer
- **THEN** the compatibility check SHALL fail until the edit is compatible or is moved
  to a new major-version schema path

#### Scenario: Retained stale approval input is supplied to a workflow boundary
- **WHEN** the existing stale-approval fixture is evaluated alongside a Change 2
  workflow or side-effect record
- **THEN** validation SHALL keep it unauthorized and SHALL not convert it into a
  workflow command, completion, or external-write authorization
