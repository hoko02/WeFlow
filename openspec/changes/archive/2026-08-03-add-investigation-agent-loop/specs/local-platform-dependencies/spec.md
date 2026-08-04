## MODIFIED Requirements

### Requirement: Offline mode is deterministic and self-contained
Offline mode SHALL execute the durable workflow, replay Agent, fixture investigation gateway, verifier, and recovery from local SQLite and named fixtures without Docker, network, model credentials, or enterprise credentials.

#### Scenario: Offline investigation recovers after an interruption
- **WHEN** a worker stops after Agent action, tool evidence, candidate, or verifier persistence
- **THEN** a fresh worker SHALL reconstruct the same safe projection without an external call or duplicate state transition