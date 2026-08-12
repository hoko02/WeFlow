## ADDED Requirements

### Requirement: Handler workflow transitions SHALL be append-only business events

The ledger SHALL append content-free events for dual binding activation/revocation/expiry, private pull, accept, candidate creation/replacement/rejection, approval request creation/invalidation, group approval decision, notification outcome, final delivery intent/result, and artifact deletion. Existing events, immutable binding records, and immutable Case revisions MUST NOT be rewritten.

#### Scenario: Candidate is replaced privately

- **WHEN** the bound handler submits a valid replacement
- **THEN** the ledger appends prior-request invalidation and new-candidate facts while retaining the earlier history

#### Scenario: Final write is accepted

- **WHEN** QQ accepts the passive group reply
- **THEN** the ledger appends provider-acceptance evidence without declaring customer receipt or resolution

#### Scenario: Operator revokes a stale dependent binding

- **WHEN** exact local confirmation and a matching current Stage 1 scope authorize revocation
- **THEN** the ledger appends one content-free terminal event while the immutable binding record remains unchanged

### Requirement: Ledger facts SHALL not disclose private content or raw QQ identity

Ledger events SHALL contain only stable internal identifiers, salted identity hashes or private locator references, artifact hashes, classifications, workflow versions, safe reason codes, provider outcome classes, and evidence links. They SHALL NOT contain credentials, raw `openid` values, source event bodies, customer issue text, candidate text, previews, or transcripts.

#### Scenario: C2C draft event is appended

- **WHEN** a private draft becomes current
- **THEN** the event records its artifact hash, length, classification, binding, Case revision, and workflow version without the draft body

### Requirement: Ledger ordering SHALL support deterministic replay

Every Stage 2 event SHALL carry a stable event identity, aggregate identity, expected prior workflow version, resulting version, correlation and causation references, and recorded-at metadata sufficient to replay duplicate, stale, replacement, approval, and recovery behavior offline.

#### Scenario: Duplicate provider event is replayed

- **WHEN** the same normalized C2C or group event is applied more than once
- **THEN** replay produces one logical transition and records the duplicate classification without a second side effect

#### Scenario: QQ reconnect resets the session-local sequence

- **WHEN** a new QQ WebSocket connection yields a new provider message whose session-local sequence
  equals or is lower than a sequence observed on an earlier connection
- **THEN** the transport enforces ordering only within the active connection, the ledger accepts the
  new natural key exactly once, and the conversation cursor remains a diagnostic high-water mark
  rather than an authorization or cross-session ordering gate
