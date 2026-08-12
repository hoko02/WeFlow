## ADDED Requirements

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

## MODIFIED Requirements

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
