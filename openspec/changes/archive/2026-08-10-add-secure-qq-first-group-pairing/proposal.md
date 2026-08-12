## Why

The QQ management portal does not expose the sandbox `group_openid`, while QQ first
reveals that identifier inside a group event. The existing QQ intake command requires
the identifier before it can start, so its real sandbox gate cannot be completed
without an unsafe ad-hoc event logger or an operator guessing with the ordinary QQ
group number.

## What Changes

- Add a dedicated, explicitly confirmed `qq-sandbox-pair-group` command that may open
  only the QQ token/gateway/WebSocket read path for one application and one
  operator-selected tenant. It has no QQ send capability.
- Generate one high-entropy, single-use, short-deadline pairing challenge and accept
  exactly one plain-text `GROUP_AT_MESSAGE_CREATE` event whose content matches that
  challenge. The group is selected by the operator sending the challenge in the target
  test group, not by a caller-supplied group identifier.
- Derive `group_openid` from the validated event and persist the minimum raw group
  locator only in the bounded local QQ adapter journal. Persist and report only a safe
  pairing ID, application/group/tenant hashes, timestamps, status, and reason codes;
  expire the raw locator after at most 24 hours.
- Allow the existing dedicated QQ intake-and-ack path to resolve its one allowlisted
  group and tenant from a current completed pairing ID. Direct pre-known
  `group_openid` configuration remains compatible, but pairing and direct selection
  are mutually exclusive and a stale, foreign, ambiguous, or conflicting pairing
  fails before Case creation or provider send.
- Add closed versioned pairing challenge/completion contracts, deterministic fake
  transports, restart/duplicate/race/expiry tests, negative security tests, and
  machine-readable reports that distinguish offline pairing verification from a real
  QQ sandbox pairing.
- Update the QQ operator runbook so first-time setup no longer assumes the portal
  exposes `group_openid`, and keep the two pending real intake/ack tasks blocked until
  pairing and the later provider-write evidence both pass.

## Non-Goals

- Creating a Case, acknowledgement intent, workflow activation, handler binding, or
  customer-visible QQ message during pairing.
- Accepting ordinary QQ group numbers, nicknames, display names, QQ-reported roles,
  attachments, cards, direct messages, arbitrary commands, or more than one group.
- Retaining pairing message text, member OpenIDs, transcripts, credentials, access
  tokens, unrestricted provider payloads, or a permanent raw group directory.
- Enabling a model, business tool, approval, final delivery, multiple tenants/groups,
  production rollout, customer-receipt claims, resolution, or Case completion.

## Capabilities

### New Capabilities

- `secure-qq-first-group-pairing`: Operator-gated discovery and short-lived local
  binding of one QQ sandbox `group_openid` through an exact single-use group-mention
  challenge, without Case creation or any QQ write.

### Modified Capabilities

- `versioned-domain-contracts`: Add payload-safe pairing challenge/completion records
  and offline/live pairing report fixtures without weakening retained v1 contracts.
- `safe-provider-runtime-boundary`: Permit one command-local, explicitly confirmed,
  read-only QQ pairing transport while keeping every QQ write, model, enterprise tool,
  ordinary command, and unrelated provider denied.
- `workspace-operability`: Add isolated pairing/verification dev commands and reject
  pairing credentials or activation from all ordinary startup and acceptance paths.

## Impact

- Contracts: additive closed JSON Schemas plus Python/TypeScript bindings and semantic
  linkage checks for pairing challenge and completion evidence.
- Control worker and kernel: a pairing controller that reuses the narrow QQ token,
  gateway, WebSocket, heartbeat, and resume interfaces but never constructs the passive
  send executor or Case ledger service.
- Persistence: a bounded pairing table in `.weflow/qq-sandbox.sqlite3` containing one
  current application/tenant/group binding, challenge digest, lifecycle timestamps,
  and the minimum raw group locator required by the subsequent intake command.
- Configuration: process-only AppID/AppSecret, server-owned tenant, exact pairing
  capability, explicit live confirmation, one safe pairing ID handoff, and fail-closed
  mutual exclusion with direct group configuration.
- Tests and evidence: offline fake acceptance remains CI-safe; a separate operator-run
  real pairing report can prove only that one sandbox group was bound, not that intake,
  acknowledgement, customer receipt, or resolution succeeded.
