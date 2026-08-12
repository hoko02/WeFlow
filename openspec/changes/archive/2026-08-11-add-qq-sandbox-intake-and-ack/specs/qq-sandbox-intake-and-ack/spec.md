## ADDED Requirements

### Requirement: QQ sandbox activation is explicit, bounded, and default-deny
WeFlow SHALL initialize a QQ network client only inside the dedicated QQ sandbox
intake-and-ack command after operator-controlled validation binds one sandbox
application, one allowlisted group, one tenant, external credential sources, and the
exact `qq.group_at.read` and `qq.passive_ack.execute` capability profile. All ordinary
commands SHALL remain Replay/offline and SHALL reject QQ credentials, destinations, or
real-write activation before network contact.

#### Scenario: The dedicated command passes every activation gate
- **WHEN** an operator supplies the exact live confirmation, sandbox environment,
  external credentials, one allowlisted group-to-tenant mapping, and bounded capability
  profile
- **THEN** the command MAY initialize the QQ token/gateway/WebSocket transports and
  SHALL report readiness without disclosing any supplied value

#### Scenario: A gate is missing or QQ is requested by an ordinary command
- **WHEN** confirmation, credentials, mapping, environment, or capability scope is
  absent or malformed, or a non-QQ command observes QQ configuration
- **THEN** startup SHALL fail closed before network contact or executor registration
  and SHALL emit only a redacted stable denial reason

### Requirement: Only an allowlisted group mention text event can enter intake
The adapter SHALL accept only a QQ group `@机器人` text event from the configured
application and allowlisted sandbox group with a stable source message identity,
positive gateway sequence, valid occurrence/receipt timestamps, and non-empty text
after mention removal. It SHALL reject direct messages, unrelated group traffic,
attachments, unsupported event types, malformed identities, and unallowlisted groups
before Case creation or acknowledgement intent.

#### Scenario: A customer mentions the robot with an incident
- **WHEN** the allowlisted sandbox group delivers a valid event equivalent to
  `@机器人 广告系统出现了API 503错误`
- **THEN** the adapter SHALL normalize one payload-safe inbound event for the configured
  tenant without collecting unrelated group messages

#### Scenario: An unsupported or foreign QQ event arrives
- **WHEN** the adapter receives a direct message, attachment, non-mention group event,
  empty mention, unsupported event type, malformed identity, or another group
- **THEN** it SHALL append no Case, acknowledgement intent, external write, or
  customer-outcome fact and SHALL expose only a redacted rejection category

### Requirement: QQ identity and content handling are server-owned and payload-safe
WeFlow SHALL derive tenant and conversation only from the server-owned application and
group mapping, and SHALL derive actor/customer references from tenant-scoped hashes of
QQ identities. The normalized event, ledger, telemetry, fixtures, and reports SHALL
contain only allowlisted identifiers/hashes, timestamps, classification, correlation,
and content SHA-256 metadata; they MUST NOT contain raw message text, group transcript,
attachment bytes, display names, credentials, access tokens, unrestricted provider
payloads, or caller-selected authority.

#### Scenario: A valid message is normalized
- **WHEN** an allowlisted QQ message passes boundary validation
- **THEN** raw text SHALL be used only transiently to validate and calculate its digest,
  then discarded before durable business records, logs, reports, fixtures, or prompts
  are produced

#### Scenario: A caller or provider field attempts to select authority
- **WHEN** an event or request supplies a tenant, role, display-name assertion,
  destination override, credential-like field, or raw provider body
- **THEN** deterministic validation SHALL ignore or reject it before Case creation and
  SHALL not leak the supplied value

### Requirement: QQ event deduplication and gateway resume create one Case
The inbound natural key SHALL bind tenant, QQ sandbox provider/application hash,
allowlisted group hash, and source message identity. The control kernel SHALL persist
one durable receipt and atomically create one stable Case, immutable CaseRevision 1,
and the existing three ordered intake BusinessEvents for the first accepted event.
Exact event replay, repeated gateway sequence, reconnect/resume replay, process restart,
or concurrent consumers SHALL return the original result without another Case,
revision, event chain, workflow activation, or acknowledgement intent. A sequence gap
or out-of-order cursor SHALL fail closed into resume/reconciliation without skipping an
unaccounted event.

#### Scenario: QQ redelivers the same event around reconnect
- **WHEN** the same source message arrives more than once with the same business natural
  key before or after a WebSocket resume
- **THEN** one receipt and one initial Case ledger SHALL exist and every retry SHALL
  resolve to that original Case

#### Scenario: Bounded live acceptance replays the same observed event in memory
- **WHEN** an explicitly confirmed live deduplication run accepts one real QQ event and
  then submits that identical in-memory provider frame to the deterministic intake and
  acknowledgement controls a second time
- **THEN** the second pass SHALL return the first Case and acknowledgement intent,
  append no receipt, Case, revision, BusinessEvent, observation, or completion, make no
  second QQ write attempt, and discard the raw frame when the command exits
#### Scenario: A gateway sequence gap is observed
- **WHEN** the next event sequence is not the expected contiguous sequence and the
  source message has no durable receipt
- **THEN** the adapter SHALL not advance the durable cursor or create an
  acknowledgement, and SHALL require resume/reconciliation

#### Scenario: Two consumers race on the same QQ message
- **WHEN** concurrent workers attempt to accept the same tenant and inbound natural key
- **THEN** uniqueness and transaction rules SHALL yield one receipt, one Case ledger,
  and one acknowledgement natural key

### Requirement: A fixed acknowledgement uses a recoverable real-write boundary
Only after the Case intake transaction commits, deterministic control code SHALL create
one immutable QQAcknowledgementIntent for the code-owned passive acknowledgement
template and original allowlisted group message. The intent SHALL bind tenant,
Case/revision, source message, fixed template hash, configured destination, deadline,
natural key, stable idempotency key, original QQ `msg_id`, and one deterministic
positive reply `msg_seq`. Processing SHALL persist intent, reconcile, execute, observe,
and complete in that order; no model, event body, fixture, caller, or QQ user may choose
the message body or destination.

#### Scenario: A new Case receives its acknowledgement
- **WHEN** a valid Case has committed, the passive reply deadline remains valid, the
  bounded capability is active, and reconciliation finds no prior result
- **THEN** the executor SHALL attempt exactly the fixed acknowledgement against the
  source group message and SHALL persist a safe observation before any completion

#### Scenario: An arbitrary reply or destination is requested
- **WHEN** any input requests changed acknowledgement text, another group, a direct
  message, a final answer, attachment, Markdown, link, model output, or caller-selected
  reply sequence
- **THEN** the boundary SHALL deny execution and append no successful completion

### Requirement: Acknowledgement retries never create a second logical send
Recovery SHALL reconcile the original intent and reuse the same QQ source `msg_id` plus
deterministic reply `msg_seq` after restart, timeout, disconnect, or lost response. A
validated provider accepted or provider duplicate/present observation MAY complete the
intent exactly once. An unreadable, conflicting, expired, or still-unknown result SHALL
remain incomplete in `NEEDS_RECONCILIATION` or a safe expired state and SHALL NOT use a
new reply sequence, blindly retry, or claim delivery.

#### Scenario: The provider accepted the acknowledgement but the response was lost
- **WHEN** recovery runs after execution may have taken effect but no observation was
  committed
- **THEN** it SHALL reconcile/retry only with the original provider deduplication tuple,
  record at most one logical completion, and SHALL not create another visible logical
  acknowledgement identity

#### Scenario: The passive reply deadline expires
- **WHEN** an unexecuted or ambiguous intent is recovered after its reply deadline
- **THEN** the executor SHALL make no new send call, retain safe failure/reconciliation
  evidence, and SHALL not change the Case to resolved or complete

#### Scenario: The provider result remains ambiguous
- **WHEN** reconciliation cannot prove accepted, duplicate/present, absent, or safely
  retryable state
- **THEN** the intent SHALL remain incomplete with a redacted reason and no customer
  receipt assertion

### Requirement: QQ acceptance evidence is truthful and independently verifiable
The repository SHALL provide an offline fake-transport acceptance path and a separate
operator-run QQ sandbox acceptance path. Reports SHALL distinguish fake verification
from real sandbox verification, SHALL keep `customer_receipt_verified=false`, and SHALL
contain only safe IDs, hashes, counts, status/reason codes, timings, and explicit
capability flags. This change SHALL NOT initialize a model, handler approval, business
tool, final delivery path, or Case/customer resolution transition.

#### Scenario: Offline CI exercises the QQ slice
- **WHEN** tests inject token, gateway, WebSocket, and send fakes with duplicate,
  reconnect, timeout, lost-response, restart, cross-tenant, unsafe-content, and denial
  cases
- **THEN** the acceptance report SHALL be reproducible without network or credentials,
  set fake verification truthfully, and leave real live verification false

#### Scenario: An operator completes a real sandbox run
- **WHEN** one allowlisted real QQ mention creates a Case and the fixed acknowledgement
  has a validated accepted/present provider result
- **THEN** the report MAY set `qq_sandbox_live_verified=true` while customer receipt,
  issue resolution, final delivery, model use, and production readiness remain false
