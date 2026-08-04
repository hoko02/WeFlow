## ADDED Requirements

### Requirement: Evidence trajectories are canonical, tenant-scoped, and source-complete
The system SHALL construct an immutable `EvidenceTrajectory` only from one effective
tenant, Case, CaseRevision, workflow identity, and declared report profile. Its
canonical ordered nodes SHALL link available accepted intake, immutable revision/event,
workflow activation/checkpoint, investigation manifest/step/tool/evidence/candidate/
verifier, policy/grant/binding, approval, and fixture-delivery facts by stable IDs,
causation references, safe classifications, and content hashes. The trajectory SHALL
persist one stable root SHA-256 over its ordered safe node representation and SHALL NOT
insert an inferred, foreign, duplicate, out-of-order, or unlinked fact.

#### Scenario: The named authorized fixture produces a complete local trajectory
- **WHEN** the checked-in API-503 policy/approval/delivery fixture reaches
  `DELIVERY_RECORDED` with valid retained source facts
- **THEN** the system SHALL persist one tenant-scoped trajectory whose root links the
  accepted Case through verified candidate, policy, approval, and exactly one local
  delivery completion without raw source content

#### Scenario: A source reference is missing, foreign, duplicated, or causally invalid
- **WHEN** trajectory construction encounters an absent source record, another tenant,
  repeated logical node, broken predecessor, invalid hash, or out-of-order sequence
- **THEN** it SHALL produce only a redacted `lineage_invalid` result and SHALL not
  persist a complete trajectory, change workflow state, or create an effect

### Requirement: Evidence artifacts and reports are immutable, content-addressed, and redacted
The system SHALL persist `Artifact` and `EvidenceReport` facts separately from Case and
workflow state. Each SHALL have a stable identity, schema identity/version, effective
tenant, allowed safe classification, canonical content SHA-256, source trajectory root,
and report/profile metadata where applicable. A report SHALL expose only safe IDs,
hashes, classifications, counts, fixed outcome/failure codes, fixture identity, and
explicit capability/environment flags. It SHALL NOT contain raw message/candidate/
prompt/context/tool/delivery content, credential, unrestricted payload, caller-supplied
role, customer receipt, resolution, completion, or general external-write assertion.

#### Scenario: An exact report request is retried
- **WHEN** the same valid trajectory and report profile are requested again
- **THEN** the system SHALL return the same persisted artifact/report identity and
  hash without adding a Case event, checkpoint, approval, intent, delivery, or second
  report record

#### Scenario: A report input or output contains prohibited content
- **WHEN** report construction or validation encounters raw private text, secret-like
  data, undeclared fields, a caller-selected authority value, or customer-success
  language
- **THEN** it SHALL reject the report before persistence with a payload-safe reason and
  SHALL expose no protected content

### Requirement: Evidence reports classify local outcomes without asserting customer success
An Evidence Report SHALL classify only the supported fixture-local outcome or safe
failure: `fixture_delivery_recorded`, `authorization_denied`,
`recovered_after_interruption`, `needs_reconciliation`, or `lineage_invalid`.
`fixture_delivery_recorded` SHALL mean only that the named local adapter record is
complete; it SHALL NOT mean a network send, provider acknowledgement, customer receipt,
incident resolution, Case completion, knowledge publication, or permission for another
effect.

#### Scenario: A revoked grant denial is reported
- **WHEN** the named fixture reaches its safe revoked-grant denial path with zero
  delivery intent and zero local delivery record
- **THEN** the Evidence Report SHALL classify `authorization_denied`, retain only safe
  policy/binding references and counts, and assert no delivery or customer outcome

#### Scenario: A recovered lost-response path is reported
- **WHEN** the named fixture recovers a declared local-delivery interruption without a
  duplicate operation
- **THEN** the Evidence Report SHALL classify `recovered_after_interruption`, link the
  same single delivery identity, and retain no raw adapter response

### Requirement: Trajectory replay is deterministic verification and has no execution authority
The trajectory replay interface SHALL accept only a persisted tenant-scoped trajectory
identity and verify its recorded source identities, order, causal links, and hashes in
canonical order. It SHALL emit a `TrajectoryReplayResult` whose replayed root equals
the stored root on success. Replay SHALL be read-only and SHALL NOT initialize or call
a model, provider, tool, policy evaluator, approval recorder, workflow command, effect
reconciler, delivery adapter, network client, Docker service, or external executor.

#### Scenario: Two replays verify the same trajectory
- **WHEN** the same valid named fixture trajectory is replayed twice from unchanged
  fixture-local SQLite source facts
- **THEN** both results SHALL have the same trajectory root, report hash, outcome
  classification, ordered node identities, and declared zero network/model/external-
  write flags

#### Scenario: A manifest or source fact is tampered with before replay
- **WHEN** replay finds a mismatched root, source hash, tenant, schema version, or
  causal reference
- **THEN** it SHALL return a redacted `lineage_invalid` result, execute no workflow or
  effect operation, and leave all durable Case/workflow/delivery facts unchanged
