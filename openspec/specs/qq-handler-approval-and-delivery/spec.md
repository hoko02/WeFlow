# qq-handler-approval-and-delivery Specification

## Purpose
TBD - created by archiving change add-qq-handler-approval-and-delivery. Update Purpose after archive.
## Requirements
### Requirement: Stage 2 activation SHALL be explicit and fail closed

The system SHALL expose a dedicated sandbox handler-workflow command that requires explicit live confirmation, the previously paired Stage 1 group, the active dual-surface handler binding, and the exact Stage 2 capability profile. Missing, stale, mismatched, or additional authority MUST fail before network contact, model invocation, Case mutation, or external write.

#### Scenario: Stage 1 command cannot activate Stage 2

- **WHEN** an operator invokes the Stage 1 intake-and-ack command or an ordinary development command
- **THEN** handler C2C reads, C2C writes, approval decisions, and final delivery remain disabled

#### Scenario: Exact Stage 2 activation succeeds

- **WHEN** the operator supplies the paired group, active handler binding, exact capabilities, and explicit live confirmation
- **THEN** the system enables only the bounded sandbox workflow described by this change

### Requirement: One handler SHALL be bound across group and C2C identity surfaces

The system SHALL bind exactly one intended handler by exact one-time challenges received from the allowlisted group's `member_openid` and the intended C2C `user_openid`, followed by local operator confirmation. Authorization MUST NOT use nickname, QQ number, display text, or provider-reported member role. If no provider-documented cross-surface identity is available, the assurance SHALL be recorded as `operator_confirmed_dual_challenge` and production readiness SHALL remain false.

#### Scenario: Both challenges are confirmed

- **WHEN** exact unexpired group and C2C challenges are observed and the local operator confirms the pair
- **THEN** one active binding links the hashed group member identity and hashed C2C user identity for the paired group and tenant

#### Scenario: Only one surface matches

- **WHEN** only the group challenge or only the C2C challenge matches
- **THEN** no handler authority is created and no workflow capability is enabled

#### Scenario: Display identity is spoofed

- **WHEN** another user copies the handler's nickname, QQ number text, or member-role presentation
- **THEN** every handler command is rejected because the provider identity does not match the binding

### Requirement: Customer issue and handler work SHALL remain confidential

The system SHALL keep the customer issue, handler task context, draft, replacement, rejection, and approval preview out of group messages. It SHALL store at most one normalized redacted customer-issue artifact and one current normalized redacted candidate artifact in the restricted expiring artifact boundary, and SHALL NOT persist a group or C2C transcript.

#### Scenario: Handler is notified

- **WHEN** a new Stage 2 Case is ready for the bound handler
- **THEN** any active C2C notification contains only a Case reference and private pull instruction, and any group nudge contains no customer issue or draft content

#### Scenario: Content appears in a report or ledger

- **WHEN** evidence or business events are emitted
- **THEN** they contain only artifact references, hashes, classifications, lengths, and safe reason codes, never issue or candidate plaintext

### Requirement: Private C2C commands SHALL form a closed handler protocol

The system SHALL accept only `WF-PULL`, `WF-ACCEPT`, `WF-ASSIST`, `WF-DRAFT`, and `WF-REJECT` from the bound C2C `user_openid`, for the paired group, active Case/revision, and expected workflow version. `WF-ASSIST` SHALL be available only in the exact Stage 3 command after private pull/accept and SHALL carry no free-form body. Task details, customer issue, model/human draft preview, safe model/evidence summary, and approval request SHALL be returned only as passive C2C replies to the current private source event.

#### Scenario: Bound handler requests model assistance

- **WHEN** the bound accepted handler submits a valid `WF-ASSIST` for the active version under the exact Stage 3 profile
- **THEN** one handler-authored assist request may run the bounded Agent and any safe outcome is returned only in C2C

#### Scenario: Bound handler drafts privately

- **WHEN** the bound C2C identity submits a valid `WF-DRAFT` for the active version
- **THEN** the system creates or replaces the current candidate, invalidates any prior model/human candidate authority, and returns its bounded preview and approval metadata only in C2C

#### Scenario: Foreign private user sends a command

- **WHEN** an unbound C2C identity sends any handler command
- **THEN** the command fails closed without disclosing Case existence or content and without mutating the Case or contacting the model

#### Scenario: Handler replaces the draft

- **WHEN** the bound handler submits a new valid candidate
- **THEN** the prior candidate, model binding when present, and approval request become unusable before the replacement becomes current

### Requirement: Final approval SHALL be metadata-only in the original group

The system SHALL accept final approval only from a group `WF-APPROVE` command that carries the approval request identifier, candidate hash prefix, and expected version but no candidate body. For a handler-authored candidate, the authoring `member_openid` MUST resolve to the same active dual-surface binding that created it. For a model-assisted candidate, it MUST resolve to the same binding whose C2C side authored the assist request and received the private preview. The model, provider, robot, customer, or another member MUST NOT approve.

#### Scenario: Matching handler approves the current candidate

- **WHEN** the bound group member submits exact current approval metadata for its current private human or model-assisted candidate before expiry
- **THEN** one approval decision is recorded for the exact candidate/provenance, Case revision, binding, and workflow version

#### Scenario: Approval includes candidate text

- **WHEN** a purported approval exposes or replaces the candidate body in the group command
- **THEN** the command is rejected as malformed and no final write is authorized

#### Scenario: Approval is stale or foreign

- **WHEN** the command is authored by another member or references a replaced, expired, foreign, mismatched, unverified, or model-detached candidate/version
- **THEN** no approval decision or external write occurs

### Requirement: Final customer delivery SHALL be a passive group reply to the approval event

After a valid decision, the system SHALL send the exact approved candidate to the original group as a passive reply using the approval event's source `msg_id`, a stable `msg_seq`, and the decision-bound idempotency key. It MUST NOT fall back to an active group send after an unknown outcome or expired passive window.

#### Scenario: Provider accepts the final reply

- **WHEN** the approved candidate is executed within the group passive-reply window and QQ accepts it
- **THEN** provider acceptance is recorded without claiming customer receipt, issue resolution, or Case completion

#### Scenario: Provider result is ambiguous

- **WHEN** the final write times out or has an unknown provider outcome
- **THEN** local reconciliation occurs before any retry and the system never switches to an active group write

### Requirement: Active C2C notification SHALL be attempted at most once

The system SHALL create one durable notification intent and make no more than one active C2C transport attempt for a Case notification. A timeout, disconnect, or unknown response SHALL remain `NOTIFICATION_UNKNOWN`, SHALL NOT be retried, and SHALL NOT be reported as delivered.

#### Scenario: Notification response is accepted

- **WHEN** QQ explicitly accepts the one active C2C attempt
- **THEN** the notification is recorded as provider accepted

#### Scenario: Notification outcome is unknown

- **WHEN** the active C2C attempt has an ambiguous result
- **THEN** the workflow uses a non-sensitive group nudge or later private pull as recovery and sends no second active C2C notification

### Requirement: Acceptance evidence SHALL be layered and privacy-safe

The system SHALL report dual-surface binding, active notification outcome, private workflow verification, group approval verification, final provider acceptance, duplicate/rejected counts, and recovery state separately. Reports MUST contain no credential, raw identity, provider event, transcript, issue text, candidate text, or unrestricted provider response.

#### Scenario: Live acceptance completes

- **WHEN** the live sandbox flow reaches final provider acceptance
- **THEN** the report keeps `model_invocation=false`, `customer_receipt_verified=false`, `issue_resolution=false`, `case_completion=false`, and `production_ready=false`

### Requirement: Handler binding revocation SHALL be explicit, local, and auditable

The system SHALL allow an operator to revoke one active handler binding only through the dedicated Stage 2 command with the safe binding selector, exact local confirmation, and a current Stage 1 pairing whose App, tenant, and group hashes match the binding. Revocation SHALL append one content-free terminal event, immediately make the private execution locators unusable and remove their raw locator values, and SHALL NOT rewrite or delete the immutable binding record. It MUST perform no provider contact, Case mutation, model invocation, or external write.

#### Scenario: Stage 1 expires before the handler binding

- **WHEN** the operator first pairs the same sandbox group again and explicitly revokes the old active binding
- **THEN** the old authority and private locators become unusable, one revocation event is retained, and a fresh dual-surface pairing may create the replacement binding

#### Scenario: Revocation scope is foreign or stale

- **WHEN** the current Stage 1 pairing does not match the binding's App, tenant, and group, or the local confirmation is absent or incorrect
- **THEN** revocation fails closed without changing binding, locator, Case, provider, or external-write state

#### Scenario: Revocation command is repeated

- **WHEN** the operator repeats the exact revocation for an already revoked binding
- **THEN** the existing terminal result is returned without another event, provider call, or locator mutation

### Requirement: Stage 3 handler activation SHALL preserve the archived manual Stage 2 boundary

The dedicated Stage 3 command SHALL require every current Stage 1/Stage 2 selector, handler identity, content, approval, and QQ write gate plus separate explicit live-model authorization and exact model/read capability profile. The archived Stage 2 command SHALL continue to reject model configuration and SHALL retain its manual-only behavior and `model_invocation=false` acceptance semantics.

#### Scenario: Stage 3 is not authorized

- **WHEN** the operator runs Stage 2 normally or omits any Stage 3 confirmation, capability, profile, credential, or current binding
- **THEN** no model client or assist request is constructed and the handler may use only the existing manual protocol

#### Scenario: Exact Stage 3 command is active

- **WHEN** all paired group/handler, QQ, model, profile, budget, and local confirmation gates pass
- **THEN** only the new private assist command is added; every existing identity, confidentiality, approval, reply-window, and final-write restriction remains enforced

### Requirement: Model candidate preview and evidence summary SHALL remain private

The system SHALL return a verifier-authorized model candidate, bounded evidence/source summary, safe model outcome, usage/budget summary, and group-safe approval metadata only as a passive C2C reply to the current bound handler source event. The original group SHALL receive no issue, prompt, tool observation, draft, model reasoning, preview, usage, or provider detail before the exact final approved reply.

#### Scenario: Model candidate reaches RESPONSE_READY

- **WHEN** the current handler assist request produces a verified candidate
- **THEN** the handler receives its bounded private preview and may replace it or approve its metadata, while the group sees no candidate content

#### Scenario: Model investigation fails safely

- **WHEN** the outcome is needs-information/operator, tool timeout, budget exhaustion, policy denial, malformed output, or provider unknown
- **THEN** only the bound handler receives a bounded safe explanation and manual drafting remains available without a model retry or group disclosure

### Requirement: Integrated acceptance evidence SHALL not overwrite Stage 2 evidence semantics

Stage 3 SHALL publish a separate acceptance report that records live-model invocation, synthetic tool/evidence lineage, model candidate verification, bound-handler initiation/private preview, exact group approval, final QQ provider acceptance, and content deletion independently. It MUST NOT alter a Stage 2 report to set `model_invocation=true` or infer model quality/customer outcomes from the integrated run.

#### Scenario: Integrated live flow is independently verified

- **WHEN** one real sandbox flow completes every Stage 3 layer
- **THEN** the Stage 3 report records the integrated facts while Stage 2 reports remain valid historical no-model evidence and customer receipt/resolution/completion/production remain false
