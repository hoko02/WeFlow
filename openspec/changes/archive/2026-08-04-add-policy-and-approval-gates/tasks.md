## 1. Authorization contracts and deterministic fixtures

- [x] 1.1 Add compatible schema, Python, and TypeScript contracts for authorization bindings, scoped Capability Grants, policy decisions, hash-bound approval records, and distinct outbound-delivery intent/observation/completion records.
- [x] 1.2 Extend cross-language semantic validators so Change 4 execution profiles require complete tenant, checkpoint, candidate, ordered evidence, policy, grant, role, resource, classification, and expiry bindings while retained v1 fixtures remain valid.
- [x] 1.3 Add valid, invalid, stale, foreign-tenant, expired, revoked, wrong-role, unsafe-classification, and raw-content fixture corpora for authorization, approval, and delivery contracts.
- [x] 1.4 Add the named API-503 policy/approval/delivery fixture with fixed clock, synthetic principals/roles, fixture-owned grants, policy versions, budgets, and safe delivery resource metadata.

## 2. Durable authorization and workflow continuation

- [x] 2.1 Add additive SQLite journal tables, indexes, append-only triggers, source-validation, projection rebuild, inspection, and snapshot support for policy, grant, authorization-binding, approval, and outbound-delivery facts.
- [x] 2.2 Extend the synthetic actor boundary with server-owned fixture principal/role derivation; reject caller-selected tenant, role, grant, policy, candidate, evidence, delivery resource, and target state.
- [x] 2.3 Implement the pure default-deny Capability/Policy evaluator with stable canonical input/output hashes, scope/expiry/revocation/data-classification/budget checks, and redacted reason codes.
- [x] 2.4 Implement explicit Change 4 continuation activation so retained `RESPONSE_READY` workflows remain inert without it, then persist one matching policy decision and authorization binding.
- [x] 2.5 Extend the allowlisted reducer, checkpoints, Case events, and recovery path for `RESPONSE_READY -> AWAITING_APPROVAL -> DELIVERING -> DELIVERY_RECORDED`, safe denial handling, and delivery reconciliation without resolution/completion claims.

## 3. Hash-bound approval boundary

- [x] 3.1 Implement deterministic approval-request creation only after an active continuation and matching allow policy decision; bind it to exact authorization material and enter `AWAITING_APPROVAL` once.
- [x] 3.2 Implement append-only approval decisions with expected workflow-version/idempotency behavior and revalidate actor-derived tenant/role plus the full authorization binding before accepting a decision.
- [x] 3.3 Add tenant-derived read and decision API routes with indistinguishable foreign/absent behavior, payload-safe errors, and no caller-controlled authority fields.
- [x] 3.4 Enforce approval invalidation and safe outcomes for rejected, expired, revoked, policy/grant/candidate/evidence/revision/checkpoint-mismatched, duplicate-conflicting, and foreign decisions.

## 4. Fixture-local outbound delivery and recovery

- [x] 4.1 Implement the named fixture-local IM adapter with no network, credential, live connector, or customer-success behavior; expose only safe IDs, versions, classifications, and content hashes.
- [x] 4.2 Implement distinct durable outbound-delivery intent/reconcile/execute/observe/complete processing with stable natural/idempotency keys and no changes to ticket SideEffect semantics.
- [x] 4.3 Add recovery for interruptions after policy, approval request, approval decision, delivery intent, execution, lost response, observation, completion, and transition persistence; unknown/conflicting results must enter reconciliation without blind resend.
- [x] 4.4 Extend safe inspection, capability/health reporting, Business Simulator output, and diagnostics so fixture approval/delivery is distinguishable from real external writes and raw content stays hidden.

## 5. Acceptance, security, and determinism evidence

- [x] 5.1 Add unit and contract tests for default-deny policy, grant lifecycle, actor-role derivation, binding hashes, approval authorization, delivery contracts, and retained-fixture compatibility.
- [x] 5.2 Add integration and security tests for cross-tenant access, forged authority fields, wrong role, expiry/revocation, unsafe instruction/secret classification, stale approval, duplicate decision, and zero delivery on every deny path.
- [x] 5.3 Add deterministic end-to-end and recovery tests proving one authorized fixture delivery, `DELIVERY_RECORDED` without a customer-success claim, and no duplicate delivery across repeated/recovered runs.
- [x] 5.4 Add a machine-readable offline Change 4 acceptance command/report that compares two equal baselines and records every declared fault boundary, authorization denial, effect count, and environment limitation.

## 6. Documentation and final verification

- [x] 6.1 Update README, Change 4 development guidance, capability support matrix, fixtures/support documentation, and project memory to distinguish fixture approval/delivery from live systems and document Node/Docker limits.
- [x] 6.2 Run `python scripts/dev.py check`, `lint`, `contracts`, `test`, the Change 4 acceptance command, repeated baseline checks, and strict OpenSpec validation; retain redacted machine-readable reports before archive.
