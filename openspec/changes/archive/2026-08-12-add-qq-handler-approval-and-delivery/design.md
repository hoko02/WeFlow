## Context

Stage 1 live-verified one allowlisted QQ sandbox group intake and one passive acknowledgement. Stage 2 adds one human handler without enabling models, business tools, production, or general QQ messaging.

The customer remains in the original group, but response preparation is confidential. QQ exposes different identities in group and C2C events, so the workflow cannot infer that a group `member_openid` and a C2C `user_openid` belong to the same person. It therefore uses an operator-confirmed dual challenge and records the resulting assurance level. Nicknames, QQ numbers, and provider member roles are never authorization inputs.

The provider offers two materially different write paths:

- an active C2C notification, which has no provider-side natural-key lookup that WeFlow can use after an ambiguous outcome;
- passive C2C and group replies, which can use the triggering `msg_id` plus a stable `msg_seq` within the provider reply window.

The design keeps those paths separate so an ambiguous notification cannot create duplicate messages and final customer delivery remains recoverable from a fresh group approval event.

## Goals / Non-Goals

**Goals:**

- bind exactly one sandbox handler across group and C2C identity surfaces;
- keep customer issue content, handler task context, drafts, replacements, rejections, and approval previews out of the group;
- support one private C2C accept/edit/reject workflow with exact candidate-version approval;
- make the group approval command metadata-only and authorize it against the same dual-surface binding;
- deliver the approved answer as a passive reply to the group approval event;
- preserve deterministic state ownership, append-only events, expiring content artifacts, idempotency evidence, and truthful live reports.

**Non-Goals:**

- no model invocation, automated diagnosis, or automated resolution;
- no QQ mail, attachments, images, Markdown drafts, arbitrary private chat, or general-purpose QQ sender;
- no draft, preview, customer issue body, or private task context in the group;
- no multiple handlers, groups, tenants, reassignment, escalation, or production rollout;
- no claim that provider acceptance proves customer receipt, issue resolution, or Case completion.

## Decisions

### 1. Activation is a dedicated, fail-closed sandbox command

`qq-sandbox-handler-approval` requires explicit live confirmation and the previously paired Stage 1 group. It enables only these Stage 2 capabilities:

- `qq.group_at.read`;
- `qq.c2c.read`;
- `qq.c2c.notification.execute` for one minimal active notification;
- `qq.c2c.passive_reply.execute` for private task and approval prompts;
- `qq.handler_approval.decide`;
- `qq.final_reply.execute` for the approved group reply.

Stage 1's `qq.passive_ack.execute` remains separate. Replay and ordinary development commands cannot activate these writes. Missing, stale, mismatched, or extra configuration fails before network contact.

### 2. Handler authority is a dual-surface binding

The local operator starts a bounded pairing session for the already paired group. The intended handler must complete:

1. an exact one-time group challenge, yielding the group `member_openid`;
2. an exact one-time C2C challenge, yielding the private `user_openid`;
3. local operator confirmation that both challenge results represent the intended person.

Only salted hashes and private provider locators needed for execution are retained. If QQ supplies a documented stable cross-surface identifier, equality is additionally required. Otherwise the binding records `operator_confirmed_dual_challenge`, and `production_ready` remains false. Nickname, QQ number, display text, and `member_role` are ignored for authorization.

Every C2C command must come from the bound `user_openid`; every group approval must come from the bound `member_openid`; both must resolve to the same active binding, group, tenant, Case, and workflow version.

Pairing confirmation and acceptance-report construction are separate durable boundaries. If both provider observations and local confirmation committed but report construction or output failed, the same command may resolve the one unexpired active binding only when App, tenant, group, and Stage 1 pairing all match. That recovery performs no Gateway or sender construction and returns `recovery_state=reconciled` instead of creating another challenge or binding.

### 3. The handler workflow is private; the group approval is metadata-only

After intake, WeFlow may make one active C2C notification attempt containing only the Case reference and `WF-PULL <case_ref>`. It contains neither the customer issue nor a draft. If active C2C is unavailable or ambiguous, the group may receive a non-sensitive nudge stating that the bound handler should privately pull the Case.

The closed C2C protocol is:

- `WF-PULL <case_ref>`: return the bounded customer issue privately;
- `WF-ACCEPT <case_ref> <expected_version>`: assign the Case to the bound handler;
- `WF-DRAFT <case_ref> <expected_version> <candidate>`: create or replace the current candidate;
- `WF-REJECT <case_ref> <expected_version> <reason_code>`: reject the current task or candidate.

Bot responses to those commands are passive replies to the current C2C source event and stay within the provider reply window and reply-count limit. After a valid draft, the private reply contains a bounded preview, `approval_request_id`, candidate hash prefix, and expected workflow version.

Final approval occurs in the original group only as:

`@机器人 WF-APPROVE <approval_request_id> <candidate_hash_prefix> <expected_version>`

The command contains no customer body, task context, draft, or preview. It is accepted only from the group member identity linked to the same binding that created the private draft. Any edit, replacement, rejection, expiration, ownership change, or workflow-version change invalidates the prior approval request.

### 4. Content is stored as two bounded, expiring artifacts—not a transcript

The Stage 2 command may store exactly:

- one normalized and redacted `QQCustomerIssueArtifact` derived from the accepted intake message;
- one current normalized and redacted `QQHandlerResponseArtifact` for the proposed answer.

Each artifact is plain text, 1–1200 Unicode scalar values after normalization, encrypted or otherwise protected by the repository's restricted artifact boundary, content-addressed, and inaccessible to logs, ledger payloads, fixtures, reports, and group messages. The maximum retention is 24 hours and deletion also occurs on the terminal Stage 2 outcome. Replacing a candidate makes the prior artifact unreachable and schedules it for deletion.

The system does not retain the group transcript, raw provider event, unrestricted tool output, or C2C transcript. Durable contracts carry artifact references, hashes, lengths, classifications, and safe reason codes only.

### 5. Candidate verification and approval are exact and version-bound

Candidate verification is deterministic and model-free. It requires the active Case revision, active dual-surface binding, customer-issue artifact hash, current candidate artifact hash, normalized candidate hash, workflow version, policy decision, and expiry.

An `ApprovalRequest` binds those facts. An `ApprovalDecision` is valid only when the group approval author resolves to the same binding and all bound values still match. The robot, candidate, or provider cannot approve. Stale, foreign, replayed, malformed, expired, or hash-prefix-ambiguous commands fail closed and produce no external write.

### 6. Side-effect recovery is path-specific

**Active C2C notification:** one intent and one transport attempt at most. A provider-accepted response completes it as accepted. A timeout, disconnect, or unknown provider outcome becomes `NOTIFICATION_UNKNOWN`; it is not retried and is not called delivered. A safe group nudge or later private pull is the recovery path.

**Passive C2C replies:** each reply derives a stable `msg_seq` and idempotency key from the C2C source `msg_id`, response kind, binding, Case, and workflow version. They execute only inside QQ's C2C passive-reply window and bounded reply count.

**Final group reply:** the valid group `WF-APPROVE` event is the source message. The approved candidate is sent once with that source `msg_id`, a stable `msg_seq`, and a natural key bound to the approval decision. Local state is reconciled before any repeat. If the provider outcome remains unknown or the passive window expires, the workflow stops for operator review; it does not switch to an active group send.

**Gateway ordering boundary:** QQ Gateway `s` values are scoped to one WebSocket session and may
restart at the same or a lower value after a new connection. The live transport rejects duplicate
or decreasing sequences inside one connection. Across connections, the durable ledger deduplicates
by the provider message natural key and retains only a diagnostic sequence high-water mark.
No path marks customer receipt, issue resolution, or Case completion from transport acceptance alone.

### 7. Evidence is layered and privacy-safe

The acceptance report separately records:

- dual-surface binding verified;
- active notification not attempted, provider accepted, or outcome unknown;
- private C2C pull/accept/draft/edit/reject flow verified;
- group metadata approval verified;
- final group passive reply provider accepted;
- duplicate attempts, rejected events, recovery state, and content-deletion evidence.

Reports contain no credentials, raw identities, provider events, customer issue, candidate text, transcript, or unrestricted response. Live verification keeps `model_invocation=false`, `customer_receipt_verified=false`, `issue_resolution=false`, `case_completion=false`, and `production_ready=false`.
Notification-attempt and artifact-deletion evidence is scoped to the current Case and binding; unrelated historical rows remain auditable but cannot inflate or satisfy the current acceptance report.

### 8. Binding revocation is local, explicit, append-only, and scope-bound

A Stage 1 group locator and its dependent Stage 2 handler binding have independent 24-hour lifetimes. A handler may therefore remain nominally active after the Stage 1 locator embedded in the immutable binding has expired. The operator may recover only after creating a new current Stage 1 pairing for the same App, tenant, and group.

The dedicated Stage 2 command exposes one local revocation phase. It requires the safe `qqhbind_...` selector, exact local confirmation, a current Stage 1 pairing, and equality of App, tenant, and group hashes. It constructs no Gateway or sender and performs no provider contact, Case mutation, model invocation, or external write.

Revocation never rewrites or deletes the immutable binding record. In one local transaction it appends one content-free `HANDLER_BINDING_REVOKED` event and clears and deactivates the binding's private provider locators. Active-binding lookup and unauthorized-rebinding checks derive current authority from the immutable binding plus that terminal event. Repeating the same revocation returns the existing terminal result without another event. A replacement dual-surface binding still requires fresh group and C2C challenges plus local confirmation.

## Risks / Trade-offs

- **Cross-surface identity assurance:** QQ may not expose a documented stable identifier joining group and C2C identities. Dual challenges plus operator confirmation are sufficient only for this sandbox increment, so production remains blocked.
- **Ambiguous active notification:** at-most-once execution can miss a notification. This is preferable to duplicate private messages; the non-sensitive group nudge and `WF-PULL` are the recovery route.
- **Two-surface user experience:** the handler drafts privately but approves in the group. The extra step supplies a fresh group event for exact authorization and provider-deduplicated final reply without leaking the draft.
- **Short passive windows:** delayed private or final replies can expire. Expiry is explicit and requires a new handler command or approval request rather than an unsafe active fallback.
- **Sensitive artifact retention:** even bounded text is private customer data. Content is redacted, restricted, content-addressed, and deleted within 24 hours or at terminal outcome.
- **Misaligned locator lifetimes:** a Stage 1 locator can expire while a dependent handler binding remains active. The local revocation path restores operability without mutating history or trusting a stale provider locator; direct SQLite edits remain forbidden.

## Migration Plan

1. Archive and sync the completed Stage 1 change before Apply begins.
2. Add contracts and schemas for dual-surface binding, customer-issue artifact, C2C commands, candidate, approval, notification, and final delivery.
3. Implement replay fixtures and negative identity/privacy tests before live transport code.
4. Add the dedicated Stage 2 command with all external writes disabled by default.
5. Live-verify dual pairing, one private workflow, one metadata-only group approval, and one final passive group reply.
6. Keep production, models, other groups, other handlers, and business integrations disabled.

Rollback disables the Stage 2 command and capabilities, locally revokes or naturally expires the handler binding, expires private artifacts, and leaves Stage 1 intake/ack behavior unchanged.

## Open Questions

None for Apply. Confidential C2C drafting and metadata-only group approval are locked for this increment. A future production proposal must resolve provider-supported cross-surface identity assurance and broader notification recovery.

## Live provider compatibility refinement

QQ may prove the real robot mention through `GROUP_AT_MESSAGE_CREATE` while omitting the mention
display token from provider-normalized `content`. The public metadata parser still requires a
mention marker. Only the provider boundary, after validating that exact event type, paired group,
message identity, timestamp, and bound member identity, may adapt mention-free `WF-APPROVE`
content into the same closed parser. Ordinary group text cannot activate this path. This live-found
provider shape does not broaden destination, identity, content, approval, or write authority.
