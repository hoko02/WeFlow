# WeFlow

WeFlow 是一个面向企业 IM 客户问题闭环的 Agent Reliability Harness。它从一条企业微信风格的客户消息出发，在受控业务工具、持久化 Workflow、模型外策略、人工审批、证据链和自动评测的共同约束下，完成：

```text
消息接入 → 客户/SLA 补全 → 问题分诊 → 证据调查 → 工单协同
→ 回复候选 → 人工审批 → 对外回复 → 知识候选 → 复盘评测
```

首个纵向场景锁定为“企业客户 API 503 故障支持闭环”。M1 的目标不是做通用客服平台，也不是堆叠多个 Agent，而是证明一条高价值业务链路能够稳定恢复、严格授权、避免重复副作用、留下可审计证据，并在重复运行中得到量化结果。

> Change 2 is archived: it adds a fixture-local durable workflow after synthetic API-503 Case intake. It can checkpoint, recover, enforce a synthetic SLA, and reconcile one local ticket handoff.
>
> Change 3 (`add-investigation-agent-loop`) is archived as `2026-08-03-add-investigation-agent-loop`: one deterministic Replay Agent can investigate the named API-503 fixture through three read-only local tools. A deterministic verifier may advance only to `RESPONSE_READY`; it does not approve, send, or resolve anything.
>
> Change 4 (`add-policy-and-approval-gates`) is archived as `2026-08-04-add-policy-and-approval-gates`: its nine delta capabilities are synced into the main specs. The named API-503 fixture binds policy, approval, and one local delivery record while remaining offline, deterministic, unable to perform a real external write, and unable to claim customer resolution.
>
> Change 5 (`add-evidence-and-trajectory-replay`) is archived as `2026-08-04-add-evidence-and-trajectory-replay`: its four delta capabilities are synced into the main specs. It creates append-only, redacted Evidence Reports and deterministic verification replay over retained API-503 fixture facts while remaining offline and unable to export raw data, invoke a model, perform external writes, or claim customer success.

> The 2026-08-05 reconciliation retained redacted Change 4 and Change 5 evidence in
> `reports/change-4-reconciliation-manifest.json` and
> `reports/change-5-reconciliation-manifest.json`. Both offline acceptances and the
> 900-second-bounded local suite passed; Docker remained unavailable and Node was
> `v22.21.1`. Strict validation of the already archived directories currently fails with
> `archived_change_has_no_delta`, so neither manifest treats it as a pass.

## 当前状态

### Verified Changes 0–5, including fixture evidence/replay

- Local Git repository, uv/pnpm workspace, five loopback-only skeleton services, and a Vue diagnostics console are implemented.
- Replay is the only enabled provider path; live providers, credentials, external writes, and multi-agent coordination fail closed.
- Canonical v1 JSON Schema, Python/TypeScript compatibility checks, synthetic fixtures, secret hygiene, offline acceptance, and CI are implemented.
- The health report separates operational readiness from unimplemented business capabilities.
- Change 1 accepts only canonical synthetic IM envelopes, derives tenant identity from an allowlisted actor header, and creates one Case, revision 1, and three append-only ledger events.
- Exact retries are deduplicated; conflicting replays and sequence gaps fail closed; foreign Case reads do not disclose existence.
- Archived Change 2 adds an append-only workflow journal, driver-neutral `RECEIVED` → `TICKET_READY` control path, immutable checkpoints, pause/resume/cancel commands, and a fixture-defined SLA clock. `TICKET_READY` means only that the local handoff is known; it is not a resolution state.
- The only effect is a deterministic, fixture-local ticket `find-or-create` plus expected-version handoff. It uses persisted `intent → reconcile → execute → observe → complete` evidence and recovery after every declared interruption boundary, including lost responses.
- Change 3 adds a deterministic Replay-only investigation continuation from `TICKET_READY` through `INVESTIGATING` to verifier-authorized `RESPONSE_READY`. It persists a Context Manifest, closed Agent actions, three local read-only tool results, evidence hashes, a response candidate, and a verifier outcome; recovery after each new durable boundary is deterministic.
- `RESPONSE_READY` is only a verified response candidate state. Retained Change 3 histories remain inert until the control kernel records an explicit Change 4 fixture activation.
- Change 4 adds one named API-503-only, default-deny Capability/Policy, hash-bound approval, and idempotent local delivery slice. It uses append-only SQLite intent/reconcile/execute/observe/complete evidence and recovers without duplicate local delivery.
- Change 5 adds an append-only, content-addressed EvidenceTrajectory, redacted EvidenceReport, and verification-only replay over retained fixture facts. It cannot progress workflow state or execute an agent, tool, policy, approval, delivery, network, Docker, or external operation.
- Fixture approval/delivery are explicitly distinguishable from live capability. Real providers, credentials, enterprise connectors, external writes, customer receipt/resolution, knowledge publication, and multi-Agent coordination remain disabled and unimplemented.

### Historical Explore snapshot (superseded)

This historical note predates the archived Change 0/1/2 increments. The current status above, `docs/PROJECT_MEMORY.md`, and the
OpenSpec change artifacts are authoritative.

## Quick start

The required local tools are `uv`, Node.js, pnpm, and Git. Docker is optional and only required for service-boundary mode.

```powershell
uv sync --all-packages --all-groups
pnpm install --frozen-lockfile

python scripts/dev.py check
python scripts/dev.py lint
python scripts/dev.py contracts
python scripts/dev.py test
python scripts/dev.py case-intake-acceptance --output reports/change-1-acceptance.json
python scripts/dev.py durable-workflow-acceptance --output reports/change-2-acceptance.json
python scripts/dev.py investigation-agent-acceptance --output reports/change-3-acceptance.json
python scripts/dev.py policy-approval-acceptance --output reports/change-4-acceptance.json
python scripts/dev.py evidence-trajectory-acceptance --output reports/change-5-evidence-trajectory-acceptance.json
python scripts/dev.py evaluation-benchmark-acceptance --output reports/change-6-evaluation-benchmark-core-acceptance.json
python scripts/dev.py reconciliation-verification --output reports/change-4-5-reconciliation-verification.json
python scripts/dev.py archive-evidence-check

python scripts/dev.py up --mode offline
python scripts/dev.py health
python scripts/dev.py down
```

`health` is machine-readable operational evidence. It returns exit code `2` when the skeletons are not ready; it never claims business completion.

For the optional Docker-backed boundary mode, run `compose up`, then `up --mode service-boundary`, and stop both stacks afterward. If Docker is unavailable, `compose status` returns `docker_unavailable` and exit code `2`; offline mode is still fully supported.


## 文档入口

- [项目长期记忆](docs/PROJECT_MEMORY.md)
- [Change 0 Foundation Development Guide](docs/development/change-0-foundation.md)
- [Change 1 Synthetic Case Intake Development Guide](docs/development/change-1-case-intake.md)
- [Change 2 Durable Support Workflow Development Guide](docs/development/change-2-durable-workflow.md)
- [Change 3 Bounded Replay Investigation Agent Development Guide](docs/development/change-3-investigation-agent-loop.md)
- [Change 4 Policy and Approval Gates Development Guide](docs/development/change-4-policy-approval-gates.md)
- [Change 5 Evidence Trajectory and Replay Development Guide](docs/development/change-5-evidence-trajectory-replay.md)
- [Change 6 Evaluation Benchmark Core Development Guide](docs/development/change-6-evaluation-benchmark.md)
- [MVP 探索结论](docs/exploration/weflow-mvp-exploration.md)
- [参考架构](docs/architecture/reference-architecture.md)
- [OpenSpec 分步开发路线](docs/development/openspec-roadmap.md)

## 与 ForgeCode 的关系

WeFlow 复用 ForgeCode 已验证的工程方法，而不是复制其业务代码：

- 先做一条可验证的业务纵切，再扩展通用平台；
- 控制面、执行面、证据面逻辑分离；
- 不可变任务 revision、追加式事件和 durable workflow；
- 外部副作用采用 `intent → reconcile → execute → complete`；
- 权限、预算、完成判断和审批全部位于模型外；
- Replay Adapter、固定 fixture、故障注入和重复运行基线；
- OpenSpec 按 `explore → propose → apply → validate → archive` 小步推进。

## 后续交互

开始任何开发前先让 Agent 阅读本文件和 `docs/PROJECT_MEMORY.md`，再执行：

```powershell
openspec list --json
```

研究问题时使用 `/opsx:explore`；准备实现某一阶段时使用 `/opsx:propose` 创建单一 change；实现完成且证据齐备后严格验证并归档。详细约定见 [OpenSpec 分步开发路线](docs/development/openspec-roadmap.md)。
