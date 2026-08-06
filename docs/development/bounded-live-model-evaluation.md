# Bounded Live-Model Evaluation Development Guide

## 1. What this increment proves

`add-bounded-live-model-evaluation` adds one explicitly authorized, command-local
OpenAI-compatible provider path for a synthetic single-Agent investigation. It runs six
checked-in tasks five times each and measures proposal validity, tool use, tokens,
estimated cost, provider/end-to-end latency, variance, safe terminal outcomes, and hard
gates.

The path starts from a fresh synthetic Case at `TICKET_READY` and stops at either a safe
failure or verifier-authorized `RESPONSE_READY`. It does not activate fixture approval or
delivery and does not register real CRM, monitoring, knowledge, ticket, IM, WeCom, or
Tencent connectors. `RESPONSE_READY` means only that code verified a response candidate;
it does not mean approved, sent, received, resolved, or complete.

Replay remains the default for normal services and all existing offline commands. The
live provider is created only inside the dedicated acceptance command and is destroyed
when the command exits.

## 2. Locked provider and price assumptions

The checked-in pilot currently binds:

- provider protocol: `openai-compatible.v1`;
- public base URL default: `https://api.deepseek.com`;
- model: `deepseek-v4-flash`;
- inference mode: `disabled` thinking for the bounded one-action JSON protocol;
- sampling: temperature `0`, top-p `1`, non-streaming JSON output;
- price profile: `deepseek-v4-flash-2026-08-06`;
- estimated prices: USD 0.14 per million input tokens and USD 0.28 per million output
  tokens;
- price validity window: 2026-08-06 through, but not including, 2026-09-06.

The values are dated evaluation evidence, not a billing guarantee. Before a later run,
verify the provider's official pricing and model documentation. If they changed, create
and review a new price profile and its source bindings; do not silently edit a report or
reuse an expired profile.

## 3. Preflight and explicit authorization

Install the normal workspace dependencies first:

```powershell
uv sync --all-packages --all-groups
pnpm install --frozen-lockfile
python scripts/dev.py check
```

Without explicit confirmation, the command fails before DNS, credential loading, SQLite,
or provider contact:

```powershell
python scripts/dev.py live-model-evaluation-acceptance
```

For a real DeepSeek run, set the credential only in the current process environment. Do
not put it in `.env`, a command argument, a fixture, source control, or a report:

```powershell
$weflowSecureKey = Read-Host "DeepSeek API key" -AsSecureString
$weflowKeyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($weflowSecureKey)

try {
    $env:WEFLOW_LIVE_MODEL_API_KEY =
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($weflowKeyPtr)

    python scripts/dev.py live-model-evaluation-acceptance --confirm-live
}
finally {
    Remove-Item Env:WEFLOW_LIVE_MODEL_API_KEY -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($weflowKeyPtr)
}
```

The endpoint and model defaults are the pinned values above. Operator overrides are
accepted only when they pass public-HTTPS/DNS checks and the model exactly matches the
dated price profile:

```powershell
python scripts/dev.py live-model-evaluation-acceptance `
  --confirm-live `
  --endpoint https://api.deepseek.com `
  --model deepseek-v4-flash
```

Endpoint/model plaintext and the authorization header are not written to reports. Reports
retain only content hashes and the price-profile identity. Redirects are denied, and IP
literals plus non-global resolved addresses fail closed.

## 4. Outputs and acceptance semantics

A successful real run publishes, in this order:

1. `reports/add-bounded-live-model-evaluation-verification.json`, containing safe
   per-attempt records and metrics;
2. `reports/add-bounded-live-model-evaluation-acceptance.json`, the canonical accepted
   suite report.

The canonical report is replaced only after all 30 attempts are complete, every hard gate
passes, and at least four of five `grounded-response-ready` attempts reach the existing
deterministic verifier's `RESPONSE_READY`. A failed or incomplete run preserves any prior
accepted report and writes bounded diagnostics to
`reports/add-bounded-live-model-evaluation-diagnostics.json`.

Injected transports, Replay, skipped attempts, or fixture-assembled records cannot set
`live_verified=true` or replace the accepted report.

Interpret metrics as follows:

- `success_rate` means the terminal outcome matched that task's checked-in oracle; safe
  denial tasks can therefore succeed without `RESPONSE_READY`;
- `hard_gate_rate` covers authorization, source/tenant/profile integrity, prompt safety,
  closed actions, budget accounting, zero writes/approval/delivery, evidence lineage,
  draft binding, and verifier ownership;
- token cost is an estimate from observed usage and the dated profile, not an invoice;
- P50/P95 and sample variance describe only five attempts per task;
- `customer_outcome_unverified=true` is invariant.

This six-task pilot does not satisfy the planned 60-task M1 corpus gate and is not a claim
of production quality.

### Accepted pilot evidence (2026-08-06)

The retained real DeepSeek session completed 30/30 attempts with 330/330 hard
gates, five of five grounded happy-path `RESPONSE_READY` outcomes, zero approvals,
deliveries, or external business writes, 100,739 observed tokens, and estimated cost
USD 0.01502032. The canonical report hash is
`cba0b5450ded45a2bf1f3ec3af6ce5edc3a1253f3da083b93e98c9d976264dd9`.

The suite-level oracle success rate is 83.33%. The missing-information task matched
its expected safe outcome zero of five times: four attempts reached `response_ready`
and one was `policy_denied`. This is retained as a model-quality limitation; it does
not weaken the 100% hard-gate result or authorize an external effect.

## 5. Privacy and retention

Raw serialized requests, provider response bodies, credentials, authorization headers,
and model-readable tool summaries remain process-local. Durable SQLite/report evidence
contains allowlisted identities, hashes, status, usage, cost, latency, and failure codes.
The checked-in prompt template carries exact read, safe-stop, and response-candidate JSON examples. The DeepSeek request explicitly disables thinking so the 600-token per-call structured-output reservation is spent on the closed proposal rather than hidden reasoning.

Accepted response drafts pass deterministic secret/PII/authority-language and evidence
checks. By default, their local content is deleted after grading. The optional
`--retain-redacted-drafts` flag keeps only redacted drafts under the ignored
`.weflow/live-eval-artifacts/` root with an expiry; a later run deletes expired content.
Metadata and hashes may remain after content deletion.

After a real run, verify hygiene:

```powershell
python scripts/scan_secrets.py
python scripts/dev.py contracts
```

Never attach a raw provider response or temporary SQLite file to an issue or portfolio.
Use the accepted and verification reports.

## 6. Failure and recovery behavior

- `observed_retryable_error`: only an explicit rate-limit or provider-unavailable response
  may use the single configured retry, if all budgets still fit;
- `provider_outcome_unknown`: timeout, connection loss, or an intent without a conclusive
  observation stops the attempt and is never blindly retried;
- `malformed_model_output`: unknown fields, arguments, authority/state/approval/delivery
  claims, missing usage, or invalid JSON are rejected before an `AgentAction`;
- `policy_denied`: foreign evidence or unsafe draft content is rejected before a response
  candidate;
- `tool_timeout`, `budget_exhausted`, `needs_information`, and `needs_operator` are safe
  terminal outcomes and cannot claim workflow/effect success.

Stable session/attempt/turn/invocation identities and append-only intent/observation
records make duplicate evidence visible. Conclusive observed-and-normalized turns are
reused on recovery; an intent without observation is closed pessimistically as unknown.

## 7. Troubleshooting

- `explicit_confirmation_required`: add `--confirm-live` only after reviewing cost and
  egress.
- `credential_missing`: set `WEFLOW_LIVE_MODEL_API_KEY` in the current process.
- `model_price_profile_mismatch` or `live_price_profile_stale_or_mismatched`: verify
  official provider metadata and propose a reviewed dated profile update.
- endpoint/DNS denial: use a public HTTPS hostname without credentials, query, fragment,
  custom port, IP literal, private/link-local/loopback resolution, or redirects.
- `live_budget_exhausted`: no over-budget call was made; inspect the safe per-attempt
  metrics instead of increasing limits ad hoc.
- no canonical report after a run: inspect the bounded diagnostics; do not rename it to an
  accepted report.

## 8. Rollback

Rollback is disabling/removing the dedicated CLI registration and provider adapter. It
requires no migration of Replay contracts or existing offline records. Generated local
content can be removed from only these explicit locations after retaining any evidence
you intend to review:

```powershell
Remove-Item -LiteralPath .weflow/live-eval-artifacts -Recurse -Force
Remove-Item -LiteralPath reports/add-bounded-live-model-evaluation-diagnostics.json -Force
```

Do not delete the canonical accepted/verification reports unless the evidence is being
formally withdrawn and that change is documented.
