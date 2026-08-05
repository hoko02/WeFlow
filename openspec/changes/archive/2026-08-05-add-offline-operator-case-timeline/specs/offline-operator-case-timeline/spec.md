## ADDED Requirements

### Requirement: Canonical operator evidence is generated from real deterministic source records
The system SHALL generate the canonical API-503 `OperatorCaseSnapshot` only by running
the allowlisted fixture through existing public deterministic intake, workflow,
investigation, verifier, policy, approval, fixture-local delivery, evidence, and replay
boundaries in a fresh temporary SQLite store. The builder SHALL revalidate every
included source record, predecessor, tenant/Case/revision/workflow reference, natural
and idempotency key, source hash, gate, aggregate count, and final snapshot hash. It
SHALL NOT read expected outcomes from a task-local mirror, query private SQLite tables,
initialize a live provider, mutate the default runtime store, or publish a partial or
failed snapshot.

#### Scenario: Two fresh canonical runs are projected
- **WHEN** the allowlisted API-503 fixture is executed twice in separate fresh stores
  and both complete with the same valid durable source chain
- **THEN** the builder SHALL produce byte-equivalent content-addressed snapshots whose
  ordered timeline entries and summaries bind to the actual source record IDs and
  hashes from each run

#### Scenario: A source chain is detached or incomplete
- **WHEN** a required source record, predecessor, identity, hash, transition, gate,
  count, evidence root, or replay link is missing, foreign, stale, or mismatched
- **THEN** the builder SHALL emit no snapshot or replacement report and SHALL expose
  only an allowlisted integrity classification

#### Scenario: Recovery or authorization evidence is inconsistent
- **WHEN** source records contain duplicate or out-of-order effect identity, a restart
  or timeout represented as duplicate completion, a denied policy followed by an
  authorized label, or stale approval followed by fixture delivery
- **THEN** generation SHALL fail as an integrity violation and SHALL NOT average,
  reorder, infer, or present those records as a successful Case path

### Requirement: Operator Case access is fixed, tenant-derived and read-only
The loopback Platform API SHALL expose only `GET /v1/operator/cases/api-503.v1` for the
canonical operator snapshot. It SHALL derive effective tenant identity from an
allowlisted synthetic actor and SHALL accept no caller-selected Case, tenant, report,
path, snapshot, source, or version. Reading or failing to read the snapshot SHALL NOT
run or repair a workflow, create a store, decide approval, issue a command, retry an
effect, mutate a report, initialize a provider, or perform an external write.

#### Scenario: The authorized fixture observer reads the canonical Case
- **WHEN** the allowlisted actor for the snapshot tenant requests the fixed route with
  no query parameters and the canonical evidence passes validation
- **THEN** the API SHALL return one valid `OperatorCaseSnapshot` and SHALL leave the
  canonical report, default runtime store, Cases, workflows, approvals, deliveries,
  effects, and evaluation report unchanged

#### Scenario: The Case is absent or belongs to another tenant
- **WHEN** no valid canonical snapshot exists or the actor-derived tenant does not
  match its tenant
- **THEN** the API SHALL return the same `operator_case_not_found` envelope without
  disclosing tenant, Case, path, hash, report, or existence information

#### Scenario: Canonical evidence fails integrity
- **WHEN** the report or snapshot is malformed, duplicate-key, unsafe, stale,
  out-of-order, detached, hash-mismatched, or semantically inconsistent
- **THEN** the API SHALL return only `operator_case_not_ready` and SHALL NOT return a
  partial timeline, raw value, source path, or exception detail

#### Scenario: A caller attempts another selection or operation
- **WHEN** a request adds a query parameter, alternate path/Case/version, request body,
  or unsupported HTTP method
- **THEN** the API SHALL reject it before report selection or snapshot construction and
  SHALL NOT echo or execute the attempted value

### Requirement: The console renders a truthful bounded Case timeline
The Vue console SHALL construct its Case workspace only from a completely validated
`OperatorCaseSnapshot`. The ready view SHALL show fixture and Case identity, immutable
revision/workflow identity, current fixture state, source/snapshot/evidence roots,
explicit offline capabilities, aggregate counts, an ordered phase timeline, and one
selected entry with bounded source identities, hashes, transition or observation,
gate/recovery status, and reason code. It SHALL NOT render unrestricted JSON, raw
customer/prompt/tool/provider data, credentials, caller authority, executable markup,
or an implication of live send, customer receipt, resolution, completion, or permission
for another effect.

#### Scenario: The canonical API-503 timeline is rendered
- **WHEN** the browser receives a valid canonical snapshot
- **THEN** it SHALL render the complete declared intake-to-evidence phase order and
  allow one source-linked entry to be inspected while labeling the final state
  `DELIVERY_RECORDED (fixture-local)` and the capability as offline and Replay-only

#### Scenario: A gate, denial, timeout or recovery fact is shown
- **WHEN** a validated timeline entry represents a failed gate, policy denial, stale
  approval, timeout, restart, reconciliation, or replay verification
- **THEN** the render model SHALL preserve that classification and SHALL NOT convert it
  into an authorized, delivered, resolved, completed, or duplicate-success state

#### Scenario: The operator surface is unavailable
- **WHEN** the API reports loading, missing/foreign, identity-denied, or
  integrity-not-ready evidence
- **THEN** the console SHALL render a stable bounded unavailable state without raw
  response content while health and the evaluation surface remain independently usable

### Requirement: Offline operator acceptance is deterministic and side-effect free
The cross-platform development command SHALL verify source-backed generation, the
snapshot contract, tenant-scoped API, pure console render model, production build, and
the complete integrity/security matrix offline. It SHALL emit a redacted
machine-readable acceptance report at an explicit repository path only after every
check passes and SHALL preserve any prior accepted report on failure.

#### Scenario: Operator timeline acceptance succeeds
- **WHEN** the current allowlisted fixture, contracts, implementation, and retained
  source definitions are valid on an offline workstation
- **THEN** two fresh snapshots SHALL be equal, every declared timeline source link and
  count SHALL match the generated durable facts, the production console build SHALL
  pass, and the report SHALL record zero default-store/report mutation, duplicate
  natural/idempotency keys, network requests, model invocations, provider operations,
  external-write attempts, or unauthorized effects

#### Scenario: A negative integrity or authority path is exercised
- **WHEN** acceptance tests missing/foreign evidence, malformed or duplicate-key JSON,
  unsafe path/field, detached hash/predecessor, duplicate/out-of-order source, count
  mismatch, stale approval, policy denial, restart/timeout duplicate completion,
  unsupported customer-success claim, arbitrary selector, or unsupported method
- **THEN** each path SHALL emit no snapshot or unsafe detail and SHALL produce its
  expected stable unavailable/denied classification

#### Scenario: Acceptance fails before publication
- **WHEN** any source, contract, API, renderer, build, determinism, isolation, or
  side-effect check fails
- **THEN** the command SHALL return failure and SHALL NOT create or replace the prior
  canonical operator acceptance report
