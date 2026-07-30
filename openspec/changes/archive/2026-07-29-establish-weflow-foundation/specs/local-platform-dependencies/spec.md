## ADDED Requirements

### Requirement: Offline mode is deterministic and self-contained
WeFlow SHALL provide an `offline` local mode as the default development mode. Offline mode SHALL use deterministic replay fixtures and local process resources only, SHALL NOT require Docker or network access, and SHALL keep all provider selections replay-only.

#### Scenario: A contributor works without Docker or network access
- **WHEN** a contributor starts and tests the foundation in offline mode while Docker is unavailable and network access is blocked
- **THEN** the declared skeleton services and contract/replay checks SHALL remain operable using synthetic local fixtures

#### Scenario: Offline mode receives a replay input
- **WHEN** the Business Simulator supplies a declared replay fixture to the Agent Runtime in offline mode
- **THEN** the runtime SHALL identify the fixture as synthetic replay input and SHALL NOT invoke a model, enterprise credential, or external network provider

### Requirement: Service-boundary mode declares and checks local dependencies
WeFlow SHALL provide an explicit `service-boundary` local mode that provisions PostgreSQL, Temporal, an S3-compatible object store, and an OpenTelemetry Collector through Compose. Application skeletons SHALL report the status of each required local dependency without exposing credentials or raw connection strings.

#### Scenario: Local service-boundary dependencies are available
- **WHEN** a contributor starts service-boundary mode with the declared Compose dependencies healthy
- **THEN** each skeleton service that depends on those services SHALL become ready and the health report SHALL identify dependency status using redacted component names

#### Scenario: A required dependency times out
- **WHEN** a required local dependency is unavailable beyond its configured readiness deadline
- **THEN** the dependent skeleton SHALL remain not-ready or fail startup with a redacted timeout diagnostic, and SHALL NOT substitute a real external provider or claim a completed workflow

### Requirement: Fault injection and replay remain local-only
The development harness SHALL support named, synthetic fault profiles for invalid configuration, unavailable dependencies, restart, duplicate delivery, and out-of-order delivery. A fault profile MUST be deterministic, recorded in test output, and incapable of producing an external side effect.

#### Scenario: A restart fault profile is replayed
- **WHEN** a test runs a named restart fault profile against an offline skeleton service
- **THEN** the test result SHALL record the injected restart, re-run readiness checks, and contain no model invocation, external write, or case-success assertion

### Requirement: Local telemetry and artifacts are safe for fixtures
Structured logs, traces, local artifacts, and replay reports SHALL include service/mode/correlation metadata and SHALL redact secrets, raw customer data, and unrestricted tool output. Local object storage, when used, SHALL contain synthetic content-addressed artifacts only.

#### Scenario: A timeout produces diagnostic evidence
- **WHEN** a service-boundary readiness check times out
- **THEN** the emitted log or trace evidence SHALL include the affected component and correlation metadata while omitting credentials, raw connection strings, and private payload content

