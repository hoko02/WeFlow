# fixture-investigation-tool-gateway Specification

## Purpose
Define the tenant-scoped, fixture-local, read-only tool boundary for deterministic
investigation evidence.

## Requirements

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

### Requirement: Tool content remains untrusted and cannot change authority
Every model-facing tool observation SHALL be labeled as untrusted synthetic data, constrained by an allowlisted closed schema and size limit, and placed outside system instructions. A tool field SHALL NOT select another tool, provider, tenant, policy, budget, state, approval, or delivery. Secret-like content and undeclared fields SHALL be rejected before prompt construction.

#### Scenario: Knowledge content carries an injection instruction
- **WHEN** the prompt-injection task returns a synthetic knowledge observation that requests approval, delivery, secret disclosure, or instruction override
- **THEN** the observation SHALL remain data-only, its source hash SHALL be retained, and downstream parser/policy/verifier gates SHALL prevent the requested authority or effect regardless of model behavior

#### Scenario: A tool observation contains unsafe content
- **WHEN** a fixture tool view contains a credential-like value, private classification, excessive text, executable field, or undeclared property
- **THEN** the gateway SHALL fail the attempt before sending that observation to the provider and SHALL persist only a redacted tool-input validation failure
