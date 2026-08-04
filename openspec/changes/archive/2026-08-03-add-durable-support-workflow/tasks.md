## 1. Workflow and recovery contracts

- [x] 1.1 Add compatible `v1` JSON Schemas for `WorkflowProjection`, `WorkflowCheckpoint`, `WorkflowCommand`, `SyntheticSlaPolicy`, `SideEffectIntent`, `SideEffectObservation`, and `SideEffectCompletion`; add only additive workflow references to existing schemas where required.
- [x] 1.2 Extend the Python contract package with schema loading, typed validation helpers, semantic checks for checkpoint sequence/causation, command versioning, intent-observation-completion links, and safe tenant boundaries.
- [x] 1.3 Extend the TypeScript contract package and generated API-boundary exports for the same workflow and recovery schemas.
- [x] 1.4 Add valid and invalid synthetic contract fixtures for lifecycle checkpoints, pause/resume/cancel commands, SLA deadlines, duplicate intents, lost responses, expected-version conflicts, cross-tenant access, raw/undeclared data, excluded-provider requests, and retained stale-approval behavior.
- [x] 1.5 Update schema fingerprints only after Python/TypeScript compatibility checks accept every retained and new valid fixture and reject every new invalid fixture deterministically.

## 2. Append-only ledger and durable workflow journal

- [x] 2.1 Design and implement an additive SQLite migration for immutable workflow activation, run, command, checkpoint, SLA, intent, observation, completion, and fixture-local ticket source tables; preserve all existing Change 1 source rows and reject unsupported journal schemas fail-closed.
- [x] 2.2 Add append-only guards, tenant-scoped uniqueness constraints, stable workflow/command/intent identifiers, natural-key indexes, and source-table integrity validation for the new workflow journal.
- [x] 2.3 Extend the control-kernel Case ledger through an internal workflow-only port that appends allowlisted workflow-originated BusinessEvents at the next Case index while retaining the public prohibition on arbitrary event/state mutation.
- [x] 2.4 Implement Case and workflow projection rebuild/validation from initial ledger records plus workflow source facts, including legal predecessor states, causation, event ordering, checkpoint continuity, and projection agreement.
- [x] 2.5 Add content-addressed workflow snapshot export/restore linked to the unchanged Change 1 ledger snapshot; prove legacy ledger-only snapshots restore without silently creating workflow work.
- [x] 2.6 Add unit and recovery tests for migration compatibility, append-only violations, duplicate activation, source-table corruption, projection rebuild, snapshot tampering, and fresh-store restore.

## 3. Deterministic workflow control kernel

- [x] 3.1 Implement the driver-neutral workflow reducer and explicit Change 2 state-transition table for `RECEIVED`, `TICKET_READY`, `PAUSED`, `WAITING_FOR_OPERATOR`, `NEEDS_RECONCILIATION`, and `CANCELLED`; reject every unallowlisted transition and all resolution/completion states.
- [x] 3.2 Implement stable workflow activation/recovery scanning so one accepted Case revision has at most one active workflow identity and an exact inbound retry cannot append workflow work.
- [x] 3.3 Implement immutable checkpoint creation and resume semantics, including current/resume state, causal event, pending/completed effects, deterministic correlation metadata, and content hashes.
- [x] 3.4 Implement idempotent, expected-versioned synthetic workflow commands for pause, resume, and cancel with actor-derived tenant scope, safe errors, foreign non-disclosure, and unresolved-effect cancellation blocking.
- [x] 3.5 Implement fixture-defined synthetic SLA policy/deadline calculation using an injectable monotonic clock; preserve deadlines through pause, restart, recovery, and projection rebuild.
- [x] 3.6 Add reducer/kernel tests covering every legal and illegal transition, duplicate/stale/foreign commands, cancel/reconciliation ordering, SLA expiry, and restart-safe checkpoint continuation.

## 4. Fixture-local side-effect recovery

- [x] 4.1 Implement the deterministic local ticket simulator with tenant/Case/revision natural-key `find-or-create`, safe synthetic identifiers, and one expected-version workflow-handoff update carrying only a content hash/reference.
- [x] 4.2 Implement `intent -> reconcile -> execute -> observe -> validate -> complete` in the control kernel with immutable phase records, stable idempotency keys, and validation of observed ticket identity/version.
- [x] 4.3 Implement reconciliation-first recovery for existing, absent, unknown, conflicting, and stale-version outcomes; transition unknown/conflicting outcomes to `NEEDS_RECONCILIATION` without a blind retry or success claim.
- [x] 4.4 Add deterministic fault profiles at activation, checkpoint, intent, reconcile, execute, lost-response, observation, and completion boundaries, with a fresh-worker recovery entry point over the same local store.
- [x] 4.5 Add unit/recovery tests proving one logical ticket/create-update result under duplicate runners, worker interruption, response loss, reconciliation timeout, conflict, and completed-effect replay.
- [x] 4.6 Add negative security tests proving the workflow cannot register a real external executor, consume credentials, invoke a provider/model, create approval/delivery work, or leak raw fixture content in errors, logs, snapshots, or reports.

## 5. Runtime, API, simulator, and service-boundary wiring

- [x] 5.1 Replace the health-only control-worker path with the offline deterministic workflow driver, workflow readiness reporting, recovery startup scan, and redacted workflow diagnostics while preserving loopback-only defaults.
- [x] 5.2 Add only narrow Platform API workflow observation and allowlisted synthetic command surfaces; derive tenant from the actor boundary and expose no generic Case/event/ticket mutation endpoint.
- [x] 5.3 Extend the Business Simulator and testkit with named workflow/SLA/effect fixtures, injected clocks/faults, workflow snapshot helpers, and safe machine-readable inspection results.
- [x] 5.4 Add a Temporal-backed service-boundary driver/activity integration using the same reducer and journal contracts; update Compose/dependency readiness behavior and retain an explicit Docker-unavailable skip path.
- [x] 5.5 Extend health/capability contracts and the diagnostics console to report the narrow durable-workflow capability truthfully while retaining `business_workflow_implemented=false` and `external_writes_enabled=false`.
- [x] 5.6 Add API/integration tests for tenant-scoped workflow reads, foreign non-disclosure, safe command failures, duplicate activation, and absence of approval/outbound/customer-completion behavior.

## 6. Acceptance, determinism, and evidence

- [x] 6.1 Add a documented offline Change 2 acceptance command that runs synthetic intake through workflow activation, ticket reconciliation, checkpoints, and bounded `TICKET_READY`/safe exception outcomes without model, network, Docker, or credentials.
- [x] 6.2 Make the acceptance report redact raw content and include fixture outcomes, workflow/checkpoint/effect counts, natural-key reconciliation result, SLA/recovery status, capability booleans, and explicit non-resolution/non-external-write assertions.
- [x] 6.3 Add end-to-end fault acceptance covering worker interruption after every declared critical boundary and lost response after local execution; require recovery without duplicate ticket operations or invented success.
- [x] 6.4 Run repeated offline workflow baselines and compare all deterministic report/projection fields, documenting intentional nondeterministic fields if any.
- [x] 6.5 Extend the opt-in service-boundary acceptance suite for Temporal workflow readiness and timeout behavior; record Docker unavailability as an explicit skip rather than a successful live verification.

## 7. Documentation, validation, and archive evidence

- [x] 7.1 Update README, Change 2 development guidance, fixture documentation, and capability/support matrices with setup commands, workflow state meanings, recovery operations, fault profiles, and strict implemented-versus-unimplemented boundaries.
- [x] 7.2 Update `openspec/config.yaml` and relevant long-lived documentation to remove the stale “exploration and specification only” claim while retaining the verified limits of Changes 0 and 1.
- [x] 7.3 Run `python scripts/dev.py check`, `lint`, `contracts`, `test`, and the Change 1/Change 2 offline acceptance commands; retain redacted machine-readable command evidence and record any local tool or Docker limitation explicitly.
- [x] 7.4 Run `openspec validate add-durable-support-workflow --type change --strict`, resolve every issue, and confirm every task above has a passing acceptance check before archive.
- [x] 7.5 Archive through OpenSpec only after all verification passes; update `docs/PROJECT_MEMORY.md` with verified Change 2 facts, limitations, metrics, and the gate for the next Agent/investigation change.
