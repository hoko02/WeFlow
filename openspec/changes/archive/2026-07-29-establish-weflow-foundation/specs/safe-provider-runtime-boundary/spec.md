## ADDED Requirements

### Requirement: Replay is the only enabled provider path by default
The Agent Runtime SHALL default to a deterministic replay provider. The default configuration SHALL set provider mode to replay and SHALL disable live model/provider access. Startup and readiness reports SHALL make the selected safe mode observable without disclosing configuration secrets.

#### Scenario: The default runtime starts
- **WHEN** the Agent Runtime starts with no provider override
- **THEN** it SHALL become ready only with the replay provider selected and SHALL not initialize a model client or an external tool client

### Requirement: Forbidden provider selections fail closed
The configuration validator SHALL reject a live model/provider selection, real enterprise credentials, an external-write adapter, or a multi-agent coordinator unless a future archived OpenSpec change explicitly introduces the capability and its gates. A rejection MUST prevent readiness and MUST produce a redacted policy-denial result.

#### Scenario: A live provider is configured accidentally
- **WHEN** configuration requests a non-replay provider or supplies real-provider credential settings
- **THEN** validation SHALL deny startup, keep the runtime not-ready, and report a redacted provider-policy denial without contacting the provider

#### Scenario: Multi-agent mode is requested
- **WHEN** configuration requests a multi-agent coordinator in Change 0
- **THEN** validation SHALL deny the request and SHALL NOT create subordinate agents, delegate work, or claim reduced workflow risk

### Requirement: No runtime component can authorize or complete a side effect
The Agent Runtime and Business Simulator SHALL NOT register an external-write executor in Change 0. They SHALL NOT treat replay content or a future model-like response as a capability grant, policy decision, approval, verifier result, external-write completion, or case-completion declaration. Only the versioned contracts and negative-path diagnostics for those concepts are in scope.

#### Scenario: A replay fixture requests an external action
- **WHEN** a synthetic replay fixture contains a proposed ticket, reply, or other external action
- **THEN** the runtime SHALL record it only as replay data or reject it by policy, SHALL NOT execute an external call, and SHALL NOT emit a successful completion result

#### Scenario: A self-approval-like input is supplied
- **WHEN** replay input presents a proposed action together with a purported approval or success assertion not bound to a valid current ApprovalDecision contract
- **THEN** the runtime SHALL reject it as unauthorized or stale and SHALL NOT grant permission, approve the action, or declare success

### Requirement: Provider-boundary tests prove the negative path
The baseline test suite SHALL exercise replay-default startup and each forbidden configuration path without real credentials or network access. Test results SHALL identify the denied capability category while redacting configuration values.

#### Scenario: CI runs provider safety checks
- **WHEN** CI executes the provider-boundary test suite with synthetic configuration fixtures
- **THEN** it SHALL pass only if every live-provider, external-write, multi-agent, and invalid self-approval attempt is denied before any network or side-effect attempt

