## 1. Live Boundary Contracts

- [x] 1.1 Add closed JSON Schemas for `ModelActionProposal` and `ModelToolObservation`, plus valid/invalid fixtures proving no identity, arbitrary arguments, authority, raw provider body, or secret field is accepted.
- [x] 1.2 Add closed `ModelInvocationIntent` and `ModelInvocationObservation` schemas for source/profile/budget/usage/latency/cost hashes and safe provider outcomes.
- [x] 1.3 Add `ResponseDraftArtifact` and `LiveCandidateBinding` schemas that link invocation, context, normalized action, draft, evidence, and candidate without storing full draft/provider content.
- [x] 1.4 Add `ProviderPriceProfile`, `LiveRunMetrics`, `LiveEvaluationAttempt`, and `LiveEvaluationSuiteReport` schemas with explicit live/model/network and zero-business-write/customer-outcome flags.
- [x] 1.5 Implement matching Python and TypeScript contract/semantic validators and cross-record linkage checks for every new live schema.
- [x] 1.6 Extend the compatibility corpus and schema fingerprints; verify all retained valid/invalid v1 fixtures preserve their prior outcomes and live payloads cannot validate as offline benchmark records.

## 2. Synthetic Live Corpus and Configuration

- [x] 2.1 Create versioned, length-bounded synthetic context, CRM, monitoring, knowledge, prompt-injection, timeout, and budget sources with stable identities, classifications, and SHA-256 hashes.
- [x] 2.2 Create the `live-pilot.v1` manifest, six task definitions and oracles, fixed five-attempt declarations, prompt template, policy/budget profiles, and a dated provider price profile.
- [x] 2.3 Implement the live-suite loader with duplicate-key, path-containment, identity/tenant/hash, prompt/tool classification, task-count, attempt-count, oracle, and price-profile validation before credential access or store creation.
- [x] 2.4 Add command-scoped `LiveEvaluationConfig` parsing with explicit confirmation, positive budgets, fixed sampling/model profile, late environment-only credential loading, and safe public-HTTPS endpoint/redirect/address validation.
- [x] 2.5 Add configuration and source-loader security tests for missing gates, unsafe destinations, fixture/model-selected settings, stale/mismatched pricing, secret-like content, path escape, and pre-contact denial.

## 3. Invocation Evidence, Recovery, and Budgets

- [x] 3.1 Add append-only temporary-store persistence for evaluation sessions, attempts, logical turns, invocation intents/observations, draft artifacts/bindings, and their immutable uniqueness/foreign-key invariants.
- [x] 3.2 Implement stable session/attempt/turn/invocation identities and recovery that reuses conclusive observed turns but closes intent-without-observation as `provider_outcome_unknown` without a blind retry.
- [x] 3.3 Implement model-external call/action/tool/no-progress/token/time/cost reservation and accounting bound to the provider price profile, including pessimistic accounting for unknown outcomes.
- [x] 3.4 Add persistence, duplicate-record, restart-after-observation, restart-after-unknown, observed-retryable-error, timeout, and over-budget tests that prove exactly-once accounting and no workflow/effect success.

## 4. Provider Adapter and Single-Agent Runtime

- [x] 4.1 Add a provider-neutral turn interface and adapt deterministic Replay execution without changing its existing zero-network/model evidence.
- [x] 4.2 Implement one command-local OpenAI-compatible adapter with injected transport, structured-output request bounds, safe status mapping, token/latency capture, redirect denial, and no raw request/response logging.
- [x] 4.3 Implement proposal validation and normalization that derives authoritative `AgentAction` identity/scope from the Context Manifest and rejects unknown fields, arguments, states, approvals, delivery, writes, and completion claims.
- [x] 4.4 Extend the fixture Tool Gateway to return ephemeral schema-bounded `ModelToolObservation` values for authorized live attempts while persisting only the existing content-addressed safe tool evidence.
- [x] 4.5 Implement prompt compilation with versioned instructions, separately labeled untrusted synthetic data, bounded turn history, source hashes, and no credential/private/unrestricted tool content.
- [x] 4.6 Implement response-draft parsing, deterministic redaction/claim-evidence checks, ephemeral or expiring local artifact storage, `LiveCandidateBinding`, and candidate hash derivation.
- [x] 4.7 Implement the bounded live loop through the existing workflow/verifier so only code can reach `RESPONSE_READY`, and ensure the path never registers Change 4 activation, approval, delivery, knowledge publication, external writes, or multi-Agent behavior.
- [x] 4.8 Add fake-transport integration tests for allowed reads, grounded candidate, needs-information/operator, malformed/excessive output, prompt injection, foreign evidence, provider errors, no progress, timeout, budget exhaustion, and self-approval/external-action denial.

## 5. Live Evaluation, Grading, and Reporting

- [x] 5.1 Implement fresh-store preparation and six-task × five-attempt execution that reaches `TICKET_READY`, runs only the live investigation slice, and captures every declared safe terminal outcome.
- [x] 5.2 Implement deterministic hard-gate grading for authorization, tenant/source/profile integrity, prompt safety, closed actions, budgets, zero approval/delivery/business writes, evidence lineage, draft binding, and verifier ownership.
- [x] 5.3 Implement deterministic quality dimensions and the closed configuration/provider/model/Harness/tool/budget/evaluator failure taxonomy without an LLM judge.
- [x] 5.4 Materialize and semantically validate per-attempt live records and metrics, including proposal validity, calls, tools, tokens, estimated cost, provider/end-to-end latency, wall time, retries, no progress, outcome, and capability flags.
- [x] 5.5 Implement per-task and suite aggregation for success/hard-gate rates, P50/P95, sample variance, counts, limitations, and the grounded happy-path 4/5 acceptance threshold.
- [x] 5.6 Implement redacted report construction, safe diagnostics output, canonical hashing, and atomic accepted-report publication that preserves a prior accepted report on any failed gate or incomplete attempt.
- [x] 5.7 Add `python scripts/dev.py live-model-evaluation-acceptance` with explicit `--confirm-live`, output/diagnostics options, safe preflight, and capability reporting that cannot be invoked through normal service/API startup.

## 6. Security, Privacy, and Offline Regression

- [x] 6.1 Add secret-sentinel and raw-content tests across exceptions, logs, temporary SQLite, artifacts, diagnostics, and accepted reports; verify credentials and raw provider bodies never persist.
- [x] 6.2 Add artifact permission/expiry/cleanup tests for ephemeral default and explicitly retained redacted local diagnostics, including cleanup after a later run detects expired content.
- [x] 6.3 Add negative security tests for cross-tenant evidence, task/fixture-selected endpoints or budgets, prompt injection, stale/fabricated approval, duplicate/out-of-order inputs, unauthorized writes, redirects, and malformed provider metadata.
- [x] 6.4 Run the complete existing offline acceptance and aggregate test surfaces and verify Replay default, 12-task report, recovery, approval/delivery fixtures, evidence replay, evaluation console, and Operator Case timeline retain zero real network/model/external-write behavior.

## 7. Real Provider Acceptance Evidence

- [x] 7.1 Run the live preflight with operator-supplied public endpoint, model, environment-only credential, fixed sampling/budgets, and matching price profile; verify no secret/config value is echoed or written.
- [x] 7.2 Execute all 30 real provider attempts and verify complete attempt records, 100% hard-gate pass, zero approvals/deliveries/external business writes, and at least 4/5 grounded happy-path `RESPONSE_READY` outcomes.
- [x] 7.3 Review and retain `reports/add-bounded-live-model-evaluation-acceptance.json` plus a machine-readable verification record with token/cost/latency/variance/failure metrics and explicit synthetic/customer-outcome limitations.
- [x] 7.4 Re-run secret hygiene and report semantic validation after publication; confirm the canonical report is source-linked, redacted, content-addressed, and not reproducible from fake transport or Replay records.

## 8. Documentation and Final Validation

- [x] 8.1 Add a bounded live-model evaluation development guide covering setup, explicit authorization, provider profile/price assumptions, commands, retention/deletion, rollback, troubleshooting, metrics interpretation, and security boundaries.
- [x] 8.2 Update README capability/quick-start text and the OpenSpec roadmap to distinguish implemented offline behavior, real live-model measurements, synthetic tools, unverified customer outcomes, the remaining 60-task gate, and deferred multi-Agent/connectors.
- [x] 8.3 Run `python scripts/dev.py check`, `lint`, `typecheck`, `contracts`, and the full test suite; record exact versions, counts, durations, Docker status, skipped live/service-boundary checks, and any limitations without converting skips into passes.
- [x] 8.4 Run focused live-boundary/runner/security/recovery tests, the canonical live acceptance, retained offline acceptances, and strict `openspec validate add-bounded-live-model-evaluation --type change --strict`; complete tasks only when each associated check passes.
- [x] 8.5 Produce the final machine-readable change verification report and confirm `openspec status --change "add-bounded-live-model-evaluation"` shows every implementation task complete before requesting archive.
