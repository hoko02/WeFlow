## MODIFIED Requirements

### Requirement: Approval requests SHALL bind the exact private candidate and workflow state

An `ApprovalRequest` SHALL bind the candidate artifact hash, normalized candidate hash, customer-issue artifact hash, Case and immutable revision, active dual-surface binding, policy/capability decisions, workflow version, creation time, and expiry. For a model-assisted candidate it SHALL additionally bind the handler-authored assist request, Context Manifest, model invocation/observation, normalized action, provider/prompt/price profiles, ordered evidence and claim references, verifier result, and budget state. Its group-safe representation SHALL contain only request identity, unambiguous hash prefix, and expected version.

#### Scenario: Private human draft creates an approval request

- **WHEN** deterministic verification succeeds for a bound-handler `WF-DRAFT`
- **THEN** the system stores the full content-free human binding and returns only bounded preview plus group-safe approval metadata to the bound handler in C2C

#### Scenario: Private model candidate creates an approval request

- **WHEN** deterministic verification succeeds for the bound handler's current assist request and complete model/evidence provenance
- **THEN** the system stores the full content-free model binding and returns only bounded preview/evidence summary plus group-safe approval metadata to that handler in C2C

#### Scenario: Group member requests candidate plaintext

- **WHEN** a group command attempts to retrieve an approval preview, model evidence summary, or draft body
- **THEN** the request is denied without disclosing whether restricted content exists

### Requirement: Approval decisions SHALL require the linked group identity and exact current binding

An `ApprovalDecision` SHALL be accepted only when the group event author matches the `member_openid` side of the same active binding whose C2C `user_openid` either created the human candidate or authored the assist request for the model candidate, and every request-bound candidate/provenance hash, Case revision, policy/capability/profile, evidence, verifier, budget, workflow version, retention state, and expiry still matches. The robot, candidate, model, provider role, tool output, customer, or another user MUST NOT approve.

#### Scenario: Correct handler approves exact metadata

- **WHEN** the linked group identity submits the current request ID, hash prefix, and expected version for its private current candidate
- **THEN** exactly one content-free approval decision is recorded

#### Scenario: Different group member copies approval metadata

- **WHEN** any unbound member submits otherwise valid metadata
- **THEN** the command is rejected and final delivery remains unauthorized

#### Scenario: Model lineage changes after preview

- **WHEN** invocation, Context, evidence, verifier, budget, provider/profile, assist request, candidate, or workflow state no longer matches the approval request
- **THEN** the approval is stale and no final delivery intent or QQ transport attempt occurs
