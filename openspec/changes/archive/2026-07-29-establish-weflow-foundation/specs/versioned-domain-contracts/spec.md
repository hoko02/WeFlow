## ADDED Requirements

### Requirement: Canonical versioned domain schemas exist
WeFlow SHALL maintain language-neutral JSON Schema files under a versioned contract directory. Each boundary object SHALL declare a stable schema identifier and `schema_version`. The initial version SHALL cover Case, CaseRevision, BusinessEvent, Artifact, EvidenceReference, CapabilityGrant, PolicyDecision, ApprovalRequest, ApprovalDecision, ReplayRequest, ReplayResult, EvaluationCase, EvaluationResult, and ExternalWriteIntent.

#### Scenario: A valid contract fixture is consumed cross-language
- **WHEN** a valid `v1` fixture for each supported boundary object is validated by the Python and TypeScript contract packages
- **THEN** both packages SHALL accept the fixture under the same schema identifier and version

#### Scenario: A required version or schema identity is absent
- **WHEN** a boundary payload omits its declared schema identity or `schema_version`
- **THEN** both contract packages SHALL reject the payload with a deterministic validation result

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
PolicyDecision, ApprovalRequest, and ApprovalDecision contracts SHALL bind their decision context to tenant, case, case revision, relevant evidence hashes, creation time, and expiry where applicable. An approval decision SHALL reference the approval request it decides. Contract validation utilities SHALL classify an expired or revision/evidence-mismatched approval as not authorized for a later action.

#### Scenario: An approval becomes stale after a revision changes
- **WHEN** an approval decision bound to one case revision or evidence hash is evaluated against a newer revision or different evidence hash
- **THEN** the validation utility SHALL classify the approval as stale and not authorized, and SHALL NOT emit a completion or external-write authorization result

### Requirement: Contract evolution is checked rather than implied
The repository SHALL retain valid and invalid synthetic fixtures for every published `v1` schema and SHALL run a compatibility check before accepting a contract change. Incompatible semantics MUST use a new major-version contract directory rather than silently changing a consumed `v1` schema.

#### Scenario: A contract change invalidates a prior fixture
- **WHEN** a proposed schema change causes a retained compatible `v1` fixture to fail validation
- **THEN** the compatibility check SHALL fail until the change is made compatible or is introduced under a new major-version schema path

