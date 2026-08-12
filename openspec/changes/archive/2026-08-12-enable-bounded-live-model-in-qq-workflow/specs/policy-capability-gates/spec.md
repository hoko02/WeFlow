## ADDED Requirements

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
