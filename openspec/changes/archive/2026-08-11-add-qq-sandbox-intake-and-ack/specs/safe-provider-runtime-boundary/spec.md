## MODIFIED Requirements

### Requirement: Forbidden provider selections fail closed
The configuration validator SHALL reject a live model/provider selection, real
enterprise credential, external-write adapter, or multi-Agent coordinator unless an
archived OpenSpec capability and the current command-specific gates explicitly permit
that exact use. The bounded live-model evaluation command continues to permit only its
synthetic command-scoped model proposal. The dedicated QQ sandbox intake-and-ack
command MAY initialize only its QQ token/gateway/WebSocket transport and fixed passive
acknowledgement executor after exact operator-controlled application, group, tenant,
credential-source, environment, and capability checks pass. It SHALL NOT initialize a
model, enterprise business tool, approval provider, final-delivery executor, arbitrary
destination/content sender, or multi-Agent execution. A rejection MUST prevent
contact/readiness and MUST produce a redacted policy-denial result.

#### Scenario: A live provider is configured accidentally
- **WHEN** normal environment configuration requests a non-Replay provider, QQ adapter,
  real-write executor, or provider credential outside its dedicated gated command
- **THEN** validation SHALL deny startup, keep the affected runtime not-ready, and
  report a redacted provider-policy denial without contacting the provider

#### Scenario: A live fixture selects its own destination or provider
- **WHEN** a task, fixture, event, model response, or caller payload supplies an
  endpoint, credential, provider, application, group, message content, or expanded
  budget
- **THEN** validation SHALL reject the input before contact because only
  operator-controlled command configuration and code-owned acknowledgement content may
  select those values

#### Scenario: The dedicated QQ sandbox command is explicitly authorized
- **WHEN** the command passes the exact sandbox, confirmation, credential-source,
  allowlisted group-to-tenant, and bounded capability gates
- **THEN** it MAY initialize only the QQ intake transport and fixed acknowledgement
  executor without changing the Replay default or enabling any public runtime
  capability

#### Scenario: Multi-agent or other external business execution is requested
- **WHEN** configuration requests a multi-Agent coordinator, business connector,
  approval/final-delivery provider, arbitrary message sender, or another external-write
  executor
- **THEN** validation SHALL deny the request and SHALL NOT create subordinate Agents,
  contact the connector, execute an effect, or claim reduced workflow risk

### Requirement: No runtime component can authorize or complete a side effect
The Agent Runtime and Business Simulator SHALL NOT register a live/external-write
executor or treat replay content, QQ content, or a model-like response as a Capability
Grant, Policy Decision, approval, verifier result, acknowledgement/delivery completion,
or Case-completion declaration. Only the deterministic control kernel may evaluate
named Capability/Policy rules and create an effect intent. The existing named fixture
path MAY invoke only its fixture-local delivery adapter after its approval gates pass.
The dedicated QQ sandbox path MAY invoke only the fixed acknowledgement executor after
its operator activation, intake commit, capability, deadline, identity, and recovery
gates pass. Neither path grants the Agent Runtime authority, and neither completion is
a customer-success assertion.

#### Scenario: A replay fixture requests an external action
- **WHEN** a synthetic replay fixture contains a proposed ticket, reply, QQ action, or
  other external action
- **THEN** the runtime SHALL record it only as replay data or reject it by policy,
  SHALL NOT execute an external call, and SHALL NOT emit a successful completion result

#### Scenario: A self-approval-like input is supplied
- **WHEN** replay or QQ input presents a proposed action together with purported
  approval, capability, completion, or success not produced by the current
  deterministic gates and recovery records
- **THEN** the runtime SHALL reject it as unauthorized or stale and SHALL NOT grant
  permission, approve the action, or declare success

#### Scenario: The named control path reaches fixture-local delivery
- **WHEN** the deterministic control kernel has a current valid policy, Capability,
  approval, and authorization binding for the named fixture
- **THEN** it MAY record the fixture-local delivery chain while the Agent Runtime and
  Business Simulator do not grant authority or contact an external provider

#### Scenario: The QQ control path reaches its fixed acknowledgement
- **WHEN** one committed QQ Case has a current bounded command capability, exact source
  and destination binding, valid deadline, durable intent, and safe reconciliation
  result
- **THEN** the control kernel MAY invoke the QQ acknowledgement executor for that intent
  only, while the Agent Runtime remains unused and no completion declares customer
  receipt or Case resolution
