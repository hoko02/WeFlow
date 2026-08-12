# QQ 沙箱受控模型辅助工作流（Stage 3）

本手册对应 `enable-bounded-live-model-in-qq-workflow`。Stage 3 只增加一条受限能力：已完成私聊拉取和接单的绑定处理人，可以发送精确的 `WF-ASSIST <case_id> <expected_version>`，让一个真实公共模型基于当前 Case 的脱敏问题视图和三个仓库内合成只读来源生成候选回复。模型不能接单、审批、选择 QQ 目标、发送消息、宣称问题解决或完成 Case；候选仍须由同一绑定处理人在原群用元数据审批。

截至 2026-08-12，凭据无关的完整离线闭环和当前真实 pairing/binding readiness 已验证；真实 QQ 加真实模型的最终验收仍必须由操作者在本地进程中提供两类凭据并亲自执行，不能用 fake 报告代替。

## 1. 固定安全边界

- 只使用一个当前 `qqpair_...` 和一个匹配的活跃 `qqhbind_...`；禁止直接提供 `group_openid` 或 tenant 覆盖。
- QQ 和模型必须分别显式确认；能力列表必须逐项、逐序完全匹配，额外能力也会拒绝。
- QQ 侧只组合已有的群 mention 读取、固定 ACK、处理人通知、C2C 被动回复、人工审批和最终群被动回复；不存在通用发送器、邮件、附件或 active-send fallback。
- 模型只可提交闭合的 `ModelActionProposal`，工具严格按 CRM → monitoring → knowledge 读取仓库内合成 fixture；不存在业务系统网络客户端或写客户端。
- 每个 Stage 3 Case 最多 6 次 Provider 调用、3 次工具读取、14,000 token、60 秒，累计估算费用硬上限为 USD 0.50；unknown 结果按悲观预算记账且不自动重试。既有六任务 live-evaluation 继续使用独立的 USD 0.02 单次评测预算，不受此调整影响。
- 客户问题、人工/模型草稿和 prompt 不进入报告。受限问题与候选最多保留 24 小时，并在替换、拒绝或最终 Provider acceptance 后不可达并删除。
- `final_provider_accepted=true` 仅表示 QQ 接受了被动回复请求；客户已读、问题解决、Case 完成和生产就绪始终分别为 `false`。

## 2. 先跑无凭据离线验收

```powershell
uv run python scripts/dev.py qq-sandbox-live-model-workflow `
  --offline-fake `
  --output reports/enable-bounded-live-model-in-qq-workflow-offline-acceptance.json `
  --verification-output reports/enable-bounded-live-model-in-qq-workflow-offline-verification.json

uv run python scripts/dev.py qq-sandbox-live-model-workflow-verify `
  --report reports/enable-bounded-live-model-in-qq-workflow-offline-acceptance.json `
  --verification reports/enable-bounded-live-model-in-qq-workflow-offline-verification.json `
  --mode offline-fake
```

离线报告应显示一次 Case、一次 ACK、一次处理人通知、一次 assist、4 次 fake 模型回合、3 个工具结果、一次私聊预览、一次群审批、一次最终回复和至少两项制品删除，同时保持：

```text
mode=offline-fake
network_contacted=false
external_write_attempted=false
live_model_contact_verified=false
customer_receipt_verified=false
issue_resolution=false
case_completion=false
production_ready=false
```

## 3. 只在当前 PowerShell 进程配置凭据

不要把 AppSecret、identity salt 或模型 API key 写入 `.env`、命令参数、源码、报告、聊天截图或 shell history。下面示例用 SecureString 暂存输入；三个明文只进入当前子进程环境：

```powershell
$qqSecretSecure = Read-Host "QQ AppSecret" -AsSecureString
$qqSaltSecure = Read-Host "WeFlow QQ identity salt (at least 32 bytes)" -AsSecureString
$modelKeySecure = Read-Host "DeepSeek API key" -AsSecureString
$qqSecretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($qqSecretSecure)
$qqSaltPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($qqSaltSecure)
$modelKeyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($modelKeySecure)

$env:WEFLOW_QQ_APP_ID = Read-Host "QQ AppID"
$env:WEFLOW_QQ_CLIENT_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($qqSecretPtr)
$env:WEFLOW_QQ_IDENTITY_SALT = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($qqSaltPtr)
$env:WEFLOW_LIVE_MODEL_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($modelKeyPtr)
$env:WEFLOW_QQ_SANDBOX_PAIRING_ID = Read-Host "Current verified qqpair_..."
$env:WEFLOW_QQ_HANDLER_BINDING_ID = Read-Host "Current active qqhbind_..."

Remove-Item Env:WEFLOW_QQ_SANDBOX_GROUP_OPENID -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_TENANT_ID -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_PROVIDER_ALLOW_LIVE -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_PROVIDER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_EXTERNAL_WRITE_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_MULTI_AGENT_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_MAIL_ENABLED -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_ATTACHMENT_ENABLED -ErrorAction SilentlyContinue

$env:WEFLOW_PROVIDER_MODE = 'openai-compatible'
$env:WEFLOW_QQ_CAPABILITIES = @(
  'qq.group_at.read'
  'qq.passive_ack.execute'
  'qq.c2c.read'
  'qq.c2c.notification.execute'
  'qq.c2c.passive_reply.execute'
  'qq.handler_approval.decide'
  'qq.final_reply.execute'
) -join ','
$env:WEFLOW_QQ_MODEL_CAPABILITIES = @(
  'model.proposal.invoke'
  'fixture.crm.read'
  'fixture.monitoring.read'
  'fixture.knowledge.read'
) -join ','
```

默认且唯一受审 Provider 设置是 `https://api.deepseek.com` 与 `deepseek-v4-flash`，通常不要在命令行覆盖。配置加载顺序是：资料与 hash → pairing/binding → 能力与预算 → 公共 HTTPS/DNS → 两类密钥 → 客户端构造。

## 4. Readiness 不读取密钥、不联网

你可以暂时移除三个密钥后执行 readiness；它只需要 AppID、安全选择器和精确能力列表：

```powershell
uv run python scripts/dev.py qq-sandbox-live-model-workflow `
  --confirm-live-qq `
  --confirm-live-model `
  --readiness-only
```

必须看到 `ready=true`、`selector_resolved=true`、`profile_current=true`，并同时看到：

```text
network_contacted=false
model_invocation=false
case_mutation=false
external_write_attempted=false
production_ready=false
```

`pairing_locator_not_current`、`handler_binding_inactive`、scope mismatch、价格 Profile 过期或能力不完全匹配都必须先修复；不要修改 SQLite、伪造 ID 或绕过 readiness。

## 5. 运行一次真实 QQ 加真实模型验收

恢复三个进程内密钥后启动：

```powershell
uv run python scripts/dev.py qq-sandbox-live-model-workflow `
  --confirm-live-qq `
  --confirm-live-model `
  --output reports/enable-bounded-live-model-in-qq-workflow-live-acceptance.json `
  --verification-output reports/enable-bounded-live-model-in-qq-workflow-live-verification.json
```

按顺序操作：

1. 客户测试账号在已配对群中真实选择机器人 mention，发送新的纯文本 `SYNTHETIC_ISSUE_API_503_STAGE3_<唯一后缀>`。机器人先发送固定受理 ACK，再仅向绑定处理人发一次工单通知。
2. 处理人在机器人私聊中依次发送通知给出的命令：

```text
WF-PULL <case_id> 1
WF-ACCEPT <case_id> 1
WF-ASSIST <case_id> 2
```

3. 模型候选成功时，机器人只在私聊返回候选、合成证据数量、调用/token/估算成本摘要，以及 `WF-APPROVE <approval_request_id> <candidate_hash_prefix> <expected_version>`。不要复制候选正文到群。
4. 如果模型安全停止，处理人仍可按机器人返回的新版本私聊发送以下人工替代命令；安全停止会推进版本，旧版本 assist 会被拒绝：

   `WF-DRAFT <case_id> <current_version>` 换行后填写人工草稿。

   这只能继续人工 Stage 2 流程，不能形成“真实模型候选已验证”的 Stage 3 accepted report。
5. 处理人回到原群，真实选择机器人 mention，仅发送私聊给出的 `WF-APPROVE` 三段元数据。机器人只会把已绑定的当前候选作为该审批消息的被动回复。

Provider rate-limit 或明确 unavailable 只允许受审预算内的一次显式重试；timeout、disconnect 或任何 outcome unknown 都会以 `provider_outcome_unknown` 等闭合 reason code 安全停止，不会自动再次调用模型。QQ unknown 同样不会切换为主动发送。

如果最终 QQ 回复已显示且终端随后仅以报告/验证错误退出，不要重发客户消息、不要再次调用模型。保留当前 selector/capability 环境变量，使用内容无关的持久化证据恢复两个报告；该命令不读取 QQ/模型密钥、不接触网络、不变更 Case，也不产生外部写入：

```powershell
uv run python scripts/dev.py qq-sandbox-live-model-workflow `
  --confirm-live-qq `
  --confirm-live-model `
  --recover-completed-case <case_id> `
  --output reports/enable-bounded-live-model-in-qq-workflow-live-acceptance.json `
  --verification-output reports/enable-bounded-live-model-in-qq-workflow-live-verification.json
```

恢复只接受当前 pairing/binding/profile 下已经 `FINAL_ACCEPTED` 且 ACK、通知、模型调用、工具、候选、审批、最终 Provider acceptance 和删除证据完整的 Case；不完整或外域 Case 会失败关闭。

## 6. 清除运行权限后独立复核

先停止 live 进程并清除所有 Stage 3 权限；独立 verifier 本身不允许继承密钥或组合能力：

```powershell
Remove-Item Env:WEFLOW_QQ_CLIENT_SECRET -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_IDENTITY_SALT -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_LIVE_MODEL_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_CAPABILITIES -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_MODEL_CAPABILITIES -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_SANDBOX_PAIRING_ID -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_HANDLER_BINDING_ID -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_PROVIDER_MODE -ErrorAction SilentlyContinue

uv run python scripts/dev.py qq-sandbox-live-model-workflow-verify `
  --report reports/enable-bounded-live-model-in-qq-workflow-live-acceptance.json `
  --verification reports/enable-bounded-live-model-in-qq-workflow-live-verification.json `
  --mode qq-model-integrated-live
```

accepted live 报告必须同时证明真实模型 contact/usage、三个合成工具证据、候选 verifier、同一处理人的私聊发起与群审批、唯一最终 QQ Provider acceptance、删除证据及所有业务成功字段为 false。fake、partial 或缺失 lineage 的报告不能通过。

## 7. 当前 Provider 复核与成本

2026-08-12 已按官方文档复核：模型 ID 为 `deepseek-v4-flash`，OpenAI ChatCompletions 基址为 `https://api.deepseek.com`，JSON Output 使用 `response_format={"type":"json_object"}`，响应 usage 包含输入/输出/总 token；当前每百万 token 的 cache-miss input/output 价格为 USD 0.14/0.28。项目内 `deepseek-v4-flash-2026-08-06` Profile 与这些值一致，有效至 2026-09-06。

- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode)
- [DeepSeek Chat Completion API](https://api-docs.deepseek.com/api/create-chat-completion)
- [DeepSeek Model List API](https://api-docs.deepseek.com/api/list-models)

价格可能变化。Profile 过期或官方值变化时，保持 live 任务未完成，重新评审并更新所有内容 hash；不得只放宽日期检查。

## 8. 隐私、回滚与面试展示

- 终止：按 `Ctrl+C`，清除本节全部环境变量，并用 `ZeroFreeBSTR` 释放三个 SecureString 指针。不要删除 `.weflow/qq-sandbox.sqlite3`，否则会破坏 unknown 结果的对账证据。
- 泄露：若 AppSecret 或模型 key 可能泄露，立即在对应管理端轮换；不要把密钥或 Provider body 发给 Codex。
- 禁止留存：真实身份、group/user openid、原始 QQ event、聊天 transcript、客户问题/草稿正文、prompt、Provider body、Authorization header、SQLite 文件和含私密正文的截图。
- 面试展示：只展示脱敏 readiness、offline/live acceptance 与 independent verification JSON，并明确区分“已实现”“离线验证”“真实 Provider accepted”“客户已读/解决/完成/生产就绪”。
