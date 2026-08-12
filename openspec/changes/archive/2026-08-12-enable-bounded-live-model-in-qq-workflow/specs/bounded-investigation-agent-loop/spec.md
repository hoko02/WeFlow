## MODIFIED Requirements

### Requirement: A single Agent produces closed structured outcomes

The runtime SHALL run exactly one Agent from an immutable Context Manifest using either the deterministic Replay provider or a live provider explicitly authorized inside the dedicated evaluation or Stage 3 QQ command. A live provider SHALL return only a `ModelActionProposal`, which the runtime SHALL validate and normalize into the existing tenant/Case/workflow-bound `AgentAction`. Each normalized action SHALL be one of `read_crm`, `read_monitoring`, `read_knowledge`, `needs_information`, `needs_operator`, or `response_candidate`. The runtime SHALL reject unknown fields, arbitrary tool arguments, identity or target-state selection, direct state changes, approval, delivery, external writes, and completion/customer-success claims. A Stage 3 Agent SHALL additionally bind every action to the private handler-authored assist request and SHALL have no QQ identity, approval, or transport access.

#### Scenario: A valid Replay fixture completes bounded investigation

- **WHEN** a named API-503 Replay fixture supplies a valid action transcript
- **THEN** the runtime SHALL preserve the existing ordered safe step facts and schema-valid terminal outcome with zero model/network calls

#### Scenario: A valid live proposal selects an allowed read

- **WHEN** an authorized evaluation or Stage 3 live attempt returns one closed read action
- **THEN** the runtime SHALL derive all identities and resource scope from the Context Manifest, persist one normalized action, and invoke only the corresponding fixture-local read

#### Scenario: A proposal claims authority

- **WHEN** a Replay or live proposal requests a state change, custom tool argument, approval, delivery, provider, external write, or completion
- **THEN** the runtime SHALL fail closed and append no workflow transition, tool effect, approval, or delivery record

### Requirement: Agent execution has deterministic duplicate, budget, and progress gates

The runtime SHALL use stable logical turn and normalized step identities and enforce action, tool, provider-call, token, wall-time, cost, and consecutive-no-progress limits outside every Agent. Evaluation attempts retain isolated attempt budgets; Stage 3 additionally enforces assist-request and cumulative Case budgets bound to the active handler and workflow version. The runtime SHALL return a safe terminal outcome at a limit. A completed Replay or live step SHALL not repeat after restart; an incomplete or unknown live invocation SHALL close its evaluation attempt or Stage 3 assist request and SHALL not be reissued under the same identity.

#### Scenario: An Agent repeats without progress

- **WHEN** the same logical action recurs beyond the configured no-progress limit
- **THEN** the runtime SHALL stop with `needs_operator` or `budget_exhausted`, preserve prior durable facts, and make no further provider or tool call

#### Scenario: A live execution restarts after an observed action

- **WHEN** recovery finds a conclusive invocation observation and persisted normalized action for a logical turn
- **THEN** it SHALL reuse the durable turn evidence without invoking the provider or recording the action again

#### Scenario: A live execution restarts after an unknown call

- **WHEN** recovery finds intent without a conclusive observation
- **THEN** it SHALL terminate that evaluation attempt or Stage 3 assist request as `provider_outcome_unknown` without a blind provider retry or workflow-success transition

#### Scenario: Repeated private assist delivery is observed

- **WHEN** QQ delivers the same valid `WF-ASSIST` source event more than once
- **THEN** the runtime SHALL reuse one assist request and its durable turns, consume no additional model budget, and create no duplicate candidate or private reply

### Requirement: Live response proposals are bound before candidate verification

For a live `response_candidate` proposal, the runtime SHALL validate and redact the bounded draft, create a content-addressed `ResponseDraftArtifact`, and persist a `LiveCandidateBinding` that links the invocation, normalized action, Context Manifest, draft artifact, ordered evidence references, and derived `ResponseCandidate`. For Stage 3 it SHALL additionally create a content-free binding to the customer-issue artifact, private assist request, active handler binding, Case revision, policy/capability profiles, and expected workflow version before normalizing the result into the current restricted QQ candidate artifact. The model SHALL NOT supply durable identities, hashes, verifier outcomes, workflow state, approval, or QQ metadata.

#### Scenario: A valid live draft is normalized for evaluation

- **WHEN** an evaluation provider proposes a bounded draft with only current evidence references and allowed response fields
- **THEN** the runtime SHALL derive the artifact, binding, and candidate identities/hashes before asking the deterministic verifier for an outcome

#### Scenario: A valid live draft is normalized for the QQ handler

- **WHEN** a Stage 3 provider proposes a bounded draft whose assist request, handler, issue, Context, evidence, Case/version, policies, and budgets all match
- **THEN** the runtime SHALL derive the model and QQ candidate bindings before any private preview or approval request is created

#### Scenario: A live draft is detached or unsafe

- **WHEN** the draft cites absent/foreign evidence, contains secret-like or prohibited claims, exceeds bounds, or mismatches its invocation/context/assist/handler/Case version
- **THEN** normalization SHALL fail, no current candidate or approval request SHALL be persisted, and `RESPONSE_READY` SHALL remain unreachable
