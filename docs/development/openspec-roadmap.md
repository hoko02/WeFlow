# WeFlow 的 OpenSpec 分步开发路线

## 1. 交互协议

本项目沿用 ForgeCode 的交互方式，但把阶段切得更小。每次开始工作时：

1. 阅读 `README.md` 和 `docs/PROJECT_MEMORY.md`；
2. 执行 `openspec list --json`；
3. 若有目标 change，执行 `openspec status --change "<name>" --json`，只读取 CLI 返回的实际 artifact 路径；
4. 先说明本轮是 Explore、Propose、Apply、Validate 还是 Archive；
5. 不跨 change 偷做未来功能，不把未验证任务标成完成。

### Explore

适用于需求澄清、架构比较、失败分析和范围调整。允许读取代码和创建用户明确要求的设计/规格文档，但不实现业务代码。

```text
/opsx:explore
/opsx:explore <change-name>
```

### Propose

一次 proposal 只交付一个可验收的纵向增量。proposal 必须写 Why、What、Non-goals、Capabilities、Impact；design 必须写状态、合同、故障路径、策略和验收；tasks 必须包含实现与验证。

```text
/opsx:propose "建立 WeFlow 工程基线和领域合同"
```

### Apply

按 CLI 的 `contextFiles` 读取全部 artifact，逐项实现并在验证通过后立即勾选任务。若实现推翻设计，暂停并返回 Explore/更新 artifact。

```text
/opsx:apply <change-name>
```

### Validate 与 Archive

完成要求不只是测试通过，还要有机器可读报告、文档更新和已知限制。归档前执行：

```powershell
openspec validate <change-name> --type change --strict
openspec status --change "<change-name>"
```

随后使用 `/opsx:archive <change-name>`，并在需要时 `/opsx:sync`。归档后更新 `docs/PROJECT_MEMORY.md` 中的实现事实与下一阶段门槛。

## 2. Change 0：`establish-weflow-foundation`

**目的**：建立可启动、可检查、无业务假实现的单仓库基线和版本化领域合同。

**范围**：

- uv/pnpm workspace、统一开发脚本、基础 CI 和秘密扫描；
- Platform API、Control Worker、Agent Runtime、Business Simulator、Web Console 的可启动空壳；
- Case、Revision、事件、Artifact、Policy、Approval、Evaluation 核心 schema；
- JSON Schema/OpenAPI/TypeScript 合同生成与兼容性测试；
- PostgreSQL/Temporal/对象存储/OTel Compose；
- Replay/live provider 配置边界，不接真实模型。

**验收**：单命令检查环境；所有进程有 health/readiness；合同跨 Python/TypeScript 一致；仓库无真实凭据；不宣称已有业务闭环。

## 3. Change 1：`add-case-intake-and-simulator`

**目的**：把重复、乱序的 IM 事件稳定转化为 Case，并建立确定性业务环境。
> 已归档：`2026-07-29-add-case-intake-and-simulator`。实际交付仅为离线、fixture 驱动的合成接入与本地账本，不包含业务工具或事故处置工作流。

**范围**：

- `InboundMessageEvent`/`CaseProjection` 合同、规范化、哈希和幂等去重；
- 离线 SQLite Case/CaseRevision/追加事件账本、派生投影与重启校验；
- 仅 fixture 的 IM Simulator、合成 actor 映射、租户范围 API 读取与快照恢复；
- actor 派生 tenant、跨租户不披露、冲突/乱序的安全错误码；
- API-503 的首次、重复、乱序三个合成黄金 fixture。

**验收**：首次投递只创建一个 Case、Revision 1 与三条事件；重复不写入；跨 tenant 不披露；快照可导出/恢复；乱序事件有稳定错误码。

## 4. Change 2：`add-durable-support-workflow`

**目的**：建立从合成 Case 接入到 fixture-local 工单交接的持久化 Workflow 主干，不产生回复候选或解决结论。

**范围**：

- driver-neutral 状态机、checkpoint、恢复扫描和合成 SLA timer；
- `RECEIVED`、`TICKET_READY`、`PAUSED`、`WAITING_FOR_OPERATOR`、`NEEDS_RECONCILIATION`、`CANCELLED`；
- tenant 派生的 pause/resume/cancel 与 expected-version 命令；
- fixture-local 工单 find-or-create、expected-version handoff 和 `intent/reconcile/execute/observe/complete`；
- Worker 中断、响应丢失与 reconciliation timeout 故障注入；
- 使用同一 reducer/journal 的 opt-in、loopback-only Temporal service-boundary driver。

**验收**：每个声明的持久化边界中断后均可离线恢复；本地工单 create/update 操作各至多一次；未知或冲突结果进入 `NEEDS_RECONCILIATION`；不声明客户问题已解决。Agent、真实 Provider、审批、外发和真实企业连接器仍不在范围内。

## 5. Change 3：`add-investigation-agent-loop`

**状态**：已归档：`2026-08-03-add-investigation-agent-loop`；已完成本地离线验证。

**目的**：让一个确定性 Replay Agent 在有界 Context Manifest 和只读 fixture 工具中完成
API-503 调查，并只提出受验证的回复候选。

**范围**：

- 只支持命名的 synthetic API-503 transcript；不初始化 live provider、网络客户端或凭据；
- `ContextManifest`、闭合 `AgentAction`、`ToolRequest/Result`、Evidence hash、
  `ResponseCandidate` 与 `VerifierOutcome` 的 v1 合同；
- 仅 CRM、monitoring、knowledge 三类 tenant-scoped、fixture-local、只读工具；
- `TICKET_READY -> INVESTIGATING -> RESPONSE_READY`，第二个转换仅由确定性 verifier
  在完整、匹配、脱敏的 evidence 后触发；
- Action/tool/no-progress budget、稳定 step ID、action/tool/candidate/verifier 持久化后的
  故障恢复，以及不含账本原始内容的 inspection snapshot；
- 只读 investigation API、能力诊断、Business Simulator 与 Control Worker recovery。

**验收**：API-503 fixture 必须在离线 SQLite 中产生 3 个按序 evidence hash、1 个
verified candidate 和 `RESPONSE_READY`；两次 baseline 完全一致；四个恢复断点无重复
工具结果或状态转换。跨 tenant、未授权工具、原始字段、格式/authority claim、live provider、
无进展、预算超限和未验证 candidate 都必须安全失败。无需 Docker、网络、模型密钥或企业凭据。

不包含审批、外发、知识发布、真实企微/腾讯云、真实工单或多 Agent。`RESPONSE_READY`
不是审批、发送或客户问题已解决。
## 6. Change 4：`add-policy-and-approval-gates`

**目的**：把租户、数据、预算和外发权限固化为模型外硬边界。

**范围**：

- 短期 Capability、验证、过期和撤销；
- tenant/action/resource/data-classification Policy Engine；
- PII/秘密脱敏和 Prompt injection 防护用例；
- ResponseCandidate、Evidence、Policy 哈希绑定；
- 审批 API、角色、有效期和候选变化失效；
- 经批准的幂等 IM Delivery。

**验收**：越租户/越权/未批准外发均为 0；候选变化使旧批准失效；外发确认丢失不重复发送。

## 7. Change 5：`add-evidence-and-trajectory-replay`

**目的**：让每次成功、失败和恢复都可以解释和重现。

**范围**：

- 统一 Artifact metadata、内容哈希和敏感度；
- OTel trace 与 Case/Revision/Tool/Policy/Approval 血缘；
- Evidence Report 和失败分类；
- Trace playback、确定性 replay 和 live rerun 语义；
- Simulator snapshot、Replay Agent 和故障矩阵；
- 12 个黄金 fixture。

**验收**：任一候选可追溯到输入、上下文、工具、策略和批准；12/12 Replay 通过；恢复不产生重复副作用。

## 8. Change 6：`add-evaluation-benchmark`

**目的**：用可复现 benchmark 量化 Agent 与 Harness，而非只展示 Demo。

**范围**：

- 统一 task-directory format；
- 60 个合成任务与污染隔离的 holdout；
- 规则、代码、检索证据和受限 LLM Judge grader；
- hard gates + weighted quality score；
- suite runner、5 次重复 live run 和机器可读报告；
- failure taxonomy 与单任务诊断包。

**验收**：一条命令生成完整报告；安全失败不会被平均分掩盖；报告包含方差、成本、P50/P95 和失败分类。

## 9. Change 7：`add-operator-console-and-demo`

**目的**：把技术能力变成面试官可在 5～8 分钟验证的产品演示。

**范围**：

- Case 列表、状态时间线、Agent/tool/policy 轨迹；
- Evidence、预算、审批绑定和 Replay；
- 评测 suite 和指标对比；
- 正常路径、Worker 中断、越权阻断、候选失效、重复消息五段演示；
- 开发指南、恢复手册、威胁模型、支持矩阵和技术报告。

**验收**：全新环境按文档可运行离线 Demo；所有页面来自真实事件/报告；技术报告区分模拟与 live 结果。

## 10. 可选 Change 8：`evaluate-multi-agent-collaboration`

**启动门槛**：Change 6 已稳定；任务可并行且不会频繁写同一资源；已有单 Agent 基线。

**实验，而非默认架构**：

- 候选角色：Triage Lead、Incident Investigator、Knowledge Reviewer、Safety Reviewer；
- 对比单 Agent、单向委派和团队协作；
- 使用同一 60-task suite；
- 报告成功率、尾延迟、Token/成本、路由错误、协作死锁和重复工具调用。

只有结果显著更好才保留运行时能力；否则把结论写入 ADR 并继续单 Agent。

## 11. 推荐的首次指令

在新的 Codex/CodeBuddy 会话中进入 `D:\Coding\code\WeFlow`，发送：

```text
请先阅读 README.md、docs/PROJECT_MEMORY.md、
docs/architecture/reference-architecture.md 和
docs/development/openspec-roadmap.md，然后运行 openspec list --json。
使用 /opsx:propose 为 establish-weflow-foundation 创建完整 proposal、design、specs 和 tasks。
严格限制在 Change 0，不实现代码。
```

审阅 artifact 后再单独发送：

```text
/opsx:apply establish-weflow-foundation
```

这种“两次会话动作”保留了人工审阅设计的机会，也让后续每个 change 都有清晰证据边界。
