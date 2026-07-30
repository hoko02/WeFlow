## ADDED Requirements

### Requirement: Synthetic IM intake validates a normalized, tenant-bound envelope
The Platform API SHALL expose a loopback-only synthetic IM intake boundary that accepts
only a valid canonical `InboundMessageEvent` from the deterministic Business Simulator.
The server SHALL resolve the effective tenant from an allowlisted synthetic actor
identity and SHALL require the envelope tenant claim to match it. The envelope SHALL
contain opaque synthetic identities, sequence/order metadata, timestamps, correlation
metadata, synthetic content classification, and a content SHA-256; it SHALL NOT accept
or persist raw customer message text, attachment bytes, credentials, or unrestricted
tool output.

#### Scenario: A valid synthetic event is accepted for its mapped tenant
- **WHEN** an allowlisted synthetic actor submits a valid `InboundMessageEvent` whose
  tenant claim matches that actor's mapped tenant
- **THEN** the intake boundary SHALL pass the effective tenant and normalized envelope
  to deterministic Case intake and return a payload-safe accepted outcome

#### Scenario: An envelope is invalid or claims a different tenant
- **WHEN** an inbound envelope is malformed, contains an unsupported/non-synthetic
  channel or raw content field, or has a tenant claim different from the resolved actor
  tenant
- **THEN** the API SHALL reject it with an allowlisted safe reason code, create no
  Case/revision/event/receipt record, and disclose no raw input or configuration value

### Requirement: Inbound delivery is idempotent and detects conflicting replays
The intake boundary SHALL derive an inbound natural key from effective tenant, channel,
and channel event identity, and SHALL derive a canonical fingerprint that excludes only
receipt-time variation. The natural key and fingerprint SHALL be evaluated atomically
before any Case creation.

#### Scenario: An identical delivery is retried
- **WHEN** a second valid envelope has the same effective tenant, natural key, and
  canonical fingerprint as an already accepted delivery
- **THEN** the API SHALL return `deduplicated` with the original Case/revision/event
  references and SHALL not append an event, create a revision, advance a sequence, or
  mutate the projection

#### Scenario: A delivery key is replayed with altered semantic content
- **WHEN** an envelope has an already accepted inbound natural key but a different
  canonical fingerprint
- **THEN** the API SHALL reject it with `inbound_event_conflict` and SHALL leave all
  durable source records and projections unchanged

### Requirement: Conversation ordering has a stable synthetic rejection behavior
For a new delivery, the intake boundary SHALL require `conversation_sequence` to equal
the next contiguous value for the effective tenant/channel/conversation. Sequence
validation SHALL occur after exact-duplicate lookup and before Case creation; it SHALL
not use wall-clock timestamps as the ordering authority.

#### Scenario: A contiguous next event is accepted
- **WHEN** a new valid delivery has the next expected sequence for its conversation
- **THEN** the intake boundary SHALL accept it and advance that conversation cursor in
the same transaction as the Case source records

#### Scenario: A late event or sequence gap is delivered
- **WHEN** a new non-duplicate delivery has a sequence lower than or greater than the
next expected sequence for its conversation
- **THEN** the API SHALL reject it with `inbound_out_of_order`, retain the existing
cursor, and create no Case/revision/event/receipt record

### Requirement: Case reads are tenant-scoped and do not leak foreign existence
The API SHALL provide tenant-scoped read surfaces for a Case projection, immutable
revision sequence, and append-only event timeline. The effective tenant SHALL be
derived from the same synthetic actor boundary for every read; the caller SHALL not
select a tenant through a path, query, or body parameter.

#### Scenario: A tenant reads its own Case history
- **WHEN** an actor mapped to the Case tenant requests its Case, revisions, or event
timeline
- **THEN** the API SHALL return only records carrying that effective tenant and order
revisions/events deterministically

#### Scenario: A tenant probes another tenant's Case id
- **WHEN** an actor mapped to a different tenant requests a Case, revision sequence, or
event timeline belonging to another tenant
- **THEN** the API SHALL return the same `case_not_found` result used for an absent
Case and SHALL not reveal the foreign tenant, Case metadata, or record count

### Requirement: Intake capability reporting remains truthful and narrowly scoped
The Platform API capability report SHALL distinguish the implemented synthetic Case
intake slice from a completed customer-support workflow. It SHALL keep external writes
and full business-workflow completion disabled in this change.

#### Scenario: Offline capability status is queried after intake is available
- **WHEN** the Platform API reports its capabilities in valid offline configuration
- **THEN** it SHALL identify synthetic Case intake as implemented while reporting
`business_workflow_implemented=false` and `external_writes_enabled=false`

