## Context

## 背景

Change 0 provides a replay-first, loopback-only workspace and canonical `v1` schemas, but no application process can accept an IM event or persist business state. The next reliable vertical must prove that a synthetic enterprise-IM delivery can become one tenant-scoped Case with immutable history, even when the same delivery is retried or arrives in an invalid sequence.

变更 0 提供了一个重放优先、仅 loopback 的工作区与规范的 `v1` schema，但没有任何应用进程能接受 IM 事件或持久化业务状态。下一个可靠的垂直切片必须证明：一个合成的企业 IM 投递可以成为一个租户范围的 Case 并带有不可变历史，即便同一投递被重试或以无效顺序到达。

The implementation must remain usable without Docker, network access, model credentials, enterprise credentials, or customer data. It must preserve the existing negative provider tests: no model, external-write executor, real adapter, approval, or multi-agent coordinator is added by this change. `business_workflow_implemented` continues to mean the full support workflow and therefore remains `false`.

实现必须在没有 Docker、网络访问、模型凭据、企业凭据或客户数据的情况下可用。它必须保留现有的否定提供方测试：本变更不新增模型、外部写入执行器、真实适配器、审批或多智能体协调器。`business_workflow_implemented` 仍表示完整的支持工作流，因此保持为 `false`。

The affected boundaries are the Platform API, the deterministic Business Simulator, the shared contract packages, and a new deterministic local ledger implementation. Temporal, CRM, monitoring, ticketing, knowledge, approval, delivery, and Agent Runtime remain consumers for later changes rather than owners of this state.

受影响的边界是 Platform API、确定性的业务模拟器、共享契约包，以及一个新增的确定性本地账本实现。Temporal、CRM、监控、工单、知识、审批、投递与智能体运行时仍是后续变更的消费者，而非本状态的拥有者。

## Goals / Non-Goals

## 目标 / 非目标

**Goals:**

**目标：**

- Accept a normalized, synthetic-only `InboundMessageEvent` through a loopback Platform API and resolve the effective tenant from a local synthetic actor registry rather than trusting a tenant selector in the request.

  - 通过 loopback 的 Platform API 接受一个规范化、仅合成的 `InboundMessageEvent`，并从本地合成参与者注册表解析有效租户，而非信任请求中的租户选择器。

- Atomically create exactly one stable Case, immutable CaseRevision 1, and three append-only BusinessEvents for a first valid delivery.

  - 为首次有效投递，原子地创建恰好一个稳定 Case、不可变 CaseRevision 1，以及三个只追加 BusinessEvent。

- Return the original result without mutating state for an identical re-delivery; reject a conflicting re-delivery or invalid conversation order with a stable safe reason code.

  - 对完全相同的重新投递，返回原始结果而不改变状态；以稳定的安全原因码拒绝冲突的重新投递或无效的会话顺序。

- Provide tenant-scoped read projections for Case, revision, and event timeline; cross-tenant reads must not reveal whether a Case exists.

  - 提供租户范围的 Case、修订与时间线的读取投影；跨租户读取不得泄露某个 Case 是否存在。

- Keep the source-of-truth records immutable and the read projection rebuildable from the ledger. Make synthetic state exportable and restorable into a fresh local store for deterministic test/replay fixtures.

  - 保持真相源记录不可变，且读取投影可从账本重建。使合成状态可导出并恢复到全新的本地存储，用于确定性测试/重放 fixtures。

- Extend compatible `v1` contracts, retain existing fixtures, and validate the new boundary identically from Python and TypeScript.

  - 扩展兼容的 `v1` 契约，保留现有 fixtures，并从 Python 与 TypeScript 以相同方式校验新边界。

**Non-Goals:**

**非目标：**

- No customer/SLA enrichment, classification, workflow execution, state transition beyond initial `RECEIVED`, ticket intent, approval, outbound delivery, knowledge candidate, evaluation result, or customer-resolution declaration.

  - 不进行客户/SLA 富化、分类、工作流执行、初始 `RECEIVED` 之外的状态转换、工单意图、审批、出站投递、知识候选、评估结果或客户解决声明。

- No real authentication or production tenancy claim. The local synthetic actor registry is a test boundary that proves tenant selection is server-derived; it is not a replacement for a future authentication/authorization change.

  - 不进行真实认证或生产租户声明。本地合成参与者注册表是一个测试边界，用于证明租户选择是服务端派生的；它并非未来认证/授权变更的替代。

- No broad CRUD API, caller-supplied Case state, arbitrary event append endpoint, raw message-content persistence, external simulator write, or migration of a production database.

  - 不提供宽泛的 CRUD API、调用方提供的 Case 状态、任意事件追加端点、原始消息内容持久化、外部模拟器写入，或生产数据库迁移。

## Decisions

## 决策

### 1. Use a narrow normalized inbound envelope with no raw message body

### 1. 使用窄化的规范化入站信封，不含原始消息体

Add `InboundMessageEvent` under the canonical `contracts/jsonschema/v1` directory. Every envelope will contain the declared tenant claim, synthetic channel and channel event identifiers, conversation and sender/customer identities, a positive contiguous conversation sequence, occurrence/receipt timestamps, a correlation identifier, synthetic content classification, and a SHA-256 content digest. It will contain no plaintext customer message, attachment bytes, credential, or unrestricted tool output.

在规范的 `contracts/jsonschema/v1` 目录下新增 `InboundMessageEvent`。每个信封将包含声明的租户声明、合成渠道与渠道事件标识、会话与发送方/客户标识、正的连续会话序号、发生/接收时间戳、关联标识、合成内容分类，以及 SHA-256 内容摘要。它不包含明文客户消息、附件字节、凭据或无限制工具输出。

The Business Simulator will turn a checked-in synthetic fixture into this normalized envelope. It owns fixture source material only; the ledger persists the redacted envelope/digests. A future change can add a content-addressed artifact reference when investigation actually needs message text.

业务模拟器将把一个已入库的合成 fixture 转换为此规范化信封。它仅拥有 fixture 源材料；账本持久化脱敏后的信封/摘要。当调查确实需要消息文本时，未来的变更可新增一个内容寻址的工件引用。

**Why this choice:** it gives the Case enough identity and ordering context to be auditable while keeping private-content handling out of the first persistence slice.

**为何如此选择：** 它给予 Case 足够的标识与排序上下文以可被审计，同时将私有内容处理排除在首个持久化切片之外。

**Alternatives considered:** persisting an arbitrary `body` field is rejected because it would establish an unsafe raw-data boundary before data classification and artifact access controls exist. Treating a fixture file name as the identity is rejected because it is not a channel-level delivery key and cannot model retries safely.

**已考虑的替代方案：** 持久化任意 `body` 字段被拒绝，因为在数据分类与工件访问控制存在之前，它会建立一个不安全的原始数据边界。将 fixture 文件名视为标识被拒绝，因为它不是渠道级投递键，无法安全地建模重试。

### 2. Resolve tenant authority from a synthetic actor registry

### 2. 从合成参与者注册表解析租户权限

The intake and read routes will require an opaque synthetic actor identity. A local `SyntheticActorRegistry`, injected by offline configuration or tests, maps that actor to exactly one synthetic tenant. The `tenant_id` inside `InboundMessageEvent` is a claim and MUST match the resolved tenant; it is never an authority selector. Case read routes have no tenant path or query parameter and apply the same resolved tenant filter.

接入与读取路由将要求一个不透明的合成参与者标识。一个由离线配置或测试注入的本地 `SyntheticActorRegistry` 将该参与者映射到恰好一个合成租户。`InboundMessageEvent` 内的 `tenant_id` 是一种声明，且必须匹配解析出的租户；它绝不是权限选择器。Case 读取路由没有租户路径或查询参数，并应用相同的解析租户过滤。

The initial local identities are synthetic fixture-only values such as `simulator-tenant-a`; they are not tokens, secrets, or a real authentication scheme.

初始本地标识仅为合成 fixture 值，如 `simulator-tenant-a`；它们不是令牌、秘密或真实的认证方案。

**Why this choice:** it allows a meaningful tenant-isolation test now and prevents an API caller from selecting another tenant merely by changing JSON input.

**为何如此选择：** 它现在就能支持有意义的租户隔离测试，并防止 API 调用方仅通过修改 JSON 输入就选择另一个租户。

**Alternatives considered:** trusting `tenant_id` in the body would make the desired hard gate untestable. Adding production OAuth/RBAC now would broaden scope far beyond synthetic intake and is deferred to the policy/authorization change.

**已考虑的替代方案：** 信任请求体中的 `tenant_id` 会使期望的硬性关卡无法测试。现在加入生产 OAuth/RBAC 会将范围扩大到远超合成接入，因此推迟到策略/授权变更。

### 3. Store source records in an offline SQLite ledger behind a domain interface

### 3. 在领域接口后的离线 SQLite 账本中存储源记录

Add a deterministic `CaseLedger` interface in the shared Python control boundary and implement it with Python's standard-library SQLite driver. The default offline store is under ignored `.weflow/` runtime state; tests inject a temporary path. The interface, not SQLite details, is consumed by Platform API and Business Simulator tests so a later PostgreSQL adapter can be introduced without changing API semantics.

在共享 Python 控制边界新增确定性的 `CaseLedger` 接口，并用 Python 标准库 SQLite 驱动实现。默认离线存储位于被忽略的 `.weflow/` 运行时状态之下；测试注入临时路径。被 Platform API 与业务模拟器测试消费的是该接口，而非 SQLite 细节，以便后续可在不改变 API 语义的情况下引入 PostgreSQL 适配器。

Source tables are insert-only: inbound receipts, Cases, CaseRevisions, and BusinessEvents. SQLite triggers reject `UPDATE` and `DELETE` against immutable revision and event source rows. A `case_projection` read model is explicitly derived data and can be rebuilt from source records. The projection is never the audit authority.

源表仅可插入：入站回执、Cases、CaseRevisions 与 BusinessEvents。SQLite 触发器拒绝针对不可变修订与事件源行的 `UPDATE` 和 `DELETE`。`case_projection` 读取模型是显式派生的数据，可从源记录重建。投影永远不是审计权威。

**Why this choice:** SQLite provides a persistent transactional store in the required offline mode without adding Docker or a new runtime dependency. An explicit interface preserves the later service-boundary path.

**为何如此选择：** SQLite 在所需的离线模式下提供了持久的事务化存储，而无需新增 Docker 或运行时依赖。显式的接口保留了后续的服务边界路径。

**Alternatives considered:** an in-memory dictionary cannot prove restart persistence or atomic uniqueness. Starting PostgreSQL for this slice would violate the required Docker-free baseline and make the first business vertical unnecessarily heavy.

**已考虑的替代方案：** 内存字典无法证明重启后的持久性或原子唯一性。为本切片启动 PostgreSQL 会违反所需的无 Docker 基线，并使首个业务垂直切片不必要地臃肿。

### 4. Make idempotency and ordering deterministic before Case creation

### 4. 在 Case 创建前使幂等性与排序确定性化

For each accepted envelope the ledger derives:

对于每个被接受的信封，账本派生：

| Value | Material | Purpose |
| --- | --- | --- |
| delivery natural key | effective tenant, channel, channel event id | unique inbound receipt |
| inbound fingerprint | canonical normalized envelope excluding `received_at` | distinguish exact retry from conflicting replay |
| Case id | versioned SHA-256 derivation of the delivery natural key | stable Case identity |
| revision/event ids | versioned SHA-256 derivations of Case/revision/event role | stable immutable history |

| 值 | 材料 | 目的 |
| --- | --- | --- |
| 投递自然键 | 有效租户、渠道、渠道事件 id | 唯一入站回执 |
| 入站指纹 | 排除 `received_at` 的规范规范化信封 | 区分精确重试与冲突重放 |
| Case id | 投递自然键的带版本 SHA-256 派生 | 稳定 Case 标识 |
| 修订/事件 id | Case/修订/事件角色的带版本 SHA-256 派生 | 稳定不可变历史 |

Within one `BEGIN IMMEDIATE` transaction, the ledger first checks the delivery natural key, then checks the per-tenant/channel/conversation sequence cursor, and only then creates records. The duplicate lookup runs before sequence validation so a true retry returns the original accepted result even after later messages have advanced the cursor.

在一个 `BEGIN IMMEDIATE` 事务内，账本先检查投递自然键，再检查每租户/渠道/会话的序号游标，之后才创建记录。重复查找在序号校验之前运行，因此即便后续消息已推进游标，真正的重试仍返回原始被接受的结果。

- Same delivery key and same fingerprint: return `deduplicated` with the original Case/revision/event references and make no write.

  - 相同投递键且相同指纹：返回 `deduplicated` 及原始 Case/修订/事件引用，且不写入。

- Same delivery key and a different fingerprint: reject with `inbound_event_conflict`; make no write.

  - 相同投递键但不同指纹：以 `inbound_event_conflict` 拒绝；不写入。

- New delivery whose sequence is not exactly the next expected sequence (initially 1): reject with `inbound_out_of_order`; make no write.

  - 序号并非恰为下一个期望序号（初始为 1）的新投递：以 `inbound_out_of_order` 拒绝；不写入。

- Valid new delivery: create one Case, CaseRevision 1, and exactly these ordered BusinessEvents: `inbound.received.v1`, `case.revision-created.v1`, and `case.state-transitioned.v1` to `RECEIVED`.

  - 有效新投递：创建一个 Case、CaseRevision 1，以及恰好以下有序 BusinessEvent：`inbound.received.v1`、`case.revision-created.v1`，以及将状态转为 `RECEIVED` 的 `case.state-transitioned.v1`。

The service assigns an immutable per-Case event index and a canonical payload digest to every new event. The existing `v1` BusinessEvent schema remains compatible by making these fields additive; Change 1 service output requires them.

服务为每个新事件分配不可变的每 Case 事件索引与规范负载摘要。现有 `v1` BusinessEvent schema 通过将这些字段设为可增量扩展而保持兼容；Change 1 的服务输出需要它们。

**Why this choice:** the natural key makes retries safe, the fingerprint detects a provider defect or altered replay, and contiguous sequence checking gives a stable definition of out-of-order behavior without relying on wall-clock timestamps.

**为何如此选择：** 自然键使重试安全，指纹可检测提供方缺陷或被篡改的重放，而连续序号检查在不依赖墙上时钟时间戳的情况下给出了乱序行为的稳定定义。

**Alternatives considered:** deduplicating solely on content would collapse distinct customer messages. Appending a `deduplicated` BusinessEvent on every retry would make replay outputs depend on retry count, so duplicate detection is a read-only outcome in this slice. Timestamp-only ordering is rejected because clocks and receipt delays are not an authoritative conversation order.

**已考虑的替代方案：** 仅基于内容去重会合并不同的客户消息。在每次重试时追加 `deduplicated` BusinessEvent 会使重放输出依赖于重试次数，因此在本切片中重复检测是一个只读结果。仅按时间戳排序被拒绝，因为时钟与接收延迟并非权威的会话顺序。

### 5. Keep legal state transition ownership inside deterministic control code

### 5. 将合法状态转换的所有权保留在确定性控制代码内

Change 1 defines one legal transition: no state to `RECEIVED`, performed only by the intake transaction. There is no public endpoint to submit a state change or arbitrary BusinessEvent. The projection is built from the ordered event ledger and reports `RECEIVED` only after the corresponding state-transition event exists. A later durable workflow change extends the transition registry and owns subsequent retries, SLA, and completion decisions.

Change 1 定义一条合法转换：从无状态到 `RECEIVED`，且仅由接入事务执行。没有公开端点可提交状态变更或任意 BusinessEvent。投影由有序事件账本构建，且只有在对应状态转换事件存在后才报告 `RECEIVED`。后续的持久工作流变更将扩展转换注册表，并拥有后续的优先级重试、SLA 与完成决策。

**Why this choice:** it demonstrates that state cannot be forged by an API client or future model-like output while avoiding a premature workflow engine.

**为何如此选择：** 它证明状态无法被 API 客户端或未来的类模型输出伪造，同时避免过早引入工作流引擎。

**Alternatives considered:** allowing a generic append endpoint would require policy, capability, and workflow state gates that are intentionally scheduled for later changes. Storing mutable `case.state` as authority would make replay/audit divergence possible.

**已考虑的替代方案：** 允许通用的追加端点将需要策略、能力与工作流状态关卡，而这些被有意安排在后续变更。将可变的 `case.state` 作为权威存储会使重放/审计出现分歧。

### 6. Expose only narrow loopback API surfaces and safe errors

### 6. 仅暴露窄化的 loopback API 接口与安全错误

The Platform API will add these local routes:

Platform API 将新增以下本地路由：

| Route | Outcome |
| --- | --- |
| `POST /v1/synthetic-im/intake` | accepts an envelope and returns `accepted` or `deduplicated` Case references |
| `GET /v1/cases/{case_id}` | returns the derived Case projection for the resolved tenant |
| `GET /v1/cases/{case_id}/revisions` | returns immutable revisions in ascending order |
| `GET /v1/cases/{case_id}/events` | returns append-only events in event-index order |

| 路由 | 结果 |
| --- | --- |
| `POST /v1/synthetic-im/intake` | 接受信封并返回 `accepted` 或 `deduplicated` 的 Case 引用 |
| `GET /v1/cases/{case_id}` | 返回解析租户的派生 Case 投影 |
| `GET /v1/cases/{case_id}/revisions` | 按升序返回不可变修订 |
| `GET /v1/cases/{case_id}/events` | 按事件索引顺序返回只追加事件 |

Errors use an allowlisted `reason_code` envelope only: invalid envelope, `tenant_identity_mismatch`, `case_not_found`, `inbound_event_conflict`, or `inbound_out_of_order`. Cross-tenant lookup and unknown Case both return `case_not_found`. No error serializes raw request fields, exception messages, database paths, or configuration values.

错误仅使用许可列表内的 `reason_code` 信封：invalid envelope、`tenant_identity_mismatch`、`case_not_found`、`inbound_event_conflict` 或 `inbound_out_of_order`。跨租户查找与未知 Case 均返回 `case_not_found`。任何错误都不序列化原始请求字段、异常消息、数据库路径或配置值。

`/foundation/capabilities` will continue to report the full business workflow and external writes as disabled. It will add a narrowly named synthetic Case-intake flag only after acceptance tests pass, so health remains truthful about the difference between an implemented intake slice and a resolved incident.

`/foundation/capabilities` 将继续报告完整业务工作流与外部写入为已禁用。它仅在验收测试通过后才新增一个窄命名的合成 Case 接入标志，从而使健康状态如实反映已实现的接入切片与已解决事件之间的差异。

**Why this choice:** the routes are sufficient for an independently verifiable slice and preserve the intended control-plane ownership boundary.

**为何如此选择：** 这些路由对于一个可独立验证的切片已足够，并保留了预期的控制平面所有权边界。

**Alternatives considered:** generic Case CRUD or a console-led mutation flow would allow behavior not protected by the ledger transaction and would obscure the next workflow change's responsibilities.

**已考虑的替代方案：** 通用的 Case CRUD 或控制台主导的变更流会允许不受账本事务保护的行为，并会掩盖下一工作流变更的职责。

### 7. Make snapshots fixture-oriented, content-addressed, and non-destructive

### 7. 使快照面向 fixture、内容寻址且非破坏性

The Business Simulator/testkit will provide an in-process snapshot export/import surface, not a production API. Export serializes only one effective tenant's source records in canonical order with a schema version and SHA-256 content hash. Restore validates the hash, tenant consistency, revision chain, event ordering, and rebuilt projection into a fresh temporary SQLite store before it is opened by a test or replay. It does not mutate an existing ledger, bypass append-only triggers, or generate new BusinessEvents.

业务模拟器/testkit 将提供一个进程内的快照导出/导入接口，而非生产 API。导出仅按规范顺序序列化一个有效租户的源记录，并附带 schema 版本与 SHA-256 内容哈希。恢复会校验哈希、租户一致性、修订链、事件顺序，以及重建后的投影，再导入一个全新的临时 SQLite 存储，之后才由测试或重放打开。它不修改现有账本、不绕过只追加触发器，也不生成新的 BusinessEvent。

**Why this choice:** a fresh-store restore makes deterministic replay and recovery testing possible without creating a privileged reset/write route in the application.

**为何如此选择：** 全新存储的恢复使确定性重放与恢复测试成为可能，而无需在应用中创建特权重置/写入路由。

**Alternatives considered:** a public reset endpoint would be a dangerous implicit write capability. Deleting ledger rows during restore would contradict the source append-only guarantee.

**已考虑的替代方案：** 公开的重置端点将是一种危险的隐式写入能力。在恢复期间删除账本行会违背源只追加的保证。

### 8. Evolve `v1` additively and retain cross-language evidence

### 8. 以增量方式演进 `v1` 并保留跨语言证据

Add `InboundMessageEvent` and `CaseProjection` schemas. Additive fields will be added to the existing Case, CaseRevision, and BusinessEvent schemas only where needed to represent this slice's source metadata and ordered safe event payload digest. Existing `v1` valid/invalid fixtures remain retained and must continue to validate; no required field or prior semantic interpretation is changed. Python and TypeScript validators will validate the new fixture corpus before the compatibility fingerprint is updated as an intentional additive Change 1 record.

新增 `InboundMessageEvent` 与 `CaseProjection` schema。仅在需要表示本切片的源元数据与有序安全事件负载摘要之处，向现有 Case、CaseRevision 与 BusinessEvent schema 添加增量字段。现有 `v1` 有效/无效 fixtures 继续保留且必须保持可验证；不更改任何必填字段或先前的语义解释。Python 与 TypeScript 校验器将在兼容性指纹作为有意的 Change 1 增量记录更新之前，先校验新的 fixture 语料库。

**Why this choice:** the contract boundary stays language-neutral and future changes can consume these records without copying Platform API DTOs.

**为何如此选择：** 契约边界保持语言无关，后续变更可在不复制 Platform API DTO 的情况下消费这些记录。

**Alternatives considered:** an unversioned FastAPI-only request model would drift from the TypeScript console and break the contract-first invariant. A `v2` directory is not needed because this is additive and retained `v1` consumers remain valid.

**已考虑的替代方案：** 无版本的仅 FastAPI 请求模型会与 TypeScript 控制台产生分歧，并破坏契约优先不变量。不需要 `v2` 目录，因为本变更是增量的，且保留的 `v1` 消费者仍有效。

## Risks / Trade-offs

## 风险 / 权衡

- [A deterministic Case id is enumerable] -> all reads use the server-derived tenant filter and return the same not-found result for absent or foreign Cases; synthetic ids and data are local-only in this change.

  - [确定性 Case id 可被枚举] → 所有读取都使用服务端派生的租户过滤，并对不存在或外部的 Case 返回相同的未找到结果；合成 id 与数据在本变更中仅限本地。

- [A sequence gap rejects a message that a real channel might later reconcile] -> the strict `inbound_out_of_order` policy is explicit for synthetic fixtures; a later reconciliation/change can add buffered ordering without weakening this baseline.

  - [序号缺口会拒绝真实渠道稍后可能协调的消息] → 严格的 `inbound_out_of_order` 策略对合成 fixtures 是显式的；后续的协调/变更可加入缓冲排序而不削弱此基线。

- [SQLite differs from PostgreSQL concurrency behavior] -> the domain interface, atomic uniqueness constraints, and adapter-agnostic tests specify behavior; service-boundary persistence is a later adapter change.

  - [SQLite 与 PostgreSQL 并发行为不同] → 领域接口、原子唯一性约束与适配器无关的测试规定了行为；服务边界持久化是后续的适配器变更。

- [Projection bugs diverge from the ledger] -> rebuild the projection from source rows in tests and snapshot restore, and never use the projection as the audit authority.

  - [投影缺陷与账本产生分歧] → 在测试与快照恢复中从源行重建投影，且绝不使用投影作为审计权威。

- [Synthetic actor headers could be mistaken for production authentication] -> label the registry test-only in API/docs, never accept real credentials, and retain the provider safety tests.

  - [合成参与者头部可能被误认为生产认证] → 在 API/文档中将注册表标记为仅测试，绝不接受真实凭据，并保留提供方安全测试。

- [Additive `v1` schema fields drift across languages] -> retain the old corpus, add new valid/invalid fixtures, and run canonical Python/TypeScript parity checks.

  - [增量的 `v1` schema 字段在语言间产生分歧] → 保留旧语料库，新增有效/无效 fixtures，并运行规范的 Python/TypeScript 一致性检查。

- [Business intake is mistaken for incident resolution] -> expose an explicit narrow capability flag while keeping full workflow completion and external writes false in health, tests, reports, and documentation.

  - [业务接入被误认为事件解决] → 暴露一个显式的窄能力标志，同时在健康、测试、报告与文档中保持完整工作流完成与外部写入为 false。

## Migration Plan

## 迁移计划

1. Add canonical contracts and retained/new fixtures first; run cross-language contract validation before adding API behavior.

   1. 先新增规范契约与保留/新增 fixtures；在添加 API 行为前运行跨语言契约校验。

2. Implement the SQLite `CaseLedger`, immutable-schema triggers, ID/fingerprint derivation, projection rebuild, and fixture snapshot helpers behind tests.

   2. 在测试后实现 SQLite `CaseLedger`、不可变 schema 触发器、ID/指纹派生、投影重建与 fixture 快照辅助函数。

3. Wire the Business Simulator's synthetic intake fixture adapter and the narrow Platform API routes; preserve loopback-only startup and replay-only runtime mode.

   3. 接入业务模拟器的合成接入 fixture 适配器与窄化 Platform API 路由；保留仅 loopback 启动与仅重放运行时模式。

4. Add duplicate, conflict, ordering, tenant, restart, snapshot, and truthfulness acceptance tests plus a machine-readable Change 1 report.

   4. 新增重复、冲突、排序、租户、重启、快照与真实性验收测试，外加机器可读的 Change 1 报告。

5. Update README/development guidance with exact commands and limitations. Archive only after strict OpenSpec validation and verified acceptance; then update `docs/PROJECT_MEMORY.md` with facts and the Change 2 gate.

   5. 用确切命令与限制更新 README/开发指南。仅在严格的 OpenSpec 验证与已验证验收之后归档；随后用事实与 Change 2 关卡更新 `docs/PROJECT_MEMORY.md`。

There is no production migration or rollout. A local rollback stops the services and removes only the ignored local SQLite runtime file. The canonical `v1` schema change is rolled back as one source-controlled change; no customer or enterprise records exist.

没有生产迁移或发布。本地回滚会停止服务，并仅移除被忽略的本地 SQLite 运行时文件。规范的 `v1` schema 变更作为一次受源代码控制的变更被回滚；不存在客户或企业记录。

## Open Questions

## 待决问题

No blocking design questions remain for Apply. The following are intentionally deferred rather than implicit decisions: production authentication and tenant administration, PostgreSQL/Temporal ownership and migration, message-body artifact retrieval, conversation buffering/reconciliation, and every transition after `RECEIVED`.

Apply 阶段已无阻塞性的设计问题。以下各项被有意推迟，而非隐式决定：生产认证与租户管理、PostgreSQL/Temporal 的所有权与迁移、消息体工件检索、会话缓冲/协调，以及 `RECEIVED` 之后的所有转换。
