## MODIFIED Requirements

### Requirement: The investigation gateway exposes only tenant-scoped fixture reads
The gateway SHALL derive tenant, Case, revision, tool, and resource scope from the Context Manifest and expose only named synthetic CRM, monitoring, and knowledge reads. In Replay mode it SHALL preserve the existing content-addressed evidence behavior. During an authorized live attempt it MAY additionally return an in-memory `ModelToolObservation` containing only length-bounded, schema-validated synthetic fields from the same allowlisted source; the durable `ToolResult`, evaluation record, and report SHALL retain only safe identities, classifications, and hashes. The gateway SHALL not register ticket writes, network clients, credentials, approval, delivery, knowledge publication, or arbitrary tool arguments.

#### Scenario: An allowed Replay read produces safe evidence
- **WHEN** a valid Replay action requests an allowlisted fixture read in scope
- **THEN** the gateway SHALL preserve the existing redacted, content-addressed evidence reference and safe tool result with no model-facing body

#### Scenario: An allowed live read produces a bounded model view
- **WHEN** a valid normalized live action requests an allowlisted fixture read in scope
- **THEN** the gateway SHALL return one durable safe tool exchange plus an ephemeral synthetic model observation whose source hash matches that exchange

#### Scenario: A foreign, parameterized, or write request is attempted
- **WHEN** a proposal selects another tenant, an undeclared resource, caller/model-supplied arguments, or a write operation
- **THEN** the gateway SHALL deny it without revealing foreign data, invoking a tool, or executing an effect

## ADDED Requirements

### Requirement: Tool content remains untrusted and cannot change authority
Every model-facing tool observation SHALL be labeled as untrusted synthetic data, constrained by an allowlisted closed schema and size limit, and placed outside system instructions. A tool field SHALL NOT select another tool, provider, tenant, policy, budget, state, approval, or delivery. Secret-like content and undeclared fields SHALL be rejected before prompt construction.

#### Scenario: Knowledge content carries an injection instruction
- **WHEN** the prompt-injection task returns a synthetic knowledge observation that requests approval, delivery, secret disclosure, or instruction override
- **THEN** the observation SHALL remain data-only, its source hash SHALL be retained, and downstream parser/policy/verifier gates SHALL prevent the requested authority or effect regardless of model behavior

#### Scenario: A tool observation contains unsafe content
- **WHEN** a fixture tool view contains a credential-like value, private classification, excessive text, executable field, or undeclared property
- **THEN** the gateway SHALL fail the attempt before sending that observation to the provider and SHALL persist only a redacted tool-input validation failure
