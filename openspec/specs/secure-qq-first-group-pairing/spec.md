# secure-qq-first-group-pairing Specification

## Purpose
Define the explicit, read-only, payload-safe process for securely pairing one operator-selected QQ sandbox group and handing its short-lived safe pairing ID to the separately gated Stage 1 intake command.

## Requirements

### Requirement: QQ first-group pairing is explicit, read-only, and default-deny
WeFlow SHALL initialize a real QQ client for group pairing only inside the dedicated
pairing command after exact operator confirmation, sandbox AppID/AppSecret credential
sources, one server-owned tenant, a repository-local journal, and the sole
`qq.group_pair.read` capability pass validation. The command MUST reject any supplied
group identifier, passive-send capability, model, business tool, external-write
executor, multi-Agent configuration, or ordinary-command activation before contact.

#### Scenario: The operator starts an authorized pairing session
- **WHEN** the dedicated command receives the exact confirmation, external credentials,
  one tenant mapping, sandbox environment, local journal, and pairing-read capability
- **THEN** it SHALL initialize only token, gateway, and WebSocket read transports and
  SHALL report readiness using hashes and safe status fields

#### Scenario: Pairing requests a destination or write authority
- **WHEN** configuration supplies a `group_openid`, ordinary QQ group number, message
  destination/body, passive acknowledgement capability, model, other external write,
  expanded capability, or repository-external store
- **THEN** activation SHALL fail before HTTP/WebSocket construction and SHALL emit only
  a stable redacted denial reason

### Requirement: One exact challenge proves the operator-selected group
The pairing controller SHALL generate a cryptographically random challenge with at
least 128 bits of entropy, a reserved `WFPAIR-` display prefix, single-use identity,
and a deadline no longer than five minutes. It SHALL accept only one plain-text
`GROUP_AT_MESSAGE_CREATE` whose mention-stripped content exactly matches the current
challenge and whose message identity, member identity, timestamp, Gateway session, and
positive sequence are structurally valid. It MUST reject direct messages, other event
types, nonmatching/expired content, attachments, ARK/cards, nested chat elements,
malformed identities, and caller/provider authority claims without selecting a group.

#### Scenario: The operator sends the challenge in the intended test group
- **WHEN** the current real or fake QQ session receives one valid group mention whose
  text exactly equals the unexpired in-memory challenge
- **THEN** the controller SHALL derive the candidate `group_openid` from that event and
  SHALL not use a nickname, member role, ordinary group number, or caller-supplied group

#### Scenario: Unrelated or unsafe QQ traffic is observed
- **WHEN** the session receives another group message, direct message, attachment,
  card, nested chat record, wrong challenge, expired challenge, malformed event, or
  authority-bearing field
- **THEN** it SHALL create no pairing completion, Case, acknowledgement, QQ write, or
  customer-outcome fact and SHALL expose only a redacted rejection category

### Requirement: Completed pairing is unique, payload-safe, and short-lived
The system SHALL persist immutable pairing challenge and completion facts with stable
schema identity, safe pairing ID, application/group/tenant hashes, challenge and source
message digests, lifecycle timestamps, expiry, status, and correlation metadata. It
SHALL persist the raw `group_openid` only in a private locator row keyed by the safe
pairing ID inside `.weflow/qq-sandbox.sqlite3`, MUST NOT expose it through contracts,
logs, terminal output, fixtures, or reports, and SHALL expire/purge that locator after
at most 24 hours. Challenge plaintext, member OpenID, display data, credentials, access
tokens, raw events, and transcripts MUST NOT be persisted.

#### Scenario: A matching event completes pairing
- **WHEN** one valid challenge event commits for an application and tenant with no
  current conflicting binding
- **THEN** exactly one completion and one private locator row SHALL exist, and the
  command SHALL return only the safe pairing ID plus redacted hashes/status

#### Scenario: Private pairing data reaches a public surface
- **WHEN** a contract, report, fixture, log, diagnostic, or terminal result contains a
  raw group/member/message identifier, challenge plaintext, credential, token, event
  body, or transcript
- **THEN** validation or secret/privacy hygiene SHALL fail and SHALL not publish the
  artifact as accepted evidence

#### Scenario: A pairing expires or is locally revoked
- **WHEN** a locator reaches its retention deadline or the operator invokes the bounded
  local revoke operation for its exact pairing ID
- **THEN** the binding SHALL become unusable without deleting immutable safe pairing
  facts or modifying any Case/acknowledgement record

### Requirement: Pairing restart, replay, race, and conflict fail closed
A pending challenge SHALL not survive process restart because its plaintext is not
durable; restart SHALL cancel or expire it and require a fresh challenge. A committed
completion SHALL be reconstructable by pairing ID. Exact duplicate source delivery,
WebSocket resume, and concurrent consumers SHALL resolve to one completion and locator.
A second group/source for the same challenge, sequence gap, foreign application/tenant,
unreadable locator, or ambiguous commit SHALL remain conflict/reconciliation evidence
and MUST NOT establish or replace a current binding.

#### Scenario: The process stops before completion
- **WHEN** the pairing process restarts after persisting a challenge digest but before
  a completion and locator commit
- **THEN** the old challenge SHALL be unusable, no group SHALL be bound, and a new run
  SHALL generate a different challenge

#### Scenario: The same source event is redelivered or raced
- **WHEN** reconnect/resume, duplicate delivery, restart-after-commit, or concurrent
  consumers process the same challenge and source identity
- **THEN** uniqueness rules SHALL return the original safe pairing ID with one
  completion and one locator row

#### Scenario: Two groups attempt one challenge
- **WHEN** different group or source identities present the same challenge before the
  controller can establish one unambiguous completion
- **THEN** the session SHALL fail closed as a conflict and SHALL not select, replace,
  or expose either raw group identifier

### Requirement: Stage 1 intake resolves exactly one trusted selector mode
The dedicated QQ intake-and-ack activation SHALL accept either its existing direct
authoritative `group_openid` mapping or one current completed pairing ID, never both.
Pairing mode SHALL resolve the raw group locator and server-owned tenant from the local
binding and SHALL verify application hash, current status, expiry, and locator integrity
before constructing intake or send services. Direct mode SHALL remain compatible. A
missing, stale, revoked, expired, foreign, conflicting, or unreadable selector SHALL
fail before Case creation or provider send.

#### Scenario: Intake uses a completed pairing
- **WHEN** the Stage 1 command supplies one current pairing ID, matching AppID
  credentials, process-only identity salt, and the exact Stage 1 capabilities
- **THEN** it SHALL resolve one allowlisted group/tenant mapping without displaying the
  raw locator and MAY proceed to the existing separate intake-and-ack gates

#### Scenario: Selector modes conflict or the binding is stale
- **WHEN** both pairing and direct group selectors are present, a tenant override
  conflicts, or the pairing is absent, foreign, revoked, expired, or corrupt
- **THEN** the command SHALL fail before Case ledger, QQ intake transport, or passive
  send executor construction

### Requirement: Pairing control messages can never become Cases
The `WFPAIR-` text prefix SHALL be reserved across the QQ boundary. The pairing command
MAY consume an exact current challenge only for pairing. The normal QQ intake path SHALL
reject any mention-stripped text beginning with the reserved prefix, including a
redelivered pairing event, before inbound receipt, Case, revision, BusinessEvent,
acknowledgement intent, or provider write creation. Pairing Gateway cursor state SHALL
remain isolated from the Stage 1 business intake cursor.

#### Scenario: A completed pairing message is replayed to intake
- **WHEN** QQ redelivers the original or another `WFPAIR-` mention while the normal
  intake-and-ack command is running
- **THEN** intake SHALL classify it as reserved control traffic and SHALL append no
  business or acknowledgement fact

### Requirement: Pairing evidence distinguishes fake, live, and later Stage 1 proof
The repository SHALL provide offline fake pairing acceptance and a separate operator-run
real QQ pairing report with independent verification. A fake SHALL set only
`fake_pairing_verified=true`. A real report MAY set
`qq_group_pairing_live_verified=true` only for a validated real-adapter completion and
private locator. Every pairing report SHALL keep Case creation, workflow activation, QQ
write attempt, acknowledgement, model invocation, handler binding, customer receipt,
issue resolution, Case completion, and production readiness false, and MUST NOT claim
that the pending Stage 1 intake/ack tasks passed.

#### Scenario: Offline CI exercises pairing
- **WHEN** deterministic fakes cover valid matching, wrong group/content, duplicate,
  race, reconnect, restart, expiry, revoke, conflict, and privacy/security cases
- **THEN** the report SHALL be reproducible without credentials/network, mark only fake
  verification true, and retain real pairing and Stage 1 verification false

#### Scenario: One real sandbox group is paired
- **WHEN** the real command observes the exact challenge and independent verification
  confirms one valid completion/locator with no prohibited effect
- **THEN** pairing live verification MAY be true while intake, acknowledgement,
  customer receipt, resolution, completion, and production readiness remain false
