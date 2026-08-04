## 1. Contracts and fixtures

- [x] 1.1 Define additive v1 JSON Schema, Python, and TypeScript types for ContextManifest, AgentAction, ToolRequest/Result, ResponseCandidate, and VerifierOutcome.
- [x] 1.2 Add valid, invalid, tenant-bound, raw-content, and retained-fixture compatibility corpus with cross-language checks.
- [x] 1.3 Add named API-503 replay transcripts and deterministic CRM, monitoring, and knowledge fixtures without raw customer content.

## 2. Durable control and evidence

- [x] 2.1 Extend the control kernel journal/projections with immutable Agent-step, tool, evidence, candidate, and verifier facts linked to workflow checkpoints.
- [x] 2.2 Extend the allowlisted workflow reducer/checkpoint/recovery path from TICKET_READY through investigation and verifier-authorized RESPONSE_READY.
- [x] 2.3 Add recovery tests for interruptions after action, tool result, candidate, and verifier persistence without duplicate transition or tool result.

## 3. Runtime and tool gateway

- [x] 3.1 Implement the Replay Agent adapter with the closed action algebra and schema validation.
- [x] 3.2 Implement Context Compiler, deterministic action/tool/no-progress/budget gates, and safe terminal outcomes.
- [x] 3.3 Implement tenant-scoped fixture Investigation Tool Gateway and redacted content-addressed evidence conversion.
- [x] 3.4 Implement deterministic response-candidate verifier and prohibit Agent authority over state, approval, delivery, external writes, and completion.

## 4. API, simulator, and observability

- [x] 4.1 Wire offline Control Worker, Agent Runtime, Business Simulator, and narrow Platform API observation surfaces to the new journal facts.
- [x] 4.2 Extend capability/health reporting and diagnostics console with truthful replay-Agent and candidate status while retaining disabled real-provider/external-write claims.
- [x] 4.3 Add safe traces, snapshots, and machine-readable inspection/report output with no raw prompt, fixture payload, credential, or unrestricted tool output.

## 5. Security, acceptance, and documentation

- [x] 5.1 Add unit, integration, security, and negative tests for cross-tenant reads, malformed/authority-claim actions, unallowlisted tools, live-provider denial, no-progress, and unverified candidates.
- [x] 5.2 Add a documented offline acceptance command covering API-503 investigation, required evidence, replay determinism, workflow recovery, and RESPONSE_READY without approval or delivery.
- [x] 5.3 Run repeated offline baselines; verify no duplicate state transition/tool result and record explicit Docker/Node limitations.
- [x] 5.4 Update README, development guidance, fixtures, support matrix, and project memory with implemented-versus-unimplemented boundaries.
- [x] 5.5 Run check, lint, contracts, test, acceptance, strict OpenSpec validation, and retain redacted machine-readable evidence before archive.