# response-candidate-verification Specification

## Purpose
Define the deterministic verifier boundary that authorizes a bounded response-ready
workflow transition from evidence-bound synthetic response candidates.
## Requirements
### Requirement: A response candidate is evidence-bound and verifier-authorized
A response candidate SHALL bind tenant, Case, revision, workflow checkpoint/version, context hash, ordered evidence hashes, risk, next step, and canonical candidate hash. For a live evaluation it SHALL retain the existing valid `LiveCandidateBinding` to the exact model invocation, normalized action, redacted `ResponseDraftArtifact`, and claim-to-evidence references. For Stage 3 it SHALL additionally bind the handler-authored assist request, active dual-surface handler binding, restricted QQ issue and candidate artifact hashes, policy/capability/provider/prompt profiles, and cumulative Case budget state. A deterministic verifier SHALL check tenant and source consistency, required/current evidence, claim grounding, draft redaction, budget integrity, retention, handler/Case/workflow binding, and prohibited approval/delivery/resolution claims before returning a safe outcome.

#### Scenario: Complete Replay evidence produces a verified candidate
- **WHEN** a Replay candidate references the required matching fixture evidence
- **THEN** the verifier SHALL preserve the existing hash-bound verified result without sending or approving content

#### Scenario: A complete live evaluation draft produces a verified candidate
- **WHEN** a live evaluation candidate has a matching invocation, action, draft artifact, Context Manifest, current evidence, allowed claims, and intact budgets
- **THEN** the verifier SHALL record a hash-bound verified result and the control kernel MAY advance only the temporary evaluation workflow to `RESPONSE_READY`

#### Scenario: A complete Stage 3 draft produces a current private candidate
- **WHEN** the model draft also matches the current handler assist request, issue artifact, handler binding, Case/revision, policy/capability/profile, workflow version, retention, and Case budget
- **THEN** the verifier SHALL record one hash-bound result and the control kernel MAY advance only the current QQ Case workflow to `RESPONSE_READY` and create a private approval preview

#### Scenario: Missing, stale, or unsafe live evidence is supplied
- **WHEN** a candidate/draft is detached, foreign, stale, tampered, ungrounded, secret-bearing, budget-invalid, retention-invalid, or contains approval, delivery, customer receipt, resolution, or completion claims
- **THEN** the verifier SHALL reject it, record the named reason, and SHALL not authorize a workflow transition, approval request, or effect

### Requirement: Draft content is redacted before persistence and omitted from reports
The live draft pipeline SHALL accept only bounded response fields, apply deterministic secret/PII/prohibited-claim and evidence checks, and persist accepted content only in an access-restricted local content-addressed artifact store with an expiry. Evaluation drafts SHALL preserve their existing synthetic-only boundary. Stage 3 drafts SHALL be normalized into the one current restricted QQ candidate artifact, SHALL be available only to the bound handler through a current passive C2C reply, and SHALL be deleted or made unreachable on replacement, rejection, final provider acceptance, or the existing 24-hour limit. Invocation records, workflow facts, evaluation/acceptance results, reports, logs, group messages, and console responses SHALL contain only draft identities, classifications, claim/evidence summaries, lengths, and hashes.

#### Scenario: A safe synthetic evaluation draft is retained temporarily
- **WHEN** a draft passes schema, redaction, grounding, and retention validation in live evaluation
- **THEN** its artifact metadata and hash MAY be persisted for the bounded retention window while reports expose no full draft text

#### Scenario: A safe Stage 3 draft is previewed
- **WHEN** a verifier-authorized model draft becomes the current QQ candidate
- **THEN** its body is retrievable only for the bound handler's current C2C preview and later exact approved final reply, never for group preview, report, ledger, or model/provider reuse

#### Scenario: Draft retention expires or is disabled
- **WHEN** the artifact reaches its expiry, is replaced/rejected/finally accepted, or an evaluation command uses ephemeral-only retention
- **THEN** the content SHALL be removed while immutable invocation/candidate/approval/report hashes and safe classifications remain valid

### Requirement: Customer issue content SHALL be a bounded restricted artifact

The system SHALL normalize and redact the accepted customer issue into at most one `QQCustomerIssueArtifact` containing 1–1200 Unicode scalar values. The artifact SHALL be content-addressed, restricted, classified, retained for no more than 24 hours, and deleted at the terminal Stage 2 outcome. Group and C2C transcripts MUST NOT be stored.

#### Scenario: Valid intake enters Stage 2

- **WHEN** one accepted Stage 1 intake is selected for handler processing
- **THEN** one bounded issue artifact is created and durable workflow metadata references its hash rather than its plaintext

#### Scenario: Issue exceeds policy bounds

- **WHEN** normalized content cannot satisfy the redaction or size policy
- **THEN** Stage 2 fails closed without notifying the handler or creating a candidate

### Requirement: Response candidates SHALL be verified deterministically and privately

The system SHALL normalize, redact, bound, and content-address one current `QQHandlerResponseArtifact` from either a valid private handler `WF-DRAFT` or a verifier-authorized Stage 3 model proposal. Human candidates SHALL bind to the submitting handler and current issue/Case/workflow facts. Model candidates SHALL additionally bind to the handler-authored assist request, model invocation/Context, ordered evidence, policy/capability/provider profiles, and budgets. Candidate plaintext SHALL be available only through the restricted artifact boundary and bound-handler C2C preview; neither provenance may bypass human group approval.

#### Scenario: Valid private handler candidate is submitted

- **WHEN** the bound C2C handler submits a policy-compliant 1–1200-character candidate for the current version
- **THEN** one verified human candidate artifact and content-free candidate revision are created

#### Scenario: Valid model candidate is verified

- **WHEN** the deterministic verifier accepts a bounded evidence-grounded proposal for the current bound-handler assist request
- **THEN** one verified model-assisted candidate artifact and content-free provenance revision are created for private review only

#### Scenario: Candidate contains prohibited content

- **WHEN** deterministic redaction, grounding, authority, retention, or policy verification rejects proposed text from either source
- **THEN** no current candidate or approval request is created and the private failure response reveals no restricted content

### Requirement: Candidate replacement SHALL invalidate prior approval state

Only one candidate may be current. Creating a handler replacement after a human or model candidate SHALL invalidate the previous candidate's approval request and any decision before the replacement can be approved. Superseded content and model-assist provenance SHALL become unusable for authorization, and superseded content SHALL become unreachable and be scheduled for deletion.

#### Scenario: Handler edits after a private preview

- **WHEN** a new private `WF-DRAFT` is accepted after a human or model-assisted approval preview exists
- **THEN** the old request, hash prefix, candidate provenance, and decision are rejected as stale and a new request is required

#### Scenario: A duplicate or stale model result arrives after replacement

- **WHEN** a late/replayed model observation attempts to restore a candidate that the handler already replaced
- **THEN** it remains historical content-free evidence and cannot become current, recreate content, or authorize approval/delivery

### Requirement: Content deletion SHALL be verifiable without content disclosure

The system SHALL emit content-free deletion evidence for issue and candidate artifacts and SHALL detect retention overruns as acceptance failures.

#### Scenario: Retention deadline or terminal outcome is reached

- **WHEN** either deletion condition occurs
- **THEN** the artifact is no longer retrievable and evidence records only its reference, hash, classification, and deletion time
