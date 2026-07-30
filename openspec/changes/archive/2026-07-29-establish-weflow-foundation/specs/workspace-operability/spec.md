## ADDED Requirements

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
The repository SHALL include automated checks for formatting or linting, workspace tests, contract compatibility, safe configuration, and committed secret material. CI output and developer diagnostics MUST redact candidate secret values and MUST distinguish an unavailable local dependency from a passed business workflow.

#### Scenario: A candidate secret is introduced
- **WHEN** the secret-hygiene check detects a credential-like value in tracked source, fixture, configuration, or report content
- **THEN** the check SHALL fail and identify the location without printing the candidate secret value

#### Scenario: A health check passes without business execution
- **WHEN** the baseline CI health check observes all offline skeletons ready
- **THEN** it SHALL record only operational readiness evidence and SHALL NOT treat the result as acceptance evidence for the API-503 support workflow

