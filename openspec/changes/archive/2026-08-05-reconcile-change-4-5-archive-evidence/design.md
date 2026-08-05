## Context

Change 4 and Change 5 are already represented by archived change directories and
synced main specifications. However, the checked-out repository is missing the
machine-readable evidence paths claimed by long-lived documentation, and their
development guides still describe sync/archive as pending. Change 5 also records that a
120-second outer tool limit interrupted the aggregate test command, which is an
environment result rather than a passing full-suite result.

This change reconciles repository evidence only. The existing fixture-local runtime,
contracts, state machine, policy/approval/delivery semantics, and evidence trajectory
remain the source behavior and are not reopened for feature work.

## Goals / Non-Goals

**Goals:**

- Establish a canonical, tracked, redacted evidence set for archived Change 4 and
  Change 5 acceptance and strict OpenSpec validation.
- Record complete verification outcomes with command identity, bounded elapsed time,
  exit classification, and Node/Docker/timeout limitations.
- Make current development guides and long-lived status text agree with the archive and
  main-spec sync facts.
- Make a full local suite result reproducible under a 15-minute outer limit, with a
  timeout treated as an explicit incomplete result and orphaned child processes cleaned
  up before evidence is written.
- Permit archive only when this active change's strict OpenSpec validation and the
  repository evidence check pass, and when any archived-change validation limitation is
  recorded truthfully with its safe reason code.

**Non-Goals:**

- Changing application APIs, JSON contracts, workflow transitions, policies, approval
  semantics, fixture delivery, evidence extraction, or replay behavior.
- Enabling a provider, credential, network destination, Docker dependency, enterprise
  connector, real approval, real delivery, external write, or customer-success claim.
- Rewriting historical archived source artifacts or manufacturing a historical pass from
  a current run.

## Decisions

### 1. Use a tracked evidence manifest rather than documentation assertions

The reconciliation SHALL create a small, canonical evidence manifest under `reports/`
for each affected archived change. It SHALL name the acceptance and strict-validation
artifacts, their content hashes, the command outcome, and declared environment limits.
The repository ignore rules SHALL explicitly allow only those redacted canonical files.

This is preferred to embedding command transcripts in guides: machine-readable records
can be checked for existence, parsed, and hashed while documentation remains readable.
Raw console output is rejected because it can contain host paths, uncontrolled output, or
credential-like content.

### 2. Treat archive metadata and synchronized main specifications as status authority

An archived change directory plus its synchronized main specs establish archive status.
The Change 4 and Change 5 development guides and `PROJECT_MEMORY.md` SHALL be adjusted
to reference that status and the actual canonical evidence paths. Archive directories
remain immutable historical input to this reconciliation.

This is preferred to moving or editing archived artifacts, which would obscure their
historical review context.

### 3. Separate command completion from verification success

Each reconciled command result SHALL be one of `passed`, `failed`, `timed_out`, or
`unavailable`. Only `passed` can support a passing verification claim. A full suite is
run with a 900-second outer limit; a timeout report includes elapsed duration and safe
process-cleanup status, but never a test count or success declaration.

This is preferred to increasing an unbounded timeout, which would make local
verification non-reproducible, and to reclassifying a timeout as a skip, which would
hide incomplete verification.

### 4. Reuse existing offline commands and fixtures

Acceptance evidence SHALL be regenerated only through the checked-in Change 4/5 command
surfaces and existing strict OpenSpec validation. Verification is performed with the
locked workspace dependencies and no live provider, connector, credential, or Docker
requirement. A missing local tool, unsupported Node version, unavailable Docker, or
failed command becomes explicit redacted evidence.

This keeps the change within repository maintenance and avoids creating a parallel
verification implementation.

### 5. Gate archive on scope-aware validation facts

Archive readiness SHALL require all of the following: the active reconciliation change
passes strict OpenSpec validation with zero issues; the repository-owned
`archive-evidence-check` passes; and the canonical Change 4/5 validation reports retain
the observed `failed` outcome and `archived_change_has_no_delta` reason for direct
validation of their archived directories. The latter is an OpenSpec CLI limitation: an
archived directory no longer exposes an active delta, so it MUST NOT be relabeled as a
passing validation or treated as evidence of a product defect.

This separates the validity of the active maintenance change from the intentionally
preserved historical input limitation. It permits an auditable archive gate without
manufacturing a false pass claim.

## Risks / Trade-offs

- **A current run differs from a historical assertion** → preserve the current result as
  a new dated reconciliation fact, correct stale documentation, and do not overwrite it
  with an unsupported pass claim.
- **The full suite exceeds 900 seconds** → record `timed_out`, clean up child processes,
  retain focused regression evidence, and leave the full-suite task incomplete rather
  than archive on an inferred result.
- **Generated reports contain unsafe material** → validate report schemas/allowlisted
  fields and run secret hygiene before tracking; reject raw console output.
- **Docker or Node differs by workstation** → record the observed availability/version
  and distinguish it from the offline core acceptance outcome.
- **OpenSpec cannot strictly validate an archived delta** → retain the exact safe
  failure reason in its canonical report, require the active change and evidence checker
  to pass, and do not treat the archived result as either a product failure or a pass.

## Migration Plan

1. Inventory documented versus present Change 4/5 evidence and define canonical paths.
2. Run existing acceptance, strict validation, and full-suite commands under the bounded
   runner; classify every outcome and redact/validate generated reports.
3. Track canonical reports and manifests, then correct guides and project memory to
   match archive metadata and observed results.
4. Run strict validation for this reconciliation change and the repository evidence
   check. Confirm that archived Change 4/5 validation results retain the known
   `archived_change_has_no_delta` limitation as `failed`, rather than as a pass, before
   archiving. Rollback is a normal Git revert of the evidence/docs-only commit; no
   runtime data migration or service rollback is needed.

## Open Questions

- If the 900-second full suite still times out, should a later maintenance change split
  the test command into bounded named suites, or is the observed timeout sufficient to
  defer that work?
- Should the canonical manifest retain a source commit SHA in addition to report hashes
  to make reruns across later code revisions easier to distinguish?
