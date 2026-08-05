## 1. Versioned benchmark contracts

- [x] 1.1 Define v1 JSON Schemas for `EvaluationTask`, `EvaluationOracle`, `GraderResult`, `RunMetrics`, and `EvaluationSuiteReport` with safe identity, hash, tenant, profile, and capability-flag boundaries.
- [x] 1.2 Evolve `EvaluationCase` and `EvaluationResult` additively for the `benchmark-core.v1` profile, including conditional completeness and the unscored-on-hard-gate-failure invariant.
- [x] 1.3 Export and semantically validate the new/additive contracts in both Python and TypeScript without breaking retained v1 fixtures.
- [x] 1.4 Add valid, invalid, and semantic cross-language contract fixtures for benchmark profiles, unsafe/raw fields, foreign references, mismatched hashes, and invalid quality scoring.

## 2. Seed corpus and task loading

- [x] 2.1 Create the JSON-only `evals/tasks/` and `evals/suites/` layout plus a deterministic `offline-seed.v1` suite manifest with exactly 12 unique API-503 task identities.
- [x] 2.2 Author safe task, fixture/environment reference, policy reference, optional fault, and oracle files covering accepted/deduplicated/out-of-order intake, investigation, SLA/operator handling, ticket/delivery recovery, policy and stale-approval denial, duplicate-effect prevention, and tampered lineage.
- [x] 2.3 Implement benchmark task/suite loading, canonical hashing, identity/reference validation, and redacted rejection of unsafe, duplicate, missing, foreign, or mismatched inputs before run-store initialization.
- [x] 2.4 Add loader tests proving deterministic suite order and 12-task coverage, plus malformed, secret-like, caller-authority, and unsupported-fault negative cases.

## 3. Deterministic offline runner and graders

- [x] 3.1 Implement a Replay-only benchmark runner that creates an isolated temporary SQLite fixture store for every task/attempt, invokes only supported existing control/simulator paths, collects safe observations, and cleans up the resolved temporary store.
- [x] 3.2 Deny live provider, credential, network, Docker, external executor, public API, and multi-Agent configuration before runner initialization; expose only redacted reason codes.
- [x] 3.3 Implement deterministic hard-gate grading for tenant/reference consistency, offline/Replay flags, unauthorized external-write absence, local-effect count/idempotency, approval binding, evidence lineage, and expected safe outcome/state.
- [x] 3.4 Implement oracle-bound deterministic quality dimensions and enforce `not_scored` whenever an applicable hard gate or oracle-integrity check fails.
- [x] 3.5 Add runner and grader tests for expected safe denials, stale approval, duplicate delivery, lost-response/restart recovery, timeout or ordering regression, tampered evidence, and no cross-task retained-state mutation.

## 4. Reports and command surface

- [x] 4.1 Implement canonical redacted per-task diagnostics and aggregate suite-report serialization with stable hashes, gate/dimension summaries, deterministic metrics, and explicit disabled-capability flags.
- [x] 4.2 Reject raw, secret-like, foreign, detached, undeclared, provider, or customer-success data during diagnostic/report construction without exposing the unsafe value.
- [x] 4.3 Add `python scripts/dev.py evaluation-benchmark-acceptance --output <path>` to run the seed suite twice, compare canonical outputs, and write the machine-readable acceptance report only to the requested path.
- [x] 4.4 Add command-level tests for accepted 12-task baselines, report determinism, no-network/no-model/no-external-write claims, and redacted failures that do not replace a prior accepted report.

## 5. Verification, documentation, and archive readiness

- [x] 5.1 Add focused contract, unit, integration, security, recovery, and end-to-end acceptance coverage for every new requirement and task category.
- [x] 5.2 Document the supported offline benchmark profile, command, report fields, simulated/disabled capabilities, 12-task limitation, and the later 60-task/live-run gate in README and a Change 6 development guide.
- [x] 5.3 Run `python scripts/dev.py check`, `lint`, `contracts`, `test`, and `evaluation-benchmark-acceptance`; retain the redacted machine-readable acceptance evidence and record unavailable diagnostics truthfully.
- [x] 5.4 Run `openspec validate add-evaluation-benchmark-core --type change --strict`, resolve all issues, and update `docs/PROJECT_MEMORY.md` with verified facts, limitations, metrics, and the next-stage gate before archive.
