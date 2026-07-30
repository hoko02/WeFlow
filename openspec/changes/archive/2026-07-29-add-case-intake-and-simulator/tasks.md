## 1. Canonical intake and ledger contracts

## 1. 规范接入与账本契约

- [x] 1.1 Add compatible `v1` JSON Schemas for `InboundMessageEvent` and `CaseProjection`; add only additive safe intake/ledger properties to Case, CaseRevision, and BusinessEvent, with no raw message-content field.

  - [x] 1.1 为 `InboundMessageEvent` 与 `CaseProjection` 新增兼容的 `v1` JSON Schema；仅向 Case、CaseRevision 与 BusinessEvent 添加增量的安全接入/账本属性，不含原始消息内容字段。

- [x] 1.2 Extend Python contract loading/semantic validation for normalized inbound envelopes, generated event index/payload digest, and Case projection invariants.

  - [x] 1.2 扩展 Python 契约加载/语义校验，支持规范化入站信封、生成的事件索引/负载摘要，以及 Case 投影不变量。

- [x] 1.3 Extend TypeScript contract exports/fixture validation for the same canonical schemas and generated API boundary objects.

  - [x] 1.3 针对相同的规范 schema 与生成的 API 边界对象，扩展 TypeScript 契约导出/fixture 校验。

- [x] 1.4 Add retained and new valid/invalid contract fixtures for a first delivery, duplicate-compatible delivery, tenant mismatch, raw/undeclared content, ordering, projection, and missing generated-ledger metadata; update the v1 fingerprint snapshot only after the full compatible corpus passes in both languages.

  - [x] 1.4 新增保留与新版的有效/无效契约 fixtures，覆盖首次投递、兼容重复投递、租户不匹配、原始/未声明内容、排序、投影，以及缺失生成的账本元数据；仅当完整兼容语料库在两种语言中均通过后，才更新 v1 指纹快照。

- [x] 1.5 Add contract regression tests proving all Change 0 valid/semantic fixtures remain valid and both languages reject the new invalid corpus deterministically.

  - [x] 1.5 新增契约回归测试，证明所有 Change 0 的有效/语义 fixtures 仍然有效，且两种语言确定性地拒绝新的无效语料库。

## 2. Deterministic Case ledger and snapshot boundary

## 2. 确定性 Case 账本与快照边界

- [x] 2.1 Define the shared `CaseLedger` domain interface, deterministic synthetic actor registry, injectable clock, canonical ID/fingerprint derivation, and safe allowlisted error/result types.

  - [x] 2.1 定义共享的 `CaseLedger` 领域接口、确定性合成参与者注册表、可注入时钟、规范 ID/指纹派生，以及安全的许可列表错误/结果类型。

- [x] 2.2 Implement the offline SQLite ledger schema with tenant-scoped uniqueness, inbound receipt natural keys, conversation sequence cursors, immutable CaseRevision and BusinessEvent source tables, append-only update/delete guards, and a derived Case projection.

  - [x] 2.2 实现离线 SQLite 账本 schema，含租户范围唯一性、入站回执自然键、会话序号游标、不可变 CaseRevision 与 BusinessEvent 源表、只追加的更新/删除守卫，以及派生的 Case 投影。

- [x] 2.3 Implement the single atomic intake transaction: tenant claim verification, exact duplicate result, conflicting replay rejection, contiguous sequence validation, Case/Revision 1 creation, and the three ordered initial BusinessEvents.

  - [x] 2.3 实现单条原子接入事务：租户声明校验、精确重复结果、冲突重放拒绝、连续序号校验、Case/Revision 1 创建，以及三条有序的初始 BusinessEvent。

- [x] 2.4 Implement projection rebuild/validation from source records, including revision-chain, event-index, tenant-reference, payload-digest, and initial-state transition checks on restart.

  - [x] 2.4 实现从源记录重建/校验投影，包括修订链、事件索引、租户引用、负载摘要，以及重启时的初始状态转换检查。

- [x] 2.5 Implement content-addressed, tenant-scoped snapshot export and fresh-store restore in the simulator/testkit; reject tampered, mixed-tenant, or internally inconsistent snapshots without mutating an existing store.

  - [x] 2.5 在模拟器/testkit 中实现内容寻址、租户范围的快照导出与全新存储恢复；在不修改现有存储的情况下，拒绝被篡改、混合租户或内部不一致的快照。

- [x] 2.6 Add unit/recovery tests for atomic rollback, source immutability, generated IDs, duplicate/conflict/order outcomes, projection rebuild, restart persistence, and snapshot restore.

  - [x] 2.6 新增针对原子回滚、源不可变性、生成的 ID、重复/冲突/排序结果、投影重建、重启持久化与快照恢复的单元/恢复测试。

## 3. Synthetic IM and Platform API surfaces

## 3. 合成 IM 与 Platform API 接口

- [x] 3.1 Extend the Business Simulator with synthetic IM fixture normalization, fixture-only actor mapping, and an in-process intake/snapshot test surface; do not register CRM, ticket, approval, delivery, model, or external-write behavior.

  - [x] 3.1 用合成 IM fixture 规范化、仅 fixture 的参与者映射，以及进程内接入/快照测试接口扩展业务模拟器；不要注册 CRM、工单、审批、投递、模型或外部写入行为。

- [x] 3.2 Add loopback Platform API routes for synthetic intake and tenant-derived Case, revision, and event reads; map all failures to safe allowlisted reason-code envelopes and do not expose a generic append/state/reset route.

  - [x] 3.2 为合成接入与租户派生的 Case、修订、事件读取新增 loopback Platform API 路由；将所有失败映射到安全的许可列表原因码信封，且不暴露通用的追加/状态/重置路由。

- [x] 3.3 Wire offline configuration to an ignored local SQLite runtime path and test injection, preserving replay-only provider selection, no-credential startup, and loopback-only binding.

  - [x] 3.3 将离线配置接入被忽略的本地 SQLite 运行时路径与测试注入，保留仅重放的提供方选择、无凭据启动，以及仅 loopback 绑定。

- [x] 3.4 Extend truthful capability reporting and the diagnostics-console contract/view to show the narrow synthetic-intake capability while retaining `business_workflow_implemented=false` and `external_writes_enabled=false`.

  - [x] 3.4 扩展如实的能力报告与诊断控制台契约/视图，以展示窄化的合成接入能力，同时保持 `business_workflow_implemented=false` 与 `external_writes_enabled=false`。

- [x] 3.5 Add API integration tests for first delivery, exact retry, altered replay, sequence gap/late delivery, own-tenant reads, cross-tenant non-disclosure, safe error rendering, and no partial state after a failure.

  - [x] 3.5 新增 API 集成测试，覆盖首次投递、精确重试、被篡改重放、序号缺口/迟到投递、本租户读取、跨租户不披露、安全错误渲染，以及失败后无部分状态。

## 4. Fixture-driven acceptance and safety evidence

## 4. 面向 fixture 的验收与安全证据

- [x] 4.1 Add three synthetic golden intake fixtures covering first API-503 delivery, duplicate delivery, and out-of-order delivery; retain only opaque synthetic IDs and content hashes in tracked fixture/report data.

  - [x] 4.1 新增三个合成 golden 接入 fixtures，覆盖首次 API-503 投递、重复投递与乱序投递；在受跟踪的 fixture/报告数据中仅保留不透明的合成 ID 与内容哈希。

- [x] 4.2 Add an offline end-to-end acceptance suite that runs fixtures through the Business Simulator, Platform API, and SQLite ledger, verifies the exact Case/Revision and three-event timeline, and proves duplicate runs do not change baseline state.

  - [x] 4.2 新增离线端到端验收套件，通过业务模拟器、Platform API 与 SQLite 账本运行 fixtures，验证确切的 Case/Revision 与三事件时间线，并证明重复运行不改变基线状态。

- [x] 4.3 Add negative safety tests proving no raw message content leaks into API errors, logs, snapshots, or reports; no model/workflow/approval/external-write behavior is initialized; and the existing provider-boundary tests remain green.

  - [x] 4.3 新增否定安全测试，证明无原始消息内容泄漏到 API 错误、日志、快照或报告中；不初始化模型/工作流/审批/外部写入行为；且现有提供方边界测试保持通过。

- [x] 4.4 Add snapshot/restart acceptance coverage that exports state, restores it into a fresh store, replays the original delivery, and compares deterministic projections and machine-readable outcomes.

  - [x] 4.4 新增快照/重启验收覆盖：导出状态、恢复到全新存储、重放原始投递，并比较确定性投影与机器可读结果。

- [x] 4.5 Extend `scripts/dev.py` with a documented offline Change 1 acceptance entry point that emits a redacted machine-readable report without claiming incident resolution; add command-dispatch and report-shape tests.

  - [x] 4.5 用有文档的离线 Change 1 验收入口扩展 `scripts/dev.py`，该入口发出脱敏的机器可读报告而不声称事件已解决；新增命令分发与报告形态测试。

## 5. Documentation, validation, and archive evidence

## 5. 文档、验证与归档证据

- [x] 5.1 Update README and a Change 1 development guide with setup/commands, route and fixture usage, snapshot semantics, implemented versus unimplemented claims, and the synthetic-actor limitation.

  - [x] 5.1 更新 README 与 Change 1 开发指南，包含设置/命令、路由与 fixture 用法、快照语义、已实现与未实现的声明，以及合成参与者的限制。

- [x] 5.2 Run `python scripts/dev.py check`, `lint`, `contracts`, `test`, and the Change 1 acceptance command; retain redacted machine-readable acceptance evidence and record any environment limitation explicitly.

  - [x] 5.2 运行 `python scripts/dev.py check`、`lint`、`contracts`、`test` 与 Change 1 验收命令；保留脱敏的机器可读验收证据，并明确记录任何环境限制。

- [x] 5.3 Run `openspec validate add-case-intake-and-simulator --type change --strict`, resolve all validation failures, and verify every task has a passing acceptance check before archive.

  - [x] 5.3 运行 `openspec validate add-case-intake-and-simulator --type change --strict`，解决所有验证失败，并在归档前确认每个任务都有通过的验收检查。

- [x] 5.4 Archive through OpenSpec only after the above checks pass; update `docs/PROJECT_MEMORY.md` with verified facts, known limitations, metrics, and the gate for the next durable-workflow change.

  - [x] 5.4 仅在上述检查通过后通过 OpenSpec 归档；用已验证事实、已知限制、指标，以及下一持久工作流变更的关卡更新 `docs/PROJECT_MEMORY.md`。
