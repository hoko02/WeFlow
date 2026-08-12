# workspace-operability Specification

## Purpose
TBD - created by archiving change establish-weflow-foundation. Update Purpose after archive.
## Requirements
### Requirement: Reproducible workspace command surface
The repository SHALL declare coordinated Python and TypeScript workspaces and SHALL provide `scripts/dev.py` as the documented cross-platform entry point for environment checks, startup, shutdown, contract checks, tests, and health checks. The environment check and offline test path MUST run without network access, model credentials, enterprise credentials, or Docker.

#### Scenario: Contributor checks an offline workstation
- **WHEN** a contributor runs `python scripts/dev.py check` with the declared local toolchain and no provider credentials
- **THEN** the command SHALL report the availability of required local tooling and safe configuration without initiating a network request or requiring Docker

#### Scenario: Required local tooling is unavailable
- **WHEN** the environment check cannot find a required workspace tool or local asset
- **THEN** it SHALL fail with an actionable, redacted diagnostic and SHALL NOT report the foundation as ready

### Requirement: Boundary skeletons report truthful operational status
The Platform API, Control Worker, Agent Runtime, Business Simulator, and Web Console skeletons SHALL each expose a stable service identity and operational status through the development command surface. Liveness SHALL indicate whether the process can serve diagnostics; readiness SHALL indicate whether its selected mode, configuration, and declared dependencies have passed checks. No skeleton endpoint or report SHALL claim that a customer issue was resolved.

#### Scenario: Offline skeleton startup succeeds
- **WHEN** a contributor starts the foundation in offline mode with valid replay-first configuration
- **THEN** every declared skeleton service SHALL become live and ready, and the Platform API SHALL expose liveness and readiness responses that identify offline mode

#### Scenario: A skeleton process restarts
- **WHEN** a skeleton process is stopped and started again in offline mode
- **THEN** it SHALL re-evaluate configuration and readiness, restore only deterministic local state, and SHALL NOT manufacture a business event, external side effect, approval, or case-completion result

### Requirement: Repository hygiene and baseline CI are enforceable
The repository SHALL include automated checks for formatting or linting, workspace
tests, contract compatibility, safe configuration, and committed secret material. CI
output and developer diagnostics MUST redact candidate secret values and MUST distinguish
an unavailable local dependency from a passed business workflow. For any archived change
whose long-lived documentation claims machine-readable verification evidence, the
repository SHALL track or safely classify the canonical evidence paths and SHALL record
whether each reconciliation command passed, failed, timed out, or was unavailable. A
reconciliation archive gate SHALL require strict zero-issue validation of the active
reconciliation change and a passing canonical evidence check; a direct archived-change
validation limitation MUST remain a truthful classified result rather than a pass claim.

#### Scenario: A candidate secret is introduced
- **WHEN** the secret-hygiene check detects a credential-like value in tracked source,
  fixture, configuration, or report content
- **THEN** the check SHALL fail and identify the location without printing the candidate
  secret value

#### Scenario: A health check passes without business execution
- **WHEN** the baseline CI health check observes all offline skeletons ready
- **THEN** it SHALL record only operational readiness evidence and SHALL NOT treat the
  result as acceptance evidence for the API-503 support workflow

#### Scenario: An archived evidence path is missing or incomplete
- **WHEN** an archived Change 4 or Change 5 document references an acceptance or strict
  validation report that is missing, failed, unavailable, or timed out
- **THEN** repository hygiene SHALL surface the discrepancy through a redacted
  reconciliation result and SHALL NOT allow the missing path to imply a successful
  verification

#### Scenario: Archive readiness encounters a documented archived-validation limitation
- **WHEN** a canonical archived Change 4 or Change 5 validation report records
  `failed` with `archived_change_has_no_delta`, while the active reconciliation change
  validates strictly with zero issues and the canonical evidence check passes
- **THEN** repository hygiene SHALL allow archive readiness, retain the archived result
  as a CLI limitation, and SHALL NOT claim that the archived validation passed

### Requirement: QQ pairing commands are isolated and reproducible
The repository SHALL expose dedicated cross-platform development commands for offline
pairing acceptance, pairing-report verification, explicitly confirmed live pairing,
and bounded local revoke/expiry handling. Offline pairing checks SHALL require no
network, QQ/model/enterprise credential, Docker, or external write. Ordinary startup,
health, tests, Replay, benchmarks, investigation, live-model evaluation, and retained
acceptance commands SHALL reject visible pairing configuration or activation before
their handlers run and SHALL not import the real pairing adapter.

#### Scenario: CI runs pairing acceptance offline
- **WHEN** the normal test/contract/security command surface executes without QQ
  configuration
- **THEN** deterministic fakes and pairing report verification SHALL pass without
  network or credentials while real pairing remains unverified

#### Scenario: An ordinary command sees pairing configuration
- **WHEN** a non-pairing command observes pairing credentials, confirmation, pairing
  capability, challenge, or pairing selector configuration
- **THEN** it SHALL fail before command work, provider contact, or runtime registration
  and SHALL output only a redacted stable reason

#### Scenario: The live pairing command is run without confirmation
- **WHEN** an operator invokes live pairing without the exact confirmation flag or with
  missing/expanded configuration
- **THEN** it SHALL fail before HTTP/WebSocket client construction and SHALL not create
  a challenge or pairing record
