## 1. Versioned Evidence Contracts

- [x] 1.1 Define additive v1 JSON Schemas and matching Python/TypeScript boundary types for `Artifact`, `EvidenceTrajectory`, `EvidenceReport`, and `TrajectoryReplayResult`, with closed safe fields, stable IDs, tenant/Case/revision/workflow linkage, canonical SHA-256 fields, and fixed outcome/failure codes.
- [x] 1.2 Implement one shared canonical serialization/hash profile and contract validators that bind ordered node/predecessor references, artifact/report/replay identities, schema versions, and recorded versus replayed roots.
- [x] 1.3 Add valid and invalid cross-language fixture chains for the named API-503 authorized, revoked-grant denial, interruption-recovery, detached, foreign-tenant, duplicate/out-of-order, tampered-hash, raw-content, secret-like, and customer-success cases; verify both packages agree while all retained v1 fixtures remain valid.

## 2. Append-Only Evidence Trajectory Storage and Extraction

- [x] 2.1 Add additive fixture-local SQLite storage and append-only protections for content-addressed evidence artifacts, trajectories, reports, and replay results, including tenant-scoped lookup indexes and idempotent identity uniqueness without changing existing Case/workflow/effect records.
- [x] 2.2 Implement the deterministic source resolver that reads the existing accepted intake, immutable revision/events, workflow activation/checkpoints, investigation/tool/evidence/candidate/verifier, policy/grant/binding, approval, and fixture-delivery facts into a canonical ordered trajectory with one root hash.
- [x] 2.3 Implement redacted Evidence Report construction and idempotent persistence from a valid trajectory, exposing only allowed identifiers, hashes, classifications, counts, reason codes, fixture identity, and explicit zero-network/model/external-write capability flags.
- [x] 2.4 Implement fail-closed trajectory extraction for missing, foreign, duplicated, out-of-order, causally unlinked, or hash-invalid source facts, returning a payload-safe `lineage_invalid` result without persisting a complete trajectory or mutating the workflow.

## 3. Read-Only Replay and Evidence Inspection

- [x] 3.1 Implement deterministic verification replay over a persisted tenant-scoped trajectory that re-resolves recorded source facts, verifies canonical order/causation/hashes, emits the same root on success, and never calls agents, models, tools, policy/approval logic, workflow commands, effect reconciliation, delivery adapters, network clients, or Docker services.
- [x] 3.2 Add tenant-derived, read-only evidence inspection that can return only an already persisted redacted report and preserves foreign-versus-absent non-disclosure; reject replay commands, caller-selected authority/profile/node/raw-field inputs, and all mutation paths.
- [x] 3.3 Extend the deterministic Business Simulator/testkit with authorized delivery-recorded, revoked-grant authorization-denied, and interrupted-local-delivery recovery trajectory fixtures plus tamper injection, preserving exactly one local delivery identity where applicable.

## 4. Offline Acceptance Evidence and Regression Tests

- [x] 4.1 Add contract and unit tests proving cross-language compatibility, canonical hash stability, closed-field redaction, idempotent artifact/report persistence, full Case-to-delivery lineage, and extraction/replay non-mutation of Case state, checkpoints, grants, approvals, intents, and effects.
- [x] 4.2 Add negative security and isolation tests for raw/private content, secret-like values, customer-success language, foreign or caller-selected references, undeclared fields, detached chains, invalid schema/version, broken causation, duplicate/out-of-order nodes, and tampered manifests/source hashes.
- [x] 4.3 Add replay integration tests that compare two equal offline baselines for the authorized, denial, and recovery paths and prove safe `lineage_invalid` results perform zero model invocation, network request, Docker initialization, workflow transition, or external-write attempt.
- [x] 4.4 Add the machine-readable `evidence-trajectory-acceptance` command behind `scripts/dev.py`; it SHALL run solely against checked-in fixtures and local SQLite, record Node/Docker availability as diagnostics, emit only redacted reports, and reject live dependency or raw-export configuration before initialization.

## 5. Documentation and Change Verification

- [x] 5.1 Document the supported fixture-local Evidence Report/replay contract, safe outcome meanings, required lineage, offline Node/Docker limitations, acceptance command, and explicit exclusions of real providers, credentials, network, external delivery, and multi-Agent execution.
- [x] 5.2 Run and record the focused contract, lint, unit, integration, security, replay-baseline, and evidence-trajectory acceptance checks; run `openspec validate add-evidence-and-trajectory-replay --strict` and update any generated redacted verification evidence needed to pass.
