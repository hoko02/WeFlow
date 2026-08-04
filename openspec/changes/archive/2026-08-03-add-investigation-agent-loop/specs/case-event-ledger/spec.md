## MODIFIED Requirements

### Requirement: Case revisions and business events are append-only source records
The ledger SHALL retain immutable CaseRevision and BusinessEvent records and allow only the deterministic control-kernel port to append allowlisted investigation-started and response-candidate-verified workflow events after validating tenant, Case, revision, checkpoint causation, predecessor state, and canonical digest.

#### Scenario: An Agent attempts to append a Case event
- **WHEN** an Agent result or API caller supplies an event or state payload
- **THEN** the ledger SHALL reject it and preserve the source timeline