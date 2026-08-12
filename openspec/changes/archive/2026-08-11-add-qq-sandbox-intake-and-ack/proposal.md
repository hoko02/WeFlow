## Why

WeFlow currently proves the API-503 support workflow only through synthetic intake and fixture-local delivery. That is enough to validate deterministic workflow behavior, but it does not prove that the project can act as a real group-chat robot. The first QQ increment should establish the smallest live boundary that is useful and independently verifiable: receive one allowlisted QQ sandbox-group `@机器人` text event, create the existing tenant-scoped Case exactly once, and return one controlled “已受理” acknowledgement without invoking a model or claiming resolution.

## What Changes

- Add an operator-started QQ sandbox adapter using QQ's WebSocket event path for one configured application, one allowlisted sandbox group, and one server-mapped tenant.
- Accept only allowlisted group `@机器人` text events. Normalize QQ identifiers and hashes into a payload-safe inbound contract; do not persist raw group transcripts, message bodies, credentials, attachment bytes, or unrestricted QQ responses in the ledger, logs, fixtures, or reports.
- Map the QQ group and sender identities to tenant, conversation, customer/actor, and role through server-owned configuration. Never trust a caller-selected tenant, display name, or QQ-reported member role as workflow authority.
- Deduplicate repeated or replayed QQ events before Case creation by a stable natural key derived from the configured QQ application/channel, group identity, and message identity. Preserve the existing append-only Case/revision/event invariants and tenant-scoped reads.
- Add one fixed, plain-text passive acknowledgement for a newly accepted Case. The acknowledgement is a narrowly scoped real external write and therefore uses durable intent, reconcile, execute, observe, and complete records with a stable idempotency key. A retry or lost response must not produce a second logical acknowledgement.
- Keep QQ live mode disabled by default. Activation requires an explicit operator-controlled sandbox command/configuration, an allowlisted group, server-side credentials, a successful readiness check, and a capability profile limited to QQ event intake and the fixed acknowledgement.
- Preserve the offline Replay path and synthetic fixtures without QQ credentials or network access. Add injected-fake transport, duplicate-event, reconnect/replay, timeout/lost-response, cross-tenant, unallowlisted-group, secret-redaction, and external-write denial acceptance checks.
- Report truthfully: this increment proves intake and an observed QQ acknowledgement attempt/result only. It does not prove customer receipt, customer resolution, handler notification/approval, final answer delivery, live model use, CRM/monitoring/knowledge access, attachment handling, multiple groups/tenants, QQ mail, or production QQ readiness.

## Capabilities

### New Capabilities

- `qq-sandbox-intake-and-ack`: Operator-gated QQ sandbox WebSocket intake for one allowlisted group and tenant, exact-once Case creation from `@机器人` text, and one fixed idempotent passive acknowledgement through a recoverable real-write boundary.

### Modified Capabilities

- `versioned-domain-contracts`: Add payload-safe, versioned QQ inbound/session and acknowledgement boundary records while retaining existing compatible v1 fixtures and prohibiting raw chat or credential fields.
- `case-event-ledger`: Permit a server-normalized QQ sandbox source alongside the synthetic source, with stable QQ natural-key deduplication, append-only Case facts, and unchanged tenant isolation.
- `safe-provider-runtime-boundary`: Add one explicit operator-controlled QQ sandbox exception to the normal no-network/no-external-write policy; keep models, enterprise tools, arbitrary destinations, and all other real writes denied.
- `idempotent-side-effect-recovery`: Extend intent/reconcile/execute/observe/complete recovery semantics to the fixed QQ acknowledgement without treating provider acceptance as customer receipt or Case completion.

## Impact

- Contracts: additive QQ gateway/inbound/acknowledgement schemas and semantic validation; retained v1 compatibility remains a hard gate.
- Services: a bounded QQ WebSocket adapter at the platform boundary, deterministic normalization and identity mapping in the control path, and a QQ acknowledgement executor isolated from the Agent Runtime.
- Persistence: durable QQ event deduplication/session progress plus append-only acknowledgement intent, observation, and completion evidence; no raw QQ message content is stored in business records.
- Configuration and security: server-owned AppID/secret/token handling, one allowlisted sandbox group, explicit live activation, redacted diagnostics, reconnect/sequence controls, bounded budgets/timeouts, and default-deny startup.
- Tests and operations: offline fake transports and negative security/recovery tests remain the normal CI path; a separate operator-run sandbox acceptance command records whether a real event and acknowledgement were live-verified.
- Documentation: record the locked three-stage QQ roadmap in `docs/PROJECT_MEMORY.md` and document the first-stage setup, limitations, evidence, and rollback/disable procedure.
