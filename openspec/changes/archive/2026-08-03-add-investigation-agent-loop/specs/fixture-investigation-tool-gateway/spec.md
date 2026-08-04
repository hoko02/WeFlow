## ADDED Requirements

### Requirement: The investigation gateway exposes only tenant-scoped fixture reads
The gateway SHALL derive tenant, Case, revision, and resource scope from the Context Manifest and expose only named synthetic CRM, monitoring, and knowledge reads. It SHALL not register ticket writes, network clients, credentials, approval, or delivery adapters.

#### Scenario: An allowed read produces safe evidence
- **WHEN** a valid Agent action requests an allowlisted fixture read in scope
- **THEN** the gateway SHALL return a redacted, content-addressed evidence reference and append a safe tool result

#### Scenario: A foreign or write request is attempted
- **WHEN** a request selects another tenant, an undeclared resource, or a write operation
- **THEN** the gateway SHALL deny it without revealing foreign data or executing an effect