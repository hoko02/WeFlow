# policy-capability-gates Specification

## Purpose
Define deterministic fixture-owned Capability Grants and default-deny policy authorization.
## Requirements
### Requirement: Fixture-owned Capability Grants are scoped, short-lived, and fail closed
Only deterministic fixture setup or the control kernel SHALL issue, revoke, or expire a
tenant-scoped Capability Grant. A grant SHALL bind one synthetic subject to allowlisted
`approval.request`, `approval.decide`, or `outbound_delivery.execute` action scope,
the named fixture resource scope, permitted data classifications, issuance/expiry, a
stable version, and a canonical hash. An API caller, Agent, replay transcript, or
request body SHALL NOT choose a tenant, role, scope, grant status, or grant hash.

#### Scenario: An active scoped grant authorizes policy evaluation
- **WHEN** the named API-503 fixture presents a current grant for the effective tenant,
  synthetic subject, action, resource, and data classification
- **THEN** the deterministic policy evaluator SHALL be able to consider the request
  without treating the grant itself as an approval or delivery authorization

#### Scenario: A missing, foreign, expired, or revoked grant is supplied
- **WHEN** a requested approval or delivery action has no matching current fixture-owned
  grant
- **THEN** the evaluator SHALL deny it with a redacted stable reason and append no
  approval, delivery intent, state transition, or effect

### Requirement: Policy decisions are deterministic, content-addressed, and default-deny
The Policy Engine SHALL evaluate a canonical input containing the effective tenant,
server-derived subject/role, requested action, fixture resource, data classification,
remaining budget, current Case/revision/workflow/checkpoint, candidate hash, ordered
evidence hashes, policy version, and Capability Grant hash. It SHALL persist one
append-only, content-addressed allow/deny `PolicyDecision` with a stable reason code;
an unspecified rule or malformed input SHALL deny.

#### Scenario: The named fixture satisfies the outbound policy
- **WHEN** all fixture-defined tenant, role, grant, resource, classification, budget,
  candidate, and evidence checks match
- **THEN** repeated evaluation SHALL produce the same allow decision identity and
  policy-decision hash without an effect

#### Scenario: Unsafe classification, budget, or instruction evidence reaches policy
- **WHEN** fixture input is classified as secret, raw/private, untrusted instruction,
  over-budget, or otherwise not allowlisted for the requested action
- **THEN** the Policy Engine SHALL produce a deny decision and SHALL not create an
  approval request, delivery intent, or customer-success claim

### Requirement: Authorization observations disclose only safe binding metadata
Policy and Capability facts SHALL expose only stable identifiers, versions, hashes,
allow/deny status, safe reason codes, and redacted classifications. They SHALL NOT
persist or expose raw candidate body, prompt, private fixture payload, credential,
unrestricted tool output, or an asserted role supplied by a caller.

#### Scenario: A denied policy decision is inspected
- **WHEN** a tenant-scoped observation or acceptance report includes a denied policy
  decision
- **THEN** it SHALL contain only safe metadata and SHALL not disclose protected content
  or foreign-tenant existence

### Requirement: Stage 2 capabilities SHALL be explicit, least-privilege, and command-scoped

The policy engine SHALL distinguish group reads, C2C reads, one minimal active C2C notification, passive C2C replies, handler approval decisions, and final passive group delivery. A grant for one capability MUST NOT imply another, and no capability SHALL enable a general-purpose C2C or group sender.

#### Scenario: Private read is granted without write

- **WHEN** policy grants `qq.c2c.read` but not a C2C write capability
- **THEN** the event may be classified but no notification or reply is executed

#### Scenario: Active notification scope is granted

- **WHEN** policy grants the exact Case-scoped notification capability
- **THEN** only the minimal Case reference and pull instruction may be attempted once for the bound C2C user

### Requirement: Every privileged action SHALL be gated by identity, state, version, and content policy

Before a notification, passive private reply, approval decision, or final group write, policy SHALL verify the paired tenant/group, active dual-surface binding, author surface, Case/revision, workflow version, content classification, retention state, capability profile, budget, and action-specific expiry.

#### Scenario: Group approval comes from the C2C handler's unlinked group identity

- **WHEN** the `WF-APPROVE` author does not resolve to the same dual-surface binding as the private candidate author
- **THEN** policy denies the decision and no external write is attempted

#### Scenario: Artifact has expired

- **WHEN** the customer issue or candidate artifact is expired or deleted
- **THEN** pull, preview, approval, and delivery fail closed

### Requirement: Notification ambiguity SHALL not authorize retries

Policy SHALL allow no more than one active C2C transport attempt for a notification natural key. An accepted, rejected, timed-out, disconnected, or unknown first attempt SHALL close the active-attempt budget.

#### Scenario: Operator repeats the command after a timeout

- **WHEN** a notification for the same Case and binding already has an ambiguous attempt
- **THEN** policy denies another active attempt and permits only the non-sensitive recovery path

### Requirement: Models and unrelated external writes SHALL remain disabled

No Stage 2 path SHALL invoke a model, QQ mail, attachment upload, business-system integration, arbitrary provider tool, or external write outside the declared QQ capabilities.

#### Scenario: Candidate generation is requested from a model

- **WHEN** any path attempts to invoke a model for drafting, approval, or completion
- **THEN** the capability gate rejects it and records a safe denial reason

### Requirement: Stage 3 SHALL require exact independent QQ and model capability profiles

The policy engine SHALL authorize Stage 3 only when the command presents the exact reviewed QQ capability profile and the exact reviewed model/read-only-tool capability profile for the same paired tenant, group, handler, Case, and process. A grant in either profile MUST NOT imply a grant in the other, and missing or additional capability MUST fail before credential loading or provider contact.

#### Scenario: Model read authority exists without final QQ authority

- **WHEN** the model profile permits a bounded investigation but the current QQ profile lacks handler approval or final passive reply authority
- **THEN** model assistance and any candidate cannot authorize a final QQ write

#### Scenario: QQ authority exists without model authority

- **WHEN** the archived Stage 2 profile is active without the exact Stage 3 model profile
- **THEN** the manual handler workflow remains available and every model invocation is denied

### Requirement: Handler-triggered model egress SHALL pass model-external policy

Before persisting an assist request or model invocation intent, policy SHALL verify explicit local live-model authorization, bound C2C handler identity, prior private pull/accept, paired tenant/group, Case/revision and expected version, issue source/classification/retention, model/prompt/provider/price profiles, tool resource scopes, and remaining per-request and cumulative Case budgets. The customer, model, provider, tool output, or caller-supplied field MUST NOT select or enlarge those values.

#### Scenario: Current bound handler requests an in-budget assist

- **WHEN** every server-owned identity, state, content, profile, scope, expiry, and budget input matches
- **THEN** policy records one content-addressed allow decision for that exact assist request without granting approval or QQ delivery

#### Scenario: Model egress input is stale or unsafe

- **WHEN** the handler, Case/version, issue artifact, provider/profile, tool scope, content classification, or budget is missing, foreign, stale, expired, over-limit, or malformed
- **THEN** policy records a safe denial and no credential is read, model intent is created, provider is contacted, or Case is advanced

### Requirement: Model, candidate, approval, and QQ delivery gates SHALL remain separate

The system SHALL evaluate model invocation, each synthetic read, candidate verification, approval decision, and final QQ delivery as distinct actions with distinct policy decisions and capability checks. Model/provider acceptance or candidate verification MUST NOT satisfy human identity/approval or QQ write policy, and QQ approval MUST NOT retroactively validate unsafe model/tool evidence.

#### Scenario: Model candidate is verified but not approved

- **WHEN** the deterministic verifier records a current `RESPONSE_READY` model candidate and no exact bound-handler group approval exists
- **THEN** final delivery policy denies with zero QQ delivery intent or transport attempt

#### Scenario: Approval references invalid model lineage

- **WHEN** the approval metadata resolves but the invocation, Context, evidence, candidate, policy, capability, budget, retention, or workflow binding is stale or invalid
- **THEN** approval/delivery is denied and the decision cannot authorize an external write
