## ADDED Requirements

### Requirement: Active C2C notification SHALL use at-most-once transport execution

The system SHALL create a durable notification intent with a stable Case/binding natural key and SHALL make no more than one active provider transport attempt. Local reconciliation SHALL precede the attempt. A provider-accepted result may be recorded as accepted; a timeout, disconnect, or unknown outcome SHALL remain ambiguous and MUST NOT be retried or reported as delivered.

#### Scenario: Process restarts before transport attempt

- **WHEN** a durable intent exists with no recorded attempt
- **THEN** recovery may make the one allowed transport attempt after local reconciliation

#### Scenario: Process restarts after ambiguous transport

- **WHEN** an attempt was started but no authoritative provider outcome is known
- **THEN** recovery records `NOTIFICATION_UNKNOWN` and makes no second active C2C attempt

### Requirement: Passive C2C replies SHALL derive idempotency from the source event

Each private pull result, task response, draft preview, or rejection response SHALL use the current C2C source `msg_id`, a stable response-kind-specific `msg_seq`, and an idempotency key bound to the Case, binding, and workflow version. Execution SHALL respect the provider passive-reply window and count limit.

#### Scenario: Duplicate C2C event is delivered

- **WHEN** QQ delivers the same private command event more than once
- **THEN** the system produces one logical transition and at most one provider-visible reply for each response kind

#### Scenario: Passive window expires

- **WHEN** a private response cannot execute within the provider window
- **THEN** it expires safely and requires a new private command rather than an active-send fallback

### Requirement: Final group delivery SHALL reconcile against the approval source and decision

The final reply intent SHALL bind the exact approval decision, candidate artifact hash, group approval source `msg_id`, stable `msg_seq`, group, Case, and workflow version. Recovery SHALL check local intent/result state before any repeat and SHALL never switch to an active group send.

#### Scenario: Worker crashes after provider acceptance is recorded

- **WHEN** the final intent is replayed after restart
- **THEN** recovery observes the completed result and performs no transport call

#### Scenario: Final outcome is unknown

- **WHEN** transport returns an ambiguous outcome
- **THEN** the workflow records the uncertainty, attempts only safe reconciliation within the passive path, and does not claim delivery or completion

### Requirement: Recovery evidence SHALL distinguish provider acceptance from business completion

Intent, reconcile, execute, and complete records SHALL retain content-free evidence for each external write path. Provider acceptance MUST NOT set customer receipt, issue resolution, or Case completion.

#### Scenario: Acceptance report is built after final provider acceptance

- **WHEN** all live provider calls were accepted
- **THEN** the report may set the transport acceptance facts while receipt, resolution, and Case completion remain false
