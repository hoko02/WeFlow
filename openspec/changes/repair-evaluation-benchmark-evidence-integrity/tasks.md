## 1. Source-bound benchmark inputs

- [ ] 1.1 Define safe canonical source-path and content-hash metadata for every seed task fixture and policy reference.
- [ ] 1.2 Implement resolved-source loading with allowlisted roots, canonical hashing, identity checks, and redacted pre-store rejection.
- [ ] 1.3 Replace task-local mirror hashes with the resolved checked-in source hashes and add source-tamper/path-escape/missing-source tests.

## 2. Public typed observations and isolation

- [ ] 2.1 Add public offline benchmark adapters for intake, workflow, investigation, policy, and evidence paths that return actual safe observations.
- [ ] 2.2 Refactor the runner to call only public adapters, remove hard-coded outcomes and suite caches, and pass one fresh store to each task attempt.
- [ ] 2.3 Add regression tests for an unexpected returned state, distinct task stores, no cross-task reuse, stale approval, recovery, and tampered lineage.

## 3. Runtime evaluation evidence chain

- [ ] 3.1 Materialize benchmark-profile EvaluationCase and EvaluationResult records for each executed task.
- [ ] 3.2 Link and semantically validate task, oracle, grader result, metrics, EvaluationResult, and suite report; use emitted EvaluationResult IDs in reports.
- [ ] 3.3 Add cross-language and end-to-end tests for detached, mismatched, unscored, and cross-task record links.

## 4. Verification and documentation

- [ ] 4.1 Regenerate the redacted 12-task acceptance report and assert the real source hashes, result IDs, and repeated baseline equality.
- [ ] 4.2 Update the benchmark guide and project memory with repaired evidence semantics and remaining offline-only limitations.
- [ ] 4.3 Run check, lint, contracts, test, benchmark acceptance, and strict OpenSpec validation; retain machine-readable evidence.
