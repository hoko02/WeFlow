# WeFlow Agent Working Agreement

These instructions apply to the whole repository.

## Start every task with repository context

Before planning or editing:

1. Read `README.md` and `docs/PROJECT_MEMORY.md` completely.
2. Read the relevant architecture/development documents linked from `README.md`.
3. Run `openspec list --json`.
4. If a change is relevant, run `openspec status --change "<name>" --json` and use the concrete artifact paths returned by the CLI.
5. Tell the user which mode is active: Explore, Propose, Apply, Validate, or Archive.

## OpenSpec boundaries

- Explore is for investigation and documentation; do not implement application code.
- Propose one independently verifiable vertical increment at a time.
- Apply only from the selected change's resolved context files and tasks.
- If implementation invalidates the design, pause, explain the evidence, and update the artifacts before continuing.
- Mark a task complete only after its acceptance check passes.
- Run strict OpenSpec validation before archive.
- After archive, update `docs/PROJECT_MEMORY.md` with verified facts, limitations, metrics, and the next-stage gate.

## Project invariants

- Deterministic workflow code owns state, retries, SLA, side effects, approval, and completion.
- Models may propose actions but cannot grant permission, approve themselves, or declare success.
- Every external write uses intent/reconcile/execute/complete with a stable idempotency key and natural key.
- Tenant isolation, unauthorized external writes, duplicate side effects, stale approval, and evidence completeness are hard gates.
- Replay mode and synthetic fixtures must remain usable without network access or model credentials.
- Real external writes, real enterprise credentials, and multi-agent collaboration stay disabled until an explicit OpenSpec change enables them.
- Never put secrets, raw private customer data, or unrestricted tool output into prompts, logs, fixtures, or reports.

## Interaction style

- Lead updates with the current outcome or decision, then the supporting evidence.
- Surface assumptions, scope changes, risks, and unknowns early.
- Prefer a narrow working vertical slice over broad scaffolding without acceptance evidence.
- Distinguish clearly among implemented, simulated, tested, live-verified, and planned capabilities.
- Report the exact checks run and any checks that could not run.
- Keep the user in control of material product choices and any real external side effect.

## Engineering conventions to preserve

- Contract-first schemas shared across service boundaries.
- Immutable task/case revisions and append-only business events.
- Model-external capability, policy, budget, verifier, and approval gates.
- Content-addressed artifacts and end-to-end evidence lineage.
- Deterministic Replay Adapter, fault injection, negative security tests, and repeated-run baselines.
- Cross-platform development commands collected behind `scripts/dev.py` once implementation begins.
