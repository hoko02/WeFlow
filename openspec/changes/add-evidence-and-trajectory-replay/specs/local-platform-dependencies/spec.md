## ADDED Requirements

### Requirement: Offline evidence trajectory and replay acceptance are self-contained and deterministic
Offline mode SHALL generate and verify the named API-503 EvidenceTrajectory and
redacted Evidence Report from checked-in fixtures, local SQLite, fixed clocks, and
project-managed dependencies only. The `evidence-trajectory-acceptance` command SHALL
compare two equal baselines for the authorized, authorization-denial, and declared
interrupted-recovery paths, emit a machine-readable redacted report, and record declared
Node/Docker availability. Core acceptance SHALL require neither Docker, network access,
model/enterprise credentials, a live trace backend, nor a real provider/approval/
delivery service.

#### Scenario: Evidence acceptance runs with Docker and network unavailable
- **WHEN** a contributor runs the named evidence trajectory acceptance command while
  Docker is unavailable and network access is blocked
- **THEN** it SHALL produce equal safe baseline reports and replay results using only
  fixture-local facts, with zero model invocation and zero external write

#### Scenario: A replay input requests a live dependency or raw export
- **WHEN** configuration or a fixture requests a live trace exporter, provider,
  credential, network destination, Docker service, raw source payload, or unrestricted
  artifact export
- **THEN** offline mode SHALL deny before initialization, produce a payload-safe report
  failure, and execute no workflow or delivery operation

### Requirement: Offline evidence reports expose only safe diagnostics
Offline diagnostics, snapshots, and acceptance reports SHALL expose only stable IDs,
hashes, classifications, counts, fixed outcome/failure codes, and declared environment
limitations. They SHALL omit raw customer, prompt, context, tool, policy input,
approval rationale, delivery content, credential, connection string, and foreign-tenant
existence.

#### Scenario: A failed replay is retained for diagnosis
- **WHEN** a source hash or causal link is invalid during offline replay
- **THEN** the machine-readable report SHALL record only the stable lineage failure
  code and safe references without revealing protected source content or making a live
  retry
