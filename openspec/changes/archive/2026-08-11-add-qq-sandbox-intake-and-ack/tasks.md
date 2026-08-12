## 1. Contract And Compatibility Boundary

- [x] 1.1 Add versioned JSON Schemas for `QQSandboxInboundEvent`, `QQGatewayCursor`, and the three `QQAcknowledgement*` records with closed payload-safe fields and semantic linkage checks.
- [x] 1.2 Add Python and TypeScript QQ contract bindings plus valid/invalid fixtures for raw text, credentials, caller-selected authority/content, foreign references, invalid sequences/hashes, and customer-success claims.
- [x] 1.3 Extend the cross-language compatibility command and tests so the QQ corpus agrees in both languages while every retained v1 valid/invalid fixture preserves its result.

## 2. Deterministic Identity, Ledger, And Recovery

- [x] 2.1 Implement the command-local QQ sandbox configuration validator with explicit live confirmation, external credential sources, one application/group-to-tenant mapping, exact capability scope, redacted readiness, and pre-contact denial tests.
- [x] 2.2 Implement payload-safe QQ event normalization, server-owned actor/customer mapping, content hashing/discard, and rejection of non-mention, direct-message, attachment, malformed, and unallowlisted events with unit tests.
- [x] 2.3 Add durable gateway cursor and inbound-receipt persistence with contiguous-sequence handling, stable QQ natural-key uniqueness, restart-safe replay, and no raw chat or secret fields.
- [x] 2.4 Integrate a first accepted QQ receipt with the existing atomic Case/CaseRevision/three-BusinessEvent transaction and prove rollback, tenant isolation, projection replay, exact retry, and concurrent-consumer behavior.
- [x] 2.5 Add the immutable QQ acknowledgement intent/observation/completion journal, stable natural/idempotency keys, fixed template hash, original `msg_id`, deterministic `msg_seq`, deadline, uniqueness, and reconstruction tests.
- [x] 2.6 Implement deterministic acknowledgement reconcile/execute/observe/complete control for accepted, duplicate/present, absent-and-retryable, unknown, conflict, unauthorized, and expired outcomes without Case-completion authority.

## 3. QQ Transport And Command Isolation

- [x] 3.1 Define narrow token, gateway, WebSocket, and passive-send transport interfaces and deterministic fakes that require no network or credentials.
- [x] 3.2 Implement the real QQ sandbox token/gateway/WebSocket adapter with heartbeat, session/cursor resume, bounded timeouts/reconnects, safe provider-response parsing, and no unrestricted response logging.
- [x] 3.3 Implement the fixed plain-text passive acknowledgement executor using only the configured group, source `msg_id`, and deterministic `msg_seq`; reject arbitrary destinations, bodies, formats, attachments, final replies, and caller-selected sequences.
- [x] 3.4 Wire the adapter only into the dedicated control-worker/dev command and prove normal startup, Agent Runtime, Business Simulator, Replay, benchmarks, investigation, and live-model evaluation cannot register or contact it.
- [x] 3.5 Add redacted QQ telemetry and short-retention adapter-journal handling for the minimum opaque reply locators, with secret-hygiene and no-raw-transcript tests.

## 4. Fault, Security, And Acceptance Verification

- [x] 4.1 Add offline acceptance cases for duplicate delivery, repeated/out-of-order/gapped sequence, reconnect/resume replay, restart after receipt, and concurrent intake, asserting one Case and one acknowledgement natural key.
- [x] 4.2 Add fault-injection cases for stop-after-intent, provider acceptance with lost response, pre-contact timeout, disconnect, duplicate response, conflicting identity, unreadable response, expired deadline, and restart, asserting no second logical acknowledgement and truthful incomplete states.
- [x] 4.3 Add negative security tests for foreign tenant/group, forged role/tenant, raw message/credential leakage, arbitrary reply/destination, missing/revoked capability, ordinary-command QQ activation, QQ-plus-model activation, and every other external-write executor.
- [x] 4.4 Add a machine-readable QQ acceptance report and verifier that distinguish fake transport from real sandbox verification, keep `customer_receipt_verified=false`, and reject raw identifiers/content, resolution, final-delivery, model-use, or production-readiness claims.
- [x] 4.5 Run the QQ offline acceptance repeatedly and the retained contract, intake, workflow, investigation, policy/approval, evidence, benchmark, operator, live-model, secret-hygiene, and full test baselines; record exact pass/fail metrics without weakening prior gates.

## 5. Operator Runbook, Live Sandbox Gate, And Closure

- [x] 5.1 Document QQ developer-portal prerequisites, sandbox group ownership/admin constraints, credential and group-mapping inputs, explicit start/stop/disable commands, redacted readiness, fixed acknowledgement text, limitations, and rollback without committing real values.
- [x] 5.2 Run the dedicated command with operator-supplied QQ sandbox credentials and one allowlisted group; send one real `@机器人 广告系统出现了API 503错误` message and capture payload-safe evidence for one Case plus one accepted/present fixed acknowledgement.
- [x] 5.3 Re-run the same real source event/reconnect or the bounded provider-deduplication acceptance procedure and verify no duplicate Case or second logical acknowledgement; if QQ cannot prove the outcome, retain `NEEDS_RECONCILIATION` and leave live verification incomplete.
- [x] 5.4 Update `docs/PROJECT_MEMORY.md` with verified implementation facts, live-versus-fake evidence, limitations, exact metrics, and the gate for `add-qq-handler-approval-and-delivery` without claiming customer receipt or resolution.
- [x] 5.5 Run strict OpenSpec validation, machine-readable evidence verification, formatting/lint/tests, and `git diff --check`; mark tasks complete only when their named checks pass.
