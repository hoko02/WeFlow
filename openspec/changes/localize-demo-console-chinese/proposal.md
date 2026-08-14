## Why

面试演示面向中文受众，但现有离线 Operator Case 与评测控制台的大部分可见文案为英文，增加了理解成本。将展示层统一为简体中文，同时保留稳定的证据标识和协议字段，可让演示聚焦于可靠性边界而非即时翻译。

## What Changes

- 将 Vue 演示控制台中面向操作者的静态文案、状态标题、能力标签、指标标签和安全提示翻译为简体中文。
- 保留 API 路径、JSON 契约、证据 ID、哈希、状态枚举、原因码和机器可读报告不变；它们仍以原有稳定标识展示或传输。
- 为中文渲染模型补充覆盖，确保就绪和不可用安全状态继续如实表达离线、Replay-only 和 fixture-local 边界。

## Capabilities

### New Capabilities

- `demo-console-chinese-localization`: 为离线演示控制台提供完整且边界如实的简体中文展示层。

### Modified Capabilities

- 无。

## Impact

- 受影响代码：`apps/web-console/src/` 中的 Vue 组件、基础状态、评测报告和 Operator Case 渲染模型，以及对应前端测试。
- API、JSON Schema、SQLite 证据、报告、后端服务和外部写入能力均不变。
- 验证仍完全离线，不要求网络、模型或企业凭据，也不启用任何外部写入。
