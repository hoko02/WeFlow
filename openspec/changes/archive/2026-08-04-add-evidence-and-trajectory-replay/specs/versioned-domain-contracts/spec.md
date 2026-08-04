## MODIFIED Requirements

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

## ADDED Requirements

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
