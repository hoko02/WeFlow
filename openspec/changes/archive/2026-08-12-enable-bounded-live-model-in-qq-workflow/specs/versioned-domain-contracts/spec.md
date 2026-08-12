## ADDED Requirements

### Requirement: Versioned contracts SHALL represent the integrated QQ model-assist lifecycle

The contract set SHALL define closed versioned schemas for Stage 3 readiness, the private `WF-ASSIST` envelope, assist request and outcome, model-safe QQ Context, Case/handler-bound invocation and budget evidence, model candidate provenance/binding, private preview metadata, invalidation/deletion evidence, and correlation/causation links through approval and final QQ delivery. Content-bearing fields SHALL remain restricted artifact references or ephemeral bounded views rather than plaintext in general domain records.

#### Scenario: An assist request contract validates

- **WHEN** a bound handler requests model assistance for a current Case
- **THEN** the schema requires safe handler/Case/revision/workflow/source identities, issue artifact reference, model/prompt/provider/profile hashes, exact capability/policy/budget bindings, and no raw QQ or content fields

#### Scenario: Model or caller supplies authority fields

- **WHEN** an input contains caller/model-selected tenant, destination, provider, tool arguments, workflow state, approval, delivery, resolution, or completion
- **THEN** contract validation fails before policy evaluation, model contact, or external write

### Requirement: Versioned reports SHALL separate integrated provider facts from business outcomes

The contract set SHALL define distinct offline-fake, real integrated acceptance, and independent verification schemas that bind report/source hashes, QQ and model provider modes, invocation/tool/candidate/approval/effect/deletion counts, usage/cost/latency availability, failure classifications, privacy flags, and capability constants. The schemas SHALL require customer receipt, issue resolution, Case completion, and production readiness to remain false for this change.

#### Scenario: Real integrated report validates

- **WHEN** actual QQ and public-model evidence plus exact handler approval and final provider acceptance are complete and source-linked
- **THEN** the schema represents each verified layer separately and retains no credential, raw identity, prompt, issue, draft, transcript, tool body, or unrestricted provider response

#### Scenario: Fake report claims live integration

- **WHEN** a fake/Replay provider report sets a live-provider fact, omits required lineage/metrics, or asserts a customer-success outcome
- **THEN** Python and TypeScript semantic validation reject it consistently
