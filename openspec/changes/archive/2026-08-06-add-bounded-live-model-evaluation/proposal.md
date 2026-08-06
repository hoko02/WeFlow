## Why

WeFlow can prove deterministic Replay behavior, recovery, policy gates, evidence integrity, and a 12-task offline baseline, but it still invokes no model and therefore cannot measure whether a real Agent selects tools, grounds a response, or stays reliable across repeated runs. A narrow, opt-in live-model pilot is the next independently verifiable increment because it closes the largest Agent-job evidence gap without enabling customer data, enterprise connectors, approvals, delivery, or any real business write.

## What Changes

- Add one command-scoped, explicitly confirmed OpenAI-compatible live provider path for synthetic evaluation only. Normal service startup, CI, and all existing commands remain Replay-only and credential-free by default.
- Run one live single-Agent loop through the existing deterministic workflow, model-external budgets, closed action algebra, fixture-local CRM/monitoring/knowledge reads, and deterministic response verifier. The live path stops at `RESPONSE_READY` or a safe terminal outcome.
- Add bounded model-safe synthetic context/tool observations and a redacted, content-addressed response-draft artifact. Raw provider requests/responses, credentials, unrestricted tool output, and customer data are never written to durable state or reports.
- Add append-only, hash-linked model invocation intent/observation records with call, token, latency, estimated-cost, timeout, malformed-output, and provider-outcome-unknown classifications. Unknown provider outcomes are never treated as successful or blindly retried.
- Add a `live-pilot.v1` suite with six synthetic API-503 investigation tasks covering a grounded happy path, missing information, conflicting evidence, prompt injection, tool timeout, and budget exhaustion. Each task runs five independent attempts when live acceptance is explicitly authorized.
- Emit a redacted machine-readable live report containing all 30 attempt outcomes, hard-gate results, tool/action validity, grounding, token/cost/latency distributions, variance, and model/Harness/tool/provider failure attribution. Live results are non-deterministic measurements, not customer-success claims.
- Preserve the existing 12-task `offline-seed.v1` report, Replay provider, no-credential test path, and all retained recovery/security baselines unchanged.
- Explicit non-goals: the 60-task M1 corpus, LLM-as-a-Judge, prompt self-modification, real customer data, real WeCom/Tencent or ticket adapters, approval or delivery execution, external business writes, public live APIs, live console controls, model training/fine-tuning, and multi-Agent collaboration.

## Capabilities

### New Capabilities

- `bounded-live-model-provider`: Explicit live-evaluation activation, egress and credential boundaries, model-safe invocation records, bounded retry/cost behavior, and fail-closed provider handling.
- `live-model-evaluation-pilot`: Six-task/five-attempt synthetic live suite, hard gates, deterministic graders, repeated-run metrics, redacted reports, and live acceptance semantics.

### Modified Capabilities

- `safe-provider-runtime-boundary`: Permit only the new command-scoped live-evaluation path while preserving Replay-only default startup and denial for every other live-provider request.
- `bounded-investigation-agent-loop`: Allow a single live provider to propose the same closed actions under deterministic state, progress, and budget ownership.
- `fixture-investigation-tool-gateway`: Expose only bounded synthetic model views during an authorized live attempt while retaining content-addressed, payload-safe durable tool evidence.
- `response-candidate-verification`: Verify a redacted live response-draft artifact and its claim-to-evidence bindings before `RESPONSE_READY`.
- `versioned-domain-contracts`: Add compatible contracts for model proposals, invocation evidence, response-draft artifacts, live run metrics, attempts, and suite reports without weakening retained offline contracts.

## Impact

- **Contracts/data:** additive language-neutral schemas and Python/TypeScript validators; new synthetic live-pilot fixtures, provider price/config metadata, temporary per-attempt SQLite state, and redacted report artifacts.
- **Runtime:** a provider-neutral single-Agent interface in `apps/agent-runtime`, one OpenAI-compatible adapter registered only by the live-evaluation command, and unchanged deterministic Workflow/Tool Gateway/Verifier ownership.
- **Evaluation/tooling:** a live runner and deterministic graders in `weflow-testkit`, one explicit `scripts/dev.py` command, focused contract/security/recovery/integration tests, and an opt-in acceptance path excluded from credential-free CI.
- **Security/privacy:** explicit operator confirmation, HTTPS destination validation, environment-only credential loading, bounded synthetic prompts, prompt-injection separation, token/call/cost/time budgets, no external-write executor, redaction before persistence, and safe failure classifications.
- **Documentation/evidence:** a live-evaluation development guide and machine-readable verification record that clearly separates Replay results, live model measurements, fixture-local effects, and unimplemented customer outcomes.
