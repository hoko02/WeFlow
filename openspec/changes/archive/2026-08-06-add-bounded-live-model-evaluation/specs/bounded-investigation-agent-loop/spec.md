## MODIFIED Requirements

### Requirement: A single Agent produces closed structured outcomes
The runtime SHALL run exactly one Agent from an immutable Context Manifest using either the deterministic Replay provider or the explicitly authorized command-local live provider. A live provider SHALL return only a `ModelActionProposal`, which the runtime SHALL validate and normalize into the existing tenant/Case/workflow-bound `AgentAction`. Each normalized action SHALL be one of `read_crm`, `read_monitoring`, `read_knowledge`, `needs_information`, `needs_operator`, or `response_candidate`. The runtime SHALL reject unknown fields, arbitrary tool arguments, identity or target-state selection, direct state changes, approval, delivery, external writes, and completion/customer-success claims.

#### Scenario: A valid Replay fixture completes bounded investigation
- **WHEN** a named API-503 Replay fixture supplies a valid action transcript
- **THEN** the runtime SHALL preserve the existing ordered safe step facts and schema-valid terminal outcome with zero model/network calls

#### Scenario: A valid live proposal selects an allowed read
- **WHEN** an authorized live attempt returns one closed read action
- **THEN** the runtime SHALL derive all identities and resource scope from the Context Manifest, persist one normalized action, and invoke only the corresponding fixture-local read

#### Scenario: A proposal claims authority
- **WHEN** a Replay or live proposal requests a state change, custom tool argument, approval, delivery, provider, external write, or completion
- **THEN** the runtime SHALL fail closed and append no workflow transition, tool effect, approval, or delivery record

### Requirement: Agent execution has deterministic duplicate, budget, and progress gates
The runtime SHALL use stable logical turn and normalized step identities and enforce action, tool, provider-call, token, wall-time, cost, and consecutive-no-progress limits outside either Agent. It SHALL return a safe terminal outcome at a limit. A completed Replay step SHALL not repeat after restart; an incomplete or unknown live invocation SHALL close its attempt and SHALL not be reissued under the same attempt identity.

#### Scenario: An Agent repeats without progress
- **WHEN** the same logical action recurs beyond the configured no-progress limit
- **THEN** the runtime SHALL stop with `needs_operator` or `budget_exhausted`, preserve prior durable facts, and make no further provider or tool call

#### Scenario: A live attempt restarts after an observed action
- **WHEN** recovery finds a conclusive invocation observation and persisted normalized action for a logical turn
- **THEN** it SHALL reuse the durable turn evidence without invoking the provider or recording the action again

#### Scenario: A live attempt restarts after an unknown call
- **WHEN** recovery finds intent without a conclusive observation
- **THEN** it SHALL terminate that attempt as `provider_outcome_unknown` without a blind provider retry or workflow-success transition

## ADDED Requirements

### Requirement: Live response proposals are bound before candidate verification
For a live `response_candidate` proposal, the runtime SHALL validate and redact the bounded draft, create a content-addressed `ResponseDraftArtifact`, and persist a `LiveCandidateBinding` that links the invocation, normalized action, Context Manifest, draft artifact, ordered evidence references, and derived `ResponseCandidate`. The model SHALL NOT supply durable identities, hashes, verifier outcomes, or workflow state.

#### Scenario: A valid live draft is normalized
- **WHEN** the provider proposes a bounded draft with only current evidence references and allowed response fields
- **THEN** the runtime SHALL derive the artifact, binding, and candidate identities/hashes before asking the deterministic verifier for an outcome

#### Scenario: A live draft is detached or unsafe
- **WHEN** the draft cites absent/foreign evidence, contains secret-like or prohibited claims, exceeds bounds, or mismatches its invocation/context
- **THEN** normalization SHALL fail, no candidate SHALL be persisted, and `RESPONSE_READY` SHALL remain unreachable
