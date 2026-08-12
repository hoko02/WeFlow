## ADDED Requirements

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
