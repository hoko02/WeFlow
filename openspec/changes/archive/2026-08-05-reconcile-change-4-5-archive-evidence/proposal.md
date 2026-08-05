## Why

The Change 4 and Change 5 archive directories and main specifications show completed,
synced increments, but this checkout lacks their documented machine-readable acceptance
and strict-validation evidence. Their development guides also still describe archive
finalization as pending. That disagreement weakens the reproducibility and audit value
of the offline harness precisely where it is intended to be strongest.

## What Changes

- Define a repository-owned reconciliation process for archived Change 4 and Change 5
  evidence, including canonical acceptance, strict-validation, and verification records.
- Regenerate missing redacted evidence from the existing offline commands and track the
  resulting files, or record a precise safe failure/timeout rather than claiming a pass.
- Align the Change 4 and Change 5 development guides and long-lived status text with
  their already-synced, archived OpenSpec state.
- Run the complete local verification suite with a bounded but sufficient outer time
  limit, preserving explicit Node, Docker, and timeout limitations in evidence.
- Define an archive-readiness gate that requires strict validation of this active
  reconciliation change and a passing repository evidence check, while retaining the
  archived Change 4/5 `archived_change_has_no_delta` result as a documented CLI
  limitation rather than a passing claim.

## Capabilities

### New Capabilities

- `archived-change-evidence-integrity`: Canonical, tracked, redacted evidence and
  documentation reconciliation for archived Change 4 and Change 5 increments.

### Modified Capabilities

- `workspace-operability`: Require reproducible verification evidence to distinguish a
  completed command, an unavailable dependency, and a bounded timeout without treating
  any of them as business success by implication.

## Impact

- Affected repository assets: `reports/`, `.gitignore`, Change 4/5 development guides,
  long-lived project status documentation, verification scripts or test orchestration
  only when required to retain safe evidence, and OpenSpec specifications.
- No application capability, public API, workflow state, contract payload, provider,
  connector, credential path, approval authority, delivery behavior, or external-write
  boundary changes.
- Validation will use existing offline fixtures and commands only; Docker, Node-version,
  and timeout constraints remain explicit environment facts rather than pass claims.
