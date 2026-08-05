## ADDED Requirements

### Requirement: Operator Case snapshots are closed, source-linked and compatible
WeFlow SHALL maintain a language-neutral compatible v1 `OperatorCaseSnapshot` schema
for the fixed offline Case workspace boundary. The snapshot SHALL bind schema and
content-addressed snapshot identity, effective tenant, allowlisted fixture, stable
Case/revision/workflow identity, current fixture state, canonical source-report and
evidence/replay roots, aggregate counts, and explicit offline capability flags. Each
ordered timeline entry SHALL bind a unique contiguous sequence and stable identity to
an allowlisted source record type, source record identity/hash, phase, bounded state
transition or observation, result, gate/recovery classification, and safe reason code.
The contract SHALL forbid undeclared or arbitrary payload maps, raw customer/prompt/
tool/provider content, absolute or escaping paths, credentials, caller authority,
executable content, live provider/customer-success assertions, and workflow, approval,
retry, delivery, completion, or external-write authority.

#### Scenario: A valid operator snapshot is consumed cross-language
- **WHEN** a complete snapshot generated from the accepted API-503 durable source chain
  is validated by the Python and TypeScript contract packages
- **THEN** both packages SHALL accept the same canonical snapshot hash, tenant/Case/
  revision/workflow links, ordered typed source entries, counts, roots, states, reason
  codes, and capability flags

#### Scenario: A snapshot is detached, misordered, unsafe or misleading
- **WHEN** a snapshot has a foreign identity, mismatched source/root/snapshot hash,
  missing or duplicate entry/source ID, non-contiguous or out-of-order sequence,
  predecessor/count mismatch, stale approval presented as valid, denial or failed gate
  presented as success, undeclared/raw/secret-like field, unsafe path, caller authority,
  live-provider/customer-success claim, or mutation/effect capability
- **THEN** both contract packages SHALL reject it before the snapshot can be retained,
  served, or rendered

#### Scenario: Retained v1 contracts remain compatible
- **WHEN** the additive operator snapshot schema and fixtures are introduced and all
  retained valid and invalid v1 fixtures are revalidated
- **THEN** their prior acceptance/rejection outcomes SHALL remain unchanged and the new
  schema fingerprint SHALL be recorded only after cross-language parity passes
