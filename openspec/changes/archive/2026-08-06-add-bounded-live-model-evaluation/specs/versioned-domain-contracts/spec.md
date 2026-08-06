## ADDED Requirements

### Requirement: Live model proposal and invocation contracts are versioned and payload-safe
WeFlow SHALL add language-neutral compatible contracts for `ModelActionProposal`, `ModelToolObservation`, `ModelInvocationIntent`, and `ModelInvocationObservation`. The contracts SHALL use stable schema identities/versions; bind safe tenant, suite/task/attempt, logical turn, Context Manifest, provider/model/profile, source, budget, usage, latency, cost, status, and hash fields where applicable; and forbid undeclared authority, arbitrary tool arguments, workflow target state, approval/delivery/external-write instructions, credentials, authorization headers, raw request/response bodies, private customer data, unrestricted errors, and customer-success claims.

#### Scenario: Valid live invocation metadata validates cross-language
- **WHEN** Python and TypeScript consume a complete safe proposal, tool observation, invocation intent, and invocation observation fixture
- **THEN** both SHALL accept the same identities, links, enumerations, counts, budgets, and hashes without needing a real credential or network call

#### Scenario: A model boundary contains raw or authority-bearing content
- **WHEN** a fixture includes a credential, raw provider body, arbitrary endpoint, caller/model-selected identity, tool arguments, state transition, approval, delivery, external write, or success assertion
- **THEN** both contract packages SHALL reject it with deterministic validation semantics

### Requirement: Live response-draft and candidate-binding contracts preserve verifier ownership
WeFlow SHALL add compatible `ResponseDraftArtifact` and `LiveCandidateBinding` contracts. The artifact contract SHALL carry only safe identity, tenant/Case/revision, content hash, media type, synthetic/redacted classification, producer invocation, bounded claim/evidence summary, creation/expiry, and retention mode. The binding SHALL link the exact Context Manifest, invocation observation, normalized Agent action, draft artifact/hash, ordered evidence hashes, derived response candidate/hash, and verifier-pending state. Neither contract SHALL contain permission, approval, delivery, customer outcome, or unrestricted draft/provider content.

#### Scenario: A valid live draft binding validates
- **WHEN** a safe draft artifact and binding reference one matching tenant, attempt, invocation, context, action, evidence set, and candidate
- **THEN** both language consumers SHALL accept the metadata chain while leaving verification and state transition to deterministic code

#### Scenario: A draft binding is detached or claims success
- **WHEN** a binding has a foreign/stale reference, changed content/evidence/candidate hash, missing predecessor, verifier outcome supplied by the model, or customer-success field
- **THEN** both contract packages SHALL reject it before candidate verification

### Requirement: Live evaluation contracts are separate from offline benchmark contracts
WeFlow SHALL add compatible `ProviderPriceProfile`, `LiveRunMetrics`, `LiveEvaluationAttempt`, and `LiveEvaluationSuiteReport` schemas for `live-pilot.v1`. They SHALL represent live/network/model capability flags, provider/model/prompt/profile hashes, attempts, gates, deterministic dimensions, closed failure attribution, token/call/tool counts, retry/no-progress counts, latency/wall-time distributions, estimated cost/currency, artifact/report hashes, retention state, and explicit zero external-business-write/customer-outcome claims. Existing `RunMetrics`, `EvaluationResult`, `EvaluationSuiteReport`, and `EvaluationSuiteSnapshot` offline schemas SHALL retain their Replay-only const semantics and SHALL NOT be broadened to accept live payloads.

#### Scenario: A complete live suite chain validates cross-language
- **WHEN** valid price-profile, attempt, metrics, candidate-binding, and live report fixtures are evaluated together
- **THEN** Python and TypeScript SHALL accept a complete hash-linked `live-pilot.v1` chain and preserve its measured non-deterministic values

#### Scenario: A live record is presented as an offline result
- **WHEN** a live/model/network payload uses an offline benchmark schema/profile or an offline fixture uses a live schema/profile
- **THEN** both validators SHALL reject the profile/capability mismatch

#### Scenario: Retained v1 fixtures are revalidated
- **WHEN** the additive live schemas and fixtures are introduced
- **THEN** every retained valid/invalid offline, Agent, workflow, approval, delivery, evidence, evaluation, and Operator Case fixture SHALL preserve its prior acceptance/rejection outcome
