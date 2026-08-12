## Why

Stage 1 has live-verified that one allowlisted QQ sandbox-group `@机器人` message can create exactly one Case and receive exactly one fixed acknowledgement, but the Case still stops before a human can privately review, edit, approve, and deliver a response. The next independently verifiable increment should add a confidential QQ C2C handler workspace while keeping the customer-visible final answer in the original group, without enabling a model, business tools, multiple groups, or production rollout.

## What Changes

- Add one operator-confirmed dual-surface handler binding for the already paired sandbox group. The intended handler completes exact one-time challenges in both the group and QQ C2C so the server can bind the group's `member_openid` and the bot-private `user_openid`; display names, ordinary QQ numbers, and QQ-reported roles never grant authority.
- Add a dedicated, explicitly confirmed QQ handler-workflow command that reuses the one application, one group, and one tenant from Stage 1. Ordinary commands and Stage 1's narrower command remain unable to activate handler approval or final delivery.
- Send one minimal active C2C notification to the bound handler containing only the Case reference and a pull command. Because QQ exposes no provider-side reconciliation lookup for an ambiguous active send, this notification is attempted at most once; an unknown result is not retried or called delivered. A non-sensitive group nudge remains the fallback.
- Support a closed private-handler protocol in C2C: pull one Case, accept it, receive the bounded customer issue, submit or replace one plain-text response candidate, and reject it. The customer and other group members MUST NOT receive the C2C task context, draft, replacement, or preview.
- Require the final approval action in the original group as a metadata-only `WF-APPROVE` command containing no candidate body. It is accepted only from the group identity linked to the same private handler binding. The robot then uses that group approval event as the provider-deduplicated passive-reply source for final delivery.
- Persist only one normalized customer-issue artifact and one current redacted handler-candidate artifact in the restricted expiring content store; do not retain or forward a whole group/C2C transcript. Logs, ledger facts, fixtures, reports, group notices, and approval commands contain only identities, classifications, hashes, safe references, and reason codes.
- Bind every approval to tenant, Case/revision, handler identity and role, candidate/artifact hash, ordered evidence hashes, policy/capability versions and hashes, workflow checkpoint/version, destination resource, and expiry. Neither QQ payloads, buttons, nor a handler command may choose tenant, role, destination, state, authorization, or delivery result.
- After the metadata-only group approval passes policy and stale-binding checks, have the robot—not an untracked manual handler message—send the privately prepared candidate to the original group as a passive reply to that approval event, using a stable `msg_id + msg_seq` tuple and durable intent/reconcile/execute/observe/complete facts. Ambiguous results reuse the same tuple only inside its validity window; expiry or unresolved ambiguity stops in reconciliation without a blind retry.
- Add offline fake-transport, identity, stale-approval, candidate-replacement, restart, timeout/lost-response, provider-duplicate, cross-tenant/group, privacy, and command-isolation acceptance cases plus a separate real QQ sandbox acceptance report.
- Add an explicitly confirmed, repository-local handler-binding revocation path for the case where the Stage 1 group locator expires before its dependent Stage 2 binding. Revocation appends content-free audit evidence, immediately disables and scrubs the private execution locators, permits a replacement binding only under a current matching Stage 1 scope, and performs no provider contact, Case mutation, model invocation, or external write.
- Report C2C notification acceptance, private-handler workflow, group approval, and final provider acceptance separately from customer receipt, issue resolution, and Case completion. This increment enables no live model, CRM/monitoring/knowledge lookup, attachment, QQ mail, multiple handler/group/tenant, automatic diagnosis, or production readiness.
- Treat archived/synced Stage 1 `add-qq-sandbox-intake-and-ack` as an Apply prerequisite. This proposal may be reviewed while Stage 1 is still active, but implementation must not begin against an unsynchronized Stage 1 contract.

## Capabilities

### New Capabilities

- `qq-handler-approval-and-delivery`: Securely bind one fixed handler across the paired group and QQ C2C, run a confidential private accept/review/draft/edit protocol, expose only a metadata-only approval command in the group, and deliver the exact privately prepared and approved candidate through a recoverable group write.

### Modified Capabilities

- `versioned-domain-contracts`: Add closed, payload-safe dual-surface binding, private command, customer/candidate artifact, metadata-only approval, delivery, and acceptance-report contracts while preserving all retained v1 results.
- `case-event-ledger`: Permit deterministic handler-notification, assignment, candidate, approval, and final-delivery events with append-only causation and no customer-resolution authority.
- `response-candidate-verification`: Admit a server-authenticated human-handler candidate origin with bounded content/redaction and lineage checks, without treating human text as model evidence or automatic resolution proof.
- `policy-capability-gates`: Add short-lived, handler- and destination-scoped C2C read/reply/notification, group approval-decision, and final-delivery grants while keeping all unspecified subjects/actions/resources denied.
- `hash-bound-approval-gates`: Extend fixture-only approval semantics to the one bound QQ handler and require exact candidate, identity, checkpoint, destination, and expiry revalidation before delivery.
- `idempotent-side-effect-recovery`: Add separate at-most-once active C2C notification evidence plus provider-deduplicated passive C2C prompt and final-group-delivery recovery chains without broadening ticket or fixture delivery executors.
- `safe-provider-runtime-boundary`: Add a command-local Stage 2 QQ exception for the exact C2C handler workflow and final group delivery while models, tools, arbitrary content/destinations, and other external writes remain disabled.

## Impact

- Contracts: additive Python/TypeScript schemas and semantic fixtures for dual-surface identity, private C2C commands, issue/candidate artifacts, metadata-only group approval, QQ write evidence, and truthful acceptance reporting.
- Control/runtime: deterministic dual-challenge handler enrollment, C2C authorization, Case-scoped private handler workflow, candidate replacement, group approval revalidation, and command-local QQ transport registration; no Agent/model initialization.
- Persistence: a server-owned group/C2C handler registry, append-only workflow/approval/delivery facts, stable deduplication identities, one expiring customer-issue artifact, and one expiring current response artifact; no full group or private transcript and no raw identifier in business records.
- QQ boundary: one paired sandbox group, one fixed C2C handler, minimal active C2C notification, passive private task/preview replies, a group `@机器人 WF-APPROVE ...` command with no candidate body, and passive final group reply to that approval event. C2C 60-minute and group five-minute reply windows, active-send ambiguity, permissions, quotas, and unknown outcomes remain explicit failure modes.
- Security/operations: explicit live confirmation, external credentials/locators, default-deny capability profile, redacted readiness and reports, bounded retention/deletion, and immediate disable/rollback without rewriting audit facts.
- Verification/docs: offline acceptance remains credential-free; live verification requires the real sandbox, bound handler, and one operator-observed workflow. The runbook and `docs/PROJECT_MEMORY.md` will record implemented versus live-verified claims and the remaining gate for Stage 3 model use.
