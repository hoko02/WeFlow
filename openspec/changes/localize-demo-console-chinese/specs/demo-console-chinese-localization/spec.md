## ADDED Requirements

### Requirement: Demo console presents operator-facing content in Simplified Chinese
离线演示控制台 SHALL 以简体中文显示面向操作者的标题、说明、能力与指标标签、
就绪/不可用状态、时间线与评测详情提示。Case ID、任务 ID、哈希、API 路径、
协议字段、状态枚举与 reason code SHALL 保持机器可读的原始值。

#### Scenario: Valid offline evidence is rendered
- **WHEN** 浏览器收到有效的基础状态、Operator Case 快照和评测快照
- **THEN** 控制台 SHALL 以简体中文展示操作状态、API-503 时间线、12 项离线评测及其详情，同时原样展示证据标识和哈希

#### Scenario: Safe evidence state is unavailable
- **WHEN** 基础状态、Operator Case 或评测证据处于加载、缺失、身份拒绝或完整性未就绪状态
- **THEN** 控制台 SHALL 显示对应的简体中文安全状态，且不得显示原始响应、未校验的内容或成功声明

### Requirement: Chinese presentation preserves reliability boundaries
中文展示 SHALL 明确标明离线、仅 Replay、无网络、无模型、无外部写入及
fixture-local 投递的限制。它 SHALL NOT 把本地记录表述为真实提供方发送、客户
签收、事件解决、Case 完成或新的授权。

#### Scenario: Fixture-local delivery is displayed
- **WHEN** 已验证的 Operator Case 时间线包含 fixture-local delivery 记录
- **THEN** 控制台 SHALL 明确标注其仅为 fixture-local 本地记录，且不得宣称客户签收、问题解决或 Case 完成

#### Scenario: Unsupported live metrics are displayed
- **WHEN** 离线评测快照不包含模型、成本、时延、方差、客户签收或解决证据
- **THEN** 控制台 SHALL 以简体中文将这些指标标为不可用或不在范围内，而不得以零值或成功状态替代

### Requirement: Chinese presentation is verified without side effects
离线控制台的自动化测试、生产构建和验收 SHALL 验证中文渲染，同时保持网络、
模型、提供方初始化、外部写入和留存状态变更为零。

#### Scenario: Localization regression checks run offline
- **WHEN** 开发者执行 Web Console 测试、生产构建和离线控制台验收
- **THEN** 检查 SHALL 在无需网络、模型或企业凭据的情况下通过，并确认中文展示未改变既有的只读和无副作用保证
