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
>
> `add-bounded-live-model-evaluation` is archived as `2026-08-06-add-bounded-live-model-evaluation`: its seven delta capabilities are synced into the main specs. One explicitly authorized command-local DeepSeek pilot is live-verified over synthetic read-only tools; normal services remain Replay-only and no approval, delivery, external business write, or customer outcome was enabled.

> The 2026-08-05 reconciliation retained redacted Change 4 and Change 5 evidence in
> `reports/change-4-reconciliation-manifest.json` and
> `reports/change-5-reconciliation-manifest.json`. Both offline acceptances and the
> 900-second-bounded local suite passed; Docker remained unavailable and Node was
> `v22.21.1`. Strict validation of the already archived directories currently fails with
> `archived_change_has_no_delta`, so neither manifest treats it as a pass.

## 当前状态

### Verified offline foundation, bounded real-model pilot, and QQ Stage 3 integration

- Local Git repository, uv/pnpm workspace, five loopback-only skeleton services, and a Vue diagnostics console are implemented.
- Replay remains the only provider path imported by normal services and offline commands. Dedicated explicit-confirmation live-model evaluation and QQ Stage 3 commands remain isolated from normal startup.
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
- The archived `add-bounded-live-model-evaluation` change has a real DeepSeek accepted report: 30/30 attempts, 330/330 hard gates, 5/5 grounded `RESPONSE_READY`, 100,739 observed tokens, estimated cost USD 0.01502032, and zero approval, delivery, or external business writes. The canonical report hash is `cba0b5450ded45a2bf1f3ec3af6ce5edc3a1253f3da083b93e98c9d976264dd9`.
- Archived change `2026-08-12-enable-bounded-live-model-in-qq-workflow` has one independently verified sandbox integration: one real QQ Case traversed fixed ACK, private handler pull/accept/assist, four real DeepSeek calls, three fixture-local read tools, verifier-authorized private candidate, exact human group approval, and one provider-accepted passive final QQ reply. The run observed 4,979 tokens, USD 0.00076034 estimated cost, 6,260 ms provider latency, and 6,460 ms end-to-end latency. Report SHA-256 is `7d5ba73ce84ed9bfa268c3d315317c94782bc7c929758ca09afc3d56f22162e1`; independent verification SHA-256 is `125702f4fc89636772757fcf9117edc1bfd15905f6de8338d97b7faa2708ed4c`.
- Live quality is not uniformly successful: the missing-information task reached its expected safe outcome 0/5 times (four `response_ready`, one `policy_denied`). The deterministic gates still remained intact, so this is retained as model-quality evidence rather than hidden by changing the acceptance threshold.
- The offline evaluation report console revalidates the fixed `offline-seed.v1` benchmark into a tenant-scoped, content-addressed snapshot and renders 12 bounded task summaries plus selected-task evidence. It remains read-only, replay-only, and local-only.
- The offline Operator Case workspace projects the fixed API-503 source evidence into a tenant-scoped 49-entry intake-to-Replay timeline. It is read-only and labels delivery as fixture-local; it grants no approval, workflow, retry, Replay, or external-write authority.
- Fixture approval/delivery remain distinguishable from the one live-integrated sandbox proof. The Stage 3 business tools are still checked-in synthetic CRM/monitoring/knowledge reads; customer receipt, issue resolution, Case completion, production readiness, enterprise connectors, knowledge publication, and multi-Agent coordination remain false, disabled, or unimplemented.

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
python scripts/dev.py evaluation-console-acceptance
python scripts/dev.py operator-case-timeline-acceptance
python scripts/dev.py reconciliation-verification --output reports/change-4-5-reconciliation-verification.json
python scripts/dev.py archive-evidence-check

python scripts/dev.py up --mode offline
python scripts/dev.py health
python scripts/dev.py down
```

The bounded live command fails before DNS or credential loading unless `--confirm-live` is present. A real DeepSeek run also requires the process-only `WEFLOW_LIVE_MODEL_API_KEY` and a current matching price profile:

```powershell
python scripts/dev.py live-model-evaluation-acceptance --confirm-live
```

Do not run it casually: it makes up to 30 real model-backed attempts and incurs estimated provider cost. See the bounded live-model guide for setup, retention, rollback, failure semantics, and the distinction between synthetic tools and real model contact.

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
- [Offline Evaluation Report Console Development Guide](docs/development/offline-evaluation-report-console.md)
- [Bounded Live-Model Evaluation Development Guide](docs/development/bounded-live-model-evaluation.md)
- [QQ Sandbox Intake and Fixed Acknowledgement Guide](docs/development/qq-sandbox-intake-and-ack.md)
- [QQ Sandbox Handler Approval and Delivery Guide](docs/development/qq-sandbox-handler-approval-and-delivery.md)
- [QQ Bounded Live-Model Workflow Guide](docs/development/qq-bounded-live-model-workflow.md)
- [Offline Operator Case Timeline Development Guide](docs/development/operator-case-timeline.md)
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
