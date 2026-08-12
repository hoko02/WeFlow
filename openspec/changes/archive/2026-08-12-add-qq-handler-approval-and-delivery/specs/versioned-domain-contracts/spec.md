## ADDED Requirements

### Requirement: Versioned contracts SHALL represent dual-surface handler authority

The contract set SHALL define versioned schemas for the handler binding, pairing evidence, assurance level, group-member identity hash, C2C-user identity hash, paired group, tenant mapping, lifecycle status, expiry, and content-free audit metadata. Raw provider identities SHALL remain behind private provider locators and MUST NOT appear in reports or general domain events.

#### Scenario: Binding contract validates

- **WHEN** both challenge results and local confirmation are recorded
- **THEN** the schema requires both identity-surface hashes, group and tenant binding, assurance level, expiry, and active status

#### Scenario: One identity surface is absent

- **WHEN** a purported binding omits either the group-member or C2C-user identity
- **THEN** contract validation fails

### Requirement: Versioned contracts SHALL separate private content from workflow metadata

The contract set SHALL define content-free schemas for `QQCustomerIssueArtifact`, `QQHandlerResponseArtifact`, C2C command envelopes, notification intent/result, candidate revision, approval request/decision, passive reply intent/result, and acceptance report. Content-bearing fields SHALL be artifact references with hash, classification, bounded length, retention deadline, and deletion state rather than plaintext.

#### Scenario: Private command envelope is serialized

- **WHEN** a `WF-DRAFT` event crosses a service boundary
- **THEN** the envelope carries source-event identity, command classification, binding, Case/revision, expected version, and candidate artifact reference without raw candidate text

#### Scenario: Group approval contract is serialized

- **WHEN** a `WF-APPROVE` event is normalized
- **THEN** it carries only approval request identity, candidate hash prefix, expected version, group author identity reference, and source `msg_id`, with no candidate body

### Requirement: Contract evolution SHALL reject unknown privileged shapes

Privileged Stage 2 inputs and outputs SHALL declare schema identifier and version, reject unknown command/action variants, and preserve backward-safe replay fixtures without network or QQ credentials.

#### Scenario: Unknown privileged action is received

- **WHEN** a contract contains an unrecognized notification, approval, or delivery action
- **THEN** validation fails before policy evaluation or external write
