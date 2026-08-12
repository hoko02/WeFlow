## ADDED Requirements

### Requirement: Customer issue content SHALL be a bounded restricted artifact

The system SHALL normalize and redact the accepted customer issue into at most one `QQCustomerIssueArtifact` containing 1–1200 Unicode scalar values. The artifact SHALL be content-addressed, restricted, classified, retained for no more than 24 hours, and deleted at the terminal Stage 2 outcome. Group and C2C transcripts MUST NOT be stored.

#### Scenario: Valid intake enters Stage 2

- **WHEN** one accepted Stage 1 intake is selected for handler processing
- **THEN** one bounded issue artifact is created and durable workflow metadata references its hash rather than its plaintext

#### Scenario: Issue exceeds policy bounds

- **WHEN** normalized content cannot satisfy the redaction or size policy
- **THEN** Stage 2 fails closed without notifying the handler or creating a candidate

### Requirement: Response candidates SHALL be verified deterministically and privately

The system SHALL normalize, redact, bound, and content-address one current `QQHandlerResponseArtifact` without model invocation. Verification SHALL bind the candidate to the issue artifact hash, Case and immutable revision, active handler binding, policy result, and workflow version. Candidate plaintext SHALL be available only through the restricted artifact boundary and bound-handler C2C preview.

#### Scenario: Valid private candidate is submitted

- **WHEN** the bound C2C handler submits a policy-compliant 1–1200-character candidate for the current version
- **THEN** one verified candidate artifact and content-free candidate revision are created

#### Scenario: Candidate contains prohibited content

- **WHEN** deterministic redaction or policy verification rejects the proposed text
- **THEN** no approval request is created and the failure response reveals no restricted content

### Requirement: Candidate replacement SHALL invalidate prior approval state

Only one candidate may be current. Creating a replacement SHALL invalidate the previous candidate's approval request and any decision before the replacement can be approved. Superseded content SHALL become unreachable and be scheduled for deletion.

#### Scenario: Handler edits after preview

- **WHEN** a new private `WF-DRAFT` is accepted after an approval preview exists
- **THEN** the old request and hash prefix are rejected as stale and a new request is required

### Requirement: Content deletion SHALL be verifiable without content disclosure

The system SHALL emit content-free deletion evidence for issue and candidate artifacts and SHALL detect retention overruns as acceptance failures.

#### Scenario: Retention deadline or terminal outcome is reached

- **WHEN** either deletion condition occurs
- **THEN** the artifact is no longer retrievable and evidence records only its reference, hash, classification, and deletion time
