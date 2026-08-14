## Context

The retained QQ Stage 1 offline acceptance report is content-addressed by the
`stable_report_sha256` field in its change-verification record. The Git index stores
that report with LF line endings, but a Windows checkout with `core.autocrlf=true`
materializes CRLF. The verification record was created from those CRLF bytes, while
GitHub Actions reads the LF checkout and fails the source-backed security test.

The failure is confirmed to predate the console-localization change: Actions runs #9
and #10 both fail the same assertion, while the preceding run succeeds. The report's
JSON semantics and all QQ capability flags are valid; only its physical byte
representation is inconsistent across platforms.

## Goals / Non-Goals

**Goals:**

- Establish one LF-canonical byte representation for the exact QQ offline acceptance
  report used by the retained verification.
- Bind `stable_report_sha256` to those canonical bytes.
- Make the existing source-backed test and baseline CI pass on Windows and Linux.
- Prevent removal of the required line-ending policy with a focused regression check.

**Non-Goals:**

- Do not change report semantics, JSON contracts, QQ runtime code, historical outcome
  counts, or capability claims.
- Do not normalize unrelated reports or introduce a general report-rewriting system.
- Do not enable network, model, QQ, approval, delivery, or other external behavior.

## Decisions

### Use a file-scoped Git attribute for canonical LF bytes

Add an `eol=lf` attribute for only
`reports/add-qq-sandbox-intake-and-ack-offline-acceptance.json`. This keeps the
maintenance increment narrowly scoped while making every fresh checkout materialize
the exact byte sequence that CI verifies.

An application-level normalization function was considered but rejected: the existing
field and test intentionally bind the retained file's bytes, and changing their meaning
would expand the evidence contract. A repository-wide `reports/*.json` rule was also
rejected because it would alter unrelated historical artifacts without acceptance
evidence.

### Rebind only the dependent verification record

Update the QQ change-verification record's `stable_report_sha256` to the SHA-256 of
the source report's canonical LF bytes. No semantic field in either report changes.
The source-backed test remains a raw-byte integrity check so an accidental content or
line-ending regression still fails closed.

### Verify both policy and source linkage

The focused security test will assert the exact tracked LF attribute as well as the
existing source-report hash binding. The implementation will materialize the known
clean tracked report through the new attribute before running the focused and complete
offline suites, so the local verification uses the same LF representation as CI.

## Risks / Trade-offs

- [A contributor's existing Windows worktree retains CRLF after the attribute is added]
  → Re-materialize only the verified clean report after checking that it has no local
  content edits; fresh checkouts use LF automatically.
- [The historical report appears changed despite identical JSON semantics] → Retain the
  report content unchanged and document that only its byte-level canonical form and the
  dependent hash are updated.
- [Future report hashes repeat the issue] → Keep the new focused test adjacent to the
  existing raw-byte linkage and scope any broader normalization to a separately reviewed
  change.

## Migration Plan

1. Add the file-scoped LF attribute and re-materialize the clean source report as LF.
2. Update the dependent stored SHA-256 and focused security regression check.
3. Run the focused test, the full offline pytest suite, strict OpenSpec validation, and
   diff/secret-hygiene checks.
4. Commit and push the maintenance change; GitHub Actions is the final Linux
   confirmation.

Rollback consists of reverting the maintenance commit as one unit. It changes no
runtime state, data store, provider configuration, or external effect.

## Open Questions

- None. The failing Linux byte hash (`ff0001cc78be0155729151ad4026ec4bca3e8070b083f63ae3779064bd08b6f6`)
  is directly observed from GitHub Actions and is the canonical Git LF value.
