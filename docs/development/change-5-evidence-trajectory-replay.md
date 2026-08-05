# Change 5 Evidence Trajectory and Replay Development Guide

`add-evidence-and-trajectory-replay` is a fixture-local, offline verification slice
over the retained API-503 investigation, policy, approval, and local-delivery facts.
It is synced into the main specifications and archived as
`2026-08-04-add-evidence-and-trajectory-replay`.

The 2026-08-05 reconciliation reran the offline acceptance command and the bounded
aggregate local suite successfully. Their redacted records are
`reports/change-5-evidence-trajectory-acceptance.json`,
`reports/change-4-5-reconciliation-verification.json`, and
`reports/change-5-reconciliation-manifest.json`. The current OpenSpec CLI cannot
strict-validate the archived directory because it no longer exposes a delta; that
truthful `failed` result is retained in `reports/change-5-openspec-validation.json`
with `archived_change_has_no_delta`. It is not a passing strict-validation claim.

## Supported contract

The only supported report profile is `fixture-local-evidence.v1` for the named
`api-503-policy-approval-delivery` fixture. Extraction reads retained immutable facts
and creates four append-only, content-addressed records:

```text
accepted Case + revision/events + workflow checkpoints
  + investigation/tool/evidence/candidate/verifier facts
  + policy/grant/binding + approval + local delivery facts
  -> EvidenceTrajectory(root SHA-256)
  -> redacted EvidenceReport + Artifact
  -> verification-only TrajectoryReplayResult
```

Each node has a fixed sequence, one predecessor link (except the root), a stable source
identity, classification, and canonical hash. An Artifact is bound to the same tenant,
Case, revision, workflow, trajectory, and report profile as its report. SQLite triggers
make evidence artifacts, trajectories, reports, and replay results append-only.

Extraction is idempotent for the same effective tenant/Case/revision/workflow/profile.
It never creates Case events, workflow checkpoints, policy decisions, grants, approval
facts, delivery intents, or delivery records. Missing, foreign, duplicate,
out-of-order, unlinked, malformed, or hash-invalid inputs return only the safe
`lineage_invalid` outcome and do not persist a complete trajectory.

## Outcomes and read boundary

Evidence Reports expose safe IDs, hashes, classifications, counts, a fixture identity,
and zero-capability flags only. Their supported outcomes mean:

| Outcome | Safe meaning |
| --- | --- |
| `fixture_delivery_recorded` | The named local adapter recorded one fixture-local delivery completion. It is not a send, receipt, resolution, or Case completion. |
| `authorization_denied` | The fixture's current authorization was denied, with no delivery intent or record. |
| `recovered_after_interruption` | A declared local lost-response path recovered without another local delivery identity. |
| `needs_reconciliation` | Retained local facts need reconciliation; no outcome is inferred. |
| `lineage_invalid` | The retained evidence could not be safely linked or verified. |

`GET /v1/cases/{case_id}/workflow/evidence` returns only an already persisted,
tenant-derived redacted report. It does not trigger extraction or replay. Foreign,
missing, and unpersisted paths are the same `404 workflow_not_found`; any query input
that tries to choose an authority, profile, node, or raw field is rejected with
`422 evidence_request_invalid`. There is no public replay, export, extraction, or
mutation route.

Verification replay accepts only a stored tenant-scoped trajectory identity internally.
It re-resolves the recorded source identities and canonical order, then compares roots.
It never starts agents, models, tools, policy/approval logic, workflow commands,
reconciliation, adapters, network clients, Docker services, or external executors.

## Offline verification

```powershell
python scripts/dev.py contracts
python scripts/dev.py evidence-trajectory-acceptance --output reports/change-5-evidence-trajectory-acceptance.json
uv run pytest tests/contracts/test_evidence_contracts.py tests/unit/test_evidence_trajectory.py tests/security/test_evidence_trajectory_security.py tests/integration/test_evidence_trajectory_api.py tests/e2e/test_evidence_trajectory_acceptance.py
python scripts/dev.py reconciliation-verification --output reports/change-4-5-reconciliation-verification.json
python scripts/dev.py archive-evidence-check
```

The acceptance command uses checked-in fixtures and temporary local SQLite only. It
runs two equal authorized baselines plus revoked-grant denial, lost-response recovery,
and tampered-lineage paths. It emits redacted machine-readable evidence and rejects
non-offline, raw-export, or provider configuration before initializing a store.

Node is required for the TypeScript contract check but not the core evidence acceptance.
The reconciliation observed Node `v22.21.1`; this environment fact is retained in the
manifest and is not a Node 24 verification claim. Docker is diagnostic-only and is not
required; Docker was unavailable on the verification workstation. No network, model key,
enterprise credential, or real provider is used.

## Explicit exclusions and next gate

This change does not enable real providers, credentials, network access, raw artifact
export, external delivery, customer receipt/resolution, knowledge publication, live
trace exporting, or multi-Agent execution. A future OpenSpec change must define the
retention, privacy, authorization, provider, reconciliation, rollout, and independent
audit controls needed before any non-fixture evidence export or external capability is
considered.
