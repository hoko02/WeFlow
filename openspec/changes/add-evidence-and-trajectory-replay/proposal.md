## Why

Changes 1–4 retain safe, append-only facts for intake, workflow, investigation,
policy, approval, and fixture-local delivery, but contributors cannot yet produce one
content-addressed explanation of a run or replay its complete trajectory from that
explanation. This increment makes the existing offline API-503 vertical slice auditable
and reproducible before any real provider, credential, external write, or benchmark is
considered.

## What Changes

- Add one fixture-only evidence-trajectory capability that collects existing durable
  facts into an immutable, tenant-scoped trajectory manifest and a redacted Evidence
  Report with one deterministic root hash.
- Add deterministic offline trajectory replay that rebuilds and verifies the named
  API-503 success, authorization-denial, and interrupted-recovery trajectories without
  invoking a model, network, Docker service, credential, or delivery adapter.
- Add content-addressed Artifact, trajectory, replay-result, and Evidence Report
  contracts plus Python/TypeScript compatibility fixtures; reports contain only safe
  identifiers, hashes, classifications, counts, reason codes, and declared environment
  limits.
- Add a machine-readable Change 5 acceptance command that compares equal baseline
  reports, verifies full Case-to-delivery lineage, and classifies safe failure paths.
- Expose tenant-derived, read-only evidence inspection only if it can return the same
  redacted report content; no route may request replay, reveal foreign existence, or
  mutate workflow state.

## Capabilities

### New Capabilities
- `evidence-trajectory-replay`: Immutable, fixture-local evidence lineage, redacted
  Evidence Reports, deterministic trajectory replay, and machine-readable acceptance
  evidence for the named API-503 workflow.

### Modified Capabilities
- `versioned-domain-contracts`: Add compatible v1 contracts and cross-language
  validation for artifacts, trajectory manifests, replay results, and Evidence Reports.
- `durable-support-workflow`: Require durable workflow facts used by a trajectory to
  retain stable, append-only linkage and to remain non-mutating during report/replay.
- `local-platform-dependencies`: Define the fully offline evidence/replay command,
  report limits, and deterministic baseline behavior without Docker or network.

## Impact

- Affected code: Python contracts and control-kernel inspection/journal readers,
  Business Simulator/testkit, Platform API read models, TypeScript contract fixtures,
  `scripts/dev.py`, acceptance reports, tests, and development documentation.
- Affected data: additive content-addressed artifact/trajectory/report records linked
  to existing Case, revision, workflow, evidence, policy, approval, and delivery IDs;
  existing histories remain valid and are never rewritten.
- Affected security boundary: report generation and replay are tenant-scoped,
  read-only, redacted, and deny raw content, foreign references, missing lineage,
  tampered hashes, or caller-selected authority.
- No breaking API or schema change is intended. This change does not enable a real
  provider, credential, network access, Docker dependency, external write, live
  approval, customer receipt/resolution, knowledge publication, evaluation benchmark,
  or multi-Agent coordination.
