# bounded-live-model-provider Specification

## Purpose
Define the explicitly authorized, command-local live model provider boundary, including safe prompts, durable invocation evidence, hard budgets, and zero business side-effect authority.

## Requirements

### Requirement: Live provider activation is command-scoped and explicit

The system SHALL register a live model provider only inside either the dedicated live-model evaluation command or the dedicated Stage 3 QQ model-workflow command after the operator supplies the command's exact explicit live confirmation, supported provider mode, model identifier, public HTTPS endpoint, positive call/token/time/cost budgets, hash-valid current price profile, and environment-only credential. The Stage 3 command SHALL additionally require the current paired sandbox group, active matching handler binding, private handler-triggered assist request, and exact independent QQ/model capability profiles. Normal service startup, public APIs, CI, Replay commands, fixtures, Stage 1, Stage 2, and model output SHALL NOT activate, configure, or select the live provider.

#### Scenario: An operator starts an authorized live evaluation

- **WHEN** the dedicated evaluation command receives every required operator-controlled gate and a valid synthetic suite
- **THEN** it SHALL register exactly one OpenAI-compatible provider for that command and expose only redacted provider/model/profile identities

#### Scenario: An operator starts an authorized QQ model workflow

- **WHEN** the dedicated Stage 3 command receives every local/provider gate and the bound handler creates one valid current assist request
- **THEN** it SHALL register exactly one command-local OpenAI-compatible provider for that bounded Case investigation without granting the model QQ authority

#### Scenario: A live gate or destination is invalid

- **WHEN** confirmation, credential, budget, price profile, model identity, endpoint validation, Stage 3 selector/binding/capability, or assist-request authorization is missing or the endpoint is non-HTTPS, credential-bearing, loopback, link-local, private, or otherwise non-public
- **THEN** the command SHALL fail before DNS/contact/model invocation and SHALL emit only a safe configuration reason code

### Requirement: Provider prompts and outputs are bounded and model-safe

The live adapter SHALL send only versioned system instructions and bounded validated context/tool views whose source identities and hashes were checked before the attempt. Evaluation prompts SHALL remain synthetic-only; Stage 3 prompts MAY additionally include one normalized redacted model-safe view of the current restricted QQ issue artifact after handler-triggered egress policy passes. Instructions and untrusted issue/fixture/tool data SHALL be separated. The versioned instructions SHALL include field-level JSON examples for every proposal class, and the selected provider profile SHALL fix and hash-bind any provider-specific inference mode required to keep structured generation inside the output budget. Provider output SHALL parse into a closed `ModelActionProposal`; unknown fields, arbitrary tool arguments, tenant/Case/QQ identifiers, workflow states, approval/delivery requests, credentials, or completion/customer-success claims SHALL be rejected before an `AgentAction` is recorded.

#### Scenario: A synthetic tool result contains prompt injection

- **WHEN** an allowlisted synthetic tool view contains text that asks the model to change authority, reveal a secret, approve, deliver, or ignore the action schema
- **THEN** the text SHALL remain classified as untrusted data and any non-schema or authority-bearing proposal SHALL be denied without a workflow transition or effect

#### Scenario: A QQ issue view contains untrusted instructions

- **WHEN** the redacted customer issue asks the model to select another tenant/provider/tool, reveal private data, approve, send, or ignore the closed protocol
- **THEN** it SHALL remain data-only and no instruction or model output may enlarge authority or bypass policy/verifier/human approval

#### Scenario: A provider returns malformed or excessive content

- **WHEN** a response is not valid structured output, exceeds configured size, contains undeclared fields, or cannot pass redaction and proposal validation
- **THEN** the attempt SHALL record a safe `malformed_model_output` classification and SHALL NOT persist the raw response or normalize an action

#### Scenario: A provider requires an explicit structured-output profile

- **WHEN** the selected checked-in provider/model profile requires a JSON shape example or explicit bounded inference mode
- **THEN** the runner SHALL send the hash-bound example and fixed mode on every invocation and SHALL reject an unrecognized mode before contact

### Requirement: Model invocations have append-only intent and observation evidence

Before each network call the runner SHALL persist one immutable `ModelInvocationIntent`. Evaluation intent SHALL retain its existing evaluation session/task/attempt binding; Stage 3 intent SHALL instead bind the paired tenant/group, Case/revision, active handler binding, assist request and expected workflow version. Every intent SHALL also bind logical turn, Context Manifest, prompt-template hash, validated input/evidence hashes, provider/model/price profile, policy/capability decisions, and reserved budgets. After contact the runner SHALL append at most one `ModelInvocationObservation` with a safe provider request-reference hash when available, status, response hash, token usage, latency, estimated cost, and failure classification. It SHALL never persist credentials, authorization headers, raw request/response bodies, QQ locators/events, issue/draft plaintext, or unrestricted provider errors.

#### Scenario: A model call completes

- **WHEN** the provider returns a schema-bounded response and usage metadata within budget
- **THEN** the runner SHALL append one linked observation, validate the proposal, and account the call, tokens, time, and estimated cost exactly once

#### Scenario: A model call times out or its result is unknown

- **WHEN** contact may have occurred but no valid response can be observed
- **THEN** the runner SHALL append `provider_outcome_unknown`, pessimistically account the reserved budget, stop the logical turn, and SHALL NOT blindly repeat it or represent it as complete

#### Scenario: The process restarts with an incomplete invocation

- **WHEN** recovery finds an invocation intent without a conclusive observation
- **THEN** it SHALL close the evaluation attempt or Stage 3 assist request with `provider_outcome_unknown`; only a new explicitly started evaluation attempt or fresh bound-handler assist request with a new identity MAY make another call

### Requirement: Model-external budgets bound every live attempt
The runner SHALL enforce provider-call, input-token, output-token, total-token, wall-time, tool-call, action, no-progress, and estimated-cost limits outside the model. It SHALL reserve worst-case output tokens and price-profile cost before contact, reject a call that cannot fit, and account provider-reported usage without allowing a model or provider response to enlarge a budget.

#### Scenario: A proposed call exceeds a remaining budget
- **WHEN** the next model invocation or tool action cannot fit within any remaining hard limit
- **THEN** the attempt SHALL stop with `budget_exhausted`, make no additional provider/tool call, and retain the prior append-only evidence

#### Scenario: Provider usage exceeds the reservation
- **WHEN** returned usage or cost metadata exceeds a declared reservation or conflicts with the provider profile
- **THEN** the attempt SHALL fail the budget-integrity hard gate, stop further calls, and report the discrepancy without accepting a candidate

### Requirement: Live model execution has no business side-effect authority
The live adapter and live evaluation runner SHALL NOT register or invoke ticket writes, approvals, outbound delivery, knowledge publication, external business executors, customer-data connectors, workflow commands, or multi-Agent coordination. A model proposal, provider acknowledgement, invocation observation, response draft, evaluation score, or report SHALL NOT grant permission or establish customer receipt, resolution, Case completion, or business success.

#### Scenario: A model proposes an external action or self-approval
- **WHEN** model output asks to approve, send, write, publish, change state, declare completion, or use a stale or fabricated approval
- **THEN** the runtime SHALL reject the proposal, record a named hard-gate failure, and produce zero approval, delivery, external-write intent, or completion records
