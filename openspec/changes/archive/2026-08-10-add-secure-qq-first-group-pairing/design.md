## Context

The implemented QQ Stage 1 command can safely consume one allowlisted group mention,
create one Case, and send one fixed acknowledgement, but its activation contract
requires a preconfigured `group_openid`. The current QQ management portal does not
surface that value; the first authoritative value is delivered inside
`GROUP_AT_MESSAGE_CREATE`. This creates a bootstrap cycle and blocks the two real QQ
acceptance tasks.

The pairing operator controls one development robot, one non-production group, and one
server-owned WeFlow tenant. The command may use real AppID/AppSecret credentials and a
real QQ WebSocket read path, but pairing must remain narrower than intake: it cannot
create a Case, construct the passive-send transport, invoke a model/tool, or claim any
customer outcome. Raw QQ group identifiers remain sensitive correlation locators.

## Goals / Non-Goals

**Goals:**

- Discover exactly one sandbox `group_openid` from an operator-proven group mention
  without accepting a QQ group number or printing a raw provider event.
- Bind the discovered group to one application and one server-owned tenant through a
  short-lived, single-use challenge and a durable safe pairing identity.
- Make the completed pairing consumable by the existing intake-and-ack command while
  keeping direct pre-known group configuration compatible and mutually exclusive.
- Recover safely from duplicate events, reconnect, process interruption, races,
  expiry, conflict, and stale or foreign pairing references.
- Preserve offline fake acceptance, command isolation, secret hygiene, payload-safe
  evidence, and truthful live-versus-fake reporting.

**Non-Goals:**

- Creating or advancing a Case, acknowledgement, workflow, handler task, approval,
  final delivery, or model-backed investigation during pairing.
- Sending a pairing confirmation or any other QQ message.
- Supporting direct messages, attachments, cards, arbitrary bot commands, more than
  one current group, multiple applications/tenants, or a permanent group directory.
- Treating a QQ nickname, member role, ordinary group number, caller payload, or raw
  event dump as authority.
- Proving Stage 1 intake/ack, customer receipt, issue resolution, Case completion, or
  production QQ readiness from pairing evidence.

## Decisions

### 1. Add a dedicated read-only pairing command

`scripts/dev.py qq-sandbox-pair-group --confirm-live-qq-pairing` is the only live
pairing entry point. It accepts process-local AppID/AppSecret and one operator-owned
tenant mapping, requires exactly the local `qq.group_pair.read` capability, and rejects
group identifiers, identity salt, passive-ack capability, model configuration, general
external-write configuration, multi-Agent configuration, and repository-external
storage before creating a network client.

The command reuses the existing narrow token, gateway, WebSocket, heartbeat, and resume
transport interfaces. It does not import or construct the passive message executor,
Case ledger, workflow, Agent Runtime, Business Simulator, or model adapter. Ordinary
commands reject visible pairing activation/configuration before their handlers run.

Alternative considered: temporarily run the intake command with a wildcard group and
print the first event. This is rejected because it exposes a raw locator/event, can
select an attacker-controlled group, and risks creating a Case or reply before the
mapping is trusted.

### 2. Prove operator intent with an exact single-use challenge

After redacted readiness, deterministic control creates a cryptographically random
128-bit-or-stronger challenge with a reserved human-readable prefix such as
`WFPAIR-<token>`. The display token exists only in command memory and terminal output;
the local journal and reports retain its SHA-256, stable challenge ID, creation time,
and a five-minute deadline.

The operator sends exactly `@机器人 WFPAIR-<token>` in the intended test group. The
pairing normalizer accepts only `GROUP_AT_MESSAGE_CREATE`, `message_type=0`, nonempty
`member_openid`, valid timestamps/sequence, no attachment, no ARK/card, no nested chat
elements, and content equal to the active challenge after QQ's mention removal and
bounded whitespace normalization. It uses neither nickname nor QQ-reported member role.
Every nonmatching event is rejected with a safe category and cannot select a group.

Alternative considered: bind on `GROUP_ADD_ROBOT`. It is rejected because that event
proves only that the bot was added; it does not prove the current operator intentionally
selected that group for this WeFlow tenant and command run.

### 3. Use an append-only pairing lifecycle and a private locator table

The durable lifecycle is:

```text
PENDING -> COMPLETED
PENDING -> EXPIRED | CANCELLED | CONFLICT
COMPLETED -> REVOKED | EXPIRED
```

`QQGroupPairingChallenge` and `QQGroupPairingCompletion` are immutable payload-safe
contracts. The completion binds challenge, safe pairing ID, application hash, group
hash, tenant hash/ID as allowed by the tenant-scoped contract, source-message hash,
Gateway session/sequence hash metadata, timestamps, expiry, and status. A uniqueness
constraint permits one completion per challenge and one current application/tenant
binding. Repeated delivery of the exact source event resolves to the same completion;
a different group or source for the same challenge is a conflict.

The raw `group_openid` is not placed in either contract, telemetry, fixture, report, or
terminal output. It is stored only in a private locator row inside
`.weflow/qq-sandbox.sqlite3`, keyed by the safe pairing ID and bound to application and
tenant hashes. The row expires after at most 24 hours and is purged on the next
dedicated QQ start. The database remains ignored runtime state and uses owner-only file
permissions where the platform supports them. The challenge text and member OpenID are
never persisted.

The pairing ID is an opaque content-addressed identifier derived from server-owned
pairing material; it does not encode or reveal `group_openid`. A local-only revoke
operation may mark a completed pairing unusable without deleting append-only safe
evidence or touching any Case/acknowledgement facts.

Alternative considered: store the raw locator in `.env` or a checked-in mapping. This
is rejected because it creates a long-lived private identifier and secret-adjacent
configuration surface. Storing only a group hash is insufficient because the later QQ
reply path needs the raw locator.

### 4. Resolve a pairing before Stage 1 constructs intake services

The existing intake-and-ack configuration accepts exactly one selector mode:

- direct mode: current `WEFLOW_QQ_SANDBOX_GROUP_OPENID` plus tenant; or
- pairing mode: `WEFLOW_QQ_SANDBOX_PAIRING_ID`, with group and tenant resolved from the
  current local pairing record.

Supplying both modes, no mode, a stale/revoked/expired pairing, a mismatched AppID hash,
an unexpected tenant override, an unreadable locator, or more than one current binding
fails before the Case ledger, passive-send executor, HTTP, or WebSocket intake client is
constructed. Pairing mode still requires the existing process-only identity salt and
the exact Stage 1 read/ack capability profile.

The prefix `WFPAIR-` is reserved at the QQ intake boundary. Pairing control messages,
including replayed source messages and any plain-text message beginning with that
prefix after mention removal, are rejected before Case creation. Pairing uses an
isolated session/cursor namespace and cannot advance the Stage 1 business intake
cursor.

Alternative considered: copy the discovered raw OpenID into an environment variable.
This is rejected for the normal operator flow because it re-exposes the value and
preserves the original manual bootstrap error surface. Direct mode remains only for
operators who already possess an authoritative OpenID.

### 5. Restart, duplicate, race, and reconnect fail closed

A pending challenge is not restart-resumable because its plaintext token is not
persisted. If the process stops before completion, recovery marks the prior challenge
cancelled/expired and a new run generates a new challenge. A completion committed
before interruption is durable and resolves to the same pairing ID after restart.

The Gateway session sequence remains session-scoped. Pairing may heartbeat/resume
within the bounded run, but it persists a separate pairing cursor and never creates an
intake receipt. Concurrent matching consumers rely on challenge/completion uniqueness;
only one stores the locator and the loser returns the original safe completion. A
same-token event from a different group, malformed identity, sequence gap, or ambiguous
completion remains conflict/reconciliation evidence and produces no current binding.

Because pairing makes no provider write, it does not use the external-effect
intent/reconcile/execute/complete chain. The security-critical local binding is still
append-only, unique, deadline-bound, revocable, and reconstructable.

### 6. Pairing evidence cannot imply intake or delivery

Offline and live pairing reports are different report modes. A fake transport can set
`fake_pairing_verified=true` only. A real report may set
`qq_group_pairing_live_verified=true` only when the real adapter observes the exact
challenge and a valid completion/locator row passes independent verification.

Every report fixes Case creation, workflow activation, QQ write attempt,
acknowledgement, model invocation, handler binding, customer receipt, issue resolution,
Case completion, and production readiness to false. Reports contain safe IDs, hashes,
counts, durations, lifecycle states, and reason codes only. Independent verification
rejects raw group/member/message IDs, challenge plaintext, credentials, tokens,
transcripts, provider bodies, or Stage 1 success claims.

## Risks / Trade-offs

- [A challenge can be copied into another group before the operator sends it] → Use at
  least 128 bits of randomness, a five-minute deadline, one current challenge, exact
  text matching, and conflict-on-second-group semantics; never auto-select the first
  unrelated group event.
- [The local SQLite locator is readable by the workstation account] → Keep it out of
  reports/source control, use the existing private runtime directory and owner-only
  permissions where available, retain only the minimum locator, and expire it within
  24 hours. At-rest encryption is not claimed.
- [A restart loses a pending challenge] → Intentionally cancel it and require a fresh
  challenge; never persist the plaintext token merely to improve convenience.
- [Pairing consumes a QQ Gateway event that could later replay] → Isolate pairing
  cursor state and reserve/reject the `WFPAIR-` prefix at intake before Case creation.
- [Two active changes touch the QQ boundary] → Archive/apply this prerequisite before
  completing the real Stage 1 tasks, and preserve its additive runtime/contract
  requirements when the older QQ change is later synced or archived.
- [The portal or QQ event semantics change] → Recheck the official event contract
  before a live run and leave live verification false on any mismatch.

## Migration Plan

1. Add the closed pairing contracts, semantic validators, fixtures, and compatibility
   checks without changing retained v1 results.
2. Add the local pairing journal, challenge controller, fake transports, reserved
   intake prefix, pairing selector resolution, and revoke/expiry behavior.
3. Add isolated dev commands, offline acceptance/report verification, negative
   security/fault tests, and runbook updates. Existing direct group configuration
   remains supported.
4. Run offline pairing acceptance repeatedly and all retained QQ/repository baselines;
   validate this change strictly.
5. With operator process-local sandbox credentials, perform one real group pairing and
   independently verify only the pairing report.
6. Use the resulting pairing ID to resume the pending real intake/ack tasks. Do not
   mark Stage 1 live-verified until its separate Case and provider-ack evidence passes.

Rollback stops the pairing process, clears process environment values, revokes or lets
the bounded pairing expire, and optionally removes the bot from the test group. It does
not delete Case, acknowledgement, or other business evidence and does not delete the
shared adapter journal while an acknowledgement outcome is unknown.

## Open Questions

No architecture question blocks Apply. The operator must still supply one development
AppID/AppSecret, one server-owned test tenant, one controlled non-production QQ group,
and the exact challenge message during the bounded live run; none of those values enter
the repository artifacts.
