## ADDED Requirements

### Requirement: Evaluation suite snapshots are closed, content-addressed and compatible
WeFlow SHALL maintain a language-neutral compatible v1 `EvaluationSuiteSnapshot`
schema for the read-only offline evaluation console boundary. The snapshot SHALL bind
tenant, suite/profile, acceptance and repeated-baseline state, suite/report and
snapshot hashes, aggregate counts, fixed capability flags, and an ordered array of
safe task views. Each task view SHALL bind its fixture/source/task/oracle/result
identities and hashes, result/failure classification, hard-gate and quality-dimension
outcomes, existing offline metrics, and safe observation facts. It SHALL forbid
undeclared/raw fields, absolute paths, credentials, caller authority, unrestricted
tool/adapter content, live-provider/customer-success claims, and any workflow,
approval, delivery, retry, or external-write authority.

#### Scenario: A valid evaluation snapshot is consumed cross-language
- **WHEN** a complete snapshot derived from the accepted `offline-seed.v1` report is
  validated by the Python and TypeScript contract packages
- **THEN** both packages SHALL accept the same closed payload, canonical snapshot hash,
  ordered result links, hard-gate semantics, counts, and capability flags

#### Scenario: A snapshot is detached, unsafe or misleading
- **WHEN** a snapshot has a foreign tenant, mismatched suite/report/result/source hash,
  duplicate or missing task/result ID, count mismatch, numeric quality after a failed
  gate, undeclared/raw/secret-like field, absolute path, caller authority, live-
  provider claim, customer-success claim, or external-write capability
- **THEN** both contract packages SHALL reject it before the snapshot can be served or
  rendered

#### Scenario: Retained evaluation contracts remain compatible
- **WHEN** all retained valid and invalid v1 evaluation fixtures are revalidated after
  the additive snapshot schema is introduced
- **THEN** their prior acceptance/rejection results SHALL remain unchanged and the new
  schema fingerprint SHALL be recorded only after cross-language compatibility passes
