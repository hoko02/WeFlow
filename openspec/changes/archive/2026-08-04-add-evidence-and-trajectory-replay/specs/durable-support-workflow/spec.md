## ADDED Requirements

### Requirement: Evidence trajectory extraction is append-only, read-only to workflow control, and idempotent
The control kernel SHALL expose a deterministic reader over append-only Case and
workflow source facts for one tenant-scoped evidence trajectory. It MAY persist a
separate content-addressed Artifact/trajectory/report fact with a stable identity, but
it SHALL NOT append a Case state event, change a workflow checkpoint/version, issue or
revoke a grant, create an approval decision, create/reconcile/execute a ticket or
delivery intent, or invoke an Agent/model/provider/tool while extracting or replaying
evidence. An exact extraction retry SHALL converge on the existing evidence artifact.

#### Scenario: An authorized completed fixture is extracted for evidence
- **WHEN** the named API-503 workflow has a valid append-only path through local
  delivery recording
- **THEN** extraction SHALL link its existing durable source facts into one evidence
  trajectory while preserving Case state, checkpoint version, approval count, and one
  local delivery record

#### Scenario: Report persistence is interrupted or retried
- **WHEN** a worker stops after an evidence artifact or report is persisted and a fresh
  worker repeats the same extraction
- **THEN** recovery SHALL return the same content-addressed evidence identity and SHALL
  not append a duplicate workflow transition, command, approval, intent, or effect

### Requirement: Invalid lineage blocks evidence replay without changing the workflow
The workflow evidence reader SHALL validate tenant, Case/revision/workflow identity,
checkpoint causation, predecessor links, content hashes, and canonical order before
emitting a replayable trajectory. Missing, foreign, tampered, duplicated, or conflicting
facts SHALL yield a redacted lineage failure and SHALL leave the latest workflow
projection and every existing effect record unchanged.

#### Scenario: A foreign or tampered source fact is selected
- **WHEN** an evidence reader encounters a source reference that does not match the
  effective tenant or recorded digest
- **THEN** it SHALL not emit a replayable trajectory or report, shall not reveal the
  foreign fact, and SHALL not move the workflow or execute a recovery path
