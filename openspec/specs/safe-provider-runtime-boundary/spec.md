# safe-provider-runtime-boundary Specification

## Purpose
TBD - created by archiving change establish-weflow-foundation. Update Purpose after archive.
## Requirements

### Requirement: Replay is the only enabled provider path by default
The Agent Runtime SHALL select only a deterministic Replay Agent provider for normal startup and every existing command. It SHALL accept named fixture transcripts but SHALL not initialize a live model client, network provider, credential, external tool client, or multi-Agent coordinator unless execution occurs inside the dedicated live-model evaluation command and every operator-controlled activation gate defined by `bounded-live-model-provider` has passed. Startup and readiness reports SHALL make the selected safe mode observable without disclosing configuration secrets.

#### Scenario: The default runtime starts
- **WHEN** the Agent Runtime starts with no provider override
- **THEN** it SHALL become ready only with the Replay provider selected and SHALL not initialize a model client or an external tool client

#### Scenario: A live provider is selected for ordinary investigation
- **WHEN** normal startup, an API request, a fixture, or a non-live command requests a live provider or credential
- **THEN** startup or execution SHALL deny it before contact and emit only a redacted reason

#### Scenario: The dedicated live command is explicitly authorized
- **WHEN** the live-model evaluation command satisfies every activation, destination, credential, source, and budget gate
- **THEN** it MAY register one command-local live provider without changing the Replay default or any public runtime capability

### Requirement: Forbidden provider selections fail closed
The configuration validator SHALL reject a live model/provider selection, real enterprise credential, external-write adapter, or multi-Agent coordinator unless an archived OpenSpec capability and the current command-specific gates explicitly permit that exact use. This change permits only synthetic, command-scoped live model evaluation; it does not permit enterprise credentials, customer data, public live APIs, approval/delivery providers, business external writes, or multi-Agent execution. A rejection MUST prevent contact/readiness and MUST produce a redacted policy-denial result.

#### Scenario: A live provider is configured accidentally
- **WHEN** normal environment configuration requests a non-Replay provider or supplies provider credential settings outside the live-evaluation command
- **THEN** validation SHALL deny startup, keep the runtime not-ready, and report a redacted provider-policy denial without contacting the provider

#### Scenario: A live fixture selects its own destination or model
- **WHEN** a task, fixture, model response, or caller payload supplies an endpoint, credential, provider, model, or expanded budget
- **THEN** validation SHALL reject the input before contact because only operator-controlled command configuration may select those values

#### Scenario: Multi-agent or external business execution is requested
- **WHEN** configuration requests a multi-Agent coordinator, real connector, approval/delivery provider, or external business-write executor
- **THEN** validation SHALL deny the request and SHALL NOT create subordinate Agents, contact the connector, execute an effect, or claim reduced workflow risk

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
The baseline test suite SHALL exercise Replay-default startup and each forbidden configuration path without real credentials or network access. It SHALL also exercise the dedicated live path through an injected fake transport to prove activation, redaction, structured-output, budget, timeout, restart, and no-authority behavior without presenting that test as real live verification. Results SHALL identify only denied capability or safe failure categories while redacting supplied values.

#### Scenario: CI runs provider safety checks
- **WHEN** CI executes provider-boundary tests with synthetic configuration and fake transport
- **THEN** it SHALL pass only if ordinary live-provider, external-write, multi-Agent, invalid destination, credential leak, self-approval, and budget-bypass attempts are denied before real network or side-effect contact

#### Scenario: Fake transport tests complete
- **WHEN** deterministic adapter tests return valid, malformed, timeout, and unknown outcomes
- **THEN** they SHALL verify the same parsing and evidence boundaries but SHALL retain `live_verified=false` and SHALL not create a canonical real-provider acceptance report
