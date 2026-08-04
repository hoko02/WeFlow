# WeFlow 项目长期记忆

> 最近更新：2026-08-03
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

- All 23 Change 4 tasks completed. Offline `check`, `lint`, `contracts`, `test`, and
  `policy-approval-acceptance` passed; the final suite reported 169 passed and 2
  explicit Docker/service-boundary skips. The strict Change and main-spec OpenSpec
  validations passed. Evidence is retained in `reports/change-4-acceptance.json` and
  `reports/change-4-openspec-validation.json`.

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
  credential, or Node runtime. Node remains necessary for the TypeScript contract and
  Web Console checks. Docker is unavailable on the verification workstation, so
  Temporal/service-boundary behavior is explicitly not live-verified.
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