# Change 0 Foundation Development Guide

This document records the runnable boundary for `establish-weflow-foundation`. It is an engineering baseline, not evidence that the API-503 customer-resolution workflow exists or works.

## Supported modes

| Mode | Purpose | External requirement | Current scope |
| --- | --- | --- | --- |
| `offline` (default) | local development, replay, CI baseline | no Docker, network, model, or enterprise credentials | five skeletons, contracts, replay, fault fixtures, health reports |
| `service-boundary` (explicit) | local dependency-boundary checks | local Docker Compose only | PostgreSQL, Temporal, MinIO, and OTel dependency probes; no business workflow |

Both modes use `provider.mode=replay`. Live providers, enterprise credentials, external-write adapters, and multi-agent coordination are denied by configuration; an environment variable cannot enable them.

## Prerequisites and commands

`scripts/dev.py` is the cross-platform command entry point. The workstation needs `uv`, Node.js, pnpm, and Git. Docker is optional and needed only for service-boundary mode.

```powershell
uv sync --all-packages --all-groups
pnpm install --frozen-lockfile

python scripts/dev.py check
python scripts/dev.py lint
python scripts/dev.py contracts
python scripts/dev.py test

python scripts/dev.py up --mode offline
python scripts/dev.py health
python scripts/dev.py down
```

`health` always emits JSON and exits with `2` when the skeletons are not operationally ready. It is operational evidence only, never business-success evidence.

```powershell
# Only when Docker is available.
python scripts/dev.py compose up
python scripts/dev.py up --mode service-boundary
python scripts/dev.py health
python scripts/dev.py down
python scripts/dev.py compose down
```

When Docker is absent, `python scripts/dev.py compose status` returns `docker_unavailable` and exit code `2`. That is an explicit skip; offline mode remains the required baseline.

## Verified Change 0 boundaries

- `contracts/jsonschema/v1/` is canonical. Python and TypeScript validate the same valid and invalid fixture corpus.
- Platform API exposes only `/health/live`, `/health/ready`, and `/foundation/capabilities`. Its OpenAPI document references the canonical health schema.
- The five skeletons bind to `127.0.0.1`. The Web Console renders only allowlisted service, mode, readiness, and policy-denial diagnostics.
- Replay does not initialize a model client or external tool client. Proposed ticket/reply data and claimed capability, policy, approval, verifier, completion, or success data cannot grant authority.
- No external-write executor is registered. Results keep `external_write_executed=false` and `case_completion_declared=false`.
- Synthetic local artifacts are SHA-256 content-addressed. Returned metadata does not include raw payloads or local filesystem paths.

## Fixtures, faults, and telemetry

All repository fixtures are synthetic. They contain no real customer, enterprise IM, CRM, ticketing, model, or credential material.

```python
from weflow_agent_runtime import run_replay
from weflow_business_simulator import load_replay_fixture

fixture = load_replay_fixture("foundation-happy-path")
result = run_replay(fixture)
```

Named fault profiles are `invalid-configuration`, `dependency-unavailable`, `restart`, `duplicate-delivery`, and `out-of-order-delivery`. Fault metadata records only the profile, deterministic flag, no-model-invocation flag, and no-external-side-effects flag.

Structured telemetry follows local OpenTelemetry resource conventions: `service.name`, `service.version`, `deployment.environment.name`, and `weflow.correlation_id`. Failure evidence keeps component and reason code while redacting secrets, connection strings, customer text, raw exceptions, and unrestricted tool output.

## Contract evolution

Every v1 schema has a stable `$id` and version. `fixtures/contracts/v1/schema-fingerprints.json` is the compatibility snapshot: a consumed v1 semantic change breaks `python scripts/dev.py contracts`.

Additive evolution must preserve retained v1 fixtures. An incompatible change requires `contracts/jsonschema/v2/` and a new OpenSpec change with migration and compatibility evidence.

## Determinism and known limitations

The offline health report intentionally excludes PIDs, timestamps, and raw configuration values. `tests/e2e/test_offline_baseline.py` starts the skeletons twice and compares the complete machine-readable reports. `.weflow/processes.json` and `.weflow/logs/` are ignored local runtime state; their PIDs are not baseline fields. Synthetic artifact timestamps are explicit fixture inputs.

The current workstation has no Docker, so the Compose topology has static and explicit-skip evidence only. Docker-enabled machines run `tests/e2e/test_service_boundary_acceptance.py` to start the topology, verify dependencies, and inject a timeout. Change 0 does not validate real Tencent/WeCom, CRM, ticketing, object-storage SaaS, model, or enterprise integrations. It has no production deployment, multi-tenant administration, or multi-agent collaboration.

## Next-stage gate

Only after strict validation and archive may Change 1 add synthetic IM intake, Case/CaseRevision handling, append-only business events, and the deterministic business simulator. The API-503 customer-resolution workflow is not implemented in Change 0 and must not be claimed in a demo, resume, or health report.
