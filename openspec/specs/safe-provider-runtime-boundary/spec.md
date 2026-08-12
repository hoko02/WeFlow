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

### Requirement: Provider-boundary tests prove the negative path
The baseline test suite SHALL exercise Replay-default startup and each forbidden configuration path without real credentials or network access. It SHALL also exercise the dedicated live path through an injected fake transport to prove activation, redaction, structured-output, budget, timeout, restart, and no-authority behavior without presenting that test as real live verification. Results SHALL identify only denied capability or safe failure categories while redacting supplied values.

#### Scenario: CI runs provider safety checks
- **WHEN** CI executes provider-boundary tests with synthetic configuration and fake transport
- **THEN** it SHALL pass only if ordinary live-provider, external-write, multi-Agent, invalid destination, credential leak, self-approval, and budget-bypass attempts are denied before real network or side-effect contact

#### Scenario: Fake transport tests complete
- **WHEN** deterministic adapter tests return valid, malformed, timeout, and unknown outcomes
- **THEN** they SHALL verify the same parsing and evidence boundaries but SHALL retain `live_verified=false` and SHALL not create a canonical real-provider acceptance report

### Requirement: Dedicated QQ pairing is a read-only command exception
The safe provider boundary SHALL permit one command-local QQ token/gateway/WebSocket
read client only after the secure first-group pairing activation gates pass. This
exception SHALL authorize only observation of one exact challenge-bearing
`GROUP_AT_MESSAGE_CREATE` and local bounded pairing persistence. It MUST NOT authorize
or construct a QQ sender, Case ledger intake, workflow, Agent/model, enterprise tool,
approval, outbound delivery, other provider, arbitrary destination/content, or
multi-Agent coordinator. Normal startup and every ordinary command SHALL retain their
existing Replay/offline or command-specific boundaries.

#### Scenario: Pairing is explicitly authorized
- **WHEN** the pairing command passes exact confirmation, sandbox credential-source,
  tenant, capability, deadline, and local-store gates
- **THEN** it MAY initialize only its bounded QQ read transports without changing any
  public runtime capability or existing default

#### Scenario: Pairing attempts a provider write or another runtime
- **WHEN** pairing configuration, event content, a caller, fixture, or runtime requests
  a QQ send, Case/workflow action, model/tool, approval/delivery, another provider,
  destination override, or expanded capability
- **THEN** deterministic validation SHALL deny it before executor/runtime construction
  and SHALL append no effect or success fact

### Requirement: Pairing observations cannot authorize a side effect
The system SHALL NOT interpret any pairing challenge, event, completion, locator,
report, QQ member role, or display value as a Capability Grant, Policy Decision, approval, intake
receipt, acknowledgement/delivery completion, Case transition, customer receipt, or
permission for an external effect. Only the later dedicated Stage 1 command MAY create
its existing Case and fixed-ack chain after independently resolving a current pairing
and passing all of its own gates.

#### Scenario: A pairing report is presented as Stage 1 authorization
- **WHEN** a caller or runtime presents a valid pairing completion/report as authority
  to create a Case, send a message, approve, deliver, or complete a workflow
- **THEN** the boundary SHALL reject the action and SHALL require the separate current
  command capability and durable Stage 1 evidence

### Requirement: QQ C2C runtime access SHALL be bounded to the paired handler workflow

The provider boundary SHALL expose only normalized C2C message reads for the bound handler, one minimal active notification operation, and passive replies to accepted C2C source events. It SHALL NOT expose unrestricted provider payloads, raw credentials, arbitrary recipients, arbitrary active messages, general chat history, or a reusable QQ sender to domain or model code.

#### Scenario: Domain requests an arbitrary C2C recipient

- **WHEN** the requested recipient is not the active binding's private provider locator
- **THEN** the provider boundary rejects the operation before network contact

#### Scenario: Notification includes private content

- **WHEN** an active notification contains the customer issue, draft, preview, or unrestricted text
- **THEN** the boundary rejects it and consumes no transport attempt

### Requirement: Group runtime access SHALL separate approval reads from final replies

The boundary SHALL normalize allowlisted group `@机器人` approval events and expose a passive final-reply operation bound to the accepted approval source. It SHALL NOT expose active group send fallback or allow group messages containing private issue, task, draft, or preview content.

#### Scenario: Final reply lacks approval source metadata

- **WHEN** execution does not include the exact valid approval source `msg_id` and stable `msg_seq`
- **THEN** the boundary rejects the write

#### Scenario: QQ omits the mention token from normalized approval content

- **WHEN** QQ emits `GROUP_AT_MESSAGE_CREATE` for the paired group and bound member while its
  normalized content begins directly with the exact `WF-APPROVE` metadata
- **THEN** the provider boundary treats the verified event type as mention proof and applies the
  same closed metadata parser, while identical text outside that provider event remains unable to
  authorize approval

### Requirement: Provider data SHALL be minimized before crossing the boundary

The boundary SHALL validate provider opcode/event kind, bot application, paired group or bound C2C user, mention/command shape, message identity, timestamp, and bounded content before producing a versioned domain envelope. Raw events, transcripts, credentials, and unrestricted provider responses SHALL not be persisted.

#### Scenario: Foreign group or C2C user sends a valid-looking command

- **WHEN** an event is outside the paired group or active private binding
- **THEN** it is rejected with a safe classification and no Case disclosure or external write

### Requirement: Provider failure classes SHALL remain explicit

The boundary SHALL distinguish accepted, rejected, rate-limited, expired-window, disconnected, timed-out, and unknown outcomes. It SHALL preserve the different recovery rules for active C2C notification and passive C2C/group replies.

#### Scenario: Active notification times out

- **WHEN** the provider outcome is unknown after the one active attempt
- **THEN** the boundary returns an ambiguous outcome that cannot be converted into success or retried by domain code

#### Scenario: Passive group reply is rejected as duplicate

- **WHEN** QQ identifies the same source `msg_id` and `msg_seq` as already processed
- **THEN** reconciliation uses existing content-free evidence and does not create a new active send
