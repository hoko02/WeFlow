## Context

WeFlow has completed architecture exploration for an enterprise-IM-native customer-issue resolution Agent Reliability Harness, but it has no executable repository baseline. The first business vertical slice will eventually process a synthetic enterprise API-503 incident; it must not be started until its contracts, provider boundaries, local modes, and verification entry points are explicit.

WeFlow 已完成面向企业 IM 的原生客户问题处理 Agent 可靠性 Harness 的架构探索，但它还没有可执行的仓库基线。第一个业务垂直切片最终将处理一个合成的企业 API-503 事件；在它的契约、提供方边界、本地模式和验证入口明确之前，不得启动。

This change is cross-cutting by design. It establishes the minimum repository, contract, and local-platform shape that makes a later vertical slice independently verifiable. It must work without network access, model credentials, customer data, or enterprise credentials, and it must run consistently from Windows as well as CI. No business workflow is delivered by this change.

本变更在设计上是跨领域的。它建立最小的仓库、契约和本地平台形态，使后续的垂直切片可独立验证。它必须在没有网络访问、模型凭据、客户数据或企业凭据的情况下工作，并且必须在 Windows 与 CI 上一致运行。本变更不交付任何业务工作流。

The controlling constraints are:

核心约束条件如下：

- Deterministic workflow/control code, not a model, will own state, retries, SLA, side effects, approvals, and completion in later changes.

  - 在后续变更中，确定性的工作流/控制代码（而非模型）将拥有状态、重试、SLA、副作用、审批与完成。

- Cases and revisions must be immutable; business events must be append-only; evidence must remain content-addressable.

  - 用例与修订必须不可变；业务事件必须只追加（append-only）；证据必须保持内容可寻址。

- A future external write must use intent/reconcile/execute/complete with a stable idempotency key and a natural key. Change 0 creates only the contracts and safety boundary for that path.

  - 未来的外部写入必须使用 intent/reconcile/execute/complete（意图/协调/执行/完成），并带有稳定的幂等键与自然键。变更 0 仅为该路径创建契约与安全边界。

- Tenant isolation, duplicate side effects, stale approvals, unauthorized writes, and missing evidence are hard gates. The baseline must fail closed before any live provider can be selected.

  - 租户隔离、重复副作用、过期审批、未授权写入与证据缺失是硬性关卡（hard gates）。在任何实时提供方被选中之前，基线必须“失败关闭”（fail closed）。

- Single-agent deterministic replay is the baseline. Multi-agent operation is intentionally absent.

  - 单智能体确定性重放是基线。多智能体操作被有意排除。

## Goals / Non-Goals

**Goals:**

**目标：**

- Create a coherent monorepo layout and one cross-platform command surface for checking, starting, testing, and stopping local development modes.

  - 创建一致的 monorepo 布局与单一跨平台命令界面，用于检查、启动、测试、停止本地开发模式。

- Make versioned JSON Schema the language-neutral contract source for the core case, revision, event, artifact/evidence, policy, approval, replay, and evaluation objects.

  - 将带版本的 JSON Schema 作为核心用例、修订、事件、工件/证据、策略、审批、重放与评估对象的语言无关契约源。

- Give Python and TypeScript consumers a checked contract representation and expose a minimal FastAPI OpenAPI document that refers to the same semantic models.

  - 为 Python 与 TypeScript 使用者提供经过校验的契约表示，并暴露一个最小的 FastAPI OpenAPI 文档，引用相同的语义模型。

- Bootstrap the five planned application boundaries—Platform API, Control Worker, Agent Runtime, Business Simulator, and Web Console—with explicit health and readiness behavior rather than fabricated business results.

  - 引导五个规划中的应用边界——平台 API、控制 Worker、智能体运行时、业务模拟器与 Web 控制台——具备明确的健康与就绪行为，而非捏造的业务结果。

- Support a default offline/replay mode and an opt-in local service-boundary mode with PostgreSQL, Temporal, object storage, and OpenTelemetry.

  - 支持默认的离线/重放模式，以及可选加入的本地服务边界模式（PostgreSQL、Temporal、对象存储与 OpenTelemetry）。

- Ensure unsafe provider selections, credentials, and external-write paths are rejected before startup or kept not-ready; establish tests that prove this negative behavior.

  - 确保在启动前拒绝不安全的提供方选择、凭据与外部写入路径，或使其保持“未就绪”；建立证明此否定行为的测试。

**Non-Goals:**

**非目标：**

- Implementing an inbound IM adapter, customer/SLA enrichment, investigation, ticket creation, human approval workflow, outbound reply, knowledge publishing, or an evaluation scorecard.

  - 实现入站 IM 适配器、客户/SLA 富化、调查、工单创建、人工审批工作流、出站回复、知识发布或评估记分卡。

- Calling a model, Tencent/WeCom, CRM, ticketing, monitoring, object-storage SaaS, or any other real external provider.

  - 调用模型、腾讯/企业微信、CRM、工单、监控、对象存储 SaaS 或任何其他真实外部提供方。

- Implementing a production database schema, tenant administration, authorization model, production deployment, or multi-agent orchestration.

  - 实现生产数据库模式、租户管理、授权模型、生产部署或多智能体编排。

- Treating a successful process startup as evidence that the future customer-issue workflow works.

  - 将成功的过程启动视为未来客户问题工作流有效的证据。

## Decisions

## 决策

### 1. Use a boundary-oriented monorepo with a single Python development entry point

### 1. 使用面向边界的 monorepo，并以单一 Python 开发入口为起点

The repository will be arranged around deployable boundaries and shared packages:

仓库将围绕可部署边界与共享包进行组织：

| Area | Responsibility in Change 0 | Explicitly absent in Change 0 |
| --- | --- | --- |
| `apps/platform-api` | FastAPI process, OpenAPI, liveness/readiness endpoints | Enterprise-facing business API behavior |
| `apps/control-worker` | Temporal worker startup boundary and dependency readiness | Case workflow execution or retries |
| `apps/agent-runtime` | Replay-provider selection boundary and readiness | Model planning or tool execution |
| `apps/business-simulator` | Synthetic fixture/replay source boundary | Real CRM, ticket, monitoring, or IM integration |
| `apps/web-console` | TypeScript/Vue startup boundary and contract consumption | Production case-management UI |
| `packages/python/*` | Contracts, control-kernel interfaces, telemetry, and test utilities | Business implementation |
| `packages/typescript/*` | Contract representations used by the console | Business implementation |
| `contracts/`, `deploy/`, `scripts/`, `tests/`, `evals/`, `docs/` | Versioned assets, local ops, verification, and guidance | Live operations |

| 区域 | 变更 0 中的职责 | 变更 0 中明确缺失的部分 |
| --- | --- | --- |
| `apps/platform-api` | FastAPI 进程、OpenAPI、存活/就绪端点 | 面向企业的业务 API 行为 |
| `apps/control-worker` | Temporal worker 启动边界与依赖就绪 | 用例工作流执行或重试 |
| `apps/agent-runtime` | 重放提供方选择边界与就绪 | 模型规划或工具执行 |
| `apps/business-simulator` | 合成 fixture/重放源边界 | 真实 CRM、工单、监控或 IM 集成 |
| `apps/web-console` | TypeScript/Vue 启动边界与契约消费 | 生产用案例管理 UI |
| `packages/python/*` | 契约、控制内核接口、遥测与测试工具 | 业务实现 |
| `packages/typescript/*` | 控制台使用的契约表示 | 业务实现 |
| `contracts/`、`deploy/`、`scripts/`、`tests/`、`evals/`、`docs/` | 带版本资产、本地运维、验证与指导 | 实时运营 |

`scripts/dev.py` is the sole cross-platform command front door once implementation starts. It will own platform-neutral subcommands such as `check`, `up`, `down`, `test`, `contracts`, `health`, and `compose`; it may call `uv`, `pnpm`, and Docker, but contributors should not need shell-specific command sequences. Python uses a uv workspace and TypeScript uses a pnpm workspace.

`scripts/dev.py` 是实现开始后唯一的跨平台命令入口。它将拥有平台中立的子命令，如 `check`、`up`、`down`、`test`、`contracts`、`health` 与 `compose`；它可以调用 `uv`、`pnpm` 与 Docker，但贡献者不应需要特定于 shell 的命令序列。Python 使用 uv workspace，TypeScript 使用 pnpm workspace。

**Why this choice:** separate process boundaries make future reliability gates observable and testable without prematurely deploying microservices. A shared application package or a shell-script-only bootstrap would make the future control/runtime split ambiguous and unreliable on Windows.

**为何如此选择：** 分离的进程边界使未来的可靠性关卡可观测、可测试，而无需过早部署微服务。共享应用包或仅 shell 脚本的引导会使未来控制/运行时拆分在 Windows 上变得模糊且不可靠。

**Alternatives considered:** a single Python service would lower initial file count, but hides the intended ownership boundaries; independently managed repositories would add release and contract coordination cost before any business value exists. Both are rejected.

**已考虑的替代方案：** 单一 Python 服务会降低初始文件数量，但会隐藏预期的职责边界；独立管理的仓库会在任何业务价值产生前增加发布与契约协调成本。两者均被拒绝。

### 2. Make versioned JSON Schema canonical, with checked language adapters

### 2. 以带版本的 JSON Schema 为规范，配合经过校验的语言适配器

The canonical contract source will live under `contracts/jsonschema/v<major>/`. Each schema has a stable `$id`, a declared `schema_version`, and a compatible fixture set. At minimum Change 0 defines schemas for:

规范契约源位于 `contracts/jsonschema/v<major>/`。每个 schema 拥有稳定的 `$id`、声明的 `schema_version` 与一组兼容的 fixture。变更 0 至少定义以下 schema：

- `Case`, `CaseRevision`, and `BusinessEvent`;

  - `Case`、`CaseRevision` 与 `BusinessEvent`；

- `Artifact` and `EvidenceReference`;

  - `Artifact` 与 `EvidenceReference`；

- `CapabilityGrant`, `PolicyDecision`, `ApprovalRequest`, and `ApprovalDecision`;

  - `CapabilityGrant`、`PolicyDecision`、`ApprovalRequest` 与 `ApprovalDecision`；

- `ReplayRequest`, `ReplayResult`, `EvaluationCase`, and `EvaluationResult`;

  - `ReplayRequest`、`ReplayResult`、`EvaluationCase` 与 `EvaluationResult`；

- a reserved `ExternalWriteIntent` envelope for later intent/reconcile/execute/complete work.

  - 为后续 intent/reconcile/execute/complete 工作保留的 `ExternalWriteIntent` 信封。

Python and TypeScript adapters validate the same JSON fixtures and publish types appropriate to each runtime. The Platform API OpenAPI document exposes its health/readiness endpoints and references the corresponding versioned schema components where a contract is exposed. A CI check must fail if a canonical schema cannot be consumed by both adapters or if a compatibility fixture changes unexpectedly.

Python 与 TypeScript 适配器校验相同的 JSON fixtures，并发布适合各自运行时的类型。Platform API 的 OpenAPI 文档暴露其健康/就绪端点，并在暴露契约处引用相应的带版本 schema 组件。如果任一适配器无法消费规范 schema，或兼容 fixture 发生意外变更，CI 检查必须失败。

Every boundary object carries `schema_version`, `tenant_id` where tenant-scoped, a stable object identity, and correlation/causation metadata where eventful. Case identity is stable; each `CaseRevision` is immutable, monotonic within its case, and points to its predecessor when one exists. `BusinessEvent` is append-only and has a unique event identity. Artifact and evidence references contain a content hash and redaction classification, not raw private payloads.

每个边界对象都携带 `schema_version`、在租户范围内携带 `tenant_id`、稳定的对象标识，以及在有事件时携带关联/因果元数据。用例标识是稳定的；每个 `CaseRevision` 不可变、在用例内单调递增，并在存在前驱时指向它。`BusinessEvent` 只追加且具有唯一事件标识。工件与证据引用包含内容哈希与脱敏分类，而非原始私有负载。

The reserved external-write intent derives its idempotency key deterministically from the tenant, provider identifier, operation, natural key, and canonical intended-state hash. It is a schema-only reservation in this change: no provider implementation may create, reconcile, execute, or complete an external side effect.

保留的外部写入意图的幂等键，由其租户、提供方标识、操作、自然键与规范预期状态哈希确定性派生。在本变更中它仅是 schema 层面的保留：任何提供方实现都不得创建、协调、执行或完成外部副作用。

**Why this choice:** JSON Schema is language-neutral, reviewable, and directly testable against synthetic fixtures. It lets FastAPI/Python and Vue/TypeScript evolve independently without making a Python model an implicit API source of truth.

**为何如此选择：** JSON Schema 语言无关、可审阅，且可直接针对合成 fixtures 进行测试。它让 FastAPI/Python 与 Vue/TypeScript 独立演进，而无需让 Python 模型成为隐含的 API 事实来源。

**Alternatives considered:** Pydantic-only source models are convenient for FastAPI but make TypeScript a secondary consumer; manually duplicated Python/TypeScript interfaces inevitably drift. Both are rejected in favor of canonical schemas plus adapter compatibility tests.

**已考虑的替代方案：** 仅 Pydantic 的源模型对 FastAPI 很方便，但会使 TypeScript 沦为次级消费者；手动复制的 Python/TypeScript 接口不可避免地会产生分歧。两者均被拒绝，改而采用规范 schema 加适配器兼容性测试。

### 3. Offer two explicit local modes, both deterministic by default

### 3. 提供两种明确的本地模式，默认均确定性

The default `offline` mode uses only local process resources and synthetic replay fixtures. It may use in-memory or local SQLite-backed test storage, but it must require neither Docker nor network access. The `service-boundary` mode is an explicit local-development option that starts PostgreSQL, Temporal, an S3-compatible object store, and OpenTelemetry Collector through Compose, then connects the application skeletons to those dependencies.

默认的 `offline` 模式仅使用本地进程资源与合成重放 fixtures。它可以使用内存或本地 SQLite 支持的测试存储，但必须既不要求 Docker 也不要求网络访问。`service-boundary` 模式是一个显式的本地开发选项，它通过 Compose 启动 PostgreSQL、Temporal、S3 兼容对象存储与 OpenTelemetry Collector，然后将应用骨架连接到这些依赖。

Both modes use `provider.mode=replay` and `provider.allow_live=false` by default. Configuration validation must reject an attempt to select a non-replay model/provider, real credentials, a real external-write adapter, or a multi-agent coordinator. The rejection is deterministic, produces a redacted diagnostic, and prevents readiness from becoming true. A future OpenSpec change—not an environment variable alone—must define the live-provider capability, policy gates, and associated negative tests before this behavior can change.

两种模式默认使用 `provider.mode=replay` 与 `provider.allow_live=false`。配置校验必须拒绝选择非重放模型/提供方、真实凭据、真实外部写入适配器或多智能体协调器的尝试。该拒绝是确定性的，产生脱敏诊断，并阻止就绪状态变为 true。未来的 OpenSpec 变更——而非仅靠环境变量——必须在该行为改变之前定义实时提供方能力、策略关卡与相关的否定测试。

**Why this choice:** offline mode preserves reproducible evaluation and lets contributors work without infrastructure; service-boundary mode catches integration assumptions early. A single Docker-only mode would make the harness inaccessible, while an unrestricted environment-variable switch could accidentally enable unsafe behavior.

**为何如此选择：** 离线模式保留可复现的评估，让贡献者无需基础设施即可工作；服务边界模式尽早捕获集成假设。仅 Docker 的单一模式会使该 harness 不可用，而无限制的环境变量开关可能意外启用不安全行为。

**Alternatives considered:** allowing a “live if credentials exist” convenience path and treating provider configuration as best-effort are rejected because they undermine the hard safety gates.

**已考虑的替代方案：** 允许“若有凭据即实时”的便利路径、将提供方配置视为尽力而为（best-effort），均被拒绝，因为它们会破坏硬性安全关卡。

### 4. Separate operational status from business success, and fail closed

### 4. 将运行状态与业务成功分离，并失败关闭

Every application skeleton exposes liveness and readiness. Liveness answers whether its process can serve diagnostics; readiness answers whether its selected mode and required dependencies have passed configuration and dependency checks. In offline mode, replay fixtures and local contract assets are readiness dependencies. In service-boundary mode, each configured local dependency is checked independently and reported as a redacted component status.

每个应用骨架暴露存活（liveness）与就绪（readiness）。存活说明其进程能否提供诊断；就绪说明其选定模式与所需依赖是否通过配置与依赖检查。在离线模式下，重放 fixtures 与本地契约资产是就绪依赖。在服务边界模式下，每个配置的本地依赖被独立检查，并作为脱敏组件状态报告。

No endpoint, test fixture, or log may represent a case as resolved or an external operation as complete in Change 0. The only permitted operational states are startup/healthy/not-ready/failed configuration. The eventual business state machine is deferred to Change 1.

在变更 0 中，任何端点、测试 fixture 或日志都不得将一个用例表示为已解决，或将外部操作表示为已完成。唯一允许的运行状态是 启动/健康/未就绪/配置失败。最终的业务状态机推迟到变更 1。

Configuration failures, invalid contracts, unavailable required dependencies, and a forbidden provider selection result in a non-ready or failed startup state. Test-only fault profiles may inject those conditions through named synthetic fixtures; they must not contact an external system. This lays the basis for future restart, timeout, out-of-order, duplicate, and denial tests without pretending those workflow transitions exist yet.

配置失败、无效契约、不可用必需依赖，或被禁止的提供方选择，会导致非就绪或失败启动状态。仅测试的故障配置可通过命名合成 fixtures 注入这些条件；它们不得联系外部系统。这为未来重启、超时、乱序、重复与拒绝测试奠定了基础，而无需假装这些工作流转换已经存在。

**Why this choice:** a green process is not proof of a correct agent workflow. Separating readiness from case success prevents false claims in demos and CI.

**为何如此选择：** 绿色进程不是正确智能体工作流的证明。将就绪与用例成功分离，可防止在演示与 CI 中做出虚假声明。

### 5. Establish observability and evidence hygiene at the boundary

### 5. 在边界建立可观测性与证据卫生

All skeleton processes will use structured, redacted logging and OpenTelemetry resource attributes for service name, build/version, local mode, and trace/correlation identifiers. Logs, traces, fixtures, and reports must not contain secrets, raw customer messages, unrestricted tool output, or credential material. The object-store boundary stores only synthetic content-addressed artifacts in local development; it is not a production evidence store.

所有骨架进程将使用结构化、脱敏日志与 OpenTelemetry 资源属性，用于服务名、构建/版本、本地模式，以及追踪/关联标识。日志、追踪、fixtures 与报告不得包含秘密、原始客户消息、无限制工具输出或凭据材料。对象存储边界在本地开发中仅存储合成的内容寻址工件；它不是生产证据存储。

The first baseline includes a redaction utility and a secret-hygiene CI check. Contract fixtures use synthetic tenant/customer identifiers. Evidence contracts carry hash, media type, producer, and redaction state so future verifiers can consume them without needing raw content.

首个基线包含一个脱敏工具与一项秘密卫生 CI 检查。契约 fixtures 使用合成的租户/客户标识。证据契约携带哈希、媒体类型、生产者与脱敏状态，以便未来验证器无需原始内容即可消费它们。

**Why this choice:** retrofitting safe observability later makes test data and demo evidence untrustworthy. A minimal convention is inexpensive now and preserves the reliability-harness premise.

**为何如此选择：** 事后改造安全的可观测性会使测试数据与演示证据变得不可信。现在采用最小约定成本很低，且保留了可靠性 harness 的前提。

### 6. Verification is contract-first and has no network/model dependency

### 6. 验证是契约优先且无网络/模型依赖

The initial acceptance harness will provide:

初始验收 harness 将提供：

- a deterministic environment check for workspace tooling, safe configuration, and required local assets;

  - 针对工作区工具、安全配置与所需本地资产的确定性环境检查；

- process-level liveness/readiness checks in offline mode;

  - 离线模式下的进程级存活/就绪检查；

- Compose dependency and readiness checks in service-boundary mode when Docker is available;

  - Docker 可用时，服务边界模式下的 Compose 依赖与就绪检查；

- Python and TypeScript validation of the same valid and invalid JSON fixtures;

  - 相同有效与无效 JSON fixtures 的 Python 与 TypeScript 校验；

- OpenAPI/schema consistency checks where the API exposes a contract;

  - API 暴露契约处的 OpenAPI/schema 一致性检查；

- negative tests for live-provider, credential, external-write, and multi-agent configuration;

  - 针对实时提供方、凭据、外部写入与多智能体配置的否定测试；

- fixture-driven fault tests for unavailable dependencies, invalid schema input, and startup/restart behavior;

  - 针对不可用依赖、无效 schema 输入与启动/重启行为的 fixture 驱动故障测试；

- CI checks for formatting/linting, tests, contract snapshots, and secrets.

  - 针对格式化/lint、测试、契约快照与秘密的 CI 检查。

These checks provide evidence that the foundation is operable and constrained. They do not provide evidence of customer-issue resolution quality, side-effect idempotency, tenant isolation in a production database, or provider correctness; those are explicit follow-on acceptance targets.

这些检查提供基础可操作且受约束的证据。它们不提供客户问题解决质量、副作用幂等性、生产数据库中租户隔离或提供方正确性的证据；这些是明确的后续验收目标。

## Risks / Trade-offs

## 风险 / 权衡

- [Canonical schema and adapters drift] → Generate or validate both adapters against shared fixtures in CI; version schemas rather than silently changing `v1` semantics.

  - [规范 schema 与适配器分歧] → 在 CI 中针对共享 fixtures 生成或校验两个适配器；对 schema 进行版本管理，而非悄悄改变 `v1` 语义。

- [Skeleton services create an illusion of completed product behavior] → Limit endpoints to health/readiness, state non-goals in API/documentation, and keep business-workflow tests out of Change 0 acceptance claims.

  - [骨架服务营造已完成产品行为的假象] → 将端点限制在健康/就绪，在 API/文档中说明非目标，并将业务工作流测试排除在变更 0 验收声明之外。

- [Docker/Temporal is too heavy for some contributor machines] → Make offline mode the required baseline and service-boundary mode opt-in, with granular readiness diagnostics.

  - [Docker/Temporal 对部分贡献者机器过重] → 将离线模式设为必需基线，服务边界模式可选加入，并提供细粒度就绪诊断。

- [A configuration convenience feature enables a live provider accidentally] → Default to replay, reject forbidden provider/credential settings before readiness, and test the rejection path.

  - [配置便利功能意外启用实时提供方] → 默认重放，在就绪前拒绝被禁止的提供方/凭据设置，并测试拒绝路径。

- [Windows shell differences make setup flaky] → Put routine commands behind `scripts/dev.py`; CI invokes the same command surface where practical.

  - [Windows shell 差异导致设置不稳定] → 将日常命令放在 `scripts/dev.py` 之后；CI 在可行时调用相同的命令界面。

- [Synthetic fixtures leak into future demonstrations as if they were live evidence] → Mark fixtures and results with deterministic source/mode metadata and retain no raw external payloads.

  - [合成 fixtures 作为实时证据泄漏到未来演示] → 用确定性来源/模式元数据标记 fixtures 与结果，不保留原始外部负载。

- [Foundation contracts over-constrain the first vertical slice] → Keep `v1` focused on invariants and permit additive future schemas; require a new OpenSpec change for incompatible revisions.

  - [基础契约过度约束首个垂直切片] → 让 `v1` 聚焦于不变量，允许未来增量 schema；不兼容修订需要新的 OpenSpec 变更。

## Migration Plan

## 迁移计划

1. Add the workspace metadata, directory skeleton, canonical `v1` contract directory, safe configuration defaults, and developer command surface without enabling a live provider.

   1. 添加工作区元数据、目录骨架、规范 `v1` 契约目录、安全配置默认值与开发者命令界面，但不启用实时提供方。

2. Add Python/TypeScript contract adapters, synthetic fixtures, health/readiness skeletons, and offline acceptance checks.

   2. 添加 Python/TypeScript 契约适配器、合成 fixtures、健康/就绪骨架与离线验收检查。

3. Add local Compose definitions and service-boundary readiness checks, keeping Docker optional for the offline baseline.

   3. 添加本地 Compose 定义与服务边界就绪检查，离线基线保持 Docker 可选。

4. Add CI gates and record the verified commands, limitations, and baseline evidence in `docs/PROJECT_MEMORY.md` when the change is archived.

   4. 添加 CI 关卡，并在变更归档时，将已验证命令、限制与基线证据记录到 `docs/PROJECT_MEMORY.md`。

There is no production data migration or rollout in this change. Rollback means disabling/removing the new local service stack and returning to the pre-foundation documentation-only state. Once `v1` contracts are consumed by a subsequent change, incompatible changes require a new major-version directory and migration/compatibility fixtures rather than in-place mutation.

本变更没有生产数据迁移或发布。回滚意味着禁用/移除新的本地服务栈，并返回到基础建立前的仅文档状态。一旦后续变更消费 `v1` 契约，不兼容变更需要新的主版本目录与迁移/兼容 fixtures，而非就地变更。

## Open Questions

## 待决问题

- Exact package and image versions will be pinned by the implementation manifests after `scripts/dev.py check` verifies the supported local toolchain; the architectural boundaries and safety defaults above do not depend on a particular patch version.

  - 精确包与镜像版本将由实现清单在 `scripts/dev.py check` 验证所支持的本地工具链后固定；上述架构边界与安全默认值不依赖特定补丁版本。

- The initial contract-code generation tool may be selected during Apply, provided the canonical JSON Schema files remain the source of truth and the Python/TypeScript fixture compatibility checks stay mandatory.

  - 初始契约代码生成工具可在 Apply 期间选择，前提是规范 JSON Schema 文件保持事实来源，且 Python/TypeScript fixture 兼容性检查保持强制。

- Compose may use a local S3-compatible implementation such as MinIO; its selection is an implementation detail so long as it remains local-only and is hidden behind the object-store boundary.

  - Compose 可使用本地 S3 兼容实现（如 MinIO）；其选择是实现细节，只要它保持仅本地且隐藏在对象存储边界之后。
