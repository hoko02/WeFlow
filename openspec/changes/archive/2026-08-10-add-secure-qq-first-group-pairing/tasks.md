## 1. Pairing Contracts And Compatibility

- [x] 1.1 Add closed v1 JSON Schemas for `QQGroupPairingChallenge`, `QQGroupPairingCompletion`, and `QQGroupPairingAcceptanceReport` with safe lifecycle/linkage fields and no challenge plaintext, raw QQ identifiers, credentials, effects, or customer-outcome claims.
- [x] 1.2 Add Python and TypeScript bindings plus semantic validators and valid/invalid fixtures for hashes, deadlines, statuses, duplicate/foreign references, fake/live evidence flags, raw locators/events, authority claims, and false Stage 1 success.
- [x] 1.3 Extend the cross-language compatibility command so every new pairing fixture agrees in both languages and every retained valid/invalid v1 result remains unchanged.

## 2. Deterministic Challenge And Pairing Journal

- [x] 2.1 Implement the command-local pairing configuration validator with exact `--confirm-live-qq-pairing`, process-only AppID/AppSecret, one server-owned tenant, the sole `qq.group_pair.read` capability, repository-local storage, redacted readiness, and pre-contact denial tests for any group/write/model/multi-Agent/expanded scope.
- [x] 2.2 Implement generation of one at-least-128-bit `WFPAIR-` challenge, five-minute deadline, digest-only persistence, exact mention-stripped plain-text matching, and rejection of direct/attachment/card/nested/malformed/expired/nonmatching events without retaining challenge text or member identity.
- [x] 2.3 Add append-only challenge/completion and private locator persistence in `.weflow/qq-sandbox.sqlite3` with one current application/tenant binding, stable safe pairing ID, source/group/application hashes, atomic completion, uniqueness, owner-only permissions where supported, 24-hour expiry/purge, and bounded local revocation.
- [x] 2.4 Prove exact duplicate, reconnect/resume, restart-before/after completion, concurrent consumer, different-group conflict, sequence gap, expired challenge, revoked binding, and corrupt/unreadable locator behavior with reconstruction and fault-injection tests.

## 3. Read-Only QQ Runtime And Stage 1 Handoff

- [x] 3.1 Reuse the narrow token/gateway/WebSocket/heartbeat/resume interfaces behind pairing-specific fakes and a pairing runner that cannot construct the passive-send executor, Case ledger, workflow, Agent Runtime, Business Simulator, model, approval, or other provider client.
- [x] 3.2 Add the real bounded pairing command and safe stop/reconnect behavior; accept one exact challenge event, commit one pairing, emit only safe evidence, and exit without any QQ API write or Case/workflow mutation.
- [x] 3.3 Add mutually exclusive Stage 1 selector modes for a pre-known direct group or a current safe pairing ID; in pairing mode resolve and verify the application/tenant/group locator before intake/send construction, while keeping the identity salt and exact Stage 1 capability gates unchanged.
- [x] 3.4 Reserve `WFPAIR-` at the normal QQ intake boundary and isolate pairing cursor/session state so pairing or replayed control messages can never create a receipt, Case, revision, BusinessEvent, acknowledgement intent, or QQ send.
- [x] 3.5 Prove ordinary startup, health, Replay, benchmarks, investigations, retained acceptances, live-model evaluation, and every non-pairing command reject pairing configuration and cannot import/contact the real pairing adapter.

## 4. Security, Fault, And Acceptance Evidence

- [x] 4.1 Add a deterministic offline pairing acceptance matrix for valid matching, wrong content/group, duplicate, race, reconnect, restart, conflict, expiry, revoke, selector handoff, and reserved-prefix rejection; compare repeated reports for a stable baseline.
- [x] 4.2 Add negative security tests for ordinary QQ group numbers, caller-selected group/tenant, nickname/member-role authority, challenge guessing/reuse, raw locator/event/member/message leakage, credential/token leakage, repository-external stores, arbitrary QQ writes, Case/workflow/model/tool/approval activation, and fake-as-live claims.
- [x] 4.3 Add separate offline and live machine-readable pairing reports plus an independent verifier that requires real-adapter completion for `qq_group_pairing_live_verified=true` and fixes Case creation, QQ writes, acknowledgement, model use, handler binding, customer receipt, resolution, completion, production readiness, and Stage 1 verification to false.
- [x] 4.4 Run secret hygiene, pairing-focused contract/unit/recovery/security/e2e tests, retained QQ tests, full contract/lint/typecheck/test baselines, and retained acceptance commands; record exact pass/fail metrics without weakening any prior gate.

## 5. Operator Runbook, Real Pairing Gate, And Closure

- [x] 5.1 Update the QQ runbook and `docs/PROJECT_MEMORY.md` with the portal bootstrap gap, process-only setup, exact challenge flow, pairing-ID handoff, expiry/revoke/rollback, raw-locator prohibition, fake-versus-live status, and the fact that existing Stage 1 tasks 5.2/5.3 remain separately blocked.
- [x] 5.2 With operator-supplied sandbox credentials and one controlled non-production group, run the dedicated command, send exactly the displayed `@机器人 WFPAIR-...` challenge, and capture payload-safe evidence for one real completed pairing with zero Case/workflow/QQ-write/model effects.
- [x] 5.3 Independently verify the real pairing report and use only its safe pairing ID to pass the Stage 1 pre-contact selector/readiness checks; do not send the API-503 intake message or mark the other change's live intake/ack tasks complete in this task.
- [x] 5.4 Run strict OpenSpec validation, machine-readable evidence verification, formatting/lint/tests, secret scanning, and `git diff --check`; mark each task complete only after its named checks pass and preserve every unavailable live prerequisite as an explicit limitation.
