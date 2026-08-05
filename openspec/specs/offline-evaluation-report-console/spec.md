# offline-evaluation-report-console Specification

## Purpose
Define the fixed, tenant-scoped, read-only presentation of fully validated offline evaluation evidence.

## Requirements

### Requirement: Canonical evaluation evidence is fully validated before presentation
The system SHALL load only the allowlisted canonical `offline-seed.v1` acceptance
report, resolve its current source-bound tasks and oracles, and validate its accepted
and repeated-baseline flags, suite/report hashes, source hashes, record identities,
hard-gate semantics, capability flags, and complete EvaluationCase, GraderResult,
RunMetrics, EvaluationResult, and suite-report links before deriving a console
snapshot. A read SHALL NOT execute the benchmark, initialize a task store, mutate the
report, or write a replacement.

#### Scenario: The canonical accepted report is read
- **WHEN** the retained report and every current source and record link are valid
- **THEN** the reader SHALL derive one deterministic content-addressed 12-task snapshot
  without changing the report or any workflow/effect state

#### Scenario: Canonical evidence is missing or fails integrity
- **WHEN** the report is absent, malformed, duplicate-key, unsafe, stale, hash-
  mismatched, detached, cross-task, or not deterministically accepted
- **THEN** the reader SHALL return only an allowlisted unavailable classification and
  SHALL NOT emit a partial snapshot, raw value, stack output, or replacement report

### Requirement: Evaluation report access is fixed, tenant-derived and read-only
The loopback Platform API SHALL expose only the fixed
`GET /v1/evaluations/offline-seed.v1` evaluation route. It SHALL derive the effective
tenant from an allowlisted synthetic actor, reject query/path/report selectors, and
return a snapshot only when its tenant matches. The route SHALL expose no method or
result that can authorize or perform a workflow transition, approval, delivery, retry,
report mutation, provider operation, or external write.

#### Scenario: An authorized synthetic observer reads the supported suite
- **WHEN** an allowlisted observer for the report tenant requests the fixed route with
  no query parameters and the canonical report is valid
- **THEN** the API SHALL return the validated `EvaluationSuiteSnapshot` and SHALL make
  zero changes to reports, Cases, workflows, approvals, deliveries, or effects

#### Scenario: A foreign tenant or absent report is requested
- **WHEN** the effective observer tenant does not match the report tenant or no valid
  report exists for that tenant
- **THEN** the API SHALL return the same non-disclosing `evaluation_report_not_found`
  response without exposing tenant, path, hash, or report existence

#### Scenario: A caller attempts to select another report
- **WHEN** a request includes a query parameter, alternate suite identity, filesystem
  path, report name, tenant, or unsupported HTTP method
- **THEN** the API SHALL reject it before filesystem selection or snapshot construction
  and SHALL NOT echo the attempted value

### Requirement: The console renders truthful bounded suite and task evidence
The Vue console SHALL render only a validated `EvaluationSuiteSnapshot`. It SHALL show
suite/report identity and hashes, accepted/deterministic state, pass/fail/unscored
counts, explicit capability flags, and an ordered bounded task view containing safe
source/result identities and hashes, result/failure classification, hard gates,
quality dimensions, observation facts, and existing offline counter metrics. It SHALL
not render an unrestricted JSON tree or imply a live model, provider send, customer
receipt/resolution, Case completion, cost, latency, variance, or authorization.

#### Scenario: A valid offline suite is rendered
- **WHEN** the browser receives a valid accepted snapshot
- **THEN** it SHALL render all 12 task summaries and allow one task's linked gates and
  diagnostics to be inspected while visibly identifying Replay-only, no-network,
  no-model, and no-external-write capability

#### Scenario: A metric or outcome is unsupported
- **WHEN** the snapshot contains no live token, cost, latency, variance, customer-
  receipt, or resolution evidence
- **THEN** the console SHALL label those claims unavailable or out of scope and SHALL
  NOT render zero, passed, delivered, or resolved as a substitute

#### Scenario: The evaluation surface is unavailable
- **WHEN** the API reports missing, foreign, identity-denied, or integrity-not-ready
  evaluation evidence
- **THEN** the console SHALL show a stable safe state without raw response content,
  while Platform API foundation readiness remains independently reported

### Requirement: Offline console acceptance is deterministic and side-effect free
The cross-platform development command SHALL verify the canonical report reader,
tenant-scoped API, snapshot contract, console render model, production build, and
negative integrity/security paths without network, Docker, model or enterprise
credentials, provider initialization, external write, or retained-state mutation. It
SHALL emit a redacted machine-readable acceptance report under an explicit repository
report path.

#### Scenario: Evaluation console acceptance succeeds
- **WHEN** the canonical 12-task report and implementation are unchanged on an offline
  workstation
- **THEN** two snapshot derivations SHALL be equal, the authorized view SHALL match the
  source hashes/counts/result IDs, all negative paths SHALL emit no snapshot, the Vue
  production build SHALL pass, and the acceptance report SHALL record zero side effects

#### Scenario: A safety or evidence boundary regresses
- **WHEN** the reader, API, snapshot, or renderer permits a detached link, foreign
  tenant, arbitrary path, unsafe field, unsupported success claim, report mutation,
  network/model use, or external-write attempt
- **THEN** acceptance SHALL fail and SHALL NOT replace a prior accepted report
