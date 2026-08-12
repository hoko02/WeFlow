## Context

WeFlow already has a deterministic synthetic IM intake, append-only Case ledger, durable workflow/recovery journal, Replay-first runtime, policy gates, and fixture-local outbound delivery. It does not have a real enterprise-IM listener or a permitted real business write. The requested product direction is a QQ group robot representing WeFlow, but enabling intake, handler approval, final delivery, and a live model at once would make failures hard to attribute and would weaken the existing safety claims.

This change is therefore the first live QQ vertical increment only. One operator-controlled process connects to one QQ sandbox application and one allowlisted group, consumes group `@机器人` text events over WebSocket, creates the existing Case ledger state, and posts a fixed passive acknowledgement. The customer, handler, and final-resolution workflow remains a later change.

The key constraints are:

- Deterministic code owns identity, deduplication, Case creation, capability checks, retries, evidence, and completion classification.
- The Agent Runtime, live-model provider, business tools, approval system, and final outbound-delivery path are not used.
- Every QQ acknowledgement is a real external write and must follow intent, reconcile, execute, observe, and complete semantics.
- Default startup, CI, Replay fixtures, and existing commands stay offline and require no QQ credentials.
- Raw QQ message text, group transcripts, attachment bytes, access tokens, secrets, and unrestricted provider payloads cannot enter ledger records, logs, fixtures, prompts, or reports.
- Provider acceptance does not prove that a customer read the acknowledgement and never proves that the Case is resolved.

## Goals / Non-Goals

**Goals:**

- Live-verify one QQ sandbox-group `@机器人` text event flowing into one tenant-scoped Case exactly once.
- Send one fixed, plain-text “已受理” acknowledgement tied to the source QQ message and Case.
- Survive duplicate gateway events, WebSocket reconnect/resume, process restart, and ambiguous send outcomes without creating a second Case or second logical acknowledgement.
- Preserve payload safety, tenant isolation, explicit live activation, redacted evidence, and offline testability.
- Produce machine-readable acceptance evidence that distinguishes simulated/fake-transport checks from real QQ sandbox verification.

**Non-Goals:**

- Handler notification, QQ mail, handler editing/approval, or a final customer answer.
- Live model use, CRM/monitoring/knowledge retrieval, investigation, diagnosis, or response drafting.
- Attachments, images, Markdown, buttons, commands other than group `@机器人` text, direct messages, or collection of unrelated group messages.
- Multiple QQ applications, groups, tenants, dynamic tenant selection, production QQ rollout, formal-environment IP allowlisting, or general connector infrastructure.
- Persisting or displaying raw QQ message text in this stage.
- Claiming customer receipt, issue resolution, Case completion, or production reliability from a successful send response.

## Decisions

### 1. Use a dedicated QQ sandbox command and WebSocket transport

The QQ adapter will run from an explicit command such as `python scripts/dev.py qq-sandbox-intake-ack`, hosted by the control-worker boundary. It will obtain the QQ gateway and maintain the WebSocket heartbeat/session cursor only inside that command. The adapter will not be registered by normal service startup and will not be imported into the Agent Runtime.

Activation requires all of the following operator-owned inputs: the exact live-confirmation flag, sandbox environment, application credentials supplied outside CLI arguments and tracked files, one allowlisted `group_openid`, one configured tenant mapping, and a capability profile containing only `qq.group_at.read` and `qq.passive_ack.execute`. Readiness fails closed before network contact if any gate is absent or malformed.

WebSocket is chosen over Webhook for the first stage because it avoids a public HTTPS callback and signature-verification deployment while preserving gateway sequence and resume behavior. Webhook support remains a later connector concern. The QQ transport is hidden behind a narrow interface with a deterministic fake so CI remains offline.

### 2. Keep QQ identity mapping server-owned and payload-safe

The operator configuration binds `(qq_environment, app_id_hash, group_openid_hash)` to exactly one `tenant_id` and conversation identity. Sender `member_openid` is transformed to a tenant-scoped actor/customer reference by a server-owned keyed hash. Display names, message text, caller fields, and QQ member-role strings never select tenant or workflow authority.

The adapter accepts only the configured group event type, an allowlisted group, a positive gateway sequence, a stable QQ message identifier, and non-empty text remaining after the robot mention is removed. Attachments, direct messages, other groups, malformed timestamps, unsupported event types, and foreign identities are rejected before Case creation or acknowledgement intent.

A new `QQSandboxInboundEvent` contract carries safe provider identity hashes, message identity, sequence, timestamps, content SHA-256, classification, and correlation fields. Raw message text exists only in adapter memory long enough to validate the event and calculate its digest, then is discarded. A short-lived adapter journal may retain the opaque source `msg_id`, fixed `msg_seq`, and configured group locator required for passive reply/recovery; it may not retain message content or sender display data.

This first step intentionally creates a Case whose source content is hash-only. Handler-visible content retention/redaction is a product and privacy decision for stage two, not an implicit side effect of stage one.

### 3. Deduplicate before the atomic Case ledger transaction

The inbound natural key is the canonical hash of:

`tenant_id | qq-sandbox | app_id_hash | group_openid_hash | source_msg_id`

The durable receipt table has a uniqueness constraint on tenant plus this natural key. For the first accepted event, the control kernel reuses the existing atomic ledger transaction to create one Case, immutable CaseRevision 1, and the three ordered BusinessEvents ending in `RECEIVED`. An exact replay returns the original Case and receipt without adding records or scheduling another acknowledgement.

The gateway cursor stores only safe application/group hashes, session identity hash, last contiguous sequence, and timestamps. A repeated sequence is deduplicated; a gap or out-of-order sequence triggers resume/reconnect handling and cannot advance the durable cursor past an unaccounted event. The cursor advances only after the inbound receipt/ledger outcome is durable. QQ resume can replay an event safely because business deduplication is independent of the session cursor.

For the bounded live deduplication acceptance only, an explicit command flag may pass
one newly observed real provider event through the deterministic intake and
acknowledgement control path a second time while that same frame remains in memory. The
second pass must resolve to the first pass's Case and acknowledgement intent, must stop
at the existing completion before any second QQ transport call, and must leave ledger
and acknowledgement counts unchanged. The frame is discarded after the command and is
never persisted or reconstructed from private chat data. If the original command has
already exited, the operator must use one new test event for this bounded procedure;
manually sending the same text twice is not evidence of source-event deduplication.
### 4. Treat the acknowledgement as a separate, fixed real-write workflow

After the intake transaction commits, deterministic control code may create one `QQAcknowledgementIntent`; intake itself does not call QQ. The acknowledgement text is code-owned and content-addressed:

`已受理，工单编号：{case_id}。当前仅确认已进入处理流程，不代表问题已解决。`

No fixture, event body, model, caller, or QQ user may replace the template or destination. The intent binds tenant, Case/revision, source message, configured group, fixed template hash, passive-reply deadline, stable natural key, and stable idempotency key. Its natural key is `tenant_id | case_id | case_revision_id | qq.passive_ack.v1`; its provider deduplication tuple uses the original source `msg_id` plus a deterministic positive `msg_seq` reserved for this acknowledgement.

Processing is always:

1. Persist intent.
2. Reconcile the local journal and provider-deduplication identity.
3. Execute only if no completed/present result is known and the passive-reply deadline is still valid.
4. Persist a safe observation.
5. Persist completion only for a validated provider-accepted or provider-duplicate/present outcome.

On timeout, disconnect, lost response, unreadable provider response, expired reply window, or conflicting identifiers, the operation remains unknown/failed and enters `NEEDS_RECONCILIATION`; it is not marked complete. A retry uses the same source `msg_id` and deterministic `msg_seq`, never a new logical message identity. If the provider cannot prove accepted/present, the system does not claim delivery. Restart reconstructs the original intent and deadline before any call.

The QQ acknowledgement executor is the only real-write executor enabled by this command. It cannot send arbitrary content, choose another group, send a final answer, invoke approval, or transition the Case to resolved/completed.

### 5. Separate operational success from customer outcome

The command records safe counters and hashes for gateway connection, accepted/rejected/deduplicated events, Case identity, acknowledgement intent/observation/completion, retry/reconciliation status, and redaction checks. It records three distinct booleans:

- `fake_transport_verified`: deterministic offline acceptance passed.
- `qq_sandbox_live_verified`: the operator-run command observed an allowlisted real QQ event and a validated QQ acknowledgement acceptance/presence result.
- `customer_receipt_verified`: always `false` in this change.

Case resolution/completion is never derived from these fields. Reports cannot include raw QQ content, open IDs, credentials, access tokens, unrestricted provider responses, or customer-success claims.

### 6. Preserve the existing Replay and synthetic behavior

Existing intake contracts and fixtures remain valid. QQ uses additive contracts and a separate adapter path rather than changing synthetic fixture semantics. Normal `check`, `up`, `test`, benchmark, investigation, live-model evaluation, and other commands remain unable to initialize QQ network clients or real-write executors. Supplying QQ credentials or a group destination to any ordinary command is a redacted startup denial.

Offline tests inject fake token, gateway, WebSocket, and send transports. The fake suite covers duplicate event delivery, out-of-order/gap sequence, reconnect/resume replay, process restart after intent, response loss after provider acceptance, timeout before acceptance, reply-window expiry, provider duplicate response, foreign tenant/group, credential-like input, arbitrary acknowledgement content, and attempts to combine QQ with a live model or another external write.

## Risks / Trade-offs

- [The first-stage Case does not retain readable customer text] → Make this limitation explicit; preserve only a content hash and defer approved retention/redaction to the handler stage.
- [QQ gateway or send semantics may differ between sandbox and formal environments] → Mark evidence as sandbox-only, pin tested API/event versions, retain fake fault cases, and require a later production-readiness change.
- [A lost send response may be impossible to prove conclusively] → Reuse the same provider deduplication tuple, keep ambiguous outcomes in `NEEDS_RECONCILIATION`, and never equate timeout with success.
- [Passive reply deadlines can expire during recovery] → Persist the source timestamp/deadline, refuse execution after expiry, and surface a safe terminal acknowledgement failure without altering the Case outcome.
- [Opaque QQ identifiers can still be sensitive correlation data] → Hash actor/application/group identity in business records, retain only the minimum reply locator in the bounded adapter journal, redact diagnostics, and apply short retention.
- [A live credential could accidentally affect normal development] → Make the QQ adapter command-local, default-deny ordinary commands, require an explicit confirmation flag, and ensure tests use injected fakes.
- [One group-to-one tenant mapping is operationally narrow] → Treat it as a deliberate first-slice constraint; multi-group/multi-tenant routing requires a later independently verified change.

## Migration Plan

1. Add and cross-language validate the additive QQ contracts and safe invalid fixtures without changing existing v1 acceptance.
2. Add the deterministic identity mapping, inbound deduplication, ledger integration, acknowledgement journal, and fake transports behind a disabled capability.
3. Add offline acceptance and negative tests; prove existing Replay and synthetic baselines unchanged.
4. Add the explicit operator command, redacted readiness, and sandbox acceptance report generation.
5. With operator-supplied QQ sandbox credentials and group membership, run the live acceptance once and record the bounded result. Lack of credentials leaves the implementation tested but not live-verified.

Rollback disables/removes the QQ command configuration and credentials, stops the adapter, and leaves append-only Cases and acknowledgement facts intact for audit. Rollback must not delete or rewrite ledger evidence. Normal offline services remain available throughout.

## Open Questions

No architecture question blocks implementation. QQ application credentials, the sandbox `group_openid`, the one-tenant mapping, and a real test message are operator prerequisites for live verification and must not be committed to the repository.
