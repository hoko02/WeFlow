## MODIFIED Requirements

### Requirement: Replay is the only enabled provider path by default
The Agent Runtime SHALL select only a deterministic Replay Agent provider for this change. It SHALL accept named fixture transcripts but SHALL not initialize a live model client, network provider, credential, external tool client, or multi-Agent coordinator.

#### Scenario: A live provider is selected for investigation
- **WHEN** configuration or a fixture requests a live provider or credential
- **THEN** startup or execution SHALL deny it before contact and emit only a redacted reason