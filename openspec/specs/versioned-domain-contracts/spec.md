# versioned-domain-contracts Specification

## Purpose
Define the versioned, language-neutral domain contracts and compatibility rules shared across WeFlow boundaries.
## Requirements
### Requirement: Canonical versioned domain schemas exist
WeFlow SHALL maintain language-neutral JSON Schema files under a versioned contract
directory. Each boundary object SHALL declare a stable schema identifier and
`schema_version`. Compatible v1 schemas SHALL cover retained boundary objects plus
ContextManifest, AgentAction, ToolRequest, ToolResult, ResponseCandidate,
VerifierOutcome, CapabilityGrant, PolicyDecision, AuthorizationBinding,
ApprovalRequest, ApprovalDecision, OutboundDeliveryIntent,
OutboundDeliveryObservation, OutboundDeliveryCompletion, Artifact,
EvidenceTrajectory, EvidenceReport, and TrajectoryReplayResult. Each investigation,
authorization, and evidence boundary SHALL have stable schema identity/version,
tenant/Case/revision linkage where applicable, forbid undeclared/raw fields, and
validate in Python and TypeScript.

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
#### Scenario: Evidence trajectory fixtures validate cross-language
- **WHEN** valid and invalid Artifact, EvidenceTrajectory, EvidenceReport, and
  TrajectoryReplayResult fixtures are consumed by both contract packages
- **THEN** both SHALL agree on acceptance and rejection while every retained v1 fixture
  remains valid

### Requirement: Case, event, artifact, and evidence invariants are representable
Every tenant-scoped contract SHALL contain `tenant_id`. A Case SHALL have a stable case identity; every CaseRevision SHALL identify its case, be immutable, and carry a monotonic revision value and predecessor reference when applicable. A BusinessEvent SHALL have a unique event identity, case reference, event type, occurrence time, receipt time, correlation metadata, and causation metadata when available. Artifact and EvidenceReference contracts SHALL identify content by cryptographic hash and SHALL carry media type and redaction classification rather than raw private payloads.

#### Scenario: A revision changes after initial capture
- **WHEN** a fixture represents an update to a case after an initial revision exists
- **THEN** it SHALL represent the update as a new immutable CaseRevision with the same case identity, a greater revision value, and a predecessor reference instead of mutating the original revision

#### Scenario: A cross-tenant evidence reference is supplied
- **WHEN** a contract fixture links a tenant-scoped case or revision to evidence with a different `tenant_id`
- **THEN** the contract-validation test suite SHALL reject the fixture as an invalid tenant boundary

### Requirement: Duplicate and out-of-order delivery are distinguishable without a side effect
ExternalWriteIntent SHALL require tenant identity, provider identifier, operation, natural key, intended-state hash, stable idempotency key, case/revision reference, and evidence references. The fixture corpus SHALL preserve event occurrence and receipt ordering separately so duplicate and out-of-order delivery can be tested without mutating an event or executing a provider action.

#### Scenario: A duplicate delivery is replayed
- **WHEN** two synthetic deliveries describe the same tenant, provider, operation, natural key, and intended-state hash
- **THEN** the fixtures SHALL resolve to the same stable idempotency key and SHALL NOT contain an execute or complete record for an external side effect in Change 0

#### Scenario: Events arrive out of order
- **WHEN** a replay fixture receives a later-occurring BusinessEvent before an earlier-occurring related BusinessEvent
- **THEN** validation SHALL preserve both occurrence and receipt metadata, classify the fixture as out-of-order for test purposes, and SHALL NOT rewrite either event or case revision

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
### Requirement: Contract evolution is checked rather than implied
The repository SHALL retain valid and invalid synthetic fixtures for every published `v1` schema and SHALL run a compatibility check before accepting a contract change. Incompatible semantics MUST use a new major-version contract directory rather than silently changing a consumed `v1` schema.

#### Scenario: A contract change invalidates a prior fixture
- **WHEN** a proposed schema change causes a retained compatible `v1` fixture to fail validation
- **THEN** the compatibility check SHALL fail until the change is made compatible or is introduced under a new major-version schema path

### Requirement: Inbound and projection contracts preserve safe intake identity
`InboundMessageEvent` SHALL require tenant, synthetic channel, channel event,
conversation, sender, customer, positive conversation-sequence, occurrence/receipt,
correlation, synthetic classification, and content-hash fields. It SHALL reject raw
message text, attachment bytes, secrets, and undeclared properties. `CaseProjection`
SHALL require tenant, Case identity, latest immutable revision reference, derived state,
source event reference, event count, correlation metadata, and safe timestamps.

#### Scenario: A normalized synthetic inbound envelope validates
- **WHEN** a fixture supplies all required safe identity, sequence, timestamp,
correlation, synthetic-classification, and SHA-256 fields under the inbound schema
- **THEN** Python and TypeScript validators SHALL accept it without requiring raw
customer content

#### Scenario: An inbound envelope contains raw or undeclared content
- **WHEN** a fixture adds a message body, attachment bytes, credential-like field, or
other undeclared property to an inbound envelope
- **THEN** both validators SHALL reject it under the canonical `v1` schema

### Requirement: Compatible v1 source contracts represent ordered safe ledger records
The compatible `v1` Case, CaseRevision, and BusinessEvent schemas SHALL support
additive safe intake metadata needed by this change, including Case channel/conversation
and customer references, revision source-event/fingerprint references, and event index
and canonical payload digest. Existing retained `v1` fixtures that predate these
additive fields SHALL remain valid; Change 1-produced source records SHALL populate the
fields required by the Case ledger service.

#### Scenario: Existing v1 fixtures remain compatible
- **WHEN** the retained Change 0 valid and semantic fixture corpus is validated after
the additive intake-contract update
- **THEN** every fixture that was previously valid SHALL remain valid and its
cross-language compatibility result SHALL remain unchanged

#### Scenario: A generated ledger event lacks safe ordering evidence
- **WHEN** Change 1 ledger validation evaluates a newly generated BusinessEvent without
its required per-Case event index or canonical payload digest
- **THEN** the ledger validation utility SHALL reject the generated record before it is
persisted or exposed as an accepted timeline event

### Requirement: Contract compatibility records intentional additive evolution
The contract compatibility command SHALL validate new inbound/projection valid and
invalid fixtures alongside all retained `v1` fixtures. It SHALL record an intentional
updated schema fingerprint only after both language consumers accept the compatible
corpus and reject the invalid corpus; an incompatible required-field or semantic change
MUST use a new major-version directory.

#### Scenario: A proposed v1 update breaks a retained consumer fixture
- **WHEN** a contract edit causes any retained valid `v1` fixture to fail in either
language consumer
- **THEN** the compatibility command SHALL fail until the edit is made compatible or
the change is moved to a new major-version contract path

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

### Requirement: Evidence contracts bind replay to a redacted immutable trajectory
The system SHALL require Artifact, EvidenceTrajectory, EvidenceReport, and
TrajectoryReplayResult contracts to bind their effective tenant, stable identity,
schema version, safe classification, content/root hash, and source trajectory identity
where applicable. A trajectory SHALL contain only ordered typed safe node references to
Case/revision/workflow and existing source facts; a replay result SHALL bind both
recorded and replayed roots plus a fixed verification outcome/failure code. Contract
validation SHALL reject raw customer or
tool content, credentials, caller-selected authority, foreign references, missing/
duplicate/out-of-order node identities, detached report/replay references, invalid hash,
or any customer-success claim.

#### Scenario: A complete fixture-local report chain validates
- **WHEN** a fixture contains a classified Artifact, canonical EvidenceTrajectory,
  redacted EvidenceReport, and matching TrajectoryReplayResult for one tenant
- **THEN** both contract packages SHALL accept the chain without requiring a provider,
  network request, external delivery payload, or customer outcome

#### Scenario: A trajectory or report is detached or unsafe
- **WHEN** a fixture contains a foreign node, missing causal reference, changed root,
  raw payload, secret-like value, invalid outcome code, or customer-resolution field
- **THEN** both contract packages SHALL reject it before it can be persisted, replayed,
  or exposed
