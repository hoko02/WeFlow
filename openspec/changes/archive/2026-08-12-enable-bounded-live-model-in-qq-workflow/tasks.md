## 1. Contracts and reviewed profiles

- [x] 1.1 Add closed v1 schemas for Stage 3 readiness, `WF-ASSIST`, assist request/outcome, model-safe QQ Context, Case-bound invocation/budget evidence, model candidate provenance, private preview metadata, integrated acceptance, and independent verification.
- [x] 1.2 Implement immutable Python contract models and semantic validators for every Stage 3 schema, including safe identifier/hash, capability, lineage, metric, privacy, and outcome-separation invariants.
- [x] 1.3 Add matching TypeScript types/validators and keep all existing Stage 1, Stage 2, Replay, and live-evaluation contracts unchanged.
- [x] 1.4 Add valid and invalid cross-language fixtures for current/foreign/stale assist commands, caller/model authority fields, detached lineage, fake-as-live claims, unsafe report content, missing metrics, and forbidden customer-success flags.
- [x] 1.5 Define one checked-in Stage 3 API-503 profile that hash-binds the sandbox tenant resource, synthetic CRM/monitoring/knowledge sources, prompt template, exact QQ/model capabilities, provider/model/price profile, retention, and hard budgets.
- [x] 1.6 Implement profile loading that rejects duplicate keys, path escape, missing/mutated sources, stale price validity, unsupported inference mode, mismatched model/provider, and expanded capabilities before credential access.
- [x] 1.7 Add Python/TypeScript compatibility tests proving old valid fixtures remain valid, old invalid fixtures remain invalid, and every new privileged shape fails closed on unknown fields.
- [x] 1.8 Decouple the Stage 3 cumulative Case budget from the retained live-evaluation attempt budget, set the reviewed Stage 3 estimated-cost hard limit to USD 0.50, and prove the USD 0.02 evaluation baseline remains unchanged in both preflight and the constructed Agent runtime.

## 2. Append-only Stage 3 state and recovery identities

- [x] 2.1 Add append-only local records for assist requests/outcomes, Context bindings, per-Case budget reservations/usage, invocation links, model candidate provenance, invalidation, and content deletion without storing raw QQ/model/private bodies.
- [x] 2.2 Derive stable natural identities and idempotency keys for assist source events, logical turns, invocation intent/observation, normalized actions, tool exchanges, candidates, private replies, approvals, and final QQ effects.
- [x] 2.3 Extend the handler-workflow projection with version-checked `ASSIST_REQUESTED`, `INVESTIGATING`, `RESPONSE_READY`, and safe manual/operator outcomes while preserving immutable Case revisions and the archived manual Stage 2 states.
- [x] 2.4 Implement duplicate/conflict detection so the same C2C source event reuses one assist request and a conflicting Case/version/handler/profile fails before model contact.
- [x] 2.5 Implement recovery that reuses conclusive invocation/action/tool/candidate/verifier evidence and closes an intent without conclusive observation as `provider_outcome_unknown` without an automatic call.
- [x] 2.6 Scope model calls/tokens/time/cost and tool/action/no-progress accounting to both the assist request and cumulative Case budget, including pessimistic reservation for ambiguous calls.
- [x] 2.7 Extend restricted artifact retention so model issue views and candidates become unreachable and emit content-free deletion evidence on replacement, rejection, final provider acceptance, or 24-hour expiry.
- [x] 2.8 Add migration/reopen tests proving existing Stage 1/2 SQLite stores remain readable, historical notification counts do not affect new Cases, and no recovery scan repeats an earlier QQ or model logical effect.

## 3. Dedicated activation and dual-provider isolation

- [x] 3.1 Add a Stage 3 configuration loader with separate exact QQ and model capability profiles, dual explicit confirmations, current pairing/binding selectors, hard budgets, and process-only QQ/model credentials.
- [x] 3.2 Enforce preflight ordering: validate non-secret source hashes, selectors, identities, capabilities, public endpoint, profiles, price validity, and budgets before reading secrets or constructing either client.
- [x] 3.3 Reuse the live provider's HTTPS/DNS/redirect/model/profile hardening and construct it only inside the dedicated Stage 3 runner; reject private/IP/credential-bearing destinations and unrestricted provider overrides.
- [x] 3.4 Compose only the existing Stage 1 fixed acknowledgement plus Stage 2 notification/passive-reply/approval/final-reply operations; do not expose a general QQ sender or alternate active-send fallback.
- [x] 3.5 Keep normal startup, CI, Replay, Stage 1, Stage 2, and isolated live-evaluation commands unable to import or inherit combined Stage 3 authority; make visible Stage 3-only configuration fail closed in those commands.
- [x] 3.6 Add a readiness-only path that resolves current safe pairing/binding and all reviewed profiles with `network_contacted=false`, `model_invocation=false`, `case_mutation=false`, and `external_write_attempted=false`.
- [x] 3.7 Support injected fake QQ and model transports through the same adapters while preventing fake/Replay modes from publishing live-integrated evidence.
- [x] 3.8 Add configuration/dispatch tests for missing/extra capabilities, stale selectors/profile, secret loading order, incompatible general-write/multi-Agent/mail/attachment switches, and ordinary-command denial.

## 4. Private assist protocol, Context, Agent, and tools

- [x] 4.1 Extend the closed C2C parser with exact `WF-ASSIST <case_id> <expected_version>` syntax and reject free-form bodies, group-surface text, attachment/card payloads, ambiguity, or unknown commands.
- [x] 4.2 Authorize `WF-ASSIST` only from the active bound C2C identity after private pull/accept for the current paired tenant/group, Case/revision, workflow version, unexpired issue artifact, profile, and budget.
- [x] 4.3 Persist one handler-authored assist request before model contact and prove that customer intake, acknowledgement, notification, pull, accept, duplicates, model output, and provider output cannot create one.
- [x] 4.4 Compile `QQModelAssistContext` from server-owned identities/hashes, one normalized redacted issue view, the reviewed synthetic source profile, current policies/capabilities, and budgets.
- [x] 4.5 Keep prompt instructions structurally separate from untrusted issue/tool data and prove raw QQ identities/locators/events, transcripts, handler/approval commands, credentials, unrestricted errors, and foreign content never enter prompts or durable evidence.
- [x] 4.6 Reuse the closed `ModelActionProposal` to `AgentAction` normalization and reject model-selected identities, providers, tools/arguments, states, approval, delivery, external writes, and success claims.
- [x] 4.7 Map Stage 3 read actions only to the current tenant-scoped checked-in CRM, monitoring, and knowledge sources, returning durable safe hashes plus ephemeral bounded model observations with no business-system network/write client.
- [x] 4.8 Enforce action/tool/provider-call/token/time/cost/no-progress budgets before every model/tool operation and allow only the reviewed explicit rate/unavailable retry; never retry an unknown outcome automatically.
- [x] 4.9 Return needs-information/operator, tool timeout, budget exhaustion, policy denial, malformed output, and provider-unknown outcomes only as bounded private replies and preserve current-version manual `WF-DRAFT` continuation.
- [x] 4.10 Add unit tests for happy-path tool sequencing, prompt injection, unsafe issue/tool content, foreign sources, arbitrary arguments, duplicate assist delivery, stale versions, restart reuse, and manual fallback.

## 5. Candidate, verifier, approval, and final delivery

- [x] 5.1 Normalize a safe model draft into one restricted `QQHandlerResponseArtifact` and persist a content-free binding from assist request through Context, invocation/action, ordered evidence, verifier, Case/version, handler, policies/profiles, and budgets.
- [x] 5.2 Extend deterministic candidate verification to enforce grounding, redaction, current evidence/retention, handler/Case/workflow/profile/budget binding, and prohibited authority/customer-success language before `RESPONSE_READY`.
- [x] 5.3 Return the model candidate, bounded evidence/source summary, usage/budget summary, and group-safe approval metadata only as a passive reply to the initiating bound-handler C2C source event.
- [x] 5.4 Preserve `WF-DRAFT` as a human replacement path that atomically invalidates the model candidate/provenance, approval request/decision, hash prefix, and content reachability before creating the replacement.
- [x] 5.5 Extend approval-request bindings for model candidates with the initiating handler, assist request, Context, invocation, provider/prompt/profile, ordered evidence, verifier, budget, issue/candidate artifacts, Case/revision, workflow version, and expiry.
- [x] 5.6 Accept metadata-only group approval only from the linked group identity for the C2C handler that authored the assist request, and reject model/provider/robot/customer/foreign/stale or body-bearing approval.
- [x] 5.7 Revalidate every identity, lineage, content, policy/capability/profile, retention, version, budget, and expiry immediately before persisting the final QQ intent.
- [x] 5.8 Reuse the Stage 2 passive final reply natural/idempotency key and `msg_id`/stable `msg_seq` recovery; prove timeout, disconnect, duplicate, expiry, and restart never switch to active send or create another logical reply.
- [x] 5.9 Keep provider acceptance separate from customer receipt, issue resolution, Case completion, production readiness, and permission for another model or QQ effect in code, schemas, reports, and tests.

## 6. Reports, privacy, offline acceptance, and fault evidence

- [x] 6.1 Build separate offline-fake and real-integrated report candidates with canonical hashes, source-linked counts, provider modes, usage/cost/latency, closed failure attribution, privacy/deletion flags, capability constants, and layered outcomes.
- [x] 6.2 Implement an independent no-network/no-credential verifier that revalidates schemas, canonical report hash, source identities, invocation/tool/candidate/approval/effect lineage, budgets, deletion evidence, provider modes, and business-outcome separation.
- [x] 6.3 Add a credential-free end-to-end fake acceptance covering customer intake/one ACK, handler notification/pull/accept/assist, model tool reads/candidate, private preview, exact group approval, one final reply, and artifact deletion.
- [x] 6.4 Add duplicate/out-of-order/concurrent/reconnect tests proving one Case, ACK, notification attempt, assist request, logical model turn/tool result/candidate, approval, and final logical QQ reply per natural key.
- [x] 6.5 Add the model failure matrix for explicit retryable rejection, timeout/disconnect/unknown, malformed/excessive output, prompt injection, tool timeout, missing/conflicting evidence, budget/no-progress exhaustion, and stale price/profile.
- [x] 6.6 Add tenant/handler/group/version/retention/approval negative tests and sentinel scans proving no secret, raw identity/locator/event, transcript, issue/draft/prompt body, unrestricted tool/provider response, or caller-supplied success enters logs, SQLite, fixtures, reports, or exceptions.
- [x] 6.7 Inject interruption after assist, invocation intent/observation, action, tool result, candidate artifact/binding, verifier, private reply intent, approval, and final QQ intent/observation/completion; verify deterministic recovery and no duplicate visible/model effect.
- [x] 6.8 Atomically publish an accepted report only after every hard gate passes; preserve any prior accepted report and emit only bounded diagnostics on incomplete/failed/fake evidence.
- [x] 6.9 Re-run retained Stage 1, manual Stage 2, Replay investigation, policy/approval, evidence, benchmark, console/timeline, and six-task live-model fake-boundary checks to prove prior semantics and reports remain valid.

## 7. Command, runbook, and real QQ-plus-model acceptance

- [x] 7.1 Register `qq-sandbox-live-model-workflow` and its independent verifier behind `scripts/dev.py`, including readiness-only, offline-fake, live, output, provider/profile, pairing, and handler selectors with safe machine-readable errors.
- [x] 7.2 Write a Stage 3 runbook for process-only QQ/model secret setup, exact capability profiles, price/profile preflight, safe pairing/binding reuse, readiness, the complete `WF-PULL`/`WF-ACCEPT`/`WF-ASSIST`/optional `WF-DRAFT`/`WF-APPROVE` flow, and evidence interpretation.
- [x] 7.3 Document privacy review, estimated-cost limits, fake-versus-live distinctions, model/tool synthetic boundaries, unknown outcome handling, manual fallback, rollback, artifact expiry/deletion, and prohibition on screenshots/raw SQLite/provider bodies.
- [x] 7.4 Reverify the selected public provider's official model/structured-output/usage and current pricing metadata; update/review the checked-in dated profile if necessary and keep the task incomplete while the profile is stale or mismatched.
- [x] 7.5 Run the readiness-only and credential-free offline-fake acceptance plus independent verification, retaining a redacted canonical offline report with `network_contacted=false` and `external_write_attempted=false`.
- [x] 7.6 Independently verify the current real Stage 1 pairing and active Stage 2 handler binding; stop if App/tenant/group/handler/profile scope is stale, revoked, expired, ambiguous, or mismatched.
- [x] 7.6a Capture and persist the current QQ `READY` session boundary before Stage 3 intake, pass that session through cursor accounting, retain same-session ordering and message-level business deduplication, and emit content-free live progress/rejection diagnostics without exposing message or identity data.
- [x] 7.6b Use canonical integrated report mode `qq-model-integrated-live` and provide a no-network, no-credential, no-effect recovery path that can publish reports only from a current completed Case with full durable ACK/handler/model/tool/candidate/approval/final/deletion evidence.
- [x] 7.7 With operator-supplied process-only sandbox and model credentials, run one new controlled synthetic API-503 QQ Case through fixed ACK, private handler `WF-ASSIST`, actual public-model/tool investigation, verifier-authorized candidate, exact group approval, and one provider-accepted passive final reply.
- [x] 7.8 Independently verify the real integrated report and confirm actual model calls/tokens/estimated cost/latency, complete lineage and deletion, no duplicate logical effects, and false customer receipt/resolution/Case completion/production readiness.

## 8. Final regression and OpenSpec closure

- [x] 8.1 Run `scripts/dev.py check`, Ruff lint/format, TypeScript lint/typecheck, Python/TypeScript contracts, focused Stage 3 tests, and the complete repository test suite with any unavailable service boundary reported honestly.
- [x] 8.2 Run repository secret scanning and inspect the change/report diff for credentials, raw QQ/provider/private content, unrestricted output, unsafe paths, and generated runtime databases/artifacts.
- [x] 8.3 Run all retained acceptance commands required by archive evidence integrity and record exact pass/fail/skip counts without converting environment limitations into passes.
- [x] 8.4 Update README capability status, the Stage 3 runbook links, and `docs/PROJECT_MEMORY.md` only with verified implementation/live facts, metrics, limitations, and the next-stage gate.
- [x] 8.5 Run `openspec validate enable-bounded-live-model-in-qq-workflow --strict`, `openspec validate --all --strict`, independent report verification, and `git diff --check`; resolve every failure before archive.
- [x] 8.6 Confirm all tasks, including real QQ-plus-model acceptance, are complete before syncing/archiving; fake transport, partial reports, provider acceptance alone, or a useful-looking model draft MUST NOT satisfy closure.
