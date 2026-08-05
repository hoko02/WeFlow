## Why

WeFlow already retains the deterministic API-503 Case, workflow, investigation,
policy, approval, local-delivery, evidence, and evaluation facts that demonstrate its
reliability boundaries, but the local console cannot present those facts as one causal
Case story. The next increment should make the existing proof inspectable in a short
offline demo before expanding the corpus or enabling any live provider.

## What Changes

- Add one closed, content-addressed `OperatorCaseSnapshot` derived from a real execution
  of the existing allowlisted API-503 fixture through public deterministic boundaries,
  with ordered source-linked timeline entries and bounded summaries for Case revisions,
  workflow checkpoints, Agent/tool activity, verifier outcome, policy, approval,
  fixture-local delivery, Evidence lineage, and replay verification.
- Add one fixed, tenant-derived, read-only Platform API boundary for the canonical
  operator Case. It exposes no arbitrary Case/report/path selector and cannot run a
  workflow, decide approval, retry an effect, or mutate retained state.
- Add a Vue Case workspace that renders the validated snapshot as an end-to-end state
  timeline and selected evidence detail while distinguishing fixture-local facts from
  live provider sends, customer receipt, incident resolution, and Case completion.
- Add deterministic offline acceptance that generates the canonical evidence from a
  temporary SQLite store, validates two equal snapshots and all source links, exercises
  integrity and tenant-isolation failures, builds the console, and records zero network,
  model, external-write, duplicate-effect, or retained-runtime mutation counts.
- Add a development guide and update project memory with exact evidence, limitations,
  and the next gate only after acceptance passes.

### Non-goals

- No live model, real provider, enterprise credential, customer data, network call,
  external write, customer receipt/resolution, or multi-Agent coordination.
- No arbitrary Case listing/search, multi-tenant administration, editable raw JSON,
  approval button, workflow command, Replay control, or fault-injection control in the
  browser.
- No 60-task corpus expansion, live-run variance/cost/latency claim, PostgreSQL or
  Temporal migration, knowledge publication, or general business-workflow completion
  claim.

## Capabilities

### New Capabilities

- `offline-operator-case-timeline`: Covers generation, validation, tenant-scoped
  read-only delivery, truthful console presentation, and offline acceptance of one
  canonical API-503 Operator Case snapshot.

### Modified Capabilities

- `versioned-domain-contracts`: Add the compatible closed v1 `OperatorCaseSnapshot`
  contract and cross-language source-link, ordering, hashing, authority, and safety
  invariants.

## Impact

- **Contracts and fixtures:** one additive v1 JSON Schema, Python/TypeScript exports,
  semantic validators, valid/invalid fixtures, and a recorded compatible fingerprint.
- **Control and evidence boundaries:** a snapshot builder over existing deterministic
  ledger/workflow evidence plus a canonical redacted report produced only by explicit
  acceptance; existing state ownership and effect execution remain unchanged.
- **Platform API:** one fixed loopback read route with actor-derived tenant isolation,
  safe unavailable classifications, and no mutation method.
- **Web Console:** one validated Case timeline/read model integrated beside current
  readiness and evaluation evidence without unrestricted response rendering.
- **Security and privacy:** closed fields, safe repository-relative references, hashes
  and reason codes only; foreign/missing non-disclosure, tamper rejection, and explicit
  fixture-only capability labels.
- **Tests and documentation:** cross-language contracts, builder/API/security/render
  tests, offline acceptance and production build, a machine-readable report,
  development guide, README entry, and verified project-memory update.
- **Dependencies and compatibility:** reuse the current Python/FastAPI/SQLite and
  TypeScript/Vue workspaces; no new provider, browser-test framework, service, or
  network dependency is introduced.
