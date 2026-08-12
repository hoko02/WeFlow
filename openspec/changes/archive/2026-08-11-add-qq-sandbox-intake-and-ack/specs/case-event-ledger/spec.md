## ADDED Requirements

### Requirement: Accepted QQ sandbox intake reuses the atomic Case ledger
For the first accepted server-normalized QQSandboxInboundEvent, the Case ledger SHALL
use the event's effective tenant, safe conversation/customer references, inbound
natural key, source content hash, and correlation metadata to create the same stable
Case, immutable CaseRevision 1, and exactly three ordered initial BusinessEvents
required for accepted IM intake. QQ source fields SHALL not weaken tenant-scoped reads,
append-only records, transaction rollback, projection replay, or deterministic
snapshot behavior.

#### Scenario: A first QQ mention creates the initial ledger
- **WHEN** a valid allowlisted QQ sandbox event passes identity, deduplication,
  sequence, and payload-safety validation
- **THEN** one transaction SHALL persist the receipt, Case, CaseRevision 1, and exactly
  the three required ordered events, and the projection SHALL report `RECEIVED`

#### Scenario: QQ source persistence fails
- **WHEN** an error or uniqueness conflict occurs before the QQ intake transaction
  commits
- **THEN** the ledger SHALL roll back without a partial receipt, Case, revision, event,
  projection, or acknowledgement intent

## MODIFIED Requirements

### Requirement: Intake state has no external side effect or completion authority
Inbound intake writes SHALL remain local payload-safe persistence. Once the initial
intake transaction commits, it SHALL be eligible for one durable, deterministic
workflow activation that records local workflow/checkpoint and simulated effect facts
through the control kernel. For an accepted QQ sandbox source only, the committed
intake MAY also cause creation of one distinct fixed QQ acknowledgement intent under
the dedicated command and capability gates; the intake transaction itself SHALL NOT
initialize a QQ executor or perform the send. Intake itself SHALL NOT initialize a
model, invoke a business/tool provider, request/decide approval, send a final reply,
execute any other real external write, or declare a Case/customer issue complete. The
existing workflow SHALL preserve Replay mode and its fixture-local ticket simulator.

#### Scenario: An accepted synthetic intake is inspected for prohibited behavior
- **WHEN** the accepted synthetic intake fixture and its telemetry/capability report are
  examined
- **THEN** the evidence SHALL show the initial local Case/Revision/Event state plus, if
  scheduled, a deterministic local workflow activation; it SHALL show no model, real
  external-write, approval, delivery, workflow-completion, or customer-resolution
  assertion

#### Scenario: An accepted QQ intake is inspected
- **WHEN** the accepted QQ sandbox intake and its durable facts are examined
- **THEN** the intake transaction SHALL contain only the initial local ledger and MAY
  be followed by one separately gated fixed acknowledgement recovery chain; it SHALL
  show no model, handler approval, final reply, other external write, Case completion,
  or customer-resolution assertion

#### Scenario: Intake is retried after workflow scheduling
- **WHEN** an exact inbound retry occurs after the original Case has a durable workflow
  activation, checkpoint, or QQ acknowledgement intent
- **THEN** the intake boundary SHALL return the original deduplicated result and SHALL
  not start another workflow, append another state event, create another simulated
  ticket intent, or create another QQ acknowledgement intent
