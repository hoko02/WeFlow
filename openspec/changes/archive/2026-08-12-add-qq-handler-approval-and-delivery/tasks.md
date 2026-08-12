## 1. Contracts and privacy boundary

- [x] 1.1 Add versioned schemas for the dual-surface handler binding, pairing evidence, assurance level, and private provider locators.
- [x] 1.2 Add versioned schemas for the bounded customer-issue artifact, handler-response artifact, C2C commands, notification intent/result, candidate revision, approval request/decision, passive reply intent/result, and acceptance report.
- [x] 1.3 Enforce 1–1200 Unicode-scalar content bounds, deterministic normalization/redaction, maximum 24-hour retention, terminal deletion, and content-addressed evidence for both private artifacts.
- [x] 1.4 Add contract-negative tests proving plaintext issue/draft/preview, raw QQ identities, provider events, credentials, and unknown privileged variants are rejected from durable metadata and reports.
- [x] 1.5 Run schema validation and offline round-trip tests for every new contract.

## 2. Dual-surface handler pairing

- [x] 2.1 Implement one bounded group challenge that captures the intended handler's `member_openid` for the already paired sandbox group.
- [x] 2.2 Implement one bounded C2C challenge that captures the intended handler's `user_openid` for the same pairing session.
- [x] 2.3 Require local operator confirmation of the two challenge results and record `operator_confirmed_dual_challenge` unless a documented stable cross-surface provider identity also matches.
- [x] 2.4 Persist only salted identity hashes, private execution locators, lifecycle/expiry facts, assurance level, group, and tenant binding.
- [x] 2.5 Add negative tests for one-sided pairing, expired/replayed challenges, foreign groups/users, nickname and role spoofing, mismatched app/tenant, and unauthorized rebinding.
- [x] 2.6 Add a live-verification report that proves dual-surface binding without revealing either raw identity and keeps `production_ready=false`.
- [x] 2.7 Add exact local operator-confirmed binding revocation that appends terminal evidence, scrubs private locators, disables old authority, and permits replacement binding only under a matching current Stage 1 scope.

## 3. Private issue and candidate workflow

- [x] 3.1 Create one restricted `QQCustomerIssueArtifact` from the accepted Stage 1 intake without persisting a group transcript or raw provider event.
- [x] 3.2 Parse a closed C2C protocol for `WF-PULL`, `WF-ACCEPT`, `WF-DRAFT`, and `WF-REJECT`; reject all other private commands without Case disclosure.
- [x] 3.3 Authorize every C2C command against the bound `user_openid`, group/tenant, active Case and immutable revision, expected workflow version, and artifact retention state.
- [x] 3.4 Implement deterministic model-free candidate normalization, redaction, verification, and restricted artifact storage.
- [x] 3.5 Make replacement atomic: invalidate the prior candidate, request, and decision before installing the new candidate; schedule superseded content deletion.
- [x] 3.6 Return customer issue, task status, candidate preview, and approval metadata only as bounded passive replies to the current C2C source event.
- [x] 3.7 Add replay and negative tests for duplicate, stale, foreign, expired, malformed, oversized, prohibited, and out-of-order C2C commands.

## 4. Confidential notification and recovery

- [x] 4.1 Implement a minimal active C2C notification template containing only a Case reference and `WF-PULL`, with no issue, draft, preview, or unrestricted text.
- [x] 4.2 Persist notification intent and local reconciliation state before transport, then enforce no more than one active attempt for the stable Case/binding natural key.
- [x] 4.3 Classify accepted, rejected, timeout, disconnect, rate-limit, and unknown outcomes without retrying any ambiguous active attempt or calling it delivered.
- [x] 4.4 Implement a non-sensitive group nudge as the only notification fallback; it must disclose neither customer content nor handler work.
- [x] 4.5 Implement passive C2C reply idempotency from source `msg_id`, stable response-kind `msg_seq`, Case, binding, and workflow version within provider window/count limits.
- [x] 4.6 Add crash/fault-injection tests before attempt, during ambiguous transport, after acceptance, on duplicate C2C events, and after passive-window expiry.

## 5. Metadata-only group approval

- [x] 5.1 Define and parse only `@机器人 WF-APPROVE <approval_request_id> <candidate_hash_prefix> <expected_version>` for final group approval.
- [x] 5.2 Reject group commands that contain candidate plaintext, request a preview, use an ambiguous hash prefix, or originate outside the paired group.
- [x] 5.3 Authorize the approval author only when the event's `member_openid` is linked to the same active dual-surface binding that created the private candidate.
- [x] 5.4 Bind requests and decisions to the issue artifact, candidate artifact and normalized hash, Case/revision, binding, policy decision, workflow version, and expiry.
- [x] 5.5 Add negative tests for copied approval metadata, foreign members, stale/replaced candidates, expired requests, changed Case/binding/version, and robot/model self-approval.

## 6. Final passive group delivery

- [x] 6.1 Create the final write intent only after a valid exact approval decision and bind it to the group approval source `msg_id`, stable `msg_seq`, candidate, Case, group, and workflow version.
- [x] 6.2 Execute the exact approved candidate as a passive group reply within the provider window; do not expose active group-send fallback.
- [x] 6.3 Implement intent/reconcile/execute/complete recovery and provider outcome classification without equating acceptance with customer receipt, resolution, or Case completion.
- [x] 6.4 Add duplicate, restart, timeout, unknown-outcome, expired-window, stale-decision, and provider-duplicate fault tests proving no second visible answer is created.

## 7. Command, evidence, and operator UX

- [x] 7.1 Add `scripts/dev.py qq-sandbox-handler-approval` with explicit live confirmation and exact configuration/capability validation before network contact.
- [x] 7.2 Keep Stage 1 and ordinary commands unable to read C2C, notify a handler, approve, or deliver a final reply.
- [x] 7.3 Add privacy-safe readiness, pairing, notification, private-workflow, group-approval, final-delivery, recovery, duplicate/rejection, and deletion evidence layers.
- [x] 7.4 Ensure every live report keeps raw identities, credentials, provider events, transcripts, issue/candidate text, and unrestricted responses absent.
- [x] 7.5 Keep `model_invocation=false`, `customer_receipt_verified=false`, `issue_resolution=false`, `case_completion=false`, and `production_ready=false` in live acceptance.
- [x] 7.6 Update the QQ sandbox runbook with dual pairing, C2C commands, metadata-only group approval, passive-window timing, at-most-once notification warning, privacy limits, and rollback.
- [x] 7.7 Document the Stage 1-before-Stage 2 expiry recovery procedure and its no-network, no-direct-SQLite boundary.

## 8. Acceptance gates

- [x] 8.1 Run all contract, unit, integration, replay, privacy, tenant-isolation, authorization, idempotency, recovery, and retention tests offline without QQ or model credentials.
- [x] 8.2 Run the Stage 2 command in readiness mode and prove it performs no network contact, external write, Case mutation, or model invocation.
- [x] 8.3 Live-verify one dual-surface pairing, one private pull/accept/draft/edit flow, one metadata-only group approval, and one provider-accepted final passive group reply.
- [x] 8.4 Live-verify one ambiguous active notification path and prove no retry or false delivery claim occurs, or provide an equivalent controlled provider fault fixture if the live provider cannot safely induce it.
- [x] 8.5 Verify artifact deletion evidence and that no private issue/draft/preview appeared in the group, logs, ledger, fixtures, or reports.
- [x] 8.6 Run `openspec validate add-qq-handler-approval-and-delivery --strict` and leave every unchecked item open unless its concrete acceptance check passes.
- [x] 8.7 Verify QQ Gateway ordering is enforced per connection while durable intake remains replay-safe across sequence resets after reconnect.
- [x] 8.8 Verify provider-omitted group mention content is accepted only after the trusted `GROUP_AT_MESSAGE_CREATE`, paired-group, and bound-member gates.
- [x] 8.9 Add offline recovery, idempotency, scope-mismatch, command-isolation, locator-scrubbing, and revoke-then-rebind tests for the local handler-binding revocation path.
