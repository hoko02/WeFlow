## ADDED Requirements

### Requirement: Approval requests SHALL bind the exact private candidate and workflow state

An `ApprovalRequest` SHALL bind the candidate artifact hash, normalized candidate hash, customer-issue artifact hash, Case and immutable revision, active dual-surface binding, policy decision, workflow version, creation time, and expiry. Its group-safe representation SHALL contain only request identity, unambiguous hash prefix, and expected version.

#### Scenario: Private draft creates an approval request

- **WHEN** deterministic candidate verification succeeds
- **THEN** the system stores the full content-free binding and returns only bounded preview plus group-safe approval metadata to the bound handler in C2C

#### Scenario: Group member requests candidate plaintext

- **WHEN** a group command attempts to retrieve an approval preview or draft body
- **THEN** the request is denied without disclosing whether restricted content exists

### Requirement: Approval decisions SHALL require the linked group identity and exact current binding

An `ApprovalDecision` SHALL be accepted only when the group event author matches the `member_openid` side of the same active binding whose C2C `user_openid` created the candidate, and every request-bound hash, Case revision, version, and expiry still matches. The robot, candidate, provider role, or model MUST NOT approve.

#### Scenario: Correct handler approves exact metadata

- **WHEN** the linked group identity submits the current request ID, hash prefix, and expected version
- **THEN** exactly one content-free approval decision is recorded

#### Scenario: Different group member copies approval metadata

- **WHEN** any unbound member submits otherwise valid metadata
- **THEN** the command is rejected and final delivery remains unauthorized

### Requirement: Changes SHALL invalidate approval authority atomically

Candidate replacement, rejection, expiry, Case revision change, handler-binding change, or workflow-version change SHALL invalidate all prior requests and decisions before any final write can begin.

#### Scenario: Candidate is edited after approval

- **WHEN** a replacement is accepted after a decision was recorded but before final execution
- **THEN** the decision cannot authorize delivery and a fresh approval request and decision are required
