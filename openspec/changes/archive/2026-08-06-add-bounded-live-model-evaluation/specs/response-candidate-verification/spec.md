## MODIFIED Requirements

### Requirement: A response candidate is evidence-bound and verifier-authorized
A response candidate SHALL bind tenant, Case, revision, workflow checkpoint, context hash, ordered evidence hashes, risk, next step, and canonical candidate hash. For a live attempt it SHALL also have a valid `LiveCandidateBinding` to the exact model invocation, normalized action, redacted `ResponseDraftArtifact`, and claim-to-evidence references from which the candidate hash was derived. A deterministic verifier SHALL check tenant and source consistency, required/current evidence, claim grounding, draft redaction, budget integrity, and prohibited approval/delivery/resolution claims before returning a safe outcome.

#### Scenario: Complete Replay evidence produces a verified candidate
- **WHEN** a Replay candidate references the required matching fixture evidence
- **THEN** the verifier SHALL preserve the existing hash-bound verified result without sending or approving content

#### Scenario: A complete live draft produces a verified candidate
- **WHEN** a live candidate has a matching invocation, action, draft artifact, Context Manifest, current evidence, allowed claims, and intact budgets
- **THEN** the verifier SHALL record a hash-bound verified result and the control kernel MAY advance only the temporary evaluation workflow to `RESPONSE_READY`

#### Scenario: Missing, stale, or unsafe live evidence is supplied
- **WHEN** a candidate/draft is detached, foreign, stale, tampered, ungrounded, secret-bearing, budget-invalid, or contains approval, delivery, customer receipt, resolution, or completion claims
- **THEN** the verifier SHALL reject it, record the named reason, and SHALL not authorize a workflow transition or effect

## ADDED Requirements

### Requirement: Draft content is redacted before persistence and omitted from reports
The live draft pipeline SHALL accept only bounded synthetic response fields, apply deterministic secret/PII/prohibited-claim checks, and persist accepted content only in an access-restricted local content-addressed artifact store with an expiry. Invocation records, workflow facts, evaluation results, reports, logs, and console responses SHALL contain only draft identities, classifications, claim/evidence summaries, and hashes.

#### Scenario: A safe synthetic draft is retained temporarily
- **WHEN** a draft passes schema, redaction, grounding, and retention validation
- **THEN** its artifact metadata and hash MAY be persisted for the bounded retention window while reports expose no full draft text

#### Scenario: Draft retention expires or is disabled
- **WHEN** the artifact reaches its expiry or the command uses ephemeral-only retention
- **THEN** the content SHALL be removed while immutable invocation/candidate/report hashes and safe classifications remain valid
