## ADDED Requirements

### Requirement: Archived Change 4 and Change 5 evidence is canonical, tracked, and redacted
The repository SHALL retain canonical, machine-readable, redacted acceptance and strict
OpenSpec-validation evidence for archived Change 4 and Change 5 under version-controlled
`reports/` paths. A reconciliation manifest SHALL identify each required artifact, its
SHA-256 content hash, the source commit, and its outcome classification. The manifest and
reports MUST contain only allowlisted IDs, hashes, counts, capability flags, safe reason
codes, command identities, and environment limitations; they MUST NOT contain raw
fixture/customer content, prompts, tool output, approval rationale, delivery content,
credentials, connection strings, or unrestricted console output.

#### Scenario: A documented archived report is absent from the checkout
- **WHEN** the reconciliation inventory finds a Change 4 or Change 5 evidence path
  documented but absent from the repository
- **THEN** it SHALL regenerate the artifact from the existing offline command or record
  a redacted non-passing outcome, update the canonical manifest, and SHALL NOT retain an
  unsupported passing claim

#### Scenario: A generated evidence record contains prohibited material
- **WHEN** report validation or secret hygiene detects a raw or credential-like field in
  a regenerated Change 4 or Change 5 evidence record
- **THEN** the record SHALL be rejected before tracking and the reconciliation SHALL
  record only a safe failure classification

#### Scenario: Direct strict validation targets an already archived change
- **WHEN** the current OpenSpec CLI directly validates an archived Change 4 or Change 5
  directory and returns `archived_change_has_no_delta`
- **THEN** its canonical validation report SHALL retain `failed` and that exact safe
  reason code, SHALL NOT present it as a passing validation or product defect, and SHALL
  remain eligible for reconciliation archive only through the separate active-change and
  evidence-check gates

### Requirement: Archived documentation agrees with archive and evidence facts
Change 4 and Change 5 archival documentation SHALL identify the changes as synced and
archived when their archive directories and main specifications do so. The development
guides and long-lived project status text SHALL reference only canonical evidence
paths that exist in the repository and SHALL distinguish a current successful
reconciliation run from a missing, failed, unavailable, or timed-out run.

#### Scenario: A guide retains pre-archive wording after archive evidence is reconciled
- **WHEN** a Change 4 or Change 5 guide says that sync or archive finalization remains
  pending while the corresponding archived directory and main specification exist
- **THEN** reconciliation SHALL replace that wording with the verified archive status
  and retain the documented offline and no-external-write limits

#### Scenario: Evidence cannot be regenerated successfully
- **WHEN** an expected Change 4 or Change 5 verification command fails, is unavailable,
  or times out during reconciliation
- **THEN** documentation SHALL record that exact safe limitation and SHALL NOT state
  that the command passed or that live behavior was verified

### Requirement: Reconciliation classifies bounded verification execution truthfully
The reconciliation SHALL run existing Change 4 and Change 5 acceptance commands, strict
OpenSpec validation, and the aggregate local verification suite with a 900-second outer
time limit. Each result SHALL be classified as `passed`, `failed`, `timed_out`, or
`unavailable`, shall include elapsed duration and safe Node/Docker availability facts,
and SHALL make a pass claim only for a completed zero-exit command. A timed-out command
MUST have its child processes cleaned up before the result is retained.

#### Scenario: The aggregate suite completes within the bounded limit
- **WHEN** the local verification suite exits with code zero before 900 seconds
- **THEN** the canonical manifest SHALL record `passed`, the elapsed duration, and the
  observed Node/Docker limitation facts without claiming any unavailable service was
  live-verified

#### Scenario: The aggregate suite exceeds the bounded limit
- **WHEN** the local verification suite exceeds 900 seconds
- **THEN** reconciliation SHALL terminate its owned child processes, record
  `timed_out` with the elapsed duration and cleanup status, retain any separately
  completed focused evidence, and SHALL NOT record the aggregate suite as passed
