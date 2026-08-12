## Context

WeFlow has two separately live-verified boundaries that have never been composed:

- the QQ sandbox path can bind one group and handler, create one Case, send one fixed acknowledgement, keep handler work in C2C, record one metadata-only group approval, and deliver one approved passive group reply;
- the bounded DeepSeek-compatible path can run one closed single-Agent investigation over synthetic CRM, monitoring, and knowledge reads, record model usage/cost/latency and evidence lineage, and stop at deterministic verifier-authorized `RESPONSE_READY`.

Stage 3 connects those boundaries for one sandbox API-503 Case. It crosses two real network providers, restricted customer content, durable workflow versions, model budgets, human approval, and a real QQ write. The design therefore preserves separate QQ and model credentials/capabilities, makes model egress a private handler decision, and never lets provider or model output become workflow authority.

The stakeholders are the customer and bound handler in the controlled QQ group, the local operator authorizing credentials/cost, and reviewers who need an honest, reproducible Agent-engineering demonstration. Business evidence remains synthetic; the change is an integration and safety proof, not a production support system or a broad model-quality benchmark.

## Goals / Non-Goals

**Goals:**

- expose one dedicated command that composes Stage 1 intake/ack, Stage 2 private handler/approval/delivery, and the existing bounded live Agent;
- require a bound handler to explicitly request model assistance for one accepted current Case before any model contact;
- give the model only a redacted issue view and the existing tenant-scoped synthetic read tools;
- persist content-free invocation, action, tool, candidate, policy, approval, QQ-effect, deletion, and report lineage;
- allow a verifier-authorized model candidate to become the current private QQ candidate while preserving human replacement and exact approval;
- recover process interruption, duplicate events, stale versions, model uncertainty, and QQ uncertainty without duplicate logical effects;
- publish independently verifiable offline-fake and real QQ-plus-model reports with usage, cost, latency, failure attribution, and honest capability labels.

**Non-Goals:**

- real CRM, monitoring, knowledge, ticketing, approval, or other business-system connectors;
- automatic model invocation from the customer event, model-owned tool arguments, arbitrary browsing, shell access, memory, prompt self-modification, or multi-Agent collaboration;
- model approval, direct model-to-QQ delivery, active-send fallback, automatic resolution, customer receipt, Case completion, or production readiness;
- additional groups, tenants, handlers, reassignment, QQ mail, attachments, images, cards, arbitrary commands, knowledge publication, or production deployment;
- the 60-task corpus, a new provider family, provider routing/fallback, or a statistically meaningful production-quality claim.

## Decisions

### 1. Use one dedicated end-to-end Stage 3 command

The command surface will be `qq-sandbox-live-model-workflow`. It is the only process allowed to construct both the bounded QQ adapter and bounded public model adapter. It requires:

- `--confirm-live-qq` and `--confirm-live-model`;
- one current safe Stage 1 `qqpair_...` selector and one active matching `qqhbind_...` selector;
- the exact Stage 3 QQ capability set: group read, fixed passive acknowledgement, C2C read, one active C2C notification, passive C2C replies, handler approval, and final passive group reply;
- a separate exact model capability set: live proposal invocation plus fixture CRM, monitoring, and knowledge reads;
- a checked-in current model/prompt/budget/price profile and process-only QQ AppSecret, identity salt, and model API key.

Configuration, source hashes, selectors, capability equality, provider profile validity, public-HTTPS destination, and budgets are checked before either network client is constructed. Secrets are loaded only after non-secret preflight. Ordinary services, CI, Stage 1, Stage 2, Replay, and evaluation commands cannot inherit this combined authority and reject visible Stage 3-only configuration.

The command reuses the Stage 1 fixed acknowledgement so the complete demonstration begins with one customer-visible “已受理” reply. The acknowledgement, C2C notification/replies, model calls, approval, and final QQ reply remain separately gated and evidenced; a grant for one does not imply another.

**Alternatives considered:** Enabling the model inside the existing Stage 2 command was rejected because it would weaken the archived no-model Stage 2 contract. A background/public API was rejected because remote authentication, scheduling, and cost authorization are outside this sandbox increment.

### 2. Make model egress an explicit bound-handler command

The private protocol adds:

`WF-ASSIST <case_id> <expected_version>`

It is accepted only after the same bound C2C identity has privately pulled and accepted the current Case. The command must match the paired tenant/group, active handler binding, immutable Case revision, current handler-workflow version, unexpired issue artifact, current Stage 3 profile, and remaining per-Case budget.

The deterministic transition is:

```text
customer @robot
  -> Case + fixed ACK + handler notification
WF-PULL -> private issue view
WF-ACCEPT -> handler ownership
WF-ASSIST -> ASSIST_REQUESTED -> INVESTIGATING
  -> RESPONSE_READY(model candidate) | safe operator/manual state
  -> private preview + approval metadata
WF-DRAFT (optional human replacement)
  -> invalidates model candidate/request/decision
group WF-APPROVE
  -> exact approved passive group reply
```

The customer message, fixed acknowledgement, notification, pull, or accept never invokes the model. Duplicate `WF-ASSIST` delivery reuses the same logical request and reply. A fresh handler-authored `WF-ASSIST` at a later expected version may start a new request only when policy and the cumulative Case budget permit; no recovery path silently creates it.

**Alternatives considered:** Automatically invoking after intake or `WF-ACCEPT` was rejected because customer data and model cost would leave the process without a clear per-Case handler decision. A free-form private instruction was rejected because it would create an unbounded bot protocol.

### 3. Compile a model-safe QQ Context without exposing provider surfaces

The Context Compiler derives a versioned `QQModelAssistContext` from server-owned facts:

- safe tenant, Case, immutable revision, handler binding, workflow and assist-request identities/hashes;
- a normalized and deterministically redacted model view of the restricted `QQCustomerIssueArtifact`;
- the allowlisted API-503 synthetic investigation profile and source hashes;
- current tool, action, token, time, cost, no-progress, and retention budgets;
- prompt, policy, capability, provider/model, and price-profile identities/hashes.

The prompt contains no raw QQ App/group/member/user/message locator, provider event, mention token, nickname, role, transcript, handler command, approval command, credential, Authorization header, or unrestricted error/body. The issue view is bounded to the existing 1–1200 Unicode-scalar policy, must pass PII/secret/prohibited-content checks, and is labeled untrusted customer data. Live acceptance uses a controlled synthetic issue rather than real customer data.

Prompt instructions and untrusted issue/tool data remain structurally separated. Raw serialized requests and provider responses are process-local; only allowlisted hashes, classifications, usage, cost, latency, and reason codes become durable.

### 4. Reuse the closed single-Agent loop and synthetic read gateway

The model continues to produce only `ModelActionProposal`. Deterministic code derives the authoritative tenant/Case/turn/action and permits only `read_crm`, `read_monitoring`, `read_knowledge`, `needs_information`, `needs_operator`, or `response_candidate`. It never exposes provider-native function execution or model-selected tool arguments.

The tool gateway maps the paired sandbox tenant and current Case to one checked-in API-503 evidence profile. It returns the existing durable safe `ToolResult` plus an ephemeral, schema-bounded model observation from the same source. There is no real business-system network client or write operation. Source mutation, path escape, foreign tenant, missing evidence, prompt injection, arbitrary parameters, or secret-like content fail before the next model call.

Safe terminal outcomes leave the Case owned by the handler and return a bounded private explanation. The handler may continue with `WF-DRAFT`; model failure cannot block the manual Stage 2 path or authorize another model call.

### 5. Bind invocation recovery and cumulative budgets to the Case

Each assist request has a stable natural identity derived from tenant, Case/revision, handler binding, expected workflow version, and accepted C2C source event. Each logical model turn has one append-only `ModelInvocationIntent` and at most one conclusive `ModelInvocationObservation` linked to the assist request and Context hash.

Stage 3 uses a dedicated, checked-in `qq-stage3-case-budget.v1` profile with a cumulative estimated-cost hard limit of USD 0.50 per Case. The provider-call, retry, token, wall-time, tool, action, and no-progress limits remain fixed at 6 calls, 1 reviewed retry, 14,000 total tokens, 60 seconds, 3 tools, 6 actions, and 2 consecutive no-progress steps. The separate six-task live-evaluation profile remains USD 0.02 per evaluation attempt and is not enlarged by this Stage 3 operator decision.

Before contact, the runtime reserves worst-case calls, input/output/total tokens, wall time, tool/action/no-progress counts, and estimated price-profile cost against both the assist-request and cumulative Case budgets. Provider usage cannot enlarge a budget. Explicitly observed rate-limit/provider-unavailable responses may use only the reviewed retry allowance; timeout, disconnect, truncated response, or restart with intent but no conclusive observation becomes `provider_outcome_unknown` and is not blindly repeated.

Recovery reuses conclusive invocation/action/tool/candidate/verifier evidence. It never repeats a completed logical turn, never converts unknown into success, and never creates a QQ approval or write from partial model evidence. Model contact is billable but not a business write, so it uses intent/observation accounting rather than pretending the model provider offers business-effect reconciliation.

### 6. Normalize the verified model draft into the current private QQ candidate

A response proposal is deterministically normalized/redacted and stored only as the current restricted `QQHandlerResponseArtifact`. A content-free `QQModelCandidateBinding` links:

```text
assist request -> Context Manifest -> invocation/normalized action
-> ordered tool/evidence hashes -> redacted draft artifact
-> ResponseCandidate/verifier -> QQ candidate revision
```

The verifier checks source/tenant consistency, required/current evidence, claim grounding, issue/draft classification, budgets, model/prompt/profile binding, prohibited authority/success language, handler binding, Case revision, and workflow version. Only the control kernel may advance to `RESPONSE_READY` and create an approval request.

The candidate body and bounded evidence summary are returned only as a passive reply to the current bound-handler C2C event. `WF-DRAFT` remains valid and creates a human replacement. Replacement first invalidates the model candidate, its artifact reachability, approval request, and any decision, then creates the new current candidate. Superseded model content is deleted under the existing terminal/replacement/24-hour policy.

### 7. Preserve human approval and Stage 2 final-delivery authority

An approval request for a model candidate binds the initiating handler, active dual-surface binding, issue artifact, assist request, Context, invocation, provider/prompt/profile, ordered evidence, candidate artifact/hash, verifier, policy/capability versions, Case/revision, workflow version, and expiry. Its group-safe form remains only request ID, unambiguous candidate hash prefix, and expected version.

Only the bound group `member_openid` linked to the C2C handler that invoked `WF-ASSIST` may approve. The model, provider, robot, tool output, customer, or another member cannot approve. Immediately before final intent persistence, the control kernel revalidates every bound fact. The final write remains the Stage 2 passive reply to the approval source `msg_id` with stable `msg_seq` and idempotency key; unknown or expired outcomes never fall back to active send.

Provider acceptance remains distinct from customer receipt, resolution, Case completion, and production readiness.

### 8. Keep capability and policy authority split by provider and phase

The policy engine evaluates separate canonical actions for QQ intake/ack, private notification/reply, model invocation, each synthetic read, candidate verification, approval decision, and final QQ delivery. Stage 3 requires exact equality of both the QQ and model capability profiles; extra capabilities fail before contact.

Every model action checks the paired tenant/group, active handler binding, accepted Case/revision, workflow version, issue retention/classification, assist-request author/source, provider/prompt/profile, tool resource, and remaining budgets. Every QQ approval/write independently rechecks the Stage 2 identity, content, version, expiry, and idempotency gates. A model allow decision never authorizes a QQ operation, and QQ authority never selects a model/tool.

The archived Stage 2 command continues to reject model configuration and invocation. General external-write, multi-Agent, QQ mail/attachment, arbitrary provider, and business-connector switches remain forbidden.

### 9. Add closed integrated contracts without weakening old reports

New or additive v1 contracts cover the Stage 3 readiness profile, `WF-ASSIST` envelope, assist request/outcome, QQ model-safe Context, Case-bound invocation/budget evidence, model candidate binding/provenance, private preview metadata, integrated acceptance report, and independent verification result. Python and TypeScript validators reject unknown fields and require safe IDs, hashes, classifications, counts, metrics, and honest capability constants.

Existing Stage 1, Stage 2, Replay, and six-task live-evaluation reports remain unchanged. A fake QQ/model run cannot set either provider live-verification flag. An integrated report cannot masquerade as the 30-attempt model-quality pilot or weaken its known missing-information limitation.

The canonical real workflow report mode is `qq-model-integrated-live`; `qq-sandbox-live` remains only the nested QQ provider mode. If the QQ final effect is already provider-accepted but report publication is interrupted, an explicit completed-Case recovery path MAY rebuild and independently verify the two content-free artifacts from the current bounded store and selectors. Recovery SHALL read no provider credential, contact no network, mutate no Case, and repeat no model or QQ effect.

### 10. Layer offline, live-provider, and business outcome evidence

Credential-free acceptance uses fake QQ and fake model transports through the real boundaries. It covers the complete happy path plus duplicate/out-of-order events, restart at every invocation/action/tool/candidate/approval/final-write boundary, stale versions, foreign handler/group, prompt injection, tool timeout, budget exhaustion, malformed output, provider unknown, candidate replacement, stale approval, expired passive window, and secret/privacy sentinels. It performs zero real network or external writes.

Real acceptance requires one new controlled QQ sandbox Case, the active handler, an exact private `WF-ASSIST`, at least one real public-model invocation, complete synthetic tool/evidence lineage, one deterministic verified model candidate, exact human group approval, artifact deletion evidence, and one final provider-accepted passive group reply. It records actual calls/tokens/estimated cost/provider and end-to-end latency but makes no statistical model-quality claim from one Case.

The report distinguishes:

- QQ intake/ack and handler binding verified;
- live model contacted and invocation observed;
- model candidate verifier-authorized;
- private handler preview and optional replacement behavior verified;
- human group approval verified;
- final QQ provider accepted;
- customer receipt, issue resolution, Case completion, and production readiness, which remain false.

Reports contain no credentials, raw identities/locators, raw issue/draft/prompt/provider body, transcript, unrestricted tool output, or approval body. An independent verifier revalidates schemas, canonical hash, source/event counts, lineage, capability constants, deletion evidence, budgets, and outcome separation without QQ/model credentials or network.

### 11. Make observability content-free and failure ownership explicit

Append-only events and report records use stable correlation/causation links from QQ source to Case, handler command, assist request, model intent/observation, action/tool, candidate/verifier, approval, final intent/result, and deletion. They store safe identities/hashes, phase, metrics, and closed reason codes only.

Failure attribution distinguishes configuration/selector, QQ transport, model transport, model output/quality, tool/fixture, Harness/policy/verifier, handler/version/approval, budget, retention/privacy, and report/evaluator integrity. No failure message includes raw provider content. Model failure returns control to the handler; QQ write ambiguity enters existing reconciliation/operator handling; neither is converted to customer success.

## Risks / Trade-offs

- **[Two real providers widen the secret and failure surface]** -> Separate credentials, late construction, exact capability profiles, isolated adapters, no cross-provider raw payload, content-free logs, sentinel tests, and independent report verification.
- **[A customer issue sent to a public model may contain private data]** -> Require handler-triggered egress, deterministic redaction/classification, bounded model-safe issue view, synthetic live acceptance, process-local prompt bodies, and deletion evidence. Production/customer-data use remains prohibited.
- **[A model invocation may be billed with an unknown outcome]** -> Persist intent first, reserve pessimistic budget, never auto-retry unknown calls, expose the uncertainty privately, and preserve manual drafting.
- **[One real Case may be mistaken for model-quality proof]** -> Treat the acceptance as integration/hard-gate evidence only, retain the separate 30-attempt pilot metrics and known limitation, and label production quality unverified.
- **[Synthetic business evidence limits realism]** -> Make every report state that CRM/monitoring/knowledge are fixture-local. Real connectors require separate adapter changes with their own privacy and authorization review.
- **[Model-generated text could bypass human intent]** -> Make `WF-ASSIST` handler-authored, preview only in C2C, bind approval to the initiating handler and full lineage, keep `WF-DRAFT` replacement, and require fresh group approval.
- **[Composing Stage 1 and 2 could duplicate QQ effects]** -> Reuse their stable natural/idempotency keys and append-only recovery records; the Stage 3 orchestrator adds no alternative sender or fallback.
- **[The dated model/price profile may expire before live acceptance]** -> Fail preflight when stale; verify official provider metadata and review a new checked-in profile rather than silently changing evidence.
- **[Handler binding remains operator-confirmed across QQ surfaces]** -> Preserve `operator_confirmed_dual_challenge` and `production_ready=false`; Stage 3 does not strengthen identity assurance.

## Migration Plan

1. Add closed contracts and compatibility fixtures while every existing command remains disabled for Stage 3.
2. Add the integrated local workflow journal/projection, Context Compiler, policy profile, and fake model/QQ acceptance before constructing real clients.
3. Extend the closed C2C parser with `WF-ASSIST`, add model-candidate normalization, replacement invalidation, private preview, and recovery paths behind the dedicated command.
4. Compose existing Stage 1/2 QQ effects and the command-local live Agent, then run contract, unit, security, recovery, retained offline, and fake end-to-end acceptance.
5. Publish the Stage 3 runbook and readiness-only command. Verify the current provider/model/price profile and perform one operator-controlled real QQ-plus-model acceptance.
6. Run independent verification, secret scanning, strict OpenSpec validation, and retain only redacted machine-readable evidence before marking live tasks complete.

Rollback stops/removes the dedicated Stage 3 command and its exact capabilities, clears process-only secrets, expires restricted model/issue/candidate content, and leaves the append-only safe evidence for reconciliation. Stage 1 and manual Stage 2 commands remain independently usable. Rollback never deletes the QQ journal to hide an unknown final write and never rewrites model invocation or approval history.

## Open Questions

None block Apply. The live operator must provide a currently valid reviewed public provider/model/price profile and process-only credentials; a stale profile keeps the real acceptance task incomplete. Real business-tool adapters, production cross-surface QQ identity, and broader tenant/group rollout remain separate future product decisions.
