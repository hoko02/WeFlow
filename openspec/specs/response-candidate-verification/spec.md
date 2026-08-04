# response-candidate-verification Specification

## Purpose
Define the deterministic verifier boundary that authorizes a bounded response-ready
workflow transition from evidence-bound synthetic response candidates.

## Requirements

### Requirement: A response candidate is evidence-bound and verifier-authorized
A response candidate SHALL bind tenant, Case, revision, workflow checkpoint, context
hash, ordered evidence hashes, risk, next step, and canonical candidate hash. A
deterministic verifier SHALL check tenant consistency, required evidence, redaction,
budget, and prohibited approval/delivery/resolution claims before returning a safe
outcome.

#### Scenario: Complete evidence produces a verified candidate
- **WHEN** a candidate references the required matching fixture evidence
- **THEN** the verifier SHALL record a hash-bound verified result without sending or
  approving content

#### Scenario: Missing or unsafe evidence is supplied
- **WHEN** a candidate is detached from its manifest/evidence or contains a prohibited
  claim
- **THEN** the verifier SHALL reject it and SHALL not authorize a workflow transition
