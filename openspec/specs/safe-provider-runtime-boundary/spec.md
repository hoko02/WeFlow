# safe-provider-runtime-boundary Specification

## Purpose
TBD - created by archiving change establish-weflow-foundation. Update Purpose after archive.
## Requirements
### Requirement: Replay is the only enabled provider path by default
The Agent Runtime SHALL select only a deterministic Replay Agent provider for this
change. It SHALL accept named fixture transcripts but SHALL not initialize a live model
client, network provider, credential, external tool client, or multi-Agent coordinator.
Startup and readiness reports SHALL make the selected safe mode observable without
disclosing configuration secrets.

#### Scenario: The default runtime starts
- **WHEN** the Agent Runtime starts with no provider override
- **THEN** it SHALL become ready only with the replay provider selected and SHALL not initialize a model client or an external tool client

#### Scenario: A live provider is selected for investigation
- **WHEN** configuration or a fixture requests a live provider or credential
- **THEN** startup or execution SHALL deny it before contact and emit only a redacted
  reason
### Requirement: Forbidden provider selections fail closed
The configuration validator SHALL reject a live model/provider selection, real enterprise credentials, an external-write adapter, or a multi-agent coordinator unless a future archived OpenSpec change explicitly introduces the capability and its gates. A rejection MUST prevent readiness and MUST produce a redacted policy-denial result.

#### Scenario: A live provider is configured accidentally
- **WHEN** configuration requests a non-replay provider or supplies real-provider credential settings
- **THEN** validation SHALL deny startup, keep the runtime not-ready, and report a redacted provider-policy denial without contacting the provider

#### Scenario: Multi-agent mode is requested
- **WHEN** configuration requests a multi-agent coordinator in Change 0
- **THEN** validation SHALL deny the request and SHALL NOT create subordinate agents, delegate work, or claim reduced workflow risk

### Requirement: No runtime component can authorize or complete a side effect
The Agent Runtime and Business Simulator SHALL NOT register a live/external-write
executor or treat replay content or a model-like response as a Capability Grant, Policy
Decision, approval, verifier result, delivery completion, or Case-completion
declaration. Only the deterministic control kernel may evaluate the named fixture-owned
Capability/Policy rules, persist a hash-bound approval, and invoke the named
fixture-local delivery adapter after all gates pass. That bounded local adapter SHALL
not initialize a network client, credential, real enterprise connector, or
customer-success behavior.

#### Scenario: A replay fixture requests an external action
- **WHEN** a synthetic replay fixture contains a proposed ticket, reply, or other
  external action
- **THEN** the runtime SHALL record it only as replay data or reject it by policy,
  SHALL NOT execute an external call, and SHALL NOT emit a successful completion result

#### Scenario: A self-approval-like input is supplied
- **WHEN** replay input presents a proposed action together with a purported approval
  or success assertion not bound to a valid current ApprovalDecision and policy/
  Capability authorization profile
- **THEN** the runtime SHALL reject it as unauthorized or stale and SHALL NOT grant
  permission, approve the action, or declare success

#### Scenario: The named control path reaches fixture-local delivery
- **WHEN** the deterministic control kernel has a current valid policy, Capability,
  approval, and authorization binding for the named fixture
- **THEN** it MAY record the fixture-local delivery chain while the Agent Runtime and
  Business Simulator do not grant authority or contact an external provider
### Requirement: Provider-boundary tests prove the negative path
The baseline test suite SHALL exercise replay-default startup and each forbidden configuration path without real credentials or network access. Test results SHALL identify the denied capability category while redacting configuration values.

#### Scenario: CI runs provider safety checks
- **WHEN** CI executes the provider-boundary test suite with synthetic configuration fixtures
- **THEN** it SHALL pass only if every live-provider, external-write, multi-agent, and invalid self-approval attempt is denied before any network or side-effect attempt
