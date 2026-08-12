## MODIFIED Requirements

### Requirement: The investigation gateway exposes only tenant-scoped fixture reads

The gateway SHALL derive tenant, Case, revision, tool, and resource scope from the Context Manifest and expose only named synthetic CRM, monitoring, and knowledge reads. In Replay mode it SHALL preserve the existing content-addressed evidence behavior. During an authorized live evaluation or Stage 3 assist request it MAY additionally return an in-memory `ModelToolObservation` containing only length-bounded, schema-validated synthetic fields from the same allowlisted source; the durable `ToolResult`, workflow/evaluation record, and report SHALL retain only safe identities, classifications, and hashes. A Stage 3 lookup SHALL also require the active paired tenant/group, handler assist request, Case/revision, and workflow version to match the server-owned API-503 fixture profile. The gateway SHALL not register real business connectors, ticket/knowledge writes, network clients, credentials, approval, delivery, QQ operations, or arbitrary tool arguments.

#### Scenario: An allowed Replay read produces safe evidence

- **WHEN** a valid Replay action requests an allowlisted fixture read in scope
- **THEN** the gateway SHALL preserve the existing redacted, content-addressed evidence reference and safe tool result with no model-facing body

#### Scenario: An allowed live evaluation read produces a bounded model view

- **WHEN** a valid normalized live evaluation action requests an allowlisted fixture read in scope
- **THEN** the gateway SHALL return one durable safe tool exchange plus an ephemeral synthetic model observation whose source hash matches that exchange

#### Scenario: An allowed Stage 3 read uses the current QQ Case scope

- **WHEN** a valid normalized Stage 3 action is bound to the current assist request and its server-owned synthetic API-503 resource
- **THEN** the gateway SHALL return the same content-addressed fixture evidence and ephemeral bounded model view without exposing QQ data or contacting a business system

#### Scenario: A foreign, parameterized, or write request is attempted

- **WHEN** a proposal selects another tenant/Case/assist request, an undeclared resource, caller/model-supplied arguments, or a write operation
- **THEN** the gateway SHALL deny it without revealing foreign data, invoking a tool/provider, or executing an effect
