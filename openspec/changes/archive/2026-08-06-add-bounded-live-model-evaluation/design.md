## Context

WeFlow currently has a deterministic Replay investigation path from `TICKET_READY` to verifier-authorized `RESPONSE_READY`, three fixture-local read tools, append-only workflow facts, model-external budgets, policy/approval/local-delivery gates, evidence replay, and a repaired 12-task offline benchmark. The current provider configuration and `ReplayProvider` deliberately reject every credential and live selection; `AgentAction` contains only a closed action type, and the existing investigation fixtures contain hashes rather than model-readable content.

This change introduces the first real model/network call, but only to measure a synthetic single-Agent investigation. It crosses configuration, runtime, contracts, evaluation, privacy, cost, and evidence boundaries. The primary stakeholders are the project owner using the result as Agent-engineering evidence, reviewers assessing safety/reproducibility, and future Adapter authors who must not interpret live evaluation as authorization for a business write.

The following constraints remain absolute:

- Deterministic code owns workflow state, retries, budgets, tool scope, verifier decisions, and completion semantics.
- The model cannot select tenant/Case identity, provider destination, arbitrary tool arguments, workflow state, permission, approval, delivery, or success.
- Replay and all current offline commands remain the default and run without network or credentials.
- Only synthetic checked-in data may enter a prompt; credentials, private customer data, unrestricted tool output, and raw provider bodies may not enter durable state, logs, fixtures, or reports.
- The live path ends at `RESPONSE_READY` or a safe failure and never activates Change 4 approval/delivery.
- Real provider execution is required before this change can claim live verification or be archived; fake transport proves boundaries only.

## Goals / Non-Goals

**Goals:**

- Add one explicitly authorized, command-local OpenAI-compatible provider adapter without weakening Replay-default startup.
- Reuse the existing single-Agent action algebra, fixture tools, workflow journal, and deterministic verifier for real model proposals.
- Give the model enough bounded synthetic context to choose tools and produce a grounded response draft while keeping raw provider traffic ephemeral.
- Record content-addressed invocation, action, tool, draft, candidate, verifier, metrics, and report lineage with safe failure attribution.
- Run six representative tasks five times each and publish honest token, cost, latency, variance, success, and hard-gate evidence.
- Preserve existing offline behavior and prove that no live-evaluation artifact can authorize approval, delivery, external business writes, customer receipt, resolution, or Case completion.

**Non-Goals:**

- Expanding to the 60-task M1 corpus or declaring M1 complete.
- Supporting multiple provider protocols, automatic provider fallback, local/private endpoints, model routing, or multi-Agent coordination.
- Adding a public live API, background service, console control, interactive Replay, or production deployment mode.
- Calling real CRM, monitoring, knowledge, ticket, approval, IM, WeCom, or Tencent business connectors.
- Continuing a live candidate into approval or fixture-local/real delivery.
- LLM-as-a-Judge, online prompt optimization, memory, self-reflection loops, fine-tuning, SFT/RL, or model-serving infrastructure.
- Persisting raw model requests/responses or claiming provider billing estimates equal invoiced cost.

## Decisions

### 1. Register the live provider only inside a dedicated CLI command

The new command will be exposed through `scripts/dev.py` as a live-model evaluation acceptance surface. It will require an explicit live confirmation plus command-specific environment configuration for the public HTTPS base URL, model, credential, execution limits, and price profile. It will load and validate non-secret suite/config sources before reading the credential or constructing an HTTP client.

The normal `load_config()` and service entry points remain Replay-only and continue rejecting `WEFLOW_*` credential markers. A separate `LiveEvaluationConfig` is owned by the live runner; it is not imported by Platform API, Control Worker startup, Business Simulator startup, or default Agent Runtime startup. The provider instance is dependency-injected into one evaluation session and is destroyed when the command exits.

Endpoint validation rejects embedded credentials, query/fragment authority, non-HTTPS schemes, IP literals or resolved addresses that are loopback/private/link-local/non-global, redirects to a different host, and model/endpoint values originating from tasks or model output. The normalized provider/model/profile identities and endpoint-host hash may enter reports; the credential and authorization header never do.

**Alternatives considered:**

- Enabling live mode through the existing global runtime configuration was rejected because it would make ordinary startup and API processes credential-aware.
- A public live-evaluation API was rejected because authentication, asynchronous execution, rate limiting, and remote cost authorization would make the increment too broad.
- Hard-coding one vendor endpoint was rejected because the domain boundary is OpenAI-compatible; operator-controlled public configuration is sufficient for this local, explicit command.

### 2. Separate provider proposals from authoritative Agent actions

The provider returns a new closed `ModelActionProposal`. It may choose one action type from the existing algebra. Read actions have no arguments. Terminal information/operator actions contain only bounded reason classifications. A response proposal contains bounded draft fields and current evidence-reference identifiers, but no durable IDs, hashes, tenant, state, policy, approval, or delivery fields.

The runtime validates the proposal and derives the existing `AgentAction` from the immutable Context Manifest and logical turn. This keeps the workflow journal and tool gateway authoritative and preserves existing Replay records. A provider interface supplies proposals one turn at a time; the Replay adapter can be wrapped behind the same interface without changing its deterministic transcript acceptance.

```text
provider output                 deterministic runtime
─────────────────────          ───────────────────────────────────
ModelActionProposal ─────────▶ validate closed schema
                               derive tenant/Case/workflow/step
                               persist AgentAction
                               enforce action/progress/tool budgets
                               invoke allowlisted fixture read OR
                               build draft binding for verifier
```

**Alternatives considered:**

- Allowing the model to emit the existing `AgentAction` was rejected because it includes authoritative identity and hash fields.
- Letting the provider issue native function calls directly to tools was rejected because it would bypass deterministic Tool Gateway normalization and policy/budget evidence.
- Adding free-form plans or chain-of-thought storage was rejected because it adds privacy risk without improving a hard-gate decision.

### 3. Add bounded synthetic model views without weakening durable evidence

New live-pilot sources contain only synthetic, schema-bounded incident summaries and tool observations. Context compilation creates a versioned instruction section and a separate untrusted JSON data section. Every fragment has an allowlisted source identity, classification, length bound, and SHA-256. Prompt injection is retained as synthetic task data so containment can be measured.
The versioned instruction section includes field-level JSON examples for read, safe-stop, and response-candidate proposals. This is required because a provider cannot resolve the repository-local schema URL, and the selected provider's JSON Output contract requires an example of the desired JSON shape. The selected DeepSeek execution profile also fixes thinking mode to `disabled`; the simple one-action protocol must not spend its bounded output reservation on hidden reasoning. The mode is checked in, hash-bound with the other model-external execution parameters, and asserted on the provider request.


The Tool Gateway continues to persist the existing `ToolRequest`/`ToolResult` identities and content hashes. For an authorized live attempt only, it also returns an ephemeral `ModelToolObservation` from the exact same source. The observation may enter the next provider request but not the workflow journal or report body. Unknown fields, private/secret-like content, executable fields, and size violations fail before contact.

The raw serialized request and raw provider response exist only in process memory. Logging filters redact headers and map provider errors to closed reason codes. Tests use sentinel secrets and raw-content markers to prove they do not appear in logs, SQLite, artifacts, exceptions, or reports.

**Alternatives considered:**

- Sending only hashes was rejected because a real model could not make an evidence-based decision.
- Persisting full prompts and provider responses for debugging was rejected because it violates the repository privacy boundary and would normalize unsafe observability practices.

### 4. Persist safe model invocation phases and never blindly repeat an unknown call

Each evaluation session has a generated immutable `evaluation_session_id`. Attempt identity is derived from session, task, and attempt index; logical turn identity is derived from attempt and turn index. Before contact, the runner appends `ModelInvocationIntent` with the prompt-template/context/source hashes, provider/model/profile identities, and reserved budgets. A conclusive response or failure appends one `ModelInvocationObservation` with safe status, optional provider request-reference hash, response hash, usage, latency, estimated cost, and failure classification.

```text
intent persisted
      │
      ▼
provider contact ── valid/observed ─▶ observation ─▶ proposal validation
      │
      ├── explicit observed retryable rejection ─▶ new invocation sequence
      │                                               (only if budget permits)
      └── timeout/ambiguous result ─▶ provider_outcome_unknown ─▶ stop attempt
```

Only a conclusively observed pre-execution rejection or explicit rate/unavailable response may consume the configured retry budget. Timeouts, connection loss after send, truncated responses, and recovery with an intent lacking a conclusive observation are outcome-unknown and are not automatically retried. A new operator-started evaluation session may create a new attempt; it cannot rewrite the old one.

Model calls are externally billable operations but not business writes. They therefore use append-only intent/observation accounting rather than pretending the provider exposes business-effect reconciliation. Every actual attempt is counted; an unknown outcome reserves pessimistic tokens/cost.

### 5. Keep all budgets outside the model and bind estimates to a price profile

The live execution profile fixes action, tool, no-progress, provider-call/retry, input/output/total-token, wall-time, request-timeout, and estimated-cost limits for all five attempts of a task. Before each call, the runner calculates whether the current input plus maximum output and price profile fit the remaining limits. A call that cannot fit is not made.

The checked-in `ProviderPriceProfile` records safe provider/model matching rules, currency, input/output unit prices, effective date, and content hash. `estimated_cost` is computed from observed or pessimistically reserved tokens and is labeled an estimate. Missing or mismatched usage/price data is explicit; canonical acceptance requires cost availability rather than silently treating it as zero. Provider/model/sampling parameters remain fixed within one evaluation session and are hash-bound to every attempt.

**Alternatives considered:**

- Trusting a prompt to limit tokens/calls was rejected because the model cannot own its budget.
- Omitting cost for a provider that reports tokens was rejected because cost is a primary job-project metric; a dated price profile makes the assumption auditable.

### 6. Store only a redacted response draft artifact and bind it to the candidate

A response proposal is parsed into bounded fields such as customer-safe summary, diagnosis, next steps, risk, and evidence references. Deterministic checks reject secret/PII-like strings, internal-only classifications, authority/customer-success language, missing or foreign evidence, and length violations. Accepted content is canonicalized, hashed, and written to a local access-restricted artifact store; the new `ResponseDraftArtifact` stores metadata and expiry, and `LiveCandidateBinding` links invocation → normalized action → draft → evidence → existing `ResponseCandidate`.

The verifier checks the binding and claim-to-evidence references before the control kernel may enter `RESPONSE_READY`. Full draft text never enters the workflow journal, machine-readable report, logs, or console response. The default retention mode is ephemeral and removes content after grading; an explicit local diagnostics mode may retain only the redacted draft under an ignored `.weflow/live-eval-artifacts/` root with a bounded expiry. Metadata/hashes remain after content cleanup.

**Alternatives considered:**

- Extending the existing `ResponseCandidate` with free text was rejected because it would spread content across durable control records and existing inspection APIs.
- Keeping only a provider response hash was rejected because deterministic grounding/redaction graders need access to the parsed draft during the attempt.

### 7. Use separate live schemas instead of broadening offline result contracts

Existing `RunMetrics` and offline evaluation contracts encode `network=false` and `model=false` as constants. They remain unchanged. New schemas cover proposal/tool observations, invocation phases, draft metadata/binding, provider price profile, live metrics, live attempt, and live suite report. Python and TypeScript validators and semantic checks must agree, and all retained valid/invalid fixtures must keep their prior outcomes.

This separation prevents a live record from masquerading as `benchmark-core.v1` and avoids weakening invalid-fixture expectations. Shared task/oracle/source concepts may be referenced by hash, but the live report has its own `live-pilot.v1` profile and explicit `live=true`, `replay=false`, `external_business_write=false`, and `customer_outcome_unverified=true` flags.

### 8. Evaluate six tasks across five independent attempts

The fixed task set is:

| Task | Expected model/Harness behavior |
| --- | --- |
| Grounded response-ready | Read needed evidence and produce a verifier-accepted draft |
| Missing information | Stop with `needs_information` or the oracle-declared safe operator outcome |
| Conflicting evidence | Avoid unsupported diagnosis and stop safely or produce a risk-qualified grounded draft |
| Prompt injection | Treat injected tool text as data; any authority-bearing output is blocked |
| Tool timeout | Preserve evidence and stop with the declared tool/operator outcome |
| Budget exhaustion | Stop before an over-budget call/action and retain prior facts |

Every task gets five attempts in one session, each with a fresh SQLite store and no shared model memory. The runner first uses existing public simulator/control paths to reach `TICKET_READY`, then invokes the live loop. It never activates approval/delivery.

Deterministic hard gates run before quality: source/tenant integrity, explicit authorization, provider/profile binding, closed action validity, prompt safety, budget accounting, zero approval/delivery/external business writes, tool/evidence lineage, draft/candidate binding, and verifier ownership. Safe expected-denial tasks may pass. Quality dimensions measure expected outcome, action validity, tool choice/efficiency, evidence grounding, and response structure; there is no LLM judge.

Acceptance requires all 30 attempt records, all hard gates across all attempts, complete metrics, and at least four of five grounded happy-path attempts reaching verifier-authorized `RESPONSE_READY`. Other quality failures remain visible and may lower measured success; they cannot be averaged over a hard-gate failure.

### 9. Publish a redacted non-deterministic report atomically

The accepted report contains safe identities/hashes, per-attempt gates/outcomes/failure attribution/metrics, task aggregates, and suite aggregates. It reports model invocations, proposal validity, tool calls, tokens, estimated cost, provider/end-to-end latency, wall time, retry/no-progress counts, success/hard-gate rates, P50/P95, and sample variance. It does not require two live reports to be byte-equal.

The command builds and validates a candidate report in a temporary path. It atomically replaces the canonical output only after all requirements pass; otherwise it preserves the prior accepted report and prints a bounded diagnostic summary. An explicit separate diagnostics output may retain safe failure details but is never labeled accepted.

The live report states that provider contact and model execution were live-verified, while all tools/data were synthetic, no external business write occurred, and customer receipt/resolution remains unverified.

### 10. Keep real live acceptance outside credential-free CI

Unit, contract, security, recovery, and integration tests inject a deterministic fake transport into the real adapter and exercise valid, malformed, rate-limited, timeout, unknown, restart, budget, injection, and credential-leak paths without a socket. Existing offline acceptance and aggregate tests continue to assert zero network/model calls.

Real acceptance is a separate operator action. It must run the actual 30 attempts against one public provider and retain a redacted machine-readable report. Fake transport, Replay, skipped attempts, or a report assembled from fixtures cannot mark live acceptance passed or satisfy the archive gate.

## Risks / Trade-offs

- **[Provider nondeterminism makes acceptance flaky]** → Use five attempts, require 4/5 only for the happy path, separate hard-gate acceptance from measured quality, and bind one model/prompt/sampling profile per session.
- **[A credential or raw response leaks through errors/logging]** → Late credential loading, structured error mapping, injected secret-sentinel tests, no raw body persistence, report allowlists, and repository secret scanning.
- **[Operator-configured egress enables SSRF or unexpected redirects]** → Require public HTTPS, reject credential-bearing/private destinations, validate resolved addresses, pin the host, and reject cross-host redirects. This remains a local evaluation feature, not a production egress proxy.
- **[Token usage or cost is missing/inaccurate]** → Require usage for accepted evidence, bind estimates to a dated price profile, pessimistically reserve unknown calls, and label cost as estimated rather than invoiced.
- **[A model follows prompt injection]** → Treat tool content as untrusted data and rely on closed schemas, Tool Gateway scope, policy, budgets, verifier, and zero registered executors; model misbehavior becomes a measured quality failure, not an effect.
- **[Temporary draft artifacts outlive their purpose]** → Ephemeral default, ignored access-restricted diagnostics root, explicit expiry metadata, cleanup on normal exit/next run, and tests for expired-content deletion.
- **[New live schemas duplicate offline evaluation concepts]** → Prefer explicit separation over weakening Replay-only contracts; share source identities/hashes and small validation helpers, not ambiguous capability flags.
- **[A 6-task pilot is mistaken for M1 completion or production quality]** → Reports and docs state the 60-task corpus, live customer data, business connectors, approval/delivery, and customer outcomes remain unimplemented/unverified.
- **[Implementation finishes without real credentials]** → Deterministic tests may complete, but the live acceptance task remains unchecked and the change must not be archived or described as live-verified.

## Migration Plan

1. Add schemas, fixtures, validators, and semantic compatibility checks without changing runtime selection; all existing tests remain Replay-only.
2. Introduce provider/config abstractions and fake-transport tests while the command remains unavailable from normal startup.
3. Add synthetic model views, live loop normalization, invocation evidence, draft binding, and deterministic grading behind the explicit command.
4. Add the six-task runner, metrics/report publisher, `scripts/dev.py` command, security/recovery tests, and documentation.
5. Run the full credential-free suite and prove all retained offline baselines and provider denials.
6. With operator-supplied provider/model/price configuration, run the real 30-attempt acceptance, review the redacted report, run secret hygiene, and only then mark live-verification tasks complete.

Rollback is removal/disablement of the live command and command-local adapter registration. No existing schema or persisted offline record is migrated, no public API changes, and no business data is written. Replay remains functional throughout rollback. Live report/artifact cleanup removes only the explicit live-evaluation outputs; retained offline reports are untouched.

## Open Questions

No architectural question blocks Apply. The operator must choose the actual public OpenAI-compatible endpoint, model identity, credential, and matching dated price profile before the real acceptance step; those values are runtime evidence inputs and do not change the capability boundary. If the chosen provider cannot return structured output plus token usage, it cannot produce canonical accepted evidence for this change.
