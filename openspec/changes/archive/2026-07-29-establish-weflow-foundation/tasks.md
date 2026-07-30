## 1. Workspace and safe configuration baseline

## 1. 工作区与安全配置基线

- [x] 1.1 Create the root uv and pnpm workspace manifests, package boundaries, toolchain constraints, and repository directory skeleton described in the design; add an automated manifest/layout check.

  - [ ] 1.1 创建设计中描述的 root uv 与 pnpm 工作区清单、包边界、工具链约束与仓库目录骨架；添加自动化清单/布局检查。

- [x] 1.2 Implement `scripts/dev.py` with cross-platform `check`, `up`, `down`, `test`, `contracts`, `health`, and `compose` command parsing; add unit tests for command dispatch and actionable failure diagnostics.

  - [ ] 1.2 实现 `scripts/dev.py`，包含跨平台 `check`、`up`、`down`、`test`、`contracts`、`health` 与 `compose` 命令解析；为命令分发与可操作的失败诊断添加单元测试。

- [x] 1.3 Add replay-first configuration models, `.env.example`, ignored local overrides, and redacted configuration loading; add tests proving a clean offline configuration needs no secret, network, or Docker.

  - [ ] 1.3 添加重放优先的配置模型、`.env.example`、被忽略的本地覆盖与脱敏配置加载；添加测试证明干净的离线配置不需要秘密、网络或 Docker。

- [x] 1.4 Add repository formatting/lint configuration and a tracked-content secret-hygiene check that reports locations without values; add positive and negative scanner fixtures.

  - [ ] 1.4 添加仓库格式化/lint 配置，以及一项跟踪内容的秘密卫生检查（报告位置而不含值）；添加正面与负面扫描 fixtures。

## 2. Canonical contracts and language adapters

## 2. 规范契约与语言适配器

- [x] 2.1 Create the canonical `contracts/jsonschema/v1` schemas with stable identifiers and versions for Case, CaseRevision, BusinessEvent, Artifact, EvidenceReference, CapabilityGrant, PolicyDecision, ApprovalRequest, ApprovalDecision, ReplayRequest, ReplayResult, EvaluationCase, EvaluationResult, and ExternalWriteIntent.

  - [ ] 2.1 创建规范 `contracts/jsonschema/v1` schema，为 Case、CaseRevision、BusinessEvent、Artifact、EvidenceReference、CapabilityGrant、PolicyDecision、ApprovalRequest、ApprovalDecision、ReplayRequest、ReplayResult、EvaluationCase、EvaluationResult 与 ExternalWriteIntent 提供稳定标识与版本。

- [x] 2.2 Encode immutable case/revision identity, tenant-scoped references, append-only event metadata, content-addressed evidence, and reserved external-write idempotency/natural-key fields in the schemas; add schema-level invalid examples where expressible.

  - [ ] 2.2 在 schema 中编码不可变用例/修订标识、租户范围引用、只追加事件元数据、内容寻址证据，以及保留的外部写入幂等/自然键字段；在可表达处添加 schema 级别的无效示例。

- [x] 2.3 Build the Python contract package around the canonical schemas and add validation utilities for cross-tenant references, duplicate/out-of-order replay fixtures, and stale approval bindings.

  - [ ] 2.3 围绕规范 schema 构建 Python 契约包，并为跨租户引用、重复/乱序重放 fixtures 与过期审批绑定添加校验工具。

- [x] 2.4 Build the TypeScript contract package from or against the same canonical schemas; add parity tests that validate the shared valid and invalid fixture corpus.

  - [ ] 2.4 基于相同的规范 schema 构建 TypeScript 契约包；添加校验共享有效与无效 fixture 语料库的等价性测试。

- [x] 2.5 Add synthetic fixture sets for valid payloads, missing version/schema identity, revision changes, cross-tenant evidence, duplicate delivery, out-of-order delivery, stale approval, and incompatible schema evolution; make the compatibility command fail on a changed `v1` semantic fixture.

  - [ ] 2.5 为有效负载、缺失版本/schema 标识、修订变更、跨租户证据、重复投递、乱序投递、过期审批与不兼容 schema 演进添加合成 fixture 集；在 `v1` 语义 fixture 变更时使兼容性命令失败。

- [x] 2.6 Expose minimal Platform API OpenAPI metadata and health/readiness contract components from the shared schema semantics; add an OpenAPI/schema consistency test.

  - [ ] 2.6 从共享 schema 语义暴露最小 Platform API OpenAPI 元数据与健康/就绪契约组件；添加 OpenAPI/schema 一致性测试。

## 3. Local platform and control skeletons

## 3. 本地平台与控制骨架

- [x] 3.1 Bootstrap the Platform API, Control Worker, Agent Runtime, Business Simulator, and Web Console process boundaries with stable service identities and no business workflow endpoints or success claims.

  - [ ] 3.1 引导 Platform API、Control Worker、Agent Runtime、Business Simulator 与 Web Console 进程边界，具有稳定服务标识，且无业务工作流端点或成功声明。

- [x] 3.2 Implement liveness and readiness semantics for offline mode, including configuration re-evaluation on restart; add process-level tests proving restart does not create events, approvals, side effects, or a case-completion result.

  - [ ] 3.2 实现离线模式的存活与就绪语义，包括重启时的配置重新评估；添加进程级测试证明重启不会创建事件、审批、副作用或用例完成结果。

- [x] 3.3 Create the local Compose topology for PostgreSQL, Temporal, an S3-compatible object store, and OpenTelemetry Collector with local-only defaults and redacted dependency labels.

  - [ ] 3.3 为 PostgreSQL、Temporal、S3 兼容对象存储与 OpenTelemetry Collector 创建本地 Compose 拓扑，具有仅本地默认值与脱敏依赖标签。

- [x] 3.4 Implement service-boundary dependency probes, deadlines, and granular not-ready diagnostics; add timeout and unavailable-dependency tests that prove no fallback to an external provider.

  - [ ] 3.4 实现服务边界依赖探针、截止时间与细粒度未就绪诊断；添加超时与不可用依赖测试，证明不会回退到外部提供方。

- [x] 3.5 Add structured redacted logging, OpenTelemetry resource/correlation conventions, and synthetic content-addressed local artifact handling; add tests that timeout/error evidence excludes secrets, connection strings, raw customer data, and unrestricted tool output.

  - [ ] 3.5 添加结构化脱敏日志、OpenTelemetry 资源/关联约定与合成内容寻址本地工件处理；添加测试证明超时/错误证据排除秘密、连接字符串、原始客户数据与无限制工具输出。

## 4. Replay runtime and hard safety gates

## 4. 重放运行时与硬性安全关卡

- [x] 4.1 Implement the deterministic replay-provider interface and offline fixture loader; add an integration test proving replay input does not initialize a model or external tool client.

  - [ ] 4.1 实现确定性重放提供方接口与离线 fixture 加载器；添加集成测试证明重放输入不初始化模型或外部工具客户端。

- [x] 4.2 Implement fail-closed provider configuration validation for live model/provider selection, enterprise credentials, external-write adapters, and multi-agent coordinators; add one negative test per denied capability category.

  - [ ] 4.2 实现针对实时模型/提供方选择、企业凭据、外部写入适配器与多智能体协调器的失败关闭提供方配置校验；为每个被拒绝能力类别添加一个否定测试。

- [x] 4.3 Ensure the runtime and simulator register no external-write executor and cannot treat replay/model-like content as a capability grant, policy decision, approval, verifier result, completion, or case success; add rejection-path tests for proposed ticket/reply and self-approval-like input.

  - [ ] 4.3 确保运行时与模拟器不注册任何外部写入执行器，且不能将重放/类模型内容视为能力授予、策略决策、审批、验证器结果、完成或用例成功；为提议的工单/回复与类自审批输入添加拒绝路径测试。

- [x] 4.4 Implement named local fault profiles for invalid configuration, unavailable dependencies, restart, duplicate delivery, and out-of-order delivery; add deterministic replay tests that record injected fault metadata without a side effect.

  - [ ] 4.4 为无效配置、不可用依赖、重启、重复投递与乱序投递实现命名本地故障配置；添加确定性重放测试，记录注入的故障元数据而无副作用。

## 5. Minimal console and developer evidence

## 5. 最小控制台与开发者证据

- [x] 5.1 Bootstrap the TypeScript/Vue Web Console with a buildable local shell that consumes the TypeScript contract package and displays only service/mode/readiness diagnostics, not simulated customer-resolution outcomes.

  - [ ] 5.1 引导 TypeScript/Vue Web Console，具有可构建的本地外壳，消费 TypeScript 契约包，并仅显示服务/模式/就绪诊断，而非模拟的客户解决结果。

- [x] 5.2 Add console build and contract-consumption checks, including a fixture that renders redacted not-ready/provider-denial status without exposing configuration values.

  - [ ] 5.2 添加控制台构建与契约消费检查，包括一个渲染脱敏未就绪/提供方拒绝状态而不暴露配置值的 fixture。

- [x] 5.3 Make `scripts/dev.py health` produce a machine-readable, redacted foundation report that separates operational readiness from unimplemented business capabilities; add a snapshot or schema test for the report.

  - [ ] 5.3 让 `scripts/dev.py health` 生成机器可读、脱敏的基础报告，将运行就绪与未实现的业务能力分离；为报告添加快照或 schema 测试。

## 6. End-to-end acceptance and CI

## 6. 端到端验收与 CI

- [x] 6.1 Add an offline acceptance suite that runs the environment check, starts all skeletons, validates shared contracts in Python and TypeScript, runs replay/fault fixtures, verifies readiness, and confirms no network/model/credential requirement.

  - [ ] 6.1 添加离线验收套件，运行环境检查、启动所有骨架、在 Python 与 TypeScript 中校验共享契约、运行重放/故障 fixtures、验证就绪，并确认无网络/模型/凭据要求。

- [x] 6.2 Add an opt-in service-boundary acceptance suite that starts Compose dependencies, verifies each dependency/readiness state, injects a dependency timeout, and records redacted evidence; make the suite skip with an explicit reason when Docker is unavailable.

  - [ ] 6.2 添加可选加入的服务边界验收套件，启动 Compose 依赖、验证每个依赖/就绪状态、注入依赖超时并记录脱敏证据；当 Docker 不可用时，让套件以明确原因跳过。

- [x] 6.3 Add CI workflows for formatting/linting, secret hygiene, contract compatibility, offline acceptance, console build, and machine-readable reports; ensure CI does not contain or require real credentials.

  - [ ] 6.3 为格式化/lint、秘密卫生、契约兼容性、离线验收、控制台构建与机器可读报告添加 CI 工作流；确保 CI 不包含或要求真实凭据。

- [x] 6.4 Run repeated offline baselines and compare their machine-readable outputs for deterministic fields; document any intentionally non-deterministic timestamps or process identifiers.

  - [ ] 6.4 运行重复离线基线并比较其机器可读输出的确定性字段；记录任何有意为之的非确定性时间戳或进程标识。

## 7. Documentation, validation, and archive evidence

## 7. 文档、验证与归档证据

- [x] 7.1 Update README and development guidance with supported modes, the `scripts/dev.py` command surface, setup prerequisites, safety limitations, and the explicit statement that no API-503 customer-resolution workflow exists yet.

  - [ ] 7.1 更新 README 与开发指导，包含支持的模式、`scripts/dev.py` 命令界面、设置先决条件、安全限制，以及明确声明尚不存在 API-503 客户解决工作流。

- [x] 7.2 Record fixture provenance, replay/fault usage, contract-versioning rules, provider-boundary limitations, and known local-platform limits in the repository documentation.

  - [ ] 7.2 在仓库文档中记录 fixture 来源、重放/故障使用、契约版本规则、提供方边界限制与已知本地平台限制。

- [x] 7.3 Run `openspec validate establish-weflow-foundation --strict`, resolve all validation failures, and retain the final machine-readable validation and acceptance command outputs as change evidence.

  - [ ] 7.3 运行 `openspec validate establish-weflow-foundation --strict`，解决所有验证失败，并保留最终的机器可读验证与验收命令输出作为变更证据。

- [x] 7.4 After every task and acceptance check passes, archive the change through OpenSpec and update `docs/PROJECT_MEMORY.md` with verified facts, limitations, baseline metrics, and the gate for Change 1.

  - [ ] 7.4 在每个任务与验收检查通过后，通过 OpenSpec 归档变更，并用已验证事实、限制、基线指标与变更 1 的关卡更新 `docs/PROJECT_MEMORY.md`。
