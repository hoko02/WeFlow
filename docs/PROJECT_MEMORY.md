# WeFlow 项目长期记忆

> 最近更新：2026-08-12
> 用途：保存跨 change 的产品定位、已锁定决策、边界和启动门槛。它不是某个 change 的实现规格；进入开发前仍需通过 OpenSpec proposal 固化本次范围。

## 1. 产品定位

WeFlow 是一个“企业 IM 原生的客户问题闭环 Agent Reliability Harness”。目标用户是企业技术支持、客户成功、客服运营和 Agent 平台团队。系统把来自企业微信风格渠道的非结构化消息转化为可追踪 Case，在受控工具和业务 Workflow 中完成调查、工单协同、回复审批、对外发送和知识沉淀。

项目的求职表达重点是 Agent 工程可靠性，而不是客服话术：

- 长任务状态与中断恢复；
- 模型、Workflow 和业务工具的责任边界；
- 多租户身份、最小权限、审批与审计；
- 副作用幂等和未知结果核对；
- Trace、Replay、Evaluator 和机器可读基线；
- 业务结果、质量、成本和时延的统一量化。

腾讯当前公开方向与本项目匹配：WorkBuddy Managed Agents 把 Agent、Runtime、Session、沙箱、Trace 和效果评测作为生产级 Harness 的核心；腾讯云 ADP 强调 Agent/Workflow 协同、权限、审计和可观测；多 Agent 文档将“客服处理 → 建工单 → 归档知识库”列为协作链路，同时明确固定流程应优先使用 Workflow。

## 2. 首个纵向业务场景

M1 只支持一个场景：**企业客户 API 503 故障支持闭环**。

示例输入：

> 客户 A 在企业 IM 中反馈：“生产环境调用支付 API 持续返回 503，今天 15:00 上线前必须恢复。”

系统必须：

1. 校验租户、渠道事件和会话身份并去重；
2. 查询客户、产品、环境、合同等级和 SLA；
3. 判断问题类别、严重度和缺失信息；
4. 查询服务健康、告警、变更记录和已知问题；
5. 查找重复工单，必要时幂等创建或更新工单；
6. 生成带证据引用、风险和下一步的回复候选；
7. 将候选、证据、策略和 Case revision 绑定后请求人工批准；
8. 经批准后幂等发送对外回复；
9. 在问题解决后生成知识库候选，但 M1 不自动发布；
10. 生成可回放 Evidence Report 和 Evaluation Result。

## 3. M1 输入与输出

### 输入

- 标准化 IM 事件及原始事件哈希；
- tenant、channel、conversation、sender 和 customer identity；
- 产品、环境、消息正文和附件元数据；
- 可用工具、资源范围、有效期和预算；
- SLA、审批策略、数据保留级别和敏感度；
- 固定的模拟业务环境快照。

### 输出

- Case、不可变 CaseRevision 和追加式事件时间线；
- CRM、监控、知识、工单、审批和 IM 工具调用记录；
- PolicyDecision、Checkpoint、Artifact 和血缘；
- 与候选哈希绑定的人工决定；
- 幂等对外回复和知识库候选；
- Trace Replay、失败分类、RunMetrics 和 Evaluation Report。

## 4. 已锁定的设计决策

### 4.1 Workflow 主干，Agent 只处理开放式决策

确定性的事件去重、状态迁移、SLA 计时、重试、审批等待、工具副作用和终止判断由 Workflow/代码负责。Agent 负责意图分类、调查计划、证据综合、回复草拟和知识候选。

M1 使用单 Agent + 专门 Skills，不启用多 Agent。只有基线证明任务确实需要并行协作，且收益覆盖额外成本和失败面，才在后续 change 中增加多 Agent。

### 4.2 模型不能授权自己，也不能宣布任务成功

所有工具调用先经过模型外 Policy Enforcement Point。硬门禁包括租户匹配、动作 scope、资源 scope、数据敏感度、预算、审批状态和候选哈希。完成状态由确定性 Verifier 汇总，模型文本中的“已解决”没有状态效力。

### 4.3 业务副作用必须可核对且至多一次生效

工单创建/更新、审批请求、外发消息和知识候选写入均采用：

```text
persist intent → reconcile natural key → execute if absent
→ verify observed result → persist completion
```

无法确认外部结果时进入 `NEEDS_RECONCILIATION`，不得盲目重试。

### 4.4 先模拟业务工具，再连接真实腾讯生态

M1 使用确定性的 CRM、工单、知识库、监控、审批和 IM Simulator。真实企微/腾讯云连接器属于后续 Adapter change；这保证无企业账号、无公网和无模型密钥时仍可完整运行验收链路。

### 4.5 评测从第一条业务链路开始，不延期建设

每次运行都必须产生稳定 Trace、工具结果、策略决定、候选、审批、业务结果和失败分类。M1 先建立 12 个黄金 fixture，随后扩展到 60 个任务 × 每任务 5 次 live run。禁止用“Demo 看起来成功”替代可复现指标。

### 4.6 参考 ForgeCode 的单仓库工程结构

建议延续 Python 控制/执行面 + TypeScript/Vue 控制台、uv + pnpm workspace、统一 `scripts/dev.py`、PostgreSQL、Temporal、对象存储和 OpenTelemetry。具体版本在第一个 proposal 中锁定，本文不替代依赖锁文件。

## 5. M1 必须能力

- IM 事件接入、规范化、验签边界和幂等去重；
- CRM、工单、知识库、监控、审批、IM 六类模拟工具；
- Case state machine、checkpoint、暂停/恢复/取消和 SLA；
- 单 Agent 调查循环、Context Manifest、Tool Gateway；
- tenant-aware capability、RBAC/ABAC、PII/秘密脱敏和预算；
- 外发消息人工审批和候选变更后批准失效；
- Evidence lineage、Trace 时间线、确定性 replay 和故障注入；
- 至少 60 个评测任务的 schema、分层 grader 和机器可读报告；
- 最小 Operator Console 和可复现求职演示。

## 6. M1 明确不做

- 通用全行业客服平台、语音/视频客服或真实生产 SaaS；
- 自动退款、自动赔付、自动发布知识、自动关闭重大事故；
- 无边界浏览器/宿主 shell/桌面控制；
- 默认启用多 Agent 或让 Agent 自由互聊；
- 生产级多地域 HA/DR、复杂计费和完整组织目录；
- 用 LLM-as-a-Judge 取代所有确定性业务校验；
- 在线自动修改 Prompt、Skill、策略或模型权重；
- 在没有重复运行数据时宣称性能、质量或 ROI 提升。

## 7. M1 完成门槛

- 12/12 黄金 fixture 在 Replay 模式通过；
- Worker/模型/工具/网络故障注入后恢复率 100%；
- 重复工单、重复审批、重复外发消息均为 0；
- 越租户、越权外发、未批准外发成功次数均为 0；
- 所有外发回复均引用可验证 Evidence；
- 60 个任务数据集可由单命令运行，输出成功率、硬门禁通过率、成本、P50/P95 时延、人工介入率和失败分类；
- 同一 live 模型每任务至少重复 5 次，报告方差而非只报最佳结果；
- 文档明确区分已验证能力、模拟能力和未来路线。

## 8. 后续阶段启动门槛

### 真实企微/腾讯云 Adapter

只有模拟链路的契约、幂等键、策略和 Evidence schema 稳定后接入。真实写入默认 feature flag 关闭，并使用测试企业/沙箱账号。

### 多 Agent 协作

只有出现可并行、低共享写冲突的任务，并通过相同数据集证明相较单 Agent 在成功率或时延上显著改善，才启用。必须同时报告 2～3 倍 Token 成本风险、路由错误和协作失败。

### Trace 驱动经验演进

只有能可靠区分模型、Harness、工具、环境和评测器失败，且存在未污染 holdout 集、版本化经验包、shadow、审批和回滚机制后启动。

## 9. 事实来源

- [WorkBuddy Managed Agents 产品介绍](https://cloud.tencent.com/document/product/1831/134407)
- [腾讯云智能体开发平台](https://adp.cloud.tencent.com/)
- [腾讯云多 Agent 协同与选型建议](https://cloud.tencent.com/document/product/1759/134193)
- [Tencent WorkBuddy Bench](https://arxiv.org/abs/2607.20911)
- [腾讯混元 OpenAI 兼容接口](https://cloud.tencent.com/document/product/1729/111007)

## 10. Verified Change 0 foundation (2026-07-29)

`establish-weflow-foundation` was archived as `2026-07-29-establish-weflow-foundation`. The main OpenSpec specifications now include workspace operability, versioned domain contracts, local platform dependencies, and the safe provider runtime boundary.

Verified facts:

- `python scripts/dev.py check`, `lint`, `contracts`, and `test` passed without network, Docker, model credentials, or enterprise credentials.
- The final local suite reported 47 passed and 1 explicit Docker-unavailable skip. The shared TypeScript contract check accepted 14 valid payloads.
- An offline start/health/stop run made Platform API, Control Worker, Agent Runtime, Business Simulator, and Web Console operationally ready. The report kept `business_workflow_implemented=false` and `external_writes_enabled=false`.
- Strict OpenSpec validation passed with one valid change, zero issues, and zero failures. Evidence is retained in `reports/change-0-acceptance.json` and `reports/change-0-openspec-validation.json`.
- Repeated offline health baselines compare equal. PIDs and local logs remain ignored runtime state and are intentionally absent from reports.

Known limitations:

- Docker is unavailable on the verification workstation, so Compose startup was explicitly skipped; the Docker-enabled service-boundary acceptance test remains available for a machine with Docker.
- Change 0 has no API-503 Case intake, Case/CaseRevision storage, business events, workflow execution, approval flow, external write, real provider, Tencent/WeCom integration, production tenant, or multi-agent capability.

Change 1 gate:

- Create a new OpenSpec change before adding synthetic IM intake or business state. It must preserve the v1 contract compatibility check, replay-first defaults, tenant/evidence invariants, no-credential offline path, negative provider tests, and the distinction between operational readiness and business success.


## 11. Verified Change 1 synthetic Case intake (2026-07-29)

`add-case-intake-and-simulator` was archived as `2026-07-29-add-case-intake-and-simulator`. Its main OpenSpec specifications now cover synthetic IM Case intake, the deterministic Case event ledger, and compatible versioned domain contracts.

Verified facts:

- The offline Platform API accepts only canonical, fixture-backed `InboundMessageEvent` envelopes. An allowlisted synthetic actor determines the effective tenant; mismatched claims, raw/undeclared fields, conflicting replays, and sequence gaps fail closed with safe reason codes.
- A first accepted delivery creates exactly one Case, immutable Revision 1, and three ordered append-only events. An exact retry returns `deduplicated` without another durable write; foreign Case reads are indistinguishable from absent Case reads.
- The SQLite source ledger rebuilds its projection at restart, rejects source mutation, and exports a content-addressed single-tenant snapshot. Fresh-store restore rejects hash, tenant, receipt/event-reference, or source-invariant inconsistencies.
- The final offline acceptance report recorded `accepted`, `deduplicated`, and `inbound_out_of_order` for the three API-503 fixtures; the accepted baseline contained 1 receipt, 1 Case, 1 revision, 3 events, and 1 projection. Snapshot restore was deterministic.
- `python scripts/dev.py check`, `lint`, `contracts`, `test`, and `case-intake-acceptance` passed without network, Docker, model credentials, or enterprise credentials. The final suite reported 71 passed and 1 explicit Docker-unavailable skip; the cross-language corpus reported 16 valid and 5 invalid TypeScript payloads alongside 14 Python contract tests.
- Strict OpenSpec validation passed with one valid item, zero issues, and zero failures. Evidence is retained in `reports/change-1-acceptance.json` and `reports/change-1-openspec-validation.json`.
- Capability reporting marks only `synthetic_case_intake_implemented=true`; `business_workflow_implemented=false` and `external_writes_enabled=false` remain enforced. No model, workflow, approval, provider, external-write intent, or customer-resolution result is initialized by Change 1.

Known limitations:

- Docker remains unavailable on the verification workstation, so the Docker-backed service-boundary test is explicitly skipped. The required Change 1 acceptance path is fully offline and does not depend on Docker.
- Change 1 has no CRM, monitoring, knowledge, ticketing, customer lookup, live Tencent/WeCom adapter, durable workflow, approval, outbound reply, external side effect, real customer data, or multi-agent behavior.
- The only supported state is initial local `RECEIVED`; later state transitions, Case revisions beyond 1, SLA/retry orchestration, and resolution assertions are deliberately out of scope.

Change 2 gate:

- Create a new OpenSpec change before adding the durable support workflow. It must define deterministic lifecycle states after `RECEIVED`, revision creation rules, checkpoint/restart semantics, SLA ownership, and an intent/reconcile/execute/complete boundary for every future external effect.
- It must retain fixture-only offline replay, actor-derived tenant isolation, append-only source ledger, safe error envelopes, snapshot/recovery tests, and the no-model/no-approval/no-external-write default until a later explicitly approved change enables each capability.
- It must prove worker interruption and response-loss recovery without duplicate effects, and must not claim customer resolution merely because a workflow or model emits text.

## 12. Verified Change 2 durable support workflow (2026-08-03)

`add-durable-support-workflow` was archived as `2026-08-03-add-durable-support-workflow`. The main OpenSpec specifications now include durable support workflow and idempotent side-effect recovery, and update the Case ledger, local dependency, and versioned-contract requirements.

Verified facts:

- Offline `check`, `lint`, `contracts`, `test`, Change 1 acceptance, and Change 2 acceptance passed without network, Docker, model credentials, or enterprise credentials. The final suite reported 132 passed and 2 explicit service-boundary skips; cross-language contracts accepted 23 valid and rejected 15 invalid payloads.
- Change 2 adds a driver-neutral, tenant-scoped control path with an append-only workflow journal, immutable checkpoints, allowlisted pause/resume/cancel commands, a fixture-defined SLA clock, and a bounded `RECEIVED` to `TICKET_READY` transition. `TICKET_READY` is a fixture-local handoff fact, not an investigation, reply, resolution, or completion claim.
- The only effect is a deterministic fixture-local ticket find-or-create plus expected-version handoff. It persists intent, reconciliation, execution, observation, validation, and completion records; eight declared interruption/lost-response boundaries recovered to `TICKET_READY` with exactly two local ticket operations and no duplicate effect.
- The SLA fixture deterministically entered `WAITING_FOR_OPERATOR` with zero ticket operations. Repeated offline reports and projections compared equal with no intentional nondeterministic fields.
- Capability evidence reports `durable_support_workflow_implemented=true` while `business_workflow_implemented=false`, `external_writes_enabled=false`, model invocation false, approval false, outbound delivery false, and customer-resolution false.
- Strict OpenSpec validation passed with zero issues. Evidence is retained in `reports/change-2-acceptance.json`, `reports/change-2-verification.json`, and `reports/change-2-openspec-validation.json`.

Known limitations:

- Node.js 22.21.1 is installed while the workspace declares Node >=24 <25. TypeScript lint, contract checks, tests, and console build passed, but Node 24-specific behavior is not locally verified.
- Docker is unavailable on the verification workstation, so two service-boundary tests are explicit skips and the Temporal driver was not live-verified. Offline deterministic workflow acceptance is verified; service-boundary readiness remains a future environment verification.
- Agent/model use, investigation, CRM/monitoring/knowledge reads, approvals, outbound delivery, real providers/connectors, real external writes, and customer-resolution claims remain unimplemented and disabled.

Next-stage gate:

- Create a new OpenSpec proposal before introducing a bounded single-Agent investigation loop. It must preserve deterministic workflow ownership, append-only Case/workflow/effect evidence, actor-derived tenant isolation, fixture-only offline replay, no duplicate effect recovery, and the no-approval/no-outbound/no-real-external-write default.
- The proposal must define Context Manifest, structured Agent action, Tool Request/Result, Evidence, response-candidate, verifier, replay/fault, budget/no-progress, and safe state-continuation semantics. The Agent may propose `needs_information`, `needs_operator`, or a response candidate only; deterministic workflow and verifier code retain authority over state and completion.

## 13. Verified Change 3 bounded Replay investigation Agent (2026-08-03)

`add-investigation-agent-loop` was archived as
`2026-08-03-add-investigation-agent-loop`. Its eight delta capabilities are now
synced into the main OpenSpec specifications before archive.

Verified facts:

- `python scripts/dev.py check`, `lint`, `contracts`, `test`, and
  `investigation-agent-acceptance` passed in offline mode. The final suite reported
  151 passed and 2 explicit Docker/service-boundary skips. Python contract tests passed
  32 cases; the TypeScript corpus accepted 29 valid and rejected 22 invalid payloads.
- The named synthetic API-503 fixture safely continues from retained Change 2
  `TICKET_READY` through `INVESTIGATING` to `RESPONSE_READY`. Its accepted baseline
  contains four ordered Agent steps, three ordered tenant-scoped evidence hashes, one
  response candidate, and one verified verifier outcome. `RESPONSE_READY` is not an
  approval, delivery, customer observation, resolution, or completion assertion.
- The durable journal persists immutable Context Manifest, Agent-step, tool
  request/result, candidate, and verifier records linked to workflow checkpoints.
  Interruption after action, tool-result, candidate, or verifier persistence recovers
  with exactly 4/3/1/1 records and no duplicate tool result or response-ready
  transition.
- A single deterministic Replay Agent has a closed action algebra and cannot directly
  change Case state, approve, deliver, select a live provider, create an external
  write, or declare success. Action/tool/no-progress budget gates and malformed,
  authority-claim, foreign-tenant, unallowlisted-tool, live-provider, and unverified-
  candidate paths fail closed.
- The only tools are fixture-local CRM, monitoring, and knowledge reads. They produce
  tenant-scoped synthetic evidence IDs and hashes; no raw prompt, fixture payload,
  credential, unrestricted tool output, or full ledger snapshot is used for the
  investigation inspection/report surface.
- Platform API observation is tenant-derived and read-only. Its investigation route
  returns redacted journal facts; foreign and absent reads are both
  `workflow_not_found`. Capability and Web Console diagnostics truthfully expose the
  Replay investigation and verifier while retaining real provider, multi-Agent,
  external write, approval, outbound delivery, and customer-resolution flags as false.
- The strict OpenSpec validation command completed successfully. Evidence is retained
  in `reports/change-3-acceptance.json`, `reports/change-3-verification.json`, and
  `reports/change-3-openspec-validation.json`.

Known limitations:

- Node.js `v24.16.0` and pnpm `11.9.0` are available and meet the workspace Node 24
  range for the current verification. Docker is unavailable, so Temporal/service-
  boundary behavior remains explicitly skipped and is not live-verified.
- The implementation supports one checked-in API-503 Replay transcript only. There is
  no live model, enterprise credential, network provider, real Tencent/WeCom or ticket
  connector, real customer data, external write, approval, outbound delivery, knowledge
  publication, or multi-Agent collaboration.

Next-stage gate:

- Create a new OpenSpec proposal before enabling any policy, approval, or delivery
  capability. It must retain deterministic workflow/state/retry/effect ownership,
  append-only Case/workflow/evidence facts, actor-derived tenant isolation, safe replay,
  and recovery baselines.
- The next increment must add model-external capability and policy decisions, bind any
  approval to candidate/evidence/policy hashes with invalidation on change, and model
  outbound delivery as an idempotent intent/reconcile/execute/complete effect. A
  verified `RESPONSE_READY` candidate alone must never permit an external write.
## 14. Archived Change 4 fixture policy, approval, and local delivery (2026-08-04)

`add-policy-and-approval-gates` was archived as
`2026-08-04-add-policy-and-approval-gates`. Its nine delta capabilities are synced into
the main OpenSpec specifications.

Verified facts:

- Historical archive metadata records all 23 Change 4 tasks as completed, with its
  then-current offline `check`, `lint`, `contracts`, `test`, and acceptance counts. That
  historical task/count record is not substituted for current reconciliation evidence.
- On 2026-08-05, the offline Change 4 acceptance rerun and the 900-second-bounded
  aggregate suite both passed. The current CLI strict validation of the archived
  directory failed with `archived_change_has_no_delta`, because archive input no longer
  exposes a delta. It is retained as a `failed` limitation, not a pass. Canonical
  evidence is `reports/change-4-acceptance.json`,
  `reports/change-4-openspec-validation.json`,
  `reports/change-4-5-reconciliation-verification.json`, and
  `reports/change-4-reconciliation-manifest.json`.

- The only new vertical slice is the checked-in `api-503-policy-approval-delivery`
  fixture. It continues an explicitly activated, verified `RESPONSE_READY` candidate
  through `AWAITING_APPROVAL`, `DELIVERING`, and `DELIVERY_RECORDED`; pre-existing
  Change 3 `RESPONSE_READY` histories remain inert without that activation.
- Capability Grants, deterministic default-deny Policy Decisions, authorization
  bindings, approval requests/decisions, and outbound delivery intent/observation/
  completion records are append-only, tenant-scoped, versioned, content-addressed, and
  redacted. The decision API derives tenant and fixture role server-side and accepts
  only request ID, approve/reject, and expected workflow version.
- The only delivery adapter is local SQLite. It requires current policy and hash-bound
  approval, uses stable natural/idempotency keys, and records `DELIVERY_RECORDED`
  without a customer receipt, resolution, completion, network call, or real external
  write claim.
- The offline Change 4 acceptance command compares two equal baselines, covers policy,
  approval, and all delivery fault boundaries, and proves exactly one local delivery
  record for every authorized recovered path. The revoked-grant denial creates zero
  delivery intent/record and reaches a safe operator state.
- Capability reporting separates fixture approval/delivery from disabled live approval,
  live outbound delivery, external writes, real providers, customer resolution, and
  multi-Agent behavior. Reports contain only safe IDs, hashes, counts, flags, and
  reason codes.

Known limitations:

- Core Change 4 acceptance requires no Docker, network, model credential, enterprise
  credential, or Node runtime. The reconciliation observed Node `v22.21.1`; Node remains
  necessary for TypeScript contract and Web Console checks, but this is not a Node 24
  verification claim. Docker is unavailable, so Temporal/service-boundary behavior is
  explicitly not live-verified.
- There is one synthetic tenant, one API-503 fixture, one local adapter resource, a
  fixed one-delivery budget, and no real approval service, enterprise identity,
  connector, customer-visible delivery, knowledge publication, or customer-success
  outcome.

Next-stage gate:

- A new OpenSpec change is required before enabling a real provider, credential,
  approval service, or external write. It must define provider-specific idempotent
  intent/reconciliation, durable operator authorization lifecycle, auditable evidence
  retention, rollout/rollback controls, live safety verification, and a strict rule
  that provider acknowledgement never alone proves customer resolution.
## 15. Archived Change 5 evidence trajectory and verification replay (2026-08-04)

`add-evidence-and-trajectory-replay` was archived as
`2026-08-04-add-evidence-and-trajectory-replay`. Its four delta capabilities are
synced into the main OpenSpec specifications.

Verified facts:

- Historical archive metadata records all 16 Change 5 tasks as completed, with its
  then-current focused Python, contract, TypeScript, secret-hygiene, and lint results.
  Those archived counts are not substituted for current reconciliation evidence.
- On 2026-08-05, the offline Change 5 acceptance rerun and the 900-second-bounded
  aggregate suite both passed. The current CLI strict validation of the archived
  directory failed with `archived_change_has_no_delta`, because archive input no longer
  exposes a delta. It is retained as a `failed` limitation, not a pass. Canonical
  evidence is `reports/change-5-evidence-trajectory-acceptance.json`,
  `reports/change-5-openspec-validation.json`,
  `reports/change-4-5-reconciliation-verification.json`, and
  `reports/change-5-reconciliation-manifest.json`.
- The named API-503 fixture now derives one append-only, tenant-scoped,
  content-addressed EvidenceTrajectory from retained Case, workflow, investigation,
  policy, approval, and one fixture-local delivery record. Artifact, EvidenceReport,
  and TrajectoryReplayResult are separate redacted durable facts; exact extraction and
  replay retries converge without changing Case state, checkpoint, grant, approval,
  intent, delivery, or effect records.
- Evidence Reports are read-only and tenant-derived. They expose only safe IDs,
  hashes, classifications, counts, fixed outcomes/failures, fixture identity, and
  capability flags. A missing/foreign report remains indistinguishable; raw/private,
  secret-like, customer-success, caller-authority, detached, duplicate, out-of-order,
  or tampered inputs fail closed with no protected disclosure.
- Deterministic verification replay re-resolves retained source facts. The authorized,
  revoked-grant denial, and lost-response recovery paths reproduce the recorded root;
  tampered lineage returns `lineage_invalid` without a workflow transition, model,
  network request, Docker initialization, or external-write attempt.
- The acceptance command is `python scripts/dev.py evidence-trajectory-acceptance` and
  uses checked-in fixtures plus temporary local SQLite only. The current reconciliation
  paths above replace the absent historical `change-5-verification` path.

Known limitations:

- Docker is unavailable on the verification workstation. The reconciliation observed
  Node `v22.21.1`, which is required for the TypeScript contract check but not core
  evidence acceptance; it is an observed environment fact, not a Node 24 claim. No
  network, model credential, enterprise credential, live provider, or external service
  was used.
- The historical 120-second tool limit is superseded by the current bounded run: the
  aggregate `uv run python scripts/dev.py test` completed with exit code 0 in
  168.028 seconds, well within the 900-second outer limit, with no child-process cleanup
  required.
- The scope remains one synthetic tenant and checked-in API-503 fixture. Raw artifact
  export, real provider/credential use, network access, customer receipt/resolution,
  knowledge publication, live trace export, real external delivery, and multi-Agent
  execution remain disabled and unimplemented.

Next-stage gate:

- Create a new OpenSpec proposal before enabling any non-fixture evidence export,
  real provider, credential, network destination, live trace backend, external delivery,
  or multi-Agent execution. It must define retention and deletion policy, privacy and
  redaction review, tenant/role authorization, provider-specific intent/reconciliation,
  independent audit access, rollout/rollback, and live safety verification.
- A provider acknowledgement, local adapter record, report, or replay result MUST NOT
  alone establish customer receipt, incident resolution, Case completion, or permission
  for another effect.

## 16. Archived Change 4/5 evidence reconciliation (2026-08-05)

`reconcile-change-4-5-archive-evidence` was archived as
`2026-08-05-reconcile-change-4-5-archive-evidence`. Its evidence-integrity requirement
is now a main OpenSpec specification, and its repository-hygiene requirement is synced
into `workspace-operability`.

Verified facts:

- Canonical, redacted Change 4/5 acceptance, validation, verification, and manifest
  reports are version controlled. The repository evidence check passed with two
  manifests and 17 documented reports.
- The Change 4 and Change 5 offline acceptances passed, and the bounded aggregate local
  suite completed successfully within its 900-second limit. Docker was unavailable and
  Node `v22.21.1` was recorded as an observed environment fact, not a Node 24 claim.
- Strict validation of this active reconciliation change completed with zero issues
  before archive. Direct strict validation of each already archived Change 4/5 directory
  returned `failed` with `archived_change_has_no_delta`; the reports retain that exact
  CLI limitation and do not present it as a product failure or a passing result.
- This reconciliation changed repository evidence, documentation, and OpenSpec
  specifications only. It did not add or enable a workflow state, API, provider,
  connector, approval, external write, customer delivery, or live service.

Known limitations:

- Current OpenSpec validation covers active changes and main specifications. The CLI
  cannot strictly validate an archived change directory after its delta is moved, so the
  archived Change 4/5 limitation must remain visible in canonical evidence.
- All acceptance remains fixture-only and offline. Docker, live providers, credentials,
  enterprise connectors, real external writes, customer receipt/resolution, and
  multi-Agent execution remain disabled or unverified.

Next-stage gate:

- No product capability is authorized by this maintenance archive. Start the next
  independently verifiable product increment only with a new OpenSpec proposal; the
  roadmap's evaluation benchmark remains a candidate next change and must preserve the
  deterministic, fixture-first, no-real-external-write boundaries.

## 17. Archived Change 6 offline evaluation benchmark core (2026-08-05)

`add-evaluation-benchmark-core` was archived as
`2026-08-05-add-evaluation-benchmark-core`. Its offline-evaluation-benchmark
requirements and two benchmark-contract requirements were synced to the main OpenSpec
specifications before archive.

Verified facts:

- The `benchmark-core.v1` profile provides five new versioned JSON Schemas plus
  additive `EvaluationCase` and `EvaluationResult` fields. Python and TypeScript
  validate safe identities, tenant links, task/oracle/report hashes, hard gates,
  capability flags, and the `not_scored` requirement after an applicable hard-gate
  failure.
- The checked-in JSON-only `offline-seed.v1` suite has exactly 12 unique API-503
  tasks across intake, durable workflow/SLA, investigation, policy/approval, and
  evidence-lineage paths. Each run uses a temporary local SQLite store and invokes
  only existing deterministic fixture controls.
- The canonical report at
  `reports/change-6-evaluation-benchmark-core-acceptance.json` passed 12/12 tasks,
  with 0 failures and 0 unscored tasks. Its report hash is
  `5ca0c7a5b9eed0d9eed7cb178b8f6084aaff23acd044911b72d030afae250631`; two
  fixed-baseline runs were equal.
- The 2026-08-05 checks passed: `python scripts/dev.py check`, `lint`, and
  `contracts` (Python 51 passed; TypeScript contract fixture check 37 valid / 29
  invalid); `uv run python scripts/dev.py evaluation-benchmark-acceptance --output
  reports/change-6-evaluation-benchmark-core-acceptance.json`; and
  `python scripts/dev.py test` (Python 224 passed, 2 skipped in 525.95 seconds,
  plus TypeScript and web-console checks). Strict OpenSpec validation passed.

Known limitations:

- This is a Replay-only, fixture-only core: all 12 task inputs are synthetic and
  redacted. Network, model invocation, provider and enterprise credentials, Docker,
  public APIs, external executors/writes, customer resolution/success, and multi-Agent
  execution are disabled and tested as unavailable. The command bootstraps the local
  `weflow-testkit` source path, so the documented bare `python` invocation is supported.
- Quality scores are deterministic oracle scores only. The profile is not a live-model
  quality claim, a customer outcome claim, or authorization for any external effect.
- The suite deliberately remains at 12 tasks. The roadmap target of 60 tasks and any
  live-run capability are planned only; `planned_live_runs` remains zero.

Next-stage gate:

- Create and approve a new OpenSpec change before adding the 60-task corpus, model
  evaluation, providers, credentials, network access, customer data, or any external
  side effect. It must define task sampling, privacy/redaction and retention controls,
  tenant isolation, independent grading/evidence, cost and safety budgets,
  intent/reconcile/execute/complete behavior for every write, rollback, and live
  safety acceptance evidence.

## 18. Archived benchmark evidence-integrity repair (2026-08-05)

`repair-evaluation-benchmark-evidence-integrity` was archived as
`2026-08-05-repair-evaluation-benchmark-evidence-integrity`. Its three repaired
offline-benchmark requirements and one runtime-record linkage requirement were synced
to the main OpenSpec specifications before archive.

Verified facts:

- Every seed task now binds to an allowlisted checked-in fixture and policy source by
  safe repository-relative path, stable identity, and canonical content hash. The
  loader rejects missing, escaped, mutated, mismatched, duplicate-key, or task-local
  mirror inputs before opening a task store.
- The runner invokes public typed offline adapters and creates a fresh temporary SQLite
  store for each task attempt. The adapters return actual safe state, outcome, evidence,
  approval, tool, and effect observations; the runner no longer substitutes cached or
  hard-coded suite outcomes.
- Each execution emits and semantically validates the complete `EvaluationCase` ->
  `GraderResult` -> `RunMetrics` -> `EvaluationResult` -> `EvaluationSuiteReport`
  chain. Suite result IDs are the 12 distinct emitted `EvaluationResult` IDs, and every
  `EvaluationCase.input_hash` matches its resolved fixture source hash.
- The regenerated redacted report at
  `reports/change-6-evaluation-benchmark-core-acceptance.json` passed 12/12 tasks with
  zero failed or unscored tasks. Its report hash is
  `a3ea07d5c88f8249de49006665630aa244720a531d3cc72ae4bef216ac6a1d11`, and two
  fixed-baseline runs were equal.
- The 2026-08-05 checks passed: `python scripts/dev.py check`, `lint`, and `contracts`
  (Python 55 passed; TypeScript 37 valid / 29 invalid); benchmark acceptance; and
  `python scripts/dev.py test` (Python 234 passed, 2 skipped in 561.55 seconds, plus
  TypeScript contract and Web Console checks). Strict OpenSpec validation passed. The
  machine-readable verification record is
  `reports/repair-evaluation-benchmark-evidence-integrity-verification.json`.

Known limitations:

- The benchmark remains Replay-only, fixture-only, synthetic, redacted, and offline.
  Network, models, provider and enterprise credentials, public APIs, external writes,
  customer outcome claims, and multi-Agent execution remain disabled or unverified.
- Deterministic oracle scores demonstrate repository acceptance behavior only; they do
  not establish live-model quality, customer receipt/resolution, or authorization for
  an external side effect. The suite still contains 12 tasks, not the planned 60-task
  corpus.

Next-stage gate:

- Any corpus expansion, live-model evaluation, credential, provider, network
  destination, customer data, or external effect requires a separate approved OpenSpec
  change with privacy, isolation, budget, approval, intent/reconciliation, rollback,
  and live safety evidence.

## 19. Verified offline evaluation report console (2026-08-05)

`add-offline-evaluation-report-console` was archived as
`2026-08-05-add-offline-evaluation-report-console`. Its four console capability
requirements and the additive `EvaluationSuiteSnapshot` contract requirement were
synced to the main OpenSpec specifications before archive. The archived slice adds a
read-only projection and local operator view over the repaired canonical
`offline-seed.v1` report. It does not run the benchmark, mutate workflow state, or
enable a provider.

Verified facts:

- `EvaluationSuiteSnapshot` is a closed v1 JSON Schema with matching Python and
  TypeScript contracts. It binds tenant, suite, report, ordered result, source, task,
  oracle, gate, dimension, metric, and observation identities and rejects unsafe paths,
  duplicates, detached hashes, undeclared fields, and live or external-write claims.
- The canonical reader accepts only
  `reports/change-6-evaluation-benchmark-core-acceptance.json`, rejects duplicate JSON
  keys and unsafe report paths, reloads current source-bound tasks and oracles, and
  revalidates the complete EvaluationCase/GraderResult/RunMetrics/EvaluationResult
  evidence chain without creating a task store or invoking an adapter.
- `GET /v1/evaluations/offline-seed.v1` derives tenant identity from the allowlisted
  synthetic actor header and accepts no caller-selected report or suite. Missing and
  foreign reports share `404 evaluation_report_not_found`; unknown identity is `403`,
  arbitrary selectors are `422`, unsupported methods are `405`, and failed evidence
  integrity is `503 evaluation_report_not_ready` with no partial snapshot.
- The Vue console validates the complete response before rendering. It shows all 12
  bounded task summaries, one selected task, aggregate hashes/counts, hard gates,
  dimensions, observations, and offline counters. Loading, missing, denied, and
  integrity-not-ready states are safe; unrestricted JSON and raw exceptions are not
  rendered.
- The final acceptance report at
  `reports/add-offline-evaluation-report-console-acceptance.json` passed 12/12 tasks,
  with zero failed or unscored tasks. Repeated snapshot reads were equal. Source-report,
  retained-store, Case/workflow/approval/delivery, network, model, and external-write
  mutation or invocation counts were all zero.
- The accepted suite hash is
  `62683ba2880cd0ab9a96abc6f2f69cec6ca671c001b05de704f491afdd80be6b`, the repaired
  report hash is
  `a3ea07d5c88f8249de49006665630aa244720a531d3cc72ae4bef216ac6a1d11`, and the snapshot
  hash is `918a5959a6d5cb8046be8286b053391aceea9d7c65a2006724f8a1c59324c079`.
- The 2026-08-05 verification passed `python scripts/dev.py check`, `lint`, `typecheck`,
  and `contracts` (Python 72 passed; TypeScript 37 valid / 29 invalid); focused
  evaluation-console/API/reader tests (33 passed); and `python scripts/dev.py test`
  (Python 279 passed, 2 skipped in 470.27 seconds, plus TypeScript contracts and Web
  Console tests). The production Vite build transformed 13 modules and emitted 80.13 kB
  JavaScript (30.11 kB gzip). Final console acceptance and strict OpenSpec validation
  passed. Node `v24.16.0` and pnpm `11.9.0` were observed; Docker was unavailable and
  was not required.

Known limitations:

- This console is a local, synthetic, Replay-only observer over retained evidence. It
  cannot select another suite/report, rerun a workflow, approve an action, execute a
  tool, perform an external write, or declare customer success.
- Latency, tokens, model cost, live-run variance, customer receipt, and incident
  resolution are explicitly unavailable rather than inferred as zero or successful.
  Fixture-local delivery records remain distinct from provider or customer receipt.
- The suite remains 12 tasks. Live models, the planned 60-task corpus, real enterprise
  credentials, networked providers, customer data, live traces, external side effects,
  and multi-Agent coordination remain disabled or unimplemented.

Next-stage gate:

- Create and approve a separate OpenSpec change before expanding the corpus or enabling
  any model, credential, provider, network destination, customer data, live trace, or
  external effect. The change must define privacy/redaction and retention, tenant/role
  isolation, budgets, independent evidence/grading, approval, stable idempotency and
  natural keys, intent/reconcile/execute/complete handling, rollback, and live safety
  acceptance.
- A report, snapshot, offline score, fixture-local record, or provider acknowledgement
  MUST NOT alone establish customer receipt, incident resolution, Case completion, or
  permission for another side effect.

## 20. Archived offline Operator Case timeline (2026-08-05)

`add-offline-operator-case-timeline` was archived as
`2026-08-05-add-offline-operator-case-timeline`. Its four Operator Case timeline
requirements and the additive `OperatorCaseSnapshot` contract requirement were synced
to the main OpenSpec specifications before archive. The slice adds a fixed, read-only
Operator Case projection over the existing synthetic API-503 evidence; it does not add
a mutable Case source, Replay control, provider, or external effect.

Verified facts:

- `OperatorCaseSnapshot` is a closed v1 JSON Schema with matching Python and
  TypeScript contracts. It binds the tenant, fixture, Case revision, workflow,
  evidence/report/Replay roots, counts, capabilities, and a contiguous source-linked
  timeline with canonical hashes and hard-gate precedence.
- Two fresh public simulator runs in separate temporary SQLite stores produced the
  same snapshot byte-for-byte. The snapshot has 49 ordered entries: 48 actual evidence
  trajectory nodes and one terminal verification-Replay result. Its snapshot hash is
  `35d65b4ad7180fd2594a8531fc63851049a1779fe3028e36937aceb6e1c4afe1`.
- The timeline records 9 Case events, 1 revision, 13 workflow checkpoints, 4 Agent
  steps, 3 tool results, 2 fixture-local ticket effects, 1 fixture-local delivery
  effect, and 1 Replay result. Every entry maps to exactly one public source record;
  duplicate natural identities and idempotency keys are zero.
- The canonical reader accepts only
  `reports/add-offline-operator-case-timeline-acceptance.json`, rejects duplicate JSON
  keys, unsafe paths/fields, stale or detached evidence, and partial reports, and never
  creates or repairs a store or report.
- `GET /v1/operator/cases/api-503.v1` derives tenant identity from the allowlisted
  synthetic actor and accepts no caller-selected Case, report, path, tenant, or
  version. Missing and foreign evidence share `404 operator_case_not_found`; integrity
  failures are `503 operator_case_not_ready`, selectors are `422`, unknown actors are
  `403`, and unsupported methods are `405`.
- The Vue workspace validates all structure and content hashes before rendering. It
  shows all 49 entries, one source-linked detail, bounded counts/roots/capabilities,
  and five safe surface states. `DELIVERY_RECORDED (fixture-local)` is not presented as
  customer delivery, resolution, Case completion, or approval/workflow authority.
- The canonical acceptance report hash is
  `aeb098b415acd54c68bc61f1287e096d69fe1ab6440affc6b092c69364b44d71`.
  Its 18 negative scenarios emit only the four allowlisted safe classifications. Two
  baselines were equal, and default-store/source-report mutations, duplicate natural
  or idempotency identities, network/model/provider calls, external-write attempts,
  and unauthorized effects were all zero. Invalid pending publication preserves the
  prior report.
- The 2026-08-05 verification passed `python scripts/dev.py check`, `lint`,
  `typecheck`, and `contracts` (Python 98 passed; TypeScript 37 valid / 53 invalid);
  57 focused Operator Case tests; and `python scripts/dev.py test` (Python 336 passed,
  2 skipped in 674.60 seconds, plus TypeScript contracts and all Web Console checks).
  The production Vite build transformed 14 modules and emitted 96.79 kB JavaScript
  (34.03 kB gzip). Final Operator Case acceptance and strict OpenSpec validation passed.
  After spec sync, strict validation passed 20/20 active-change and main-spec items,
  and the active change list was empty after archive.

Known limitations:

- This view is fixed to one synthetic API-503 fixture and one retained report. It is
  offline, report-backed, read-only, and verification-Replay-only; it cannot list or
  select Cases, rerun a workflow, inject a fault, approve, retry, execute a tool,
  perform an external write, or declare customer success.
- Network, models, live providers, real credentials, customer data, customer
  receipt/resolution, Case completion, and multi-Agent coordination remain disabled,
  unsupported, or unverified. Fixture-local delivery is only a durable local record.

Next-stage gate:

- Interactive Replay or fault controls require a separate approved OpenSpec change.
  It must define a closed command contract, tenant/role authorization, immutable run
  identity, bounded fixture/fault selection, deterministic state ownership, budgets,
  idempotency and audit evidence, cancellation/recovery, and negative proof that an
  observer cannot mutate the source Case or grant approval, workflow, retry, provider,
  or external-write authority.

## 21. Archived bounded live-model evaluation (2026-08-06)

`add-bounded-live-model-evaluation` was archived as
`2026-08-06-add-bounded-live-model-evaluation`. Its seven delta capabilities were
synced into the main OpenSpec specifications before archive: 17 requirements were
added and 7 were modified, with no removals or renames.

Verified facts:

- A dedicated, explicit-confirmation command can create one OpenAI-compatible DeepSeek
  provider for a bounded synthetic investigation. Normal services and retained offline
  commands remain Replay-only; the live adapter is command-local and grants no workflow,
  approval, delivery, external-write, knowledge-publication, or multi-Agent authority.
- The retained real session completed 30/30 attempts and passed 330/330 deterministic
  hard-gate checks. The grounded happy path reached verifier-authorized
  `RESPONSE_READY` 5/5 times. Approval, delivery, and external business-write counts
  were all zero; credentials were not persisted.
- Observed usage was 100,739 tokens with estimated cost USD 0.01502032. The accepted
  report hash is `cba0b5450ded45a2bf1f3ec3af6ce5edc3a1253f3da083b93e98c9d976264dd9`;
  its source-linked verification hash is
  `33e3cf5809a40f5941dcfee4282dabf292ab8e2c59c86ff16b95140e23f0ebe3`.
  The final change-verification hash is
  `63f671bced8f2ea4b6e9d270f662a32ab9b5b4490dfdc7f6f21ced04175263e5`.
- Suite-level oracle success was 83.33%. `missing-information` matched its expected safe
  outcome 0/5 times: four attempts reached `response_ready` and one was
  `policy_denied`. This model-quality limitation is retained rather than hidden by
  weakening the accepted 100% hard-gate result.
- The final verification passed 71 focused live contract/provider/runtime/security/
  runner tests, secret hygiene with zero findings, Python/TypeScript lint, retained
  offline acceptances, and strict OpenSpec validation. Contracts passed 104 Python
  tests; the TypeScript corpus accepted 37 valid and rejected 60 invalid payloads.
  The full aggregate suite had previously passed 396 Python tests with 2 explicit
  service-boundary skips; Docker was unavailable.

Known limitations:

- The pilot uses six checked-in synthetic tasks, synthetic CRM/monitoring/knowledge
  reads, and five attempts per task. It is not the planned 60-task M1 corpus and does
  not establish production quality, customer receipt, incident resolution, or ROI.
- Missing-information behavior requires prompt/evaluator/product investigation before
  claiming uniformly reliable model quality. Five samples per task are too small for
  broad statistical conclusions, and provider cost is an estimate rather than an
  invoice.
- The dated DeepSeek model and price profile are evaluation evidence only and expire
  before 2026-09-06. A later live run requires official provider re-verification and a
  reviewed profile rather than silently reusing stale pricing.
- Real customer data, enterprise credentials, WeCom/Tencent/ticket connectors, real
  approval or outbound delivery, external business writes, production deployment,
  customer outcomes, knowledge publication, and multi-Agent coordination remain
  disabled, unsupported, or unverified. Docker-backed service boundaries were not
  live-verified on this workstation.

Next-stage gate:

- Start one new independently verifiable OpenSpec proposal before expanding the corpus,
  changing prompts/oracles, exposing live reports in an operator demo, adding a provider
  or connector, or enabling any external effect. The next portfolio-oriented increment
  should preserve the Replay default, synthetic no-write demo path, explicit live
  authorization, deterministic hard gates, report lineage, and honest capability labels.
- Any 60-task expansion must define sampling, holdout contamination controls, repeated
  live-run budgets, failure attribution, privacy/retention, and comparison baselines.
  Any external write still requires stable natural/idempotency keys, durable
  intent/reconcile/execute/complete evidence, tenant/role policy, independent approval,
  rollback, and proof that provider acknowledgement alone cannot establish customer
  receipt, resolution, Case completion, or permission for another effect.

## 22. Locked QQ integration roadmap (2026-08-10)

Product decision:

- The intended QQ form of WeFlow is one group containing the customer, a server-bound
  handler, and the robot. The customer starts a Case by mentioning the robot with an
  incident such as “广告系统出现了API 503错误”. Deterministic workflow code remains the
  system of record; QQ is an input/output surface, not the owner of workflow authority.
- The QQ work is split into the following three independently verifiable OpenSpec
  increments. Later stages MUST NOT be folded into an earlier stage merely because an
  API or credential is available.

### Stage 1: add-qq-sandbox-intake-and-ack

- One QQ sandbox application, one allowlisted group, one server-mapped tenant, and only
  group @机器人 text intake.
- Use the QQ WebSocket event path for the first vertical slice so no public callback is
  required. Normal services and CI stay offline/Replay-first.
- One accepted real QQ event creates the existing Case/CaseRevision/BusinessEvent
  ledger exactly once and causes one fixed, plain-text “已受理” passive acknowledgement.
- The acknowledgement is a narrowly scoped real external write. It MUST use durable
  intent, reconcile, execute, observe, and complete facts plus stable natural and
  idempotency keys. Lost response, reconnect, replay, restart, or duplicate input MUST
  NOT produce another logical Case or acknowledgement.
- This stage has no model, investigation tools, handler notification/approval, final
  answer, attachment handling, QQ mail, readable transcript retention, customer-receipt
  proof, resolution, or Case-completion authority.

### Stage 2: add-qq-handler-approval-and-delivery

- Bind one fixed handler to the tenant/group through server-owned identity mapping and
  notify that handler of the Case through a bounded QQ interaction defined by the
  stage-two proposal. Do not trust QQ nickname or caller-supplied role.
- Introduce the minimum reviewed retention/redaction boundary needed for the handler to
  see the relevant customer question; do not collect or forward the whole group chat by
  default. Whether same-group mention, direct QQ interaction, or QQ mail is permitted
  must be decided explicitly in that proposal, with same-group customer/handler/robot
  workflow as the target user experience.
- The handler can accept, edit, and approve an exact response candidate. Approval MUST
  bind the current tenant, Case/revision, handler identity/role, candidate hash,
  evidence hashes, policy/capability versions, checkpoint, and expiry.
- The robot, not an untracked manual handler message, sends the final reply to the
  original group so approval and delivery evidence stay bound. Delivery MUST recover
  from lost responses without a duplicate logical reply. Provider acknowledgement still
  does not prove customer receipt or issue resolution.

### Stage 3: enable-bounded-live-model-in-qq-workflow

- Promote the already bounded DeepSeek-compatible model path from its isolated
  evaluation command into the QQ Case workflow only after stages one and two pass.
- The model may use only explicitly authorized read-only CRM, monitoring, and knowledge
  evidence and may propose a response only up to RESPONSE_READY.
- Deterministic policy, budgets, verifier, evidence lineage, and workflow state remain
  outside the model. The model cannot select tenant/destination, approve itself, send a
  QQ message, declare delivery, resolve the Case, or claim customer success.
- Every final QQ send still requires a current handler approval bound to the exact
  candidate and evidence. Replay and offline synthetic paths remain available without
  QQ/model credentials.

Cross-stage hard gates:

- QQ application/group/member identities are mapped server-side; raw nicknames and
  QQ-reported roles are not authorization. Only allowlisted @机器人 messages enter the
  workflow, and unrelated group conversation is not harvested.
- Credentials, access tokens, raw private customer data, unrestricted provider output,
  and full transcripts do not enter prompts, logs, fixtures, reports, or ledger facts.
  Any later readable-content store requires explicit classification, retention,
  authorization, and deletion design.
- All real QQ writes are default-disabled and command/capability scoped. Every effect
  follows intent/reconcile/execute/observe/complete with a stable natural key and
  idempotency key; ambiguous observations remain incomplete.
- Reports distinguish implemented, fake-transport tested, QQ-sandbox live-verified,
  provider-accepted, customer-received, and customer-resolved. The latter two cannot be
  inferred from a send response.
- Multi-group/multi-tenant routing, formal production rollout, QQ mail, attachments,
  arbitrary bot commands, knowledge publication, and multi-Agent coordination require
  separate approved increments.

Current gate:

- add-qq-sandbox-intake-and-ack is the active proposal as of 2026-08-10. Its artifacts
  define the first stage only; application implementation and real QQ live verification
  remain unverified until Apply tasks and acceptance evidence pass.
- Stage 2 cannot begin until stage 1 proves one real allowlisted mention creates one Case
  and one provider-deduplicated fixed acknowledgement, with no duplicate, secret leak,
  model use, customer-receipt claim, or Case-completion claim.

## 23. QQ sandbox intake and fixed acknowledgement implementation (2026-08-10)

Verified implementation facts:

- `add-qq-sandbox-intake-and-ack` now implements the first QQ stage in application code.
  Five closed v1 contracts cover the payload-safe inbound event, Gateway cursor, and
  acknowledgement intent/observation/completion chain, with Python and TypeScript
  semantic validation and additive compatibility fixtures.
- The explicit `qq-sandbox-intake-ack --confirm-live-qq` command is the only path that
  imports the real adapter. It binds one process-supplied QQ application, one allowlisted
  sandbox group, one server-owned tenant, and exactly `qq.group_at.read` plus
  `qq.passive_ack.execute`. Ordinary commands reject visible QQ configuration before
  their handler runs; QQ cannot be combined with a live model, multi-Agent mode, general
  external writes, caller-selected content, destination, format, attachment, or reply
  sequence.
- The real adapter uses the current QQ Access Token, `/gateway`, WebSocket
  `GROUP_AND_C2C_EVENT (1 << 25)`, heartbeat/Resume protocol, and
  `/v2/groups/{group_openid}/messages`. It accepts only `GROUP_AT_MESSAGE_CREATE` plain
  text (`message_type=0`) from the configured group and sends only:
  `已受理，工单编号：{case_id}。当前仅确认已进入处理流程，不代表问题已解决。`
  with the original `msg_id` and deterministic `msg_seq=1`.
- Raw message text is hashed and discarded before the Case ledger. App/group/member and
  session identities are hashed in durable business/cursor records. Credentials,
  authorization headers, raw provider bodies, display names, attachments, ARK/chat
  elements, and transcripts are absent from contracts, logs, fixtures, reports, and the
  Case ledger. Only the opaque group/source locators needed for reply recovery remain in
  the bounded adapter journal and expire after 24 hours.
- One accepted source natural key creates exactly one Case, immutable CaseRevision 1,
  three initial BusinessEvents, and one acknowledgement natural key. QQ Gateway sequence
  is session-scoped: a new `READY` session resets the transport cursor, while business
  deduplication remains stable across sessions and excludes the Gateway sequence from the
  source fingerprint. Same-session gaps or new out-of-order messages fail before Case
  creation.
- Acknowledgement execution follows intent, local/provider reconcile, execute, observe,
  and complete. Provider code `40054005` is the documented QQ deduplication outcome and
  may prove the one logical acknowledgement present. Timeout, disconnect, oversized or
  unreadable response, conflict, unauthorized capability, and expiry do not complete the
  intent. Startup recovers one eligible pending intent before listening for a new event,
  reusing the original `msg_id + msg_seq`; expired, unauthorized, or conflicting facts
  are not automatically resent. Access tokens refresh with a 60-second safety margin.
- Fake Gateway runs cannot select live evidence mode. The offline acceptance and live
  report types are different, and the strict verifier requires real-adapter mode plus a
  completion record before `qq_sandbox_live_verified=true`. Every report still fixes
  `customer_receipt_verified=false`, `case_completion=false`, `issue_resolution=false`,
  `final_delivery=false`, `model_invocation=false`, and `production_ready=false`.

Verified evidence and metrics:

- `reports/add-qq-sandbox-intake-and-ack-offline-acceptance.json` passes the independent
  offline verifier and covers 14 duplicate, sequence, concurrent, reconnect, restart,
  lost-response, timeout/disconnect, deduplication, conflict, unreadable, expiry, and
  capability scenarios. Three consecutive runs produced the identical SHA-256
  `308d07e2eac5065a16e292ab187a945456beafe7452fb7e33ccfd3410d294fbc`.
- All QQ-named contract/unit/recovery/security/e2e tests pass: 89 passed in the final
  focused run. The full repository baseline passes with 488 Python tests, 2 expected
  Docker/service-boundary skips, TypeScript contract validation of 42 valid and 68
  invalid payloads, and successful web-console status/evaluation/operator verification
  plus production build.
- The full Python contract suite passes 115 tests. Secret hygiene reports zero findings;
  Ruff, TypeScript lint, and TypeScript typecheck pass. Nine retained Case intake,
  durable workflow, investigation, policy/approval, evidence, benchmark, evaluation
  console, operator timeline, and archive-evidence acceptance commands all returned exit
  code 0. Strict OpenSpec validation returned one passed change and zero issues.

Live-versus-fake status and limitations:

- The implementation is offline/fake-transport verified but NOT QQ-sandbox
  live-verified. No real AppID/AppSecret, group OpenID, QQ event, Access Token, or provider
  send response was supplied in this Apply session. OpenSpec tasks 5.2 and 5.3 therefore
  remain intentionally incomplete; no live report is checked in and no provider/customer
  outcome is claimed.
- This stage remains one application, one group, one tenant, one group-mention text
  intake, a hash-only Case source, and one fixed passive acknowledgement. It does not
  retain handler-readable customer text, notify or bind a handler, support QQ mail,
  attachments, arbitrary commands, multiple groups/tenants, investigation tools, a live
  model, approval, a final customer answer, customer receipt, issue resolution, Case
  completion, or production rollout.
- The real command and current QQ protocol fields are implemented and tested with fakes,
  but sandbox/formal-environment behavior, portal permission setup, real rate limits,
  provider deduplication response, and end-user client rendering remain unverified until
  an operator performs the bounded live run in the documented sandbox group.

Next-stage gate:

- Complete tasks 5.2 and 5.3 only with operator-supplied process-local QQ sandbox
  credentials and one allowlisted test group: observe one real `@机器人 广告系统出现了API
  503错误` event, verify one Case plus one provider-accepted/present fixed
  acknowledgement, then exercise reconnect/provider deduplication without a second Case
  or logical acknowledgement. Ambiguity remains `NEEDS_RECONCILIATION` and does not pass
  the gate.
- `add-qq-handler-approval-and-delivery` must not start until that live evidence passes,
  contains no raw private values, and still makes no customer-receipt, resolution, or
  Case-completion claim. Stage two must separately decide minimum readable-content
  retention/redaction, bind one server-owned handler identity, and verify exact candidate
  approval plus idempotent final group delivery. Stage three live-model integration
  remains blocked behind both stages.

## 2026-08-10: Secure QQ first-group pairing Apply snapshot

Implemented facts:

- `add-secure-qq-first-group-pairing` now provides a dedicated
  `qq-sandbox-pair-group --confirm-live-qq-pairing` read-only command. It generates
  one at-least-128-bit, five-minute `WFPAIR-` challenge and can construct only the QQ
  token, Gateway, WebSocket, heartbeat, and resume read path. It constructs no QQ
  sender, Case ledger, workflow, Agent/model, approval, handler, or business tool.
- The challenge plaintext is process/terminal-only. SQLite stores its SHA-256 and
  append-only lifecycle evidence. A completed binding stores a safe `qqpair_` ID and
  hashes in payload-safe evidence; the raw `group_openid` exists only in the private
  locator table in `.weflow/qq-sandbox.sqlite3`, expires within 24 hours, and can be
  locally revoked.
- Matching accepts only one plain `GROUP_AT_MESSAGE_CREATE`, `message_type=0`, no
  attachment/card/nested elements, valid member/message/group identities, and content
  exactly equal to the active challenge after bounded mention removal/whitespace
  normalization. Member identity, raw event, message text, credentials, and tokens are
  not persisted or reported.
- Duplicate and concurrent matching events converge to one completion. Restart before
  completion cancels the unusable digest-only challenge and creates a new one; restart
  after completion resolves the durable safe pairing. Different-group reuse conflicts,
  and sequence gaps, expiry, revocation, foreign AppID, missing/corrupt locator, caller
  group/tenant overrides, expanded capabilities, model/write scope, and external stores
  fail closed.
- Stage 1 now supports mutually exclusive direct-group and safe-pairing selectors. The
  pairing ID is resolved and AppID/tenant/status/expiry are checked before constructing
  the Stage 1 network, Case ledger, or passive sender. Stage 1 still requires its
  process-only identity salt and exact `qq.group_at.read,qq.passive_ack.execute`
  capability profile. `WFPAIR-` is reserved at normal intake before any receipt,
  Case, acknowledgement intent, or send.
- Separate offline/live v1 report contracts fix Case creation, workflow activation, QQ
  writes, acknowledgement, model, handler binding, customer receipt, resolution, Case
  completion, production readiness, and Stage 1 verification to false. Fake transports
  cannot publish live verification. Offline report
  `reports/add-secure-qq-first-group-pairing-offline-acceptance.json` independently
  verifies with SHA-256
  `a6af49f2a18ec2e0ed855d90bdb92be1fbdbef0421f0f06d63fb45f8c3dd677a`.

Verification facts:

- Pairing-specific tests pass 16/16; all QQ-named tests pass 105/105. Python contracts
  pass 121/121. TypeScript contracts retain 42 valid and 68 invalid results.
- The complete Python suite passes 504 tests with 2 expected service-boundary skips
  when run with the isolated repository-local pytest temporary root. Two earlier runs
  against the Windows system Temp had non-repeatable historical SQLite `disk I/O
  error` failures; the failed tests passed individually and the isolated complete run
  passed.
- Secret scanning reports zero findings. Ruff, TypeScript lint/typecheck, the full
  TypeScript tests, console checks, production Vite build, strict OpenSpec validation,
  independent pairing report verification, and `git diff --check` pass.
- Retained Change 1-6, evaluation-console, operator-timeline, and prior QQ offline
  acceptances returned exit code 0. `archive-evidence-check` remains failed with
  `documentation_report_path_untracked` because the preceding active QQ change/report
  is still uncommitted; this is a working-tree evidence limitation, not treated as pass.

Live status and next gate:

- No real AppID/AppSecret, real QQ event, or controlled test-group challenge was supplied
  in this Apply session. Real pairing tasks 5.2/5.3 remain incomplete; the retained
  offline report has `qq_group_pairing_live_verified=false` and
  `stage1_verified=false`.
- The existing `add-qq-sandbox-intake-and-ack` live tasks 5.2/5.3 also remain
  independently incomplete. A real pairing does not prove API-503 intake or a provider
  acknowledgement.
- Next, the operator must run the documented live pairing command with process-only
  sandbox credentials, send exactly the displayed challenge in one controlled group,
  independently verify the live report, and use only its safe pairing ID to pass Stage
  1 pre-contact readiness. Do not send the API-503 message until that prerequisite is
  verified.

## 2026-08-10: Secure QQ first-group pairing live closure

Live-verified facts:

- The operator supplied process-only sandbox credentials and sent the exact displayed
  challenge through a real robot mention in one controlled non-production QQ group.
  `reports/add-secure-qq-first-group-pairing-live.json` records one completed binding:
  report `qqpr_4b072fcb4923cd001111f5bac9c972cc`, safe pairing ID
  `qqpair_d450e2c542fc51e8b59beacdbffb9505`, and report SHA-256
  `a90e462c98a92186a1a458616dfa37179f839d1fd1574781d353099f3710577a`.
  `qq_group_pairing_live_verified=true`; QQ writes, Case/workflow/model activation,
  handler binding, customer receipt, issue resolution, Case completion, production
  readiness, and Stage 1 verification remain false.
- The independent verifier passed the live report. The safe pairing ID, and no raw
  group locator, then passed the Stage 1 selector/configuration pre-contact gate.
  `reports/add-secure-qq-first-group-pairing-stage1-readiness.json` records
  `selector_resolved=true`, `readiness.ready=true`, `network_contacted=false`,
  `case_creation=false`, `qq_write_attempted=false`, and `stage1_verified=false`.
- The live command now displays its challenge only after QQ Gateway `READY`, appends an
  `EXPIRED` lifecycle event and exits when the five-minute deadline elapses, separates
  Token transport failure from Gateway endpoint failure, and provides
  `qq-sandbox-intake-ack --readiness-only` for a canonical no-network handoff check.

Closure verification:

- All QQ-named tests pass 110/110; the complete Python suite passes 509 tests with 2
  expected service-boundary skips. Python contracts pass 121/121; TypeScript contracts
  retain 42 valid and 68 invalid fixture results. Project lint, typecheck, TypeScript
  tests/build, secret hygiene with zero findings, independent live-report verification,
  strict OpenSpec validation, and `git diff --check` pass.
- The four pairing delta specs were synced before archive: the new
  `secure-qq-first-group-pairing` main capability contains 7 requirements, while
  `safe-provider-runtime-boundary`, `versioned-domain-contracts`, and
  `workspace-operability` received 2, 2, and 1 additive requirements respectively.
  No requirement was removed or renamed.

Archive result and next gate:

- `add-secure-qq-first-group-pairing` is archived as
  `2026-08-10-add-secure-qq-first-group-pairing` with all 20 tasks complete and its
  `.openspec.yaml` metadata preserved.
- This archive proves only real read-only discovery and binding of one controlled QQ
  group. It does not prove Stage 1 Case intake or the fixed acknowledgement external
  write, and it does not authorize handler notification, approval, final delivery,
  customer receipt, issue resolution, Case completion, production rollout, or a model.
- Resume `add-qq-sandbox-intake-and-ack` tasks 5.2/5.3 next. The operator must send one
  real allowlisted `@robot API-503` message and retain a separately verified live report
  showing one Case and one provider-accepted/present fixed acknowledgement without a
  duplicate logical effect or any customer-success claim.
## 2026-08-10: QQ sandbox Stage 1 live intake/ack closure

Live-verified facts:

- `reports/add-qq-sandbox-intake-and-ack-live-acceptance.json` records one real
  allowlisted group mention accepted as Case
  `case_1b52609062ed680ed2f2c072c0b0aaa6`, with exactly one acknowledgement intent,
  observation, and completion. The fixed passive acknowledgement was visible in the
  controlled QQ group. The report and independent `live` verifier passed with
  `accepted=true`, `qq_sandbox_live_verified=true`, and
  `acknowledgement_status=completed`.
- `reports/add-qq-sandbox-intake-and-ack-live-dedup.json` records a second controlled
  real event for the bounded same-frame deduplication procedure. Its one in-memory
  replay returned the original Case `case_cace369cb85a9ee3e043a5684c9345eb` and original
  acknowledgement intent. The report has `duplicate_event_count=1`, all per-run
  Case/intent/observation/completion deltas equal to one,
  `same_event_deduplication_verified=true`, `second_qq_write_attempted=false`, and
  `second_logical_acknowledgement=false`. The independent `live-dedup` verifier passed.
- Both live reports keep raw-message, transcript, credential, and unrestricted provider
  response persistence false. They keep model invocation, handler approval, final
  delivery, customer receipt, issue resolution, Case completion, and production
  readiness false. Provider acceptance proves only the fixed sandbox acknowledgement
  boundary, not that a customer read it or that the issue was resolved.

Implementation and verification closure:

- The explicit `--verify-live-event-dedup` mode processes one new real QQ event normally,
  then passes that identical provider frame through deterministic intake a second time
  while it remains in memory. Existing Case and acknowledgement completion facts stop
  the second pass before another QQ transport call. The raw frame is discarded on exit
  and cannot be reconstructed from durable private chat data.
- `add-qq-sandbox-intake-and-ack` now has all 24 tasks complete. QQ-selected
  unit/recovery/security tests pass 92/92; the focused runner/report/runbook suite passes
  19/19. The complete Python suite passes 510 tests with 2 expected skips. TypeScript
  contracts retain 42 valid and 68 invalid fixture results; console status, evaluation,
  operator-timeline checks, and the production Vite build pass. Ruff lint/format,
  independent live and live-dedup report verification, strict OpenSpec validation, and
  `git diff --check` pass.

Next-stage gate:

- Stage 1 now proves one controlled sandbox group's real `@robot` text intake, exact
  Case/acknowledgement reuse for the same observed source event, and one fixed passive
  acknowledgement. It still does not implement readable handler content retention,
  handler notification, QQ mail, handler editing/approval, final customer delivery,
  live model/tool investigation, attachments, multiple groups/tenants, or production
  QQ readiness.
- `add-qq-handler-approval-and-delivery` may be proposed next as a separate vertical
  change. It must decide approved customer-content retention/redaction and then prove
  handler binding, notification, immutable edit/approval, and final-delivery recovery
  without granting the model or QQ input authority.

## 2026-08-11: QQ sandbox Stage 1 spec sync and archive

Archive facts:

- All 24 `add-qq-sandbox-intake-and-ack` tasks and all four planning artifacts were
  complete before archive. The change-level strict validation passed immediately
  before sync and archive.
- All five Stage 1 delta capabilities were synced to main specifications. A new
  `qq-sandbox-intake-and-ack` main spec contains 7 requirements;
  `case-event-ledger` received 1 added requirement and 1 modified requirement;
  `idempotent-side-effect-recovery` received 2 added requirements;
  `safe-provider-runtime-boundary` received 2 modified requirements; and
  `versioned-domain-contracts` received 2 added requirements. No requirement was
  removed or renamed.
- Post-sync strict validation passed 25/25 active-change and main-spec items with zero
  failures. Every Stage 1 delta requirement heading was present in its corresponding
  main specification.
- The change is archived as
  `openspec/changes/archive/2026-08-11-add-qq-sandbox-intake-and-ack`, with its
  `.openspec.yaml`, proposal, design, delta specs, and completed tasks preserved.

Verified boundary after archive:

- The archive carries forward the already retained live facts: one controlled QQ
  sandbox-group mention created one Case and one fixed passive acknowledgement, and a
  bounded same-event replay reused the same Case/acknowledgement without a second QQ
  write. These facts still do not prove customer receipt, issue resolution, Case
  completion, final delivery, production readiness, or model quality.
- Stage 1 still retains no readable customer transcript and grants no handler binding,
  C2C handler notification, drafting, approval, final answer, attachment, QQ mail,
  multi-group/multi-tenant, model, or production authority.

Next-stage gate:

- `add-qq-handler-approval-and-delivery` may now enter Apply only from its reviewed
  active OpenSpec artifacts. Handler work is confidential: issue pull, task context,
  draft/edit/reject, and approval preview stay in the dual-bound handler's QQ C2C;
  the original group carries only a non-sensitive nudge, metadata-only approval, and
  the final approved reply. Active C2C notification is at-most-once and an ambiguous
  result is not retried or called delivered.
- Stage 3 live-model integration remains blocked until Stage 2 implementation, offline
  privacy/recovery verification, real sandbox handler binding, exact approval, and
  final-delivery evidence all pass without customer-success or production claims.

## 2026-08-12: QQ sandbox Stage 2 handler approval/delivery archive

Live-verified facts:

- One operator-confirmed dual-surface handler binding completed against the previously
  paired sandbox group. The live flow kept the customer issue, private pull/accept,
  draft creation and replacement, and draft previews in QQ C2C. The group carried only
  metadata-only approval and the exact final approved reply.
- `reports/add-qq-handler-approval-and-delivery-live.json` records binding
  `qqhbind_e65300fbc9ac0b075e2563aecc83ded5`,
  `dual_surface_binding_verified=true`, `private_workflow_verified=true`,
  `group_approval_verified=true`, `notification_attempt_count=1`,
  `notification_status=accepted`, `artifact_deletion_verified=true`, and
  `final_provider_accepted=true`. The independently verified report digest is
  `d401b44e2c0fca08198493a774a29ab25d03a408b3bda602ca1fcae6b81fed7f`.
- The approved reply `SYNTHETIC_RESPONSE_V2` was visible in the controlled group.
  Provider acceptance does not prove customer receipt, issue resolution, Case
  completion, or production readiness; all four remain false. Model invocation also
  remains false.

Implementation and verification closure:

- The notification attempt budget is scoped to the current Case and handler binding,
  so historical notification attempts cannot exhaust a newly paired workflow. Exact
  matching confirmed bindings can be reconciled after report/output interruption
  without repeating the dual challenge or contacting QQ.
- The Stage 2 focused QQ handler suite passes 98/98. Ruff lint and format checks,
  privacy/secret scanning with zero findings, independent live-report verification,
  strict change validation, and `git diff --check` pass.
- All 50 tasks and all planning artifacts were complete before archive. The eight
  delta specs added 34 requirements: 9 in the new
  `qq-handler-approval-and-delivery` main capability, plus 3, 3, 4, 4, 4, 4, and 3
  requirements in `case-event-ledger`, `hash-bound-approval-gates`,
  `idempotent-side-effect-recovery`, `policy-capability-gates`,
  `response-candidate-verification`, `safe-provider-runtime-boundary`, and
  `versioned-domain-contracts`. No requirement was modified, removed, or renamed.
- The change is archived as
  `openspec/changes/archive/2026-08-12-add-qq-handler-approval-and-delivery`, with its
  `.openspec.yaml`, proposal, design, delta specs, and completed tasks preserved.

Verified boundary and next gate:

- The live binding assurance is `operator_confirmed_dual_challenge`, not a
  provider-documented cross-surface identity proof. The slice covers one sandbox App,
  tenant, group, and handler; it does not enable models, business tools, QQ mail,
  attachments, multiple groups/handlers/tenants, automatic issue resolution, or
  production rollout.
- Stage 3 requires a separate OpenSpec change for bounded model-assisted investigation
  and private drafting. Deterministic workflow code must retain state, policy, tool and
  evidence gates, approval authority, final-write authority, retry/reconciliation, and
  completion decisions. The model must not see unrestricted QQ/provider data, approve
  itself, send directly, or claim resolution/customer receipt.

## 2026-08-12: QQ Stage 3 bounded live-model Apply snapshot

Verified implementation facts:

- `enable-bounded-live-model-in-qq-workflow` adds the exact private command
  `WF-ASSIST <case_id> <expected_version>` only after the current bound handler has
  privately pulled and accepted the current Case. Customer messages do not invoke the
  model automatically. Group text, free-form command bodies, stale identities or
  versions, unsafe issue egress, and expanded capabilities fail before model contact.
- The dedicated runner composes the existing Stage 1 ACK and Stage 2 private
  notification/pull/accept/draft/metadata-only approval/final passive-reply boundaries
  with a separate bounded model provider. The model can request only the reviewed CRM,
  monitoring, and knowledge reads from checked-in synthetic fixtures; it cannot select
  a QQ destination, mutate a business system, approve, deliver, complete a Case, or
  declare customer receipt or resolution.
- The checked-in profile binds DeepSeek `deepseek-v4-flash`, JSON-object structured
  output, the public HTTPS endpoint, dated price metadata, exact QQ/model capabilities,
  a 6-call/3-tool/14,000-token/60-second/USD-0.50 cumulative Stage 3 Case budget, and 24-hour
  restricted-content retention. Live construction validates selectors, public DNS,
  profile/source hashes, price validity, capabilities, and budgets before reading either
  process-only credential.
- The Stage 3 cumulative Case budget is independently hash-bound in
  `evals/qq-model/stage3-case-budget.v1.json`; the retained six-task live-evaluation
  attempt budget remains USD 0.02 and is not enlarged by Stage 3.
- Assist requests, Context bindings, invocation intent/observation, normalized actions,
  tool evidence, budgets, candidates, verification, approval, deletion, and QQ effects
  are append-only and naturally idempotent. Ambiguous provider contact becomes
  `provider_outcome_unknown`, consumes pessimistic budget, advances to a safe manual
  fallback version, and is never automatically retried. Conclusive work is reused after
  restart; an interrupted pre-provider policy denial also resumes with zero model calls.
- Model candidates and issue views remain private. Human `WF-DRAFT` atomically replaces
  and invalidates model candidate/provenance/approval reachability. Replacement,
  rejection, final QQ provider acceptance, and 24-hour expiry remove restricted content
  while retaining content-free lifecycle evidence.

Verified offline evidence and checks:

- `reports/enable-bounded-live-model-in-qq-workflow-offline-acceptance.json` independently
  verifies one Case, ACK, handler notification/pull/accept/assist, four replay-fake model
  turns, three synthetic tool results, one private preview, exact group approval, one
  fake final provider acceptance, and two artifact deletions. After the reviewed
  Stage 3 Case budget/profile update, its current report SHA-256 is
  `1da22c53bd070fd6bbbab220ba1f4d5b62400ad6405d97afffaa9dd6cbb8c680`;
  verification SHA-256 is
  `1bc64431bff305ea860a029aa8ff3295ef20ff87bca18e68e6a6ff334c3e09fd`.
  Network contact and external writes are false, as are customer receipt, issue
  resolution, Case completion, live-model contact, and production readiness.
- The Stage 3 focused suite, including completed-Case report recovery and fake
  zero-usage rejection, passes. The final complete Python run collected 662 tests:
  660 passed and 2 expected service-boundary skips. Python contracts passed
  141/141; QQ-selected tests passed 251/251; TypeScript contracts retained 42 valid and
  68 invalid fixtures, and TypeScript lint/typecheck/tests plus the web-console build
  passed. Ruff lint, Stage 3 targeted format, secret scanning with zero findings, and
  retained offline acceptances passed.
- Full-repository `ruff format --check .` remains unsuccessful because 51 existing or
  unrelated files would be reformatted; they were not bulk-rewritten. The archive
  evidence checker now allowlists the existing content-free QQ Stage 0-3 report paths
  and passes with 31 documented reports and 2 historical manifests. The format
  limitation is not converted into a pass.

Live-verified integrated evidence and remaining boundary:

- A fresh controlled sandbox Case traversed real QQ intake/fixed acknowledgement,
  private handler pull/accept/assist, four actual DeepSeek calls, the three reviewed
  fixture-local CRM/monitoring/knowledge reads, one verifier-authorized private model
  candidate, exact metadata-only group approval by the bound handler, and one
  provider-accepted passive final QQ reply. The current active handler binding is
  `qqhbind_88a57460ba6e8c8a18c723a963d10ff0`.
- The accepted report records 4 provider calls, 4,527 input tokens, 452 output tokens,
  4,979 total tokens, estimated cost USD 0.00076034, 6,260 ms provider latency,
  6,460 ms end-to-end latency, 3 tool results, one candidate, one approval decision,
  one final reply, and two restricted-artifact deletions. Its canonical mode is
  `qq-model-integrated-live`, while the nested QQ provider mode remains
  `qq-sandbox-live`.
- The original live command completed the external effect but initially failed report
  schema validation because the runner incorrectly used the QQ provider mode as the
  top-level integrated workflow mode. The implementation now uses the contract-defined
  mode and provides `--recover-completed-case`, which rebuilds reports only from a
  current `FINAL_ACCEPTED` Case with complete positive-token model, tool, candidate,
  approval, final-effect, and deletion evidence. Recovery was executed with all three
  provider credentials absent and performed no network contact, model call, Case
  mutation, or external write.
- `reports/enable-bounded-live-model-in-qq-workflow-live-acceptance.json` has report
  SHA-256 `7d5ba73ce84ed9bfa268c3d315317c94782bc7c929758ca09afc3d56f22162e1`.
  `reports/enable-bounded-live-model-in-qq-workflow-live-verification.json` passed the
  no-network/no-credential independent verifier with verification SHA-256
  `125702f4fc89636772757fcf9117edc1bfd15905f6de8338d97b7faa2708ed4c`.
- The retained Change 1-6, console, Operator Case, QQ Stage 0-3 offline acceptances,
  independent offline/live Stage 3 verification, and the 900-second-bounded aggregate
  check all passed. The aggregate rerun completed in about 322 seconds; its historical
  manifest-bound report file was then restored byte-for-byte rather than rewriting
  archived evidence.
- This is one integration and hard-gate proof, not a statistically meaningful model
  quality result. Customer receipt, issue resolution, Case completion, production
  readiness, real CRM/monitoring/knowledge connectors, additional groups/handlers/
  tenants, attachments/mail, and multi-Agent collaboration remain false, disabled, or
  unimplemented. Strict final validation subsequently passed; spec sync and archive are
  recorded below.

## 2026-08-12: QQ Stage 3 bounded live-model archive closure

Archive and specification closure:

- All 68 implementation tasks and all planning artifacts were complete before archive.
- The nine Stage 3 delta specs were synchronized into main specs as 31 semantic
  changes: 16 added requirements and 15 modified requirements, with no removals or
  renames. The new `bounded-live-model-qq-workflow` main capability was created, and
  existing scenarios not targeted by the deltas were preserved.
- Post-sync verification found all 31 delta requirement headings and all 80 delta
  scenario headings exactly once in the corresponding main specs. Strict validation
  passed for the change and for all 26 current OpenSpec items; the synchronized spec
  files also passed `git diff --check` apart from non-failing Windows line-ending
  notices.
- The complete change is archived at
  `openspec/changes/archive/2026-08-12-enable-bounded-live-model-in-qq-workflow`, with
  `.openspec.yaml`, proposal, design, nine delta specs, and completed tasks preserved.

Verified evidence retained by the archive:

- The live sandbox proof remains one real QQ Case with fixed acknowledgement, private
  handler pull/accept/assist, four actual DeepSeek calls, three reviewed fixture-local
  read tools, one verifier-authorized private candidate, exact metadata-only human
  group approval, and one provider-accepted passive final QQ reply.
- The accepted run retained 4,979 total tokens, estimated cost USD 0.00076034,
  6,260 ms provider latency, and 6,460 ms end-to-end latency. The acceptance report
  SHA-256 is `7d5ba73ce84ed9bfa268c3d315317c94782bc7c929758ca09afc3d56f22162e1`;
  the independent verification SHA-256 is
  `125702f4fc89636772757fcf9117edc1bfd15905f6de8338d97b7faa2708ed4c`.
- The complete Python run remains 660 passed and 2 expected service-boundary skips;
  contract, QQ-selected, TypeScript, web-console, lint, secret-scan, retained evidence,
  and archive-evidence checks passed. Full-repository `ruff format --check .` remains a
  documented limitation because 51 existing or unrelated files would be reformatted.

Verified boundary and next gate:

- This archive does not prove customer receipt, issue resolution, Case completion,
  production readiness, model quality at scale, real enterprise data access, multiple
  groups/handlers/tenants, attachments/mail, or multi-Agent collaboration.
- The original three-step QQ route is now implemented and sandbox-live-verified:
  secure first-group pairing, intake/fixed acknowledgement, private handler approval
  and delivery, followed by bounded handler-triggered live-model assistance.
- Any next increment requires a separate OpenSpec change. The narrow recommended gate
  is to replace exactly one fixture-local investigation read with a tenant-scoped,
  read-only real business connector while preserving replay fixtures, model-external
  policy and budget checks, evidence lineage, private previews, exact human approval,
  and deterministic QQ delivery. Real business writes and production rollout remain
  disabled until separately proposed and verified.
