# versioned-domain-contracts Specification

## Purpose
Define the versioned, language-neutral domain contracts and compatibility rules shared across WeFlow boundaries.
## Requirements
### Requirement: Canonical versioned domain schemas exist
WeFlow SHALL maintain language-neutral JSON Schema files under a versioned contract
directory. Each boundary object SHALL declare a stable schema identifier and
`schema_version`. Compatible v1 schemas SHALL cover retained boundary objects plus
ContextManifest, AgentAction, ToolRequest, ToolResult, ResponseCandidate,
VerifierOutcome, CapabilityGrant, PolicyDecision, AuthorizationBinding,
ApprovalRequest, ApprovalDecision, OutboundDeliveryIntent,
OutboundDeliveryObservation, OutboundDeliveryCompletion, Artifact,
EvidenceTrajectory, EvidenceReport, and TrajectoryReplayResult. Each investigation,
authorization, and evidence boundary SHALL have stable schema identity/version,
tenant/Case/revision linkage where applicable, forbid undeclared/raw fields, and
validate in Python and TypeScript.

#### Scenario: A valid contract fixture is consumed cross-language
- **WHEN** a valid `v1` fixture for each supported boundary object is validated by the
  Python and TypeScript contract packages
- **THEN** both packages SHALL accept the fixture under the same schema identifier and
  version

#### Scenario: A required version or schema identity is absent
- **WHEN** a boundary payload omits its declared schema identity or `schema_version`
- **THEN** both contract packages SHALL reject the payload with a deterministic
  validation result

#### Scenario: New Agent boundary fixtures validate cross-language
- **WHEN** valid and invalid replay Agent fixtures are consumed by both contract
  packages
- **THEN** both SHALL agree on acceptance and rejection while retained v1 fixtures
  remain valid

#### Scenario: New authorization and delivery fixtures validate cross-language
- **WHEN** valid and invalid Capability, Policy, AuthorizationBinding, approval, and
  outbound-delivery fixtures are consumed by both contract packages
- **THEN** both SHALL agree on acceptance and rejection while all retained v1 fixtures
  remain valid
#### Scenario: Evidence trajectory fixtures validate cross-language
- **WHEN** valid and invalid Artifact, EvidenceTrajectory, EvidenceReport, and
  TrajectoryReplayResult fixtures are consumed by both contract packages
- **THEN** both SHALL agree on acceptance and rejection while every retained v1 fixture
  remains valid

### Requirement: Case, event, artifact, and evidence invariants are representable
Every tenant-scoped contract SHALL contain `tenant_id`. A Case SHALL have a stable case identity; every CaseRevision SHALL identify its case, be immutable, and carry a monotonic revision value and predecessor reference when applicable. A BusinessEvent SHALL have a unique event identity, case reference, event type, occurrence time, receipt time, correlation metadata, and causation metadata when available. Artifact and EvidenceReference contracts SHALL identify content by cryptographic hash and SHALL carry media type and redaction classification rather than raw private payloads.

#### Scenario: A revision changes after initial capture
- **WHEN** a fixture represents an update to a case after an initial revision exists
- **THEN** it SHALL represent the update as a new immutable CaseRevision with the same case identity, a greater revision value, and a predecessor reference instead of mutating the original revision

#### Scenario: A cross-tenant evidence reference is supplied
- **WHEN** a contract fixture links a tenant-scoped case or revision to evidence with a different `tenant_id`
- **THEN** the contract-validation test suite SHALL reject the fixture as an invalid tenant boundary

### Requirement: Duplicate and out-of-order delivery are distinguishable without a side effect
ExternalWriteIntent SHALL require tenant identity, provider identifier, operation, natural key, intended-state hash, stable idempotency key, case/revision reference, and evidence references. The fixture corpus SHALL preserve event occurrence and receipt ordering separately so duplicate and out-of-order delivery can be tested without mutating an event or executing a provider action.

#### Scenario: A duplicate delivery is replayed
- **WHEN** two synthetic deliveries describe the same tenant, provider, operation, natural key, and intended-state hash
- **THEN** the fixtures SHALL resolve to the same stable idempotency key and SHALL NOT contain an execute or complete record for an external side effect in Change 0

#### Scenario: Events arrive out of order
- **WHEN** a replay fixture receives a later-occurring BusinessEvent before an earlier-occurring related BusinessEvent
- **THEN** validation SHALL preserve both occurrence and receipt metadata, classify the fixture as out-of-order for test purposes, and SHALL NOT rewrite either event or case revision

### Requirement: Policy and approval bindings cannot be silently reused
PolicyDecision, CapabilityGrant, AuthorizationBinding, ApprovalRequest, and ApprovalDecision contracts SHALL bind their decision context to tenant, Case, Case
revision, workflow/checkpoint, requested action/resource/data classification, current
candidate hash, ordered evidence hashes, policy version/hash, capability grant
version/hash/status, creation time, and expiry where applicable. An approval decision
SHALL reference the approval request and exact authorization binding it decides.
Contract validation utilities SHALL classify an expired, revoked, foreign,
role/scope-mismatched, candidate/evidence/policy/grant-mismatched, or revision/
checkpoint-mismatched approval as not authorized for a later action.

#### Scenario: An approval becomes stale after a revision changes
- **WHEN** an approval decision bound to one Case revision or evidence hash is evaluated
  against a newer revision or different evidence hash
- **THEN** the validation utility SHALL classify the approval as stale and not
  authorized, and SHALL NOT emit a completion or external-write authorization result

#### Scenario: A policy or Capability Grant changes after approval
- **WHEN** an approval decision is evaluated with a different policy hash/version,
  Capability Grant hash/version/status, action, resource, data classification, or
  authorization binding
- **THEN** the validation utility SHALL classify it as unauthorized before a delivery
  intent can be created

### Requirement: Contract evolution is checked rather than implied
The repository SHALL retain valid and invalid synthetic fixtures for every published `v1` schema and SHALL run a compatibility check before accepting a contract change. Incompatible semantics MUST use a new major-version contract directory rather than silently changing a consumed `v1` schema.

#### Scenario: A contract change invalidates a prior fixture
- **WHEN** a proposed schema change causes a retained compatible `v1` fixture to fail validation
- **THEN** the compatibility check SHALL fail until the change is made compatible or is introduced under a new major-version schema path

### Requirement: Inbound and projection contracts preserve safe intake identity
`InboundMessageEvent` SHALL require tenant, synthetic channel, channel event,
conversation, sender, customer, positive conversation-sequence, occurrence/receipt,
correlation, synthetic classification, and content-hash fields. It SHALL reject raw
message text, attachment bytes, secrets, and undeclared properties. `CaseProjection`
SHALL require tenant, Case identity, latest immutable revision reference, derived state,
source event reference, event count, correlation metadata, and safe timestamps.

#### Scenario: A normalized synthetic inbound envelope validates
- **WHEN** a fixture supplies all required safe identity, sequence, timestamp,
correlation, synthetic-classification, and SHA-256 fields under the inbound schema
- **THEN** Python and TypeScript validators SHALL accept it without requiring raw
customer content

#### Scenario: An inbound envelope contains raw or undeclared content
- **WHEN** a fixture adds a message body, attachment bytes, credential-like field, or
other undeclared property to an inbound envelope
- **THEN** both validators SHALL reject it under the canonical `v1` schema

### Requirement: Compatible v1 source contracts represent ordered safe ledger records
The compatible `v1` Case, CaseRevision, and BusinessEvent schemas SHALL support
additive safe intake metadata needed by this change, including Case channel/conversation
and customer references, revision source-event/fingerprint references, and event index
and canonical payload digest. Existing retained `v1` fixtures that predate these
additive fields SHALL remain valid; Change 1-produced source records SHALL populate the
fields required by the Case ledger service.

#### Scenario: Existing v1 fixtures remain compatible
- **WHEN** the retained Change 0 valid and semantic fixture corpus is validated after
the additive intake-contract update
- **THEN** every fixture that was previously valid SHALL remain valid and its
cross-language compatibility result SHALL remain unchanged

#### Scenario: A generated ledger event lacks safe ordering evidence
- **WHEN** Change 1 ledger validation evaluates a newly generated BusinessEvent without
its required per-Case event index or canonical payload digest
- **THEN** the ledger validation utility SHALL reject the generated record before it is
persisted or exposed as an accepted timeline event

### Requirement: Contract compatibility records intentional additive evolution
The contract compatibility command SHALL validate new inbound/projection valid and
invalid fixtures alongside all retained `v1` fixtures. It SHALL record an intentional
updated schema fingerprint only after both language consumers accept the compatible
corpus and reject the invalid corpus; an incompatible required-field or semantic change
MUST use a new major-version directory.

#### Scenario: A proposed v1 update breaks a retained consumer fixture
- **WHEN** a contract edit causes any retained valid `v1` fixture to fail in either
language consumer
- **THEN** the compatibility command SHALL fail until the edit is made compatible or
the change is moved to a new major-version contract path

### Requirement: Workflow control contracts are tenant-bound, immutable, and payload-safe
WorkflowProjection, WorkflowCheckpoint, WorkflowCommand, and SyntheticSlaPolicy SHALL
identify effective tenant, Case, CaseRevision, stable workflow identity/version, and
safe correlation/timing metadata. A checkpoint SHALL have a monotonic sequence and
canonical content hash. A command SHALL have a stable command identity, allowlisted
command type, and expected workflow version, and SHALL NOT contain a caller-selected
target state, tenant, raw customer content, secret, credential, provider configuration,
or unrestricted tool output.

#### Scenario: A valid workflow checkpoint and command validate cross-language
- **WHEN** a synthetic fixture contains a checkpoint, an allowlisted version-checked
  command, and a fixture-defined SLA policy with all required safe references
- **THEN** Python and TypeScript validators SHALL accept the same `v1` payloads without
  requiring model, provider, or customer data

#### Scenario: A workflow command attempts arbitrary authority
- **WHEN** a workflow command fixture supplies another tenant, a direct Case state,
  raw message content, credential-like data, an unallowlisted command type, or omits
  its expected workflow version
- **THEN** both validators SHALL reject it before it can authorize a transition or
  effect

### Requirement: Side-effect recovery contracts distinguish intent, observation, and completion
SideEffectIntent, SideEffectObservation, and SideEffectCompletion SHALL be distinct,
immutable tenant-scoped records. An intent SHALL carry the stable natural key,
idempotency key, intended-state hash, Case/revision, causal checkpoint, operation, and
safe evidence references. An observation and completion SHALL reference that intent and
record only safe outcome identity/version/hash metadata. The schemas SHALL represent an
unknown or conflicting observation without representing it as complete or authorized
for an external provider.

#### Scenario: An interrupted ticket operation is represented without duplication
- **WHEN** a fixture records one ticket intent, an unknown observation, and a later
  reconciled observation/completion for the same idempotency key
- **THEN** validation SHALL retain the phase order and identity references without
  producing a second intent or an external-write authorization

#### Scenario: A completion is detached from its intent or tenant
- **WHEN** an observation or completion has a missing intent reference, a different
  tenant/Case/revision, an invalid version, or raw provider output
- **THEN** contract validation SHALL reject the fixture as an invalid recovery boundary

### Requirement: Workflow contract evolution preserves existing v1 safety fixtures
The contract compatibility command SHALL validate the new workflow/recovery corpus
alongside every retained Change 0/1 valid, invalid, duplicate-delivery, out-of-order,
cross-tenant, and stale-approval fixture. New workflow fields SHALL be additive for
retained `v1` consumers; a required-field or semantic incompatibility MUST use a new
major-version contract directory.

#### Scenario: A workflow contract edit breaks a retained fixture
- **WHEN** a proposed `v1` workflow/recovery schema edit causes any retained valid
  fixture to fail in either language consumer
- **THEN** the compatibility check SHALL fail until the edit is compatible or is moved
  to a new major-version schema path

#### Scenario: Retained stale approval input is supplied to a workflow boundary
- **WHEN** the existing stale-approval fixture is evaluated alongside a Change 2
  workflow or side-effect record
- **THEN** validation SHALL keep it unauthorized and SHALL not convert it into a
  workflow command, completion, or external-write authorization

### Requirement: Outbound delivery contracts are distinct, safe, and recoverable
WeFlow SHALL maintain OutboundDeliveryIntent, OutboundDeliveryObservation, and
OutboundDeliveryCompletion as distinct immutable tenant-scoped contracts rather
than aliases of ticket side-effect contracts. An intent SHALL bind Case/revision,
workflow/checkpoint, channel/conversation resource, candidate hash, authorization
binding hash, natural key, idempotency key, and safe evidence references. An
observation and completion SHALL reference that intent and expose only safe local
outcome identity/version/hash metadata; they SHALL represent unknown/conflicting
outcomes without representing a customer-success assertion.

#### Scenario: A valid fixture delivery recovery chain validates
- **WHEN** a fixture records one delivery intent, an unknown or present observation,
  and a reconciled completion for the same natural/idempotency key
- **THEN** both contract packages SHALL preserve the chain and reject a duplicate intent
  or an unauthorized completion

#### Scenario: A delivery contract contains raw or foreign authority data
- **WHEN** a delivery fixture contains raw message text, secret/credential data, a
  foreign tenant, mismatched binding, or detached intent reference
- **THEN** contract validation SHALL reject it before it can authorize or report a
  delivery

### Requirement: Evidence contracts bind replay to a redacted immutable trajectory
The system SHALL require Artifact, EvidenceTrajectory, EvidenceReport, and
TrajectoryReplayResult contracts to bind their effective tenant, stable identity,
schema version, safe classification, content/root hash, and source trajectory identity
where applicable. A trajectory SHALL contain only ordered typed safe node references to
Case/revision/workflow and existing source facts; a replay result SHALL bind both
recorded and replayed roots plus a fixed verification outcome/failure code. Contract
validation SHALL reject raw customer or
tool content, credentials, caller-selected authority, foreign references, missing/
duplicate/out-of-order node identities, detached report/replay references, invalid hash,
or any customer-success claim.

#### Scenario: A complete fixture-local report chain validates
- **WHEN** a fixture contains a classified Artifact, canonical EvidenceTrajectory,
  redacted EvidenceReport, and matching TrajectoryReplayResult for one tenant
- **THEN** both contract packages SHALL accept the chain without requiring a provider,
  network request, external delivery payload, or customer outcome

#### Scenario: A trajectory or report is detached or unsafe
- **WHEN** a fixture contains a foreign node, missing causal reference, changed root,
  raw payload, secret-like value, invalid outcome code, or customer-resolution field
- **THEN** both contract packages SHALL reject it before it can be persisted, replayed,
  or exposed

### Requirement: Benchmark-core contracts are versioned, payload-safe, and compatible
WeFlow SHALL maintain language-neutral v1 schemas for `EvaluationTask`,
`EvaluationOracle`, `GraderResult`, `RunMetrics`, and `EvaluationSuiteReport` alongside
the retained `EvaluationCase` and `EvaluationResult` schemas. Each benchmark boundary
SHALL declare stable schema identity/version, forbid undeclared fields, carry tenant,
suite/task/run, fixture/oracle, and SHA-256 linkage where applicable, and contain only
safe IDs, hashes, enumerations, counts, reason codes, and explicit capability flags.
The schemas SHALL reject raw customer/prompt/context/tool/adapter data, credentials,
caller-selected authority, external provider/delivery claims, customer receipt,
resolution, and Case-completion assertions.

#### Scenario: A valid benchmark task and result validate cross-language
- **WHEN** a valid offline benchmark-core task, oracle, grader result, metrics, suite
  report, and linked evaluation result fixture are consumed by Python and TypeScript
  validators
- **THEN** both packages SHALL accept the same schema identities and versions while all
  retained valid v1 fixtures remain valid

#### Scenario: A benchmark boundary contains unsafe or foreign data
- **WHEN** a benchmark contract has raw/secret-like content, an undeclared field, a
  caller-selected authority, a foreign tenant/reference, an invalid hash, or a
  customer-success or external-provider assertion
- **THEN** both validators SHALL reject the fixture before it can become a task input or
  report output

### Requirement: Benchmark-profile results are complete without breaking retained v1 fixtures
Existing `EvaluationCase` and `EvaluationResult` schemas SHALL evolve only additively.
Legacy v1 fixtures without the benchmark profile SHALL remain valid. When an
`EvaluationResult` declares the `benchmark-core.v1` profile, semantic validation SHALL
require safe linkage to its task and oracle hashes, named hard-gate results,
deterministic grader-result and metrics references, explicit offline/Replay/no-network/
no-model/no-external-write flags, and a canonical report reference. A failed hard gate
or oracle-integrity failure SHALL require `quality_score=not_scored`; a numeric quality
score SHALL be allowed only when every applicable hard gate passes.

#### Scenario: A retained foundation evaluation result is revalidated
- **WHEN** the retained v1 evaluation-case and evaluation-result fixtures are validated
  without a `benchmark-core.v1` profile
- **THEN** both language consumers SHALL preserve their existing acceptance result

#### Scenario: A benchmark-profile result is incomplete or mis-scored
- **WHEN** a `benchmark-core.v1` result omits a required safe linkage/flag, refers to a
  different task or oracle hash, reports a numeric quality score after a failed hard
  gate, or marks an external/customer-success claim as true
- **THEN** both language consumers SHALL reject it with a deterministic validation
  result

### Requirement: Benchmark runtime records are materially linked
The benchmark runtime SHALL emit benchmark-profile `EvaluationCase` and
`EvaluationResult` records for every graded task. Their tenant, suite/task, task/oracle
hashes, hard-gate result, capability flags and grader/metrics/report references SHALL
match the emitted records, and `EvaluationSuiteReport.task_result_ids` SHALL identify
the emitted EvaluationResult records.

#### Scenario: A runner emits a benchmark task result
- **WHEN** a safe offline task is graded successfully or fails a hard gate
- **THEN** Python and TypeScript-compatible runtime records SHALL retain one complete
  hash-bound evaluation chain and use `not_scored` for every failed applicable gate

### Requirement: Evaluation suite snapshots are closed, content-addressed and compatible
WeFlow SHALL maintain a language-neutral compatible v1 `EvaluationSuiteSnapshot`
schema for the read-only offline evaluation console boundary. The snapshot SHALL bind
tenant, suite/profile, acceptance and repeated-baseline state, suite/report and
snapshot hashes, aggregate counts, fixed capability flags, and an ordered array of
safe task views. Each task view SHALL bind its fixture/source/task/oracle/result
identities and hashes, result/failure classification, hard-gate and quality-dimension
outcomes, existing offline metrics, and safe observation facts. It SHALL forbid
undeclared/raw fields, absolute paths, credentials, caller authority, unrestricted
tool/adapter content, live-provider/customer-success claims, and any workflow,
approval, delivery, retry, or external-write authority.

#### Scenario: A valid evaluation snapshot is consumed cross-language
- **WHEN** a complete snapshot derived from the accepted `offline-seed.v1` report is
  validated by the Python and TypeScript contract packages
- **THEN** both packages SHALL accept the same closed payload, canonical snapshot hash,
  ordered result links, hard-gate semantics, counts, and capability flags

#### Scenario: A snapshot is detached, unsafe or misleading
- **WHEN** a snapshot has a foreign tenant, mismatched suite/report/result/source hash,
  duplicate or missing task/result ID, count mismatch, numeric quality after a failed
  gate, undeclared/raw/secret-like field, absolute path, caller authority, live-
  provider claim, customer-success claim, or external-write capability
- **THEN** both contract packages SHALL reject it before the snapshot can be served or
  rendered

#### Scenario: Retained evaluation contracts remain compatible
- **WHEN** all retained valid and invalid v1 evaluation fixtures are revalidated after
  the additive snapshot schema is introduced
- **THEN** their prior acceptance/rejection results SHALL remain unchanged and the new
  schema fingerprint SHALL be recorded only after cross-language compatibility passes

### Requirement: Operator Case snapshots are closed, source-linked and compatible
WeFlow SHALL maintain a language-neutral compatible v1 `OperatorCaseSnapshot` schema
for the fixed offline Case workspace boundary. The snapshot SHALL bind schema and
content-addressed snapshot identity, effective tenant, allowlisted fixture, stable
Case/revision/workflow identity, current fixture state, canonical source-report and
evidence/replay roots, aggregate counts, and explicit offline capability flags. Each
ordered timeline entry SHALL bind a unique contiguous sequence and stable identity to
an allowlisted source record type, source record identity/hash, phase, bounded state
transition or observation, result, gate/recovery classification, and safe reason code.
The contract SHALL forbid undeclared or arbitrary payload maps, raw customer/prompt/
tool/provider content, absolute or escaping paths, credentials, caller authority,
executable content, live provider/customer-success assertions, and workflow, approval,
retry, delivery, completion, or external-write authority.

#### Scenario: A valid operator snapshot is consumed cross-language
- **WHEN** a complete snapshot generated from the accepted API-503 durable source chain
  is validated by the Python and TypeScript contract packages
- **THEN** both packages SHALL accept the same canonical snapshot hash, tenant/Case/
  revision/workflow links, ordered typed source entries, counts, roots, states, reason
  codes, and capability flags

#### Scenario: A snapshot is detached, misordered, unsafe or misleading
- **WHEN** a snapshot has a foreign identity, mismatched source/root/snapshot hash,
  missing or duplicate entry/source ID, non-contiguous or out-of-order sequence,
  predecessor/count mismatch, stale approval presented as valid, denial or failed gate
  presented as success, undeclared/raw/secret-like field, unsafe path, caller authority,
  live-provider/customer-success claim, or mutation/effect capability
- **THEN** both contract packages SHALL reject it before the snapshot can be retained,
  served, or rendered

#### Scenario: Retained v1 contracts remain compatible
- **WHEN** the additive operator snapshot schema and fixtures are introduced and all
  retained valid and invalid v1 fixtures are revalidated
- **THEN** their prior acceptance/rejection outcomes SHALL remain unchanged and the new
  schema fingerprint SHALL be recorded only after cross-language parity passes

### Requirement: Live model proposal and invocation contracts are versioned and payload-safe
WeFlow SHALL add language-neutral compatible contracts for `ModelActionProposal`, `ModelToolObservation`, `ModelInvocationIntent`, and `ModelInvocationObservation`. The contracts SHALL use stable schema identities/versions; bind safe tenant, suite/task/attempt, logical turn, Context Manifest, provider/model/profile, source, budget, usage, latency, cost, status, and hash fields where applicable; and forbid undeclared authority, arbitrary tool arguments, workflow target state, approval/delivery/external-write instructions, credentials, authorization headers, raw request/response bodies, private customer data, unrestricted errors, and customer-success claims.

#### Scenario: Valid live invocation metadata validates cross-language
- **WHEN** Python and TypeScript consume a complete safe proposal, tool observation, invocation intent, and invocation observation fixture
- **THEN** both SHALL accept the same identities, links, enumerations, counts, budgets, and hashes without needing a real credential or network call

#### Scenario: A model boundary contains raw or authority-bearing content
- **WHEN** a fixture includes a credential, raw provider body, arbitrary endpoint, caller/model-selected identity, tool arguments, state transition, approval, delivery, external write, or success assertion
- **THEN** both contract packages SHALL reject it with deterministic validation semantics

### Requirement: Live response-draft and candidate-binding contracts preserve verifier ownership
WeFlow SHALL add compatible `ResponseDraftArtifact` and `LiveCandidateBinding` contracts. The artifact contract SHALL carry only safe identity, tenant/Case/revision, content hash, media type, synthetic/redacted classification, producer invocation, bounded claim/evidence summary, creation/expiry, and retention mode. The binding SHALL link the exact Context Manifest, invocation observation, normalized Agent action, draft artifact/hash, ordered evidence hashes, derived response candidate/hash, and verifier-pending state. Neither contract SHALL contain permission, approval, delivery, customer outcome, or unrestricted draft/provider content.

#### Scenario: A valid live draft binding validates
- **WHEN** a safe draft artifact and binding reference one matching tenant, attempt, invocation, context, action, evidence set, and candidate
- **THEN** both language consumers SHALL accept the metadata chain while leaving verification and state transition to deterministic code

#### Scenario: A draft binding is detached or claims success
- **WHEN** a binding has a foreign/stale reference, changed content/evidence/candidate hash, missing predecessor, verifier outcome supplied by the model, or customer-success field
- **THEN** both contract packages SHALL reject it before candidate verification

### Requirement: Live evaluation contracts are separate from offline benchmark contracts
WeFlow SHALL add compatible `ProviderPriceProfile`, `LiveRunMetrics`, `LiveEvaluationAttempt`, and `LiveEvaluationSuiteReport` schemas for `live-pilot.v1`. They SHALL represent live/network/model capability flags, provider/model/prompt/profile hashes, attempts, gates, deterministic dimensions, closed failure attribution, token/call/tool counts, retry/no-progress counts, latency/wall-time distributions, estimated cost/currency, artifact/report hashes, retention state, and explicit zero external-business-write/customer-outcome claims. Existing `RunMetrics`, `EvaluationResult`, `EvaluationSuiteReport`, and `EvaluationSuiteSnapshot` offline schemas SHALL retain their Replay-only const semantics and SHALL NOT be broadened to accept live payloads.

#### Scenario: A complete live suite chain validates cross-language
- **WHEN** valid price-profile, attempt, metrics, candidate-binding, and live report fixtures are evaluated together
- **THEN** Python and TypeScript SHALL accept a complete hash-linked `live-pilot.v1` chain and preserve its measured non-deterministic values

#### Scenario: A live record is presented as an offline result
- **WHEN** a live/model/network payload uses an offline benchmark schema/profile or an offline fixture uses a live schema/profile
- **THEN** both validators SHALL reject the profile/capability mismatch

#### Scenario: Retained v1 fixtures are revalidated
- **WHEN** the additive live schemas and fixtures are introduced
- **THEN** every retained valid/invalid offline, Agent, workflow, approval, delivery, evidence, evaluation, and Operator Case fixture SHALL preserve its prior acceptance/rejection outcome

### Requirement: QQ group-pairing contracts are versioned and payload-safe
WeFlow SHALL maintain compatible language-neutral schemas for
`QQGroupPairingChallenge`, `QQGroupPairingCompletion`, and
`QQGroupPairingAcceptanceReport`. Each SHALL declare a stable schema identity/version,
forbid undeclared properties, bind safe pairing/application/group/tenant identities and
lifecycle timestamps where applicable, and contain only allowlisted opaque IDs, hashes,
enumerations, counts, status/reason codes, and explicit capability flags. They MUST
reject challenge plaintext, raw group/member/message identifiers, ordinary QQ group
numbers, credentials, access tokens, raw events/provider bodies, transcripts,
caller-selected authority, QQ-write claims, Case/workflow effects, customer receipt,
resolution, and Case-completion claims.

#### Scenario: Valid pairing fixtures validate cross-language
- **WHEN** Python and TypeScript consume a complete safe challenge, completion, and
  offline/live report fixture chain
- **THEN** both packages SHALL accept the same identities, hashes, links, lifecycle,
  and capability flags without needing a QQ credential, raw locator, or network call

#### Scenario: A pairing fixture contains private data or false authority
- **WHEN** a pairing fixture contains challenge text, raw OpenID/message/event data,
  credentials, caller-selected group/tenant, a detached/foreign reference, invalid
  expiry/hash/status, QQ send, Case creation, or customer-success assertion
- **THEN** both validators SHALL reject it before pairing or report publication

### Requirement: Pairing contract evolution preserves every retained v1 result
The compatibility command SHALL validate the pairing corpus in Python and TypeScript
alongside every retained valid and invalid v1 fixture. Pairing schemas SHALL be additive
and SHALL not broaden existing QQ intake, provider, workflow, approval, delivery,
evidence, benchmark, or operator contracts. An incompatible semantic change MUST use a
new major-version contract path.

#### Scenario: The pairing corpus is added to compatibility checks
- **WHEN** cross-language compatibility runs after pairing contracts and semantic
  fixtures are introduced
- **THEN** all retained fixtures SHALL preserve their prior result and both languages
  SHALL agree on every new pairing valid/invalid result

### Requirement: QQ sandbox boundary contracts are versioned and payload-safe
WeFlow SHALL maintain compatible language-neutral schemas for QQSandboxInboundEvent,
QQGatewayCursor, QQAcknowledgementIntent, QQAcknowledgementObservation, and
QQAcknowledgementCompletion. Each contract SHALL declare stable schema identity and
version, bind its effective tenant and safe QQ application/group/source identities,
forbid undeclared properties, and contain only allowlisted opaque identifiers, hashes,
sequence/timestamp metadata, classification, correlation, status, and reason codes.
The contracts MUST reject raw message text, group transcripts, attachment bytes,
display names, credentials, access tokens, unrestricted provider bodies,
caller-selected authority/destination/content, customer-receipt claims, resolution
claims, and Case-completion claims.

#### Scenario: Valid QQ boundary fixtures validate cross-language
- **WHEN** valid inbound, gateway-cursor, acknowledgement intent, observation, and
  completion fixtures are consumed by Python and TypeScript validators
- **THEN** both packages SHALL accept the same schema identities and versions without
  requiring a QQ credential, raw chat payload, or network request

#### Scenario: A QQ boundary fixture contains unsafe data or authority
- **WHEN** a fixture contains raw text, transcript data, an undeclared credential,
  caller-selected tenant/group/content, foreign Case reference, invalid sequence/hash,
  or customer-success assertion
- **THEN** both validators SHALL reject it before intake or execution

### Requirement: QQ contract evolution preserves all retained v1 fixtures
QQ sandbox contracts SHALL be additive to the existing synthetic inbound, workflow,
delivery, evidence, benchmark, operator, and live-model contracts. The compatibility
command SHALL validate valid/invalid QQ fixtures in both languages alongside every
retained v1 fixture and SHALL reject any silent semantic change to an existing schema.

#### Scenario: The QQ corpus is added to compatibility checks
- **WHEN** cross-language compatibility runs after the QQ schemas and fixtures are
  introduced
- **THEN** all retained valid fixtures SHALL remain valid, retained invalid fixtures
  SHALL remain invalid, and the new QQ corpus SHALL agree across languages

#### Scenario: A QQ edit breaks a retained contract
- **WHEN** a QQ-related schema change invalidates a retained compatible fixture or
  weakens an existing safety rejection
- **THEN** compatibility SHALL fail until the change becomes additive or uses a new
  major-version contract path

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

### Requirement: Versioned contracts SHALL represent the integrated QQ model-assist lifecycle

The contract set SHALL define closed versioned schemas for Stage 3 readiness, the private `WF-ASSIST` envelope, assist request and outcome, model-safe QQ Context, Case/handler-bound invocation and budget evidence, model candidate provenance/binding, private preview metadata, invalidation/deletion evidence, and correlation/causation links through approval and final QQ delivery. Content-bearing fields SHALL remain restricted artifact references or ephemeral bounded views rather than plaintext in general domain records.

#### Scenario: An assist request contract validates

- **WHEN** a bound handler requests model assistance for a current Case
- **THEN** the schema requires safe handler/Case/revision/workflow/source identities, issue artifact reference, model/prompt/provider/profile hashes, exact capability/policy/budget bindings, and no raw QQ or content fields

#### Scenario: Model or caller supplies authority fields

- **WHEN** an input contains caller/model-selected tenant, destination, provider, tool arguments, workflow state, approval, delivery, resolution, or completion
- **THEN** contract validation fails before policy evaluation, model contact, or external write

### Requirement: Versioned reports SHALL separate integrated provider facts from business outcomes

The contract set SHALL define distinct offline-fake, real integrated acceptance, and independent verification schemas that bind report/source hashes, QQ and model provider modes, invocation/tool/candidate/approval/effect/deletion counts, usage/cost/latency availability, failure classifications, privacy flags, and capability constants. The schemas SHALL require customer receipt, issue resolution, Case completion, and production readiness to remain false for this change.

#### Scenario: Real integrated report validates

- **WHEN** actual QQ and public-model evidence plus exact handler approval and final provider acceptance are complete and source-linked
- **THEN** the schema represents each verified layer separately and retains no credential, raw identity, prompt, issue, draft, transcript, tool body, or unrestricted provider response

#### Scenario: Fake report claims live integration

- **WHEN** a fake/Replay provider report sets a live-provider fact, omits required lineage/metrics, or asserts a customer-success outcome
- **THEN** Python and TypeScript semantic validation reject it consistently
