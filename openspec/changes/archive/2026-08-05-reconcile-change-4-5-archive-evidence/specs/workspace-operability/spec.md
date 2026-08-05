## MODIFIED Requirements

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
