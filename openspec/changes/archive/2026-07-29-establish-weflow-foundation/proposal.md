## Why

## 动机

WeFlow currently has an explored architecture but no runnable, contract-checked baseline from which later incident-resolution slices can be developed and evaluated. Establishing that baseline now prevents later changes from coupling business behavior to unversioned schemas, unsafe provider configuration, or environment-specific startup assumptions.

WeFlow 当前已有一个被探索过的架构，但没有可运行、经过契约检查的基线，后续的事件处理切片可基于其进行开发与评估。现在建立该基线，可防止后续变更将业务行为与未版本化 schema、不安全的提供方配置，或特定于环境的启动假设耦合在一起。

## What Changes

## 变更内容

- Establish a single WeFlow monorepo layout with Python and TypeScript workspaces, a cross-platform development entry point, service startup skeletons, and machine-checkable health/readiness behavior.

  - 建立单一 WeFlow monorepo 布局，包含 Python 与 TypeScript 工作区、跨平台开发入口、服务启动骨架，以及可机器检查的健康/就绪行为。

- Define versioned, contract-first schemas for cases, immutable revisions, append-only business events, artifacts/evidence, policy decisions, approvals, replay inputs, and evaluation results; publish compatible JSON Schema/OpenAPI and Python/TypeScript consumer contracts.

  - 为用例、不可变修订、只追加业务事件、工件/证据、策略决策、审批、重放输入与评估结果，定义带版本、契约优先的 schema；发布兼容的 JSON Schema/OpenAPI，以及 Python/TypeScript 消费者契约。

- Provide local offline and service-boundary development modes. The latter provisions PostgreSQL, Temporal, object storage, and OpenTelemetry through Compose, while the default provider path remains deterministic replay with synthetic fixtures.

  - 提供本地离线与服务边界开发模式。后者通过 Compose 配置 PostgreSQL、Temporal、对象存储与 OpenTelemetry，而默认提供方路径保持确定性重放与合成 fixtures。

- Establish provider-safety configuration so models, real enterprise credentials, real external writes, and multi-agent collaboration are disabled unless a future OpenSpec change explicitly enables them.

  - 建立提供方安全配置，使模型、真实企业凭据、真实外部写入与多智能体协作默认禁用，除非未来的 OpenSpec 变更显式启用它们。

- Add baseline CI, contract compatibility checks, health checks, secret-hygiene checks, and developer documentation needed to verify the foundation without network access or model credentials.

  - 添加基线 CI、契约兼容性检查、健康检查、秘密卫生检查与开发者文档，无需网络访问或模型凭据即可验证基础。

## Capabilities

## 能力

### New Capabilities

### 新增能力

- `workspace-operability`: A reproducible monorepo baseline, development commands, service health/readiness contracts, CI checks, and secret-safe configuration conventions.

  - `workspace-operability`：可复现的 monorepo 基线、开发命令、服务健康/就绪契约、CI 检查与秘密安全配置约定。

- `versioned-domain-contracts`: Canonical, versioned cross-language schemas for the case, revision, event, evidence, policy, approval, replay, and evaluation domains.

  - `versioned-domain-contracts`：针对用例、修订、事件、证据、策略、审批、重放与评估领域的规范、带版本跨语言 schema。

- `local-platform-dependencies`: Explicit offline and Compose-backed local platform modes for the services and their PostgreSQL, Temporal, object-store, and telemetry dependencies.

  - `local-platform-dependencies`：服务及其 PostgreSQL、Temporal、对象存储与遥测依赖的明确离线与 Compose 支持的本地平台模式。

- `safe-provider-runtime-boundary`: A replay-first provider boundary that rejects live model, real-credential, external-write, and multi-agent operation by default.

  - `safe-provider-runtime-boundary`：重放优先的提供方边界，默认拒绝实时模型、真实凭据、外部写入与多智能体操作。

### Modified Capabilities

### 修改的能力

- None; no baseline capability specifications exist yet.

  - 无；尚不存在基线能力规范。

## Impact

## 影响

- Planned code and configuration surface: root workspace metadata; `scripts/dev.py`; startup skeletons under `apps/`; Python and TypeScript contract packages; local Compose, observability, CI, and test configuration.

  - 计划中的代码与配置面：根工作区元数据；`scripts/dev.py`；`apps/` 下的启动骨架；Python 与 TypeScript 契约包；本地 Compose、可观测性、CI 与测试配置。

- Planned interfaces: versioned JSON Schema and OpenAPI documents plus generated or checked Python and TypeScript contract representations. This change does not expose a real enterprise-facing integration API.

  - 计划的接口：带版本的 JSON Schema 与 OpenAPI 文档，加上生成或经过校验的 Python 与 TypeScript 契约表示。本变更不暴露真实的企业集成 API。

- Planned data and security boundary: local development dependencies and synthetic fixtures only; no customer data, secrets, model credentials, real tenant access, or external writes.

  - 计划的数据与安全边界：仅为本地开发依赖与合成 fixtures；无客户数据、秘密、模型凭据、真实租户访问或外部写入。

- Planned verification and documentation: contract compatibility, negative provider-safety checks, service health/readiness checks, environment validation, and updates to developer guidance and project memory.

  - 计划的验证与文档：契约兼容性、否定提供方安全检查、服务健康/就绪检查、环境验证，以及更新开发者指导与项目记忆。

## Non-Goals and Validation Boundary

## 非目标与验证边界

- This change does not implement the API-503 support-resolution workflow, ticket creation, outbound replies, approvals, knowledge publishing, SLA enforcement, or an evaluation scorecard.

  - 本变更不实现 API-503 支持解决工作流、工单创建、出站回复、审批、知识发布、SLA 执行或评估记分卡。

- It does not validate any real Tencent/WeCom, CRM, ticketing, monitoring, model, or enterprise-IM integration. Those claims remain simulated, disabled, and unverified.

  - 它不验证任何真实腾讯/企业微信、CRM、工单、监控、模型或企业 IM 集成。这些声明保持模拟、禁用且未验证。

- It does not enable production deployment, production tenancy, real external side effects, or multi-agent collaboration.

  - 它不启用生产部署、生产租户、真实外部副作用或多智能体协作。
