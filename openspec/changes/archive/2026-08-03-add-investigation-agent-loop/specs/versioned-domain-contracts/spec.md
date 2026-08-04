## MODIFIED Requirements

### Requirement: Canonical versioned domain schemas exist
WeFlow SHALL maintain compatible v1 schemas for retained boundary objects plus ContextManifest, AgentAction, ToolRequest, ToolResult, ResponseCandidate, and VerifierOutcome. Each SHALL have stable schema identity/version, tenant/Case/revision linkage where applicable, forbid undeclared/raw fields, and validate in Python and TypeScript.

#### Scenario: New Agent boundary fixtures validate cross-language
- **WHEN** valid and invalid replay Agent fixtures are consumed by both contract packages
- **THEN** both SHALL agree on acceptance and rejection while retained v1 fixtures remain valid