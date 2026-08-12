# bounded-live-model-qq-workflow Specification

## Purpose
Define the explicit, handler-triggered Stage 3 composition of bounded QQ workflow and live-model investigation while preserving deterministic policy, approval, delivery, privacy, budget, recovery, and outcome boundaries.

## Requirements

### Requirement: Stage 3 activation SHALL be explicit, combined, and fail closed

The system SHALL expose one dedicated sandbox Stage 3 command that requires explicit live QQ and live-model confirmations, a current Stage 1 pairing, an active matching dual-surface handler binding, exact QQ and model capability profiles, current prompt/provider/price profiles, hard budgets, and process-only credentials. Missing, stale, mismatched, additional, or caller/model-selected authority MUST fail before either network client is constructed, a credential is read, a Case is mutated, a model is invoked, or an external write is attempted.

#### Scenario: Exact Stage 3 preflight succeeds

- **WHEN** the local operator supplies every current selector, profile, capability, budget, confirmation, and process-only credential for the same sandbox App, tenant, group, and handler
- **THEN** the command enables only bounded QQ intake/ack, handler C2C, one model-assisted investigation, exact human approval, and passive final reply for that process

#### Scenario: An ordinary or earlier-stage command sees Stage 3 configuration

- **WHEN** normal startup, CI, Replay, Stage 1, Stage 2, or an unrelated development command observes a live-model credential or Stage 3-only capability
- **THEN** it fails before model/QQ contact and grants no combined authority

### Requirement: Only the bound handler SHALL trigger model assistance

The system SHALL accept `WF-ASSIST <case_id> <expected_version>` only as a private C2C command from the active bound handler after that identity has pulled and accepted the current Case. Customer intake, acknowledgement, notification, pull, accept, group text, duplicate delivery, model output, and provider output MUST NOT independently trigger a model invocation.

#### Scenario: Bound handler requests assistance

- **WHEN** the bound C2C identity sends an exact current `WF-ASSIST` command for its accepted Case with an unexpired issue artifact and sufficient budget
- **THEN** the control kernel records one version-bound assist request and may begin the bounded single-Agent investigation

#### Scenario: Customer or foreign user copies the command

- **WHEN** the command arrives from the group, an unbound C2C user, another tenant/group, or a stale Case/version
- **THEN** it is rejected without disclosing Case existence or content and without model contact, Case mutation, approval, or QQ write

### Requirement: Model Context SHALL contain only bounded redacted Case and synthetic evidence views

The system SHALL compile a versioned model Context from server-owned Case/revision, handler-workflow, policy/capability, budget, prompt/profile, and source hashes; one normalized redacted view of the restricted customer-issue artifact; and only the existing tenant-scoped fixture CRM, monitoring, and knowledge observations. It SHALL NOT include raw QQ identities/locators/events, nicknames/roles, transcripts, handler or approval commands, credentials, unrestricted provider/tool output, or content from another tenant or Case.

#### Scenario: A valid sandbox issue enters the prompt

- **WHEN** the accepted issue passes the model-safe classification, redaction, length, retention, tenant, and source checks
- **THEN** only its bounded untrusted issue view and source hash enter the ephemeral prompt

#### Scenario: Issue or tool content is unsafe

- **WHEN** content is secret-like, raw/private beyond policy, over-limit, foreign, detached, expired, prompt-injecting, or schema-invalid
- **THEN** the attempt stops before the affected provider call and persists only a safe classification and hashes

### Requirement: The integrated Agent SHALL stop at RESPONSE_READY or a safe handler outcome

The system SHALL run exactly one closed Agent per assist request under deterministic action, tool, call, token, time, cost, and no-progress budgets. The reviewed Stage 3 profile SHALL enforce a cumulative estimated-cost hard limit of USD 0.50 per Case without modifying or enlarging the retained USD 0.02 live-evaluation attempt budget. The model may request only allowlisted fixture reads or propose `needs_information`, `needs_operator`, or a response candidate. Only the deterministic verifier and control kernel may advance the current Case workflow to `RESPONSE_READY`; no model proposal may approve, deliver, resolve, complete, select a destination, or change authority.

#### Scenario: Evidence-grounded candidate is verified

- **WHEN** the Agent produces a safe candidate bound to complete current matching evidence and every budget/policy/verifier gate passes
- **THEN** the control kernel records one current model-assisted candidate at `RESPONSE_READY` and makes it available only to the bound handler's private workflow

#### Scenario: Investigation stops safely

- **WHEN** evidence is missing/conflicting, a tool times out, a budget is exhausted, output is malformed/unsafe, policy denies, or the provider outcome is unknown
- **THEN** the system records the named safe outcome, performs no approval or QQ final write, and preserves the handler's manual `WF-DRAFT` path

### Requirement: Model recovery SHALL not duplicate logical turns or effects

Every assist request, logical turn, invocation intent/observation, normalized action, tool result, candidate, verifier result, approval, and QQ effect SHALL have stable natural identities and append-only correlation/causation links. Recovery SHALL reuse conclusive evidence, SHALL classify an invocation intent without conclusive observation as `provider_outcome_unknown`, and MUST NOT blindly repeat that call or create another candidate, approval, acknowledgement, notification, or final reply.

#### Scenario: Worker restarts after a conclusive model turn

- **WHEN** the durable invocation observation, normalized action, and tool/candidate outcome are complete
- **THEN** recovery reuses them without another provider call or logical transition

#### Scenario: Worker restarts after ambiguous model contact

- **WHEN** an invocation intent exists without a conclusive observation
- **THEN** that assist request stops as outcome unknown, its reserved budget remains accounted, and only a fresh later handler command with a new version may request another bounded attempt

### Requirement: Human replacement and approval SHALL remain authoritative

A verified model candidate SHALL become at most the current restricted candidate initiated by the bound handler. The handler SHALL receive its preview and safe evidence summary only in C2C, MAY replace it through current-version `WF-DRAFT`, and MUST approve the exact current candidate through the existing metadata-only group command before final QQ delivery. Replacement SHALL invalidate and delete/schedule deletion of the model candidate and invalidate every linked approval request or decision before the human candidate becomes current.

#### Scenario: Handler approves the model candidate unchanged

- **WHEN** the initiating bound handler reviews the private preview and submits exact current approval metadata from the linked group identity
- **THEN** one decision may authorize only the Stage 2 passive final reply for the exact model/evidence/candidate binding

#### Scenario: Handler edits the model candidate

- **WHEN** the bound handler submits a valid `WF-DRAFT` at the current version
- **THEN** all model-candidate approval authority becomes stale before the human replacement receives a new preview and approval request

### Requirement: Stage 3 acceptance evidence SHALL be layered, content-free, and independently verifiable

The system SHALL publish separate offline-fake and real QQ-plus-model report types. The real report SHALL distinguish QQ intake/ack, handler binding/private workflow, live model contact, invocation/tool/evidence lineage, candidate verification, human approval, artifact deletion, and final QQ provider acceptance from customer receipt, issue resolution, Case completion, model quality, and production readiness. Reports MUST contain no credential, raw identity/locator/event, transcript, issue/draft/prompt body, unrestricted tool/provider response, or caller-supplied success claim.

#### Scenario: Real integrated acceptance completes

- **WHEN** one controlled sandbox Case reaches a verifier-authorized real-model candidate, exact human approval, content deletion evidence, and one provider-accepted passive QQ final reply
- **THEN** the report may set the corresponding integration facts true while keeping `customer_receipt_verified=false`, `issue_resolution=false`, `case_completion=false`, and `production_ready=false`

#### Scenario: Fake or partial evidence is presented as live

- **WHEN** either provider is fake/Replay, an invocation or approval/final effect is missing/ambiguous, lineage or budgets fail, or report integrity is invalid
- **THEN** independent verification fails and no live-integrated acceptance claim is published

### Requirement: Manual Stage 2 and offline Replay SHALL remain independently usable

The system SHALL preserve the archived manual-only Stage 2 `WF-DRAFT` flow and every no-credential Replay/offline command when Stage 3 is disabled, rolled back, misconfigured, or unavailable. Stage 3 installation MUST NOT make ordinary startup credential-aware or change prior zero-model/zero-network acceptance semantics.

#### Scenario: Operator runs manual Stage 2 without a model key

- **WHEN** the existing Stage 2 command receives only its exact archived configuration
- **THEN** the handler may complete the existing manual workflow while model invocation remains impossible

#### Scenario: Credential-free CI runs after Stage 3 is installed

- **WHEN** CI executes contracts, Replay, fake-provider, recovery, and retained acceptance checks without QQ/model credentials or network
- **THEN** all deterministic checks run and real Stage 3 acceptance is reported as not run rather than passed
