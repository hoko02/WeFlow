## 1. Evidence inventory and safe artifact boundary

- [x] 1.1 Inventory archived Change 4/5 directories, main specs, documentation claims,
  ignore rules, and present report files; define the canonical acceptance,
  strict-validation, and reconciliation-manifest path matrix.
- [x] 1.2 Add a repository-local, machine-readable manifest format and validation helper
  that allowlists report fields, command outcome classifications, artifact hashes,
  source commit identity, and Node/Docker/timeout facts.
- [x] 1.3 Update `.gitignore` so only the canonical redacted Change 4/5 reconciliation
  artifacts are tracked; keep transient reports, raw command output, stores, and other
  local artifacts ignored.
- [x] 1.4 Add negative checks that reject missing referenced evidence, unknown outcome
  classifications, unsafe/raw fields, invalid hashes, and documentation links to
  untracked report paths.

## 2. Reproducible Change 4/5 evidence regeneration

- [x] 2.1 Synchronize the locked workspace dependencies and record the safe local tool
  inventory, including observed Node version and Docker availability, without contacting
  a provider or enterprise service.
- [x] 2.2 Run the existing Change 4 offline acceptance command and retain its canonical
  redacted report; if it does not complete successfully, retain only its safe
  `failed`, `timed_out`, or `unavailable` result.
- [x] 2.3 Run the existing Change 5 evidence-trajectory acceptance command and retain
  its canonical redacted report under the same truthful outcome rules.
- [x] 2.4 Run strict OpenSpec validation for the archived Change 4 and Change 5 artifacts
  and retain canonical machine-readable validation results with zero-issue status only
  when the command actually passes.
- [x] 2.5 Run the aggregate local verification suite with a 900-second outer limit;
  classify completion truthfully, terminate owned child processes on timeout, and retain
  elapsed duration plus cleanup status.
- [x] 2.6 Build canonical Change 4 and Change 5 reconciliation manifests that reference
  only validated redacted evidence, include source commit and SHA-256 hashes, and record
  every Node, Docker, failed, unavailable, or timeout limitation explicitly.

## 3. Documentation reconciliation

- [x] 3.1 Update Change 4 and Change 5 development guides to state their actual synced,
  archived status and to reference only canonical evidence paths present in the
  repository.
- [x] 3.2 Update README, `docs/PROJECT_MEMORY.md`, and relevant support/roadmap text to
  distinguish historical archive facts from the current reconciliation result and its
  limitations.
- [x] 3.3 Verify that all updated language retains fixture-only, offline, no-provider,
  no-real-external-write, no-customer-resolution, and no-live-service claims.

## 4. Verification and change evidence

- [x] 4.1 Add focused tests for canonical evidence presence, hash/field validation,
  truthful timeout classification, report redaction, and guide/archive consistency.
- [x] 4.2 Run secret hygiene, lint, contract checks, the focused reconciliation suite,
  and every completed Change 4/5 acceptance command; retain only redacted machine-
  readable evidence.
- [x] 4.3 Run `openspec validate reconcile-change-4-5-archive-evidence --type change
  --strict` and `python scripts/dev.py archive-evidence-check`, resolve every issue, and
  confirm no task or evidence claim treats a skipped, timed-out, failed, or unavailable
  check as passed.
- [x] 4.4 Archive through OpenSpec only after the active reconciliation change strictly
  validates with zero issues, the canonical evidence check passes, and the archived
  Change 4/5 reports truthfully retain `failed` with
  `archived_change_has_no_delta` as a CLI limitation; update
  `docs/PROJECT_MEMORY.md` with verified reconciliation facts and the next-stage gate.
