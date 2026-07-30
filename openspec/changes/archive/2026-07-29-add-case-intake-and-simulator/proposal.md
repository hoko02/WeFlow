## Why

## 动机

Change 0 established versioned contracts and safe offline service boundaries, but it cannot turn an inbound enterprise-IM message into a durable business record. The smallest useful reliability vertical is therefore a deterministic synthetic IM intake that creates exactly one tenant-scoped Case, immutable initial CaseRevision, and auditable append-only event trail under duplicate and out-of-order delivery.

变更 0 建立了带版本的契约与安全的离线服务边界，但它无法将一个入站企业 IM 消息转化为持久的业务记录。因此，最小有用的可靠性垂直切片是一个确定性的合成 IM 接入，在重复投递与乱序投递下，创建恰好一个租户范围的 Case、不可变的初始 CaseRevision，以及可审计的只追加事件轨迹。

This change makes the first business-state claim testable without introducing a model, durable workflow, real provider, external write, or customer-resolution claim.

本变更使首个业务状态声明可被测试，而无需引入模型、持久工作流、真实提供方、外部写入或客户解决声明。

## What Changes

## 变更内容

- Add a synthetic, local-only IM intake boundary that accepts a versioned normalized inbound message envelope, validates tenant/channel/conversation/sender identity, and derives a stable inbound natural key and content fingerprint.

  - 新增一个合成、仅本地的 IM 接入边界，接受带版本的规范化入站消息信封，校验租户/渠道/会话/发送方标识，并派生稳定的入站自然键与内容指纹。

- Add deterministic duplicate and ordering handling: an identical delivery returns the original Case result without appending another creation event; an invalid or unsupported out-of-order delivery is rejected with a stable, payload-safe error code and leaves durable state unchanged.

  - 新增确定性的重复与排序处理：相同投递返回原始 Case 结果且不追加另一个创建事件；无效或不支持的乱序投递以稳定、对负载安全的错误码被拒绝，且不改变持久状态。

- Persist one stable Case and immutable CaseRevision 1 for an accepted inbound event, alongside an append-only BusinessEvent ledger and a tenant-scoped read projection. The only initial Case state is `RECEIVED`; later workflow state transitions remain out of scope.

  - 为被接受的入站事件持久化一个稳定 Case 与不可变 CaseRevision 1，外加只追加的 BusinessEvent 账本与租户范围的读取投影。唯一的初始 Case 状态是 `RECEIVED`；后续工作流状态转换不在本范围内。

- Expose narrow local Platform API and IM Simulator surfaces for intake, Case lookup, revision/timeline lookup, deterministic snapshot export/restore, and reset used by synthetic fixtures. The API never accepts caller-provided tenant authority.

  - 暴露窄化的本地 Platform API 与 IM 模拟器接口，用于接入、Case 查询、修订/时间线查询、确定性快照导出/恢复，以及合成 fixtures 使用的重置。该 API 绝不接受调用方提供的租户权限。

- Extend the canonical compatible `v1` contracts with the inbound message and Case projection boundary objects needed by this slice; retain all existing `v1` fixtures and cross-language compatibility checks.

  - 用本切片所需的入站消息与 Case 投影边界对象扩展规范的兼容 `v1` 契约；保留所有现有 `v1` fixtures 与跨语言兼容性检查。

- Add three synthetic golden fixtures and negative tests covering first delivery, duplicate delivery, tenant isolation, and out-of-order rejection. Update the development guide to distinguish implemented intake/ledger behavior from the still unimplemented support-resolution workflow.

  - 新增三个合成 golden fixtures 与否定测试，覆盖首次投递、重复投递、租户隔离与乱序拒绝。更新开发指南，区分已实现接入/账本行为与仍未实现的支持解决工作流。

## Capabilities

## 能力

### New Capabilities

### 新增能力

- `synthetic-im-case-intake`: Local deterministic ingestion of normalized synthetic IM events with identity validation, canonical fingerprinting, idempotent case creation, tenant isolation, and stable intake outcomes.

  - `synthetic-im-case-intake`：本地确定性接入规范化合成 IM 事件，含标识校验、规范指纹、幂等 Case 创建、租户隔离与稳定的接入结果。

- `case-event-ledger`: Immutable Case and CaseRevision records, append-only business events, deterministic read projections, and snapshot/restore semantics for the synthetic local business state.

  - `case-event-ledger`：不可变 Case 与 CaseRevision 记录、只追加业务事件、确定性读取投影，以及用于合成本地业务状态的快照/恢复语义。

### Modified Capabilities

### 修改的能力

- `versioned-domain-contracts`: Extend compatible `v1` contract coverage and cross-language fixtures for inbound IM envelopes and the tenant-scoped Case projection used at the new API boundary.

  - `versioned-domain-contracts`：为入站 IM 信封与新 API 边界使用的租户范围 Case 投影，扩展兼容 `v1` 契约覆盖范围与跨语言 fixtures。

## Impact

## 影响

- Affected code: `apps/platform-api`, `apps/business-simulator`, shared Python and TypeScript contract packages, local fixture/test directories, `scripts/dev.py`, and developer documentation.

  - 受影响的代码：`apps/platform-api`、`apps/business-simulator`、共享 Python 与 TypeScript 契约包、本地 fixture/测试目录、`scripts/dev.py`，以及开发者文档。

- Affected interfaces: local loopback-only synthetic IM intake, tenant-scoped Case query, revision/timeline query, and deterministic simulator snapshot endpoints.

  - 受影响的接口：仅本地 loopback 的合成 IM 接入、租户范围 Case 查询、修订/时间线查询，以及确定性模拟器快照端点。

- Affected data boundary: offline local state contains synthetic identifiers and redacted/content-hashed message metadata only; raw private customer content, credentials, real enterprise identities, and unrestricted tool output remain out of scope.

  - 受影响的数据边界：离线本地状态仅包含合成标识与脱敏/内容哈希的消息元数据；原始私有客户内容、凭据、真实企业标识与无限制工具输出仍不在范围内。

- Verification: retained `v1` compatibility checks, API/contract parity checks, duplicate and out-of-order negative tests, tenant-isolation tests, repeated-run baseline checks, and a machine-readable Change 1 acceptance report.

  - 验证：保留的 `v1` 兼容性检查、API/契约一致性检查、重复与乱序否定测试、租户隔离测试、重复运行基线检查，以及机器可读的 Change 1 验收报告。

## Non-Goals and Validation Boundary

## 非目标与验证边界

- Do not implement CRM, monitoring, knowledge, ticketing, approval, or outbound IM simulators beyond the narrow inbound synthetic IM source required for this slice.

  - 除本切片所需的窄化入站合成 IM 源外，不实现 CRM、监控、知识、工单、审批或出站 IM 模拟器。

- Do not start Temporal workflows, perform SLA enrichment, invoke a model, call a real Tencent/WeCom or enterprise provider, create an external write intent, or enable multi-agent coordination.

  - 不启动 Temporal 工作流、不执行 SLA 富化、不调用模型、不调用真实腾讯/企业微信或企业提供方、不创建外部写入意图、不启用多智能体协作。

- Do not claim the API-503 incident is triaged, investigated, resolved, approved, or delivered. This change proves only safe, durable Case intake and auditability.

  - 不声称 API-503 事件已被分诊、调查、解决、审批或交付。本变更仅证明安全、持久的 Case 接入与可审计性。
