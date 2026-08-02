## MODIFIED Requirements

### Requirement: Offline mode is deterministic and self-contained
WeFlow SHALL provide an `offline` local mode as the default development mode. Offline
mode SHALL use deterministic replay fixtures, local process resources, a local SQLite
workflow journal, and an injectable fixture clock only; it SHALL NOT require Docker or
network access, and SHALL keep all provider selections replay-only. The offline control
worker SHALL execute the driver-neutral workflow reducer and fixture-local ticket
simulator without initializing Temporal, a model, an enterprise credential, or an
external-write executor.

#### Scenario: A contributor works without Docker or network access
- **WHEN** a contributor starts and tests the foundation in offline mode while Docker
  is unavailable and network access is blocked
- **THEN** the declared skeleton services, deterministic workflow fixtures, and
  contract/replay checks SHALL remain operable using synthetic local resources only

#### Scenario: Offline mode receives a replay input
- **WHEN** the Business Simulator supplies a declared replay fixture to the Agent
  Runtime in offline mode
- **THEN** the runtime SHALL identify the fixture as synthetic replay input and SHALL
  NOT invoke a model, enterprise credential, or external network provider

#### Scenario: Offline mode recovers a durable workflow
- **WHEN** an offline control worker restarts with a persisted workflow checkpoint and
  side-effect journal for a synthetic Case
- **THEN** it SHALL rebuild the same workflow/Cases projections and reconcile only the
  fixture-local natural key without requiring a service-boundary dependency

### Requirement: Service-boundary mode declares and checks local dependencies
WeFlow SHALL provide an explicit `service-boundary` local mode that provisions
PostgreSQL, Temporal, an S3-compatible object store, and an OpenTelemetry Collector
through Compose. Application skeletons and the Temporal-backed control-worker driver
SHALL report the status of each required local dependency without exposing credentials
or raw connection strings.

#### Scenario: Local service-boundary dependencies are available
- **WHEN** a contributor starts service-boundary mode with the declared Compose
  dependencies healthy
- **THEN** each skeleton service that depends on those services SHALL become ready and
  the health report SHALL identify dependency status using redacted component names

#### Scenario: A required dependency times out
- **WHEN** a required local dependency is unavailable beyond its configured readiness
  deadline
- **THEN** the dependent skeleton SHALL remain not-ready or fail startup with a redacted
  timeout diagnostic, and SHALL NOT substitute a real external provider or claim a
  completed workflow

#### Scenario: The Temporal workflow driver cannot start
- **WHEN** service-boundary mode cannot establish its declared local Temporal driver
  before the readiness deadline
- **THEN** the control worker SHALL report a redacted workflow-dependency reason,
  execute no effect, and leave its existing local source records unchanged

### Requirement: Fault injection and replay remain local-only
The development harness SHALL support named, synthetic fault profiles for invalid
configuration, unavailable dependencies, restart, duplicate delivery, out-of-order
delivery, workflow activation, checkpoint persistence, intent persistence,
reconciliation, effect execution, lost response, observation persistence, and
completion persistence. A fault profile MUST be deterministic, recorded in test output,
and incapable of producing an external side effect.

#### Scenario: A restart fault profile is replayed
- **WHEN** a test runs a named restart fault profile against an offline skeleton
  service
- **THEN** the test result SHALL record the injected restart, re-run readiness checks,
  and contain no model invocation, external write, or case-success assertion

#### Scenario: A lost response fault is recovered through reconciliation
- **WHEN** a deterministic fault drops the local ticket-simulator response after the
  simulator operation has taken effect
- **THEN** a fresh worker SHALL recover by natural-key reconciliation, report one safe
  recovered outcome or `NEEDS_RECONCILIATION`, and SHALL not execute another ticket
  operation

#### Scenario: A checkpoint persistence fault interrupts the worker
- **WHEN** a fault interrupts the worker at a declared checkpoint persistence boundary
- **THEN** recovery SHALL use the last durable checkpoint/source facts, append no
  duplicate Case event or effect, and produce deterministic redacted evidence
