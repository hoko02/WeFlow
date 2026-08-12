## ADDED Requirements

### Requirement: QQ C2C runtime access SHALL be bounded to the paired handler workflow

The provider boundary SHALL expose only normalized C2C message reads for the bound handler, one minimal active notification operation, and passive replies to accepted C2C source events. It SHALL NOT expose unrestricted provider payloads, raw credentials, arbitrary recipients, arbitrary active messages, general chat history, or a reusable QQ sender to domain or model code.

#### Scenario: Domain requests an arbitrary C2C recipient

- **WHEN** the requested recipient is not the active binding's private provider locator
- **THEN** the provider boundary rejects the operation before network contact

#### Scenario: Notification includes private content

- **WHEN** an active notification contains the customer issue, draft, preview, or unrestricted text
- **THEN** the boundary rejects it and consumes no transport attempt

### Requirement: Group runtime access SHALL separate approval reads from final replies

The boundary SHALL normalize allowlisted group `@机器人` approval events and expose a passive final-reply operation bound to the accepted approval source. It SHALL NOT expose active group send fallback or allow group messages containing private issue, task, draft, or preview content.

#### Scenario: Final reply lacks approval source metadata

- **WHEN** execution does not include the exact valid approval source `msg_id` and stable `msg_seq`
- **THEN** the boundary rejects the write

#### Scenario: QQ omits the mention token from normalized approval content

- **WHEN** QQ emits `GROUP_AT_MESSAGE_CREATE` for the paired group and bound member while its
  normalized content begins directly with the exact `WF-APPROVE` metadata
- **THEN** the provider boundary treats the verified event type as mention proof and applies the
  same closed metadata parser, while identical text outside that provider event remains unable to
  authorize approval

### Requirement: Provider data SHALL be minimized before crossing the boundary

The boundary SHALL validate provider opcode/event kind, bot application, paired group or bound C2C user, mention/command shape, message identity, timestamp, and bounded content before producing a versioned domain envelope. Raw events, transcripts, credentials, and unrestricted provider responses SHALL not be persisted.

#### Scenario: Foreign group or C2C user sends a valid-looking command

- **WHEN** an event is outside the paired group or active private binding
- **THEN** it is rejected with a safe classification and no Case disclosure or external write

### Requirement: Provider failure classes SHALL remain explicit

The boundary SHALL distinguish accepted, rejected, rate-limited, expired-window, disconnected, timed-out, and unknown outcomes. It SHALL preserve the different recovery rules for active C2C notification and passive C2C/group replies.

#### Scenario: Active notification times out

- **WHEN** the provider outcome is unknown after the one active attempt
- **THEN** the boundary returns an ambiguous outcome that cannot be converted into success or retried by domain code

#### Scenario: Passive group reply is rejected as duplicate

- **WHEN** QQ identifies the same source `msg_id` and `msg_seq` as already processed
- **THEN** reconciliation uses existing content-free evidence and does not create a new active send
