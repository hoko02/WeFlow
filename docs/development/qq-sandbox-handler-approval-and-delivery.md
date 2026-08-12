# QQ 沙箱处理人私聊审批与群交付运行手册

本手册对应 `add-qq-handler-approval-and-delivery`。它把机器人扩展为一个受限的工单流程入口：客户在唯一测试群中 `@机器人` 提问，处理人在与机器人的 QQ 私聊中拉取问题、接单、起草和改稿，再由同一处理人在原群发送不含草稿正文的审批元数据，机器人最后把已审批的原文作为该审批消息的被动群回复。

这一阶段仍然不调用模型、不调用业务系统、不使用 QQ 邮件/附件、不支持任意收件人、多处理人、多群或生产环境。QQ 接受消息也不代表客户已读、问题已解决或 Case 已完成。

## 1. 安全边界

- 只允许一个已完成 Stage1 配对的 `qqpair_...` 群选择器。
- 处理人必须分别完成群事件与 C2C 私聊事件挑战，再由本机操作者输入 `CONFIRM-DUAL-QQ-HANDLER`。
- 群 `member_openid` 与私聊 `user_openid` 不被系统假定为同一身份；没有 QQ 官方稳定跨通道 ID 时，报告只声明 `operator_confirmed_dual_challenge`，并保持 `production_ready=false`。
- 昵称、QQ 号文本、群主/管理员标记和机器人显示名都不参与授权。
- 客户问题和候选回复只存在于受限 artifact 表，最多保留 24 小时；替换、拒绝或最终 provider acceptance 会使相应内容不可达并产生无正文删除证据。
- 普通命令与 Stage1 命令不会导入 Stage2 runner，也不能读取 C2C、通知处理人、审批或交付最终回复。

## 2. 先做离线验收

这一步不需要 QQ 凭据、网络或模型：

```powershell
uv run python scripts/dev.py qq-sandbox-handler-approval `
  --offline-acceptance `
  --output reports/add-qq-handler-approval-and-delivery-offline-acceptance.json

uv run python scripts/dev.py qq-sandbox-handler-verify `
  --report reports/add-qq-handler-approval-and-delivery-offline-acceptance.json `
  --mode offline-fake
```

报告必须分别证明双通道绑定、一次通知、私聊 pull/accept/draft/edit、群元数据审批、最终 provider acceptance、重复事件抑制和 artifact 删除；同时必须保持：

```text
network_contacted=false
external_write_attempted=false
model_invocation=false
customer_receipt_verified=false
issue_resolution=false
case_completion=false
production_ready=false
```

## 3. 当前 PowerShell 进程的凭据与权限

先确认 `add-secure-qq-first-group-pairing` 的真实报告已经独立验证，准备其中的安全 `qqpair_...`，不要复制数据库里的原始 `group_openid`。AppSecret 和 identity salt 只进入当前进程，不写入 `.env`、命令参数、源码、报告或截图。

```powershell
$weflowQqSecret = Read-Host "QQ AppSecret" -AsSecureString
$weflowQqSalt = Read-Host "WeFlow QQ identity salt" -AsSecureString
$weflowQqSecretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($weflowQqSecret)
$weflowQqSaltPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($weflowQqSalt)

$env:WEFLOW_QQ_APP_ID = Read-Host "QQ AppID"
$env:WEFLOW_QQ_CLIENT_SECRET =
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($weflowQqSecretPtr)
Remove-Item Env:WEFLOW_QQ_SANDBOX_GROUP_OPENID -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_TENANT_ID -ErrorAction SilentlyContinue
$env:WEFLOW_QQ_SANDBOX_PAIRING_ID = Read-Host "Verified pairing ID (qqpair_...)"
$env:WEFLOW_QQ_IDENTITY_SALT =
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($weflowQqSaltPtr)
$env:WEFLOW_PROVIDER_MODE = 'replay'
$env:WEFLOW_QQ_CAPABILITIES = @(
    'qq.group_at.read'
    'qq.c2c.read'
    'qq.c2c.notification.execute'
    'qq.c2c.passive_reply.execute'
    'qq.handler_approval.decide'
    'qq.final_reply.execute'
) -join ','
```

下列通用或越权开关必须不存在，否则命令会在联网前拒绝：`WEFLOW_PROVIDER_API_KEY`、`WEFLOW_PROVIDER_ALLOW_LIVE`、`WEFLOW_EXTERNAL_WRITE_ENABLED`、`WEFLOW_MULTI_AGENT_ENABLED`、`WEFLOW_QQ_MAIL_ENABLED`、`WEFLOW_QQ_ATTACHMENT_ENABLED`、`WEFLOW_LIVE_MODEL_API_KEY`。

## 4. Readiness：只检查，不联网

```powershell
uv run python scripts/dev.py qq-sandbox-handler-approval `
  --confirm-live-qq `
  --readiness-only
```

必须看到 `ready=true`、`selector_resolved=true`、`network_contacted=false`、`external_write_attempted=false`、`case_mutation=false`、`model_invocation=false`。该模式只解析安全 pairing selector；不会构造 Gateway、创建 Stage2 表、创建 Case 或发送 QQ 消息。

## 5. 双通道处理人配对

```powershell
uv run python scripts/dev.py qq-sandbox-handler-approval `
  --confirm-live-qq `
  --pair-handler `
### 4.1 C2C 隐私安全探针

若群事件可观察但处理人私聊没有进入配对流程，先运行只读探针，不要继续发送群挑战：

```powershell
uv run python scripts/dev.py qq-sandbox-handler-approval `
  --confirm-live-qq `
  --probe-c2c
```

由已配置的开发体验用户在机器人单聊中发送终端显示的完整 `WFH-C2C-...`。探针最多等待五分钟，只报告是否收到 `C2C_MESSAGE_CREATE`、是否存在 `user_openid`、`msg_id`、时间戳和序列、正文是否精确匹配以及正常 pairing matcher 是否接受。它不创建 binding、Case、Stage 2 journal 或外部写，不持久化 provider event，也不输出身份或正文。

`pairing_matcher=accepted` 证明 QQ C2C 路由和 WeFlow matcher 均可用；`c2c_event_received=false` 表示在窗口内没有收到 C2C 事件；收到事件但 `has_user_openid=false`、`content_exact_probe=false` 或 matcher reason code 非 accepted 时，保留脱敏输出并停止正式配对。

  --output reports/add-qq-handler-approval-and-delivery-live-pairing.json
```

命令显示两个五分钟有效、只显示不持久化的挑战：

1. 预定处理人在已配对测试群中，从成员列表选择真实机器人 mention，发送完整 `WFH-GROUP-...`；
2. 同一预定处理人打开与机器人的 C2C 私聊，发送完整 `WFH-C2C-...`；
3. 终端分别显示两个 surface 已观察后，本机操作者核对确为同一人，再输入 `CONFIRM-DUAL-QQ-HANDLER`。

不要把两个令牌发给其他人，不要添加正文、附件或卡片，不要重用过期挑战。成功报告只包含 salted hash 和安全 `qqhbind_...`。把该安全 binding ID 留在当前进程：

```powershell
$env:WEFLOW_QQ_HANDLER_BINDING_ID = '<qqhbind_...>'
```

If both surfaces were observed and `CONFIRM-DUAL-QQ-HANDLER` was entered, but report construction or output then failed (for example, an older build returned `notification_attempt_count:maximum`), do not delete the store, revoke the binding, or resend the challenges. Keep the same App, tenant, group, Stage 1 pairing, and capability configuration, then rerun this section's `--pair-handler` command unchanged. It resolves the one matching unexpired confirmed binding before network construction and reports `recovery_state=reconciled`, `network_contacted=false`, and `notification_attempt_count=0`; a mismatched or ambiguous scope still fails closed.

## 6. 单工单真实流程

启动后再发送新的测试事件；不要重用 Stage1 的旧群消息：

```powershell
uv run python scripts/dev.py qq-sandbox-handler-approval `
  --confirm-live-qq `
  --handler-binding-id $env:WEFLOW_QQ_HANDLER_BINDING_ID `
  --output reports/add-qq-handler-approval-and-delivery-live.json
```

按下面顺序操作：

1. 客户测试账号在原群真实 `@机器人`，发送纯文本测试问题，例如 `SYNTHETIC_ISSUE_API_503`。同一事件先进入既有 Stage1 Case 账本，但本命令不启用 Stage1 `qq.passive_ack.execute`；随后只在受限 artifact 中保留规范化/脱敏的问题正文。
2. 机器人最多主动私聊处理人一次，正文只有 Case 编号与 `WF-PULL <case_id> <version>`。如果响应超时、断线或 unknown，不会重试，也不会宣称已送达；唯一 fallback 是群内不含问题/草稿的固定提醒。
3. 处理人在私聊中依次发送：

```text
WF-PULL <case_id> 1
WF-ACCEPT <case_id> 1
WF-DRAFT <case_id> 2
SYNTHETIC_RESPONSE_V1
WF-DRAFT <case_id> 3
SYNTHETIC_RESPONSE_V2
```

`WF-DRAFT` 的第一行只能包含命令、Case 和 expected version；候选正文从下一行开始，规范化后必须为 1–1200 个 Unicode scalar。第二次 draft 是本次 live acceptance 的 edit 证据；实际产品流只提交一次合法 draft 也能继续。

若要拒绝任务，使用安全 reason code，不附加自由文本：

```text
WF-REJECT <case_id> <expected_version> not_my_scope
```

4. 每次私聊命令都必须在源消息后的 60 分钟被动回复窗口内完成；群审批后的最终被动回复窗口仍为五分钟。机器人只在私聊回复客户问题、状态、候选预览与审批元数据；过窗后不会切换为主动任意消息。
5. 最终私聊预览会给出一行 `WF-APPROVE <approval_request_id> <candidate_hash_prefix> <expected_version>`。处理人回到原群，真实 `@机器人` 并原样发送这三个元数据；不得附带候选正文或请求群内预览。
6. 只有群事件的 `member_openid` 与该私聊候选的双通道绑定完全匹配时，机器人才能记录审批，并以该审批消息的 `msg_id + msg_seq=5` 被动回复精确候选正文。unknown、过窗或 stale decision 都不会改用主动群发。

独立验证真实报告：

```powershell
Remove-Item Env:WEFLOW_QQ_HANDLER_BINDING_ID -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_CAPABILITIES -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_SANDBOX_PAIRING_ID -ErrorAction SilentlyContinue

uv run python scripts/dev.py qq-sandbox-handler-verify `
  --report reports/add-qq-handler-approval-and-delivery-live.json `
  --mode qq-sandbox-live
```

即使 `final_provider_accepted=true`，验证器仍要求 customer receipt、resolution、Case completion 与 production readiness 全为 false。

## 7. 恢复、隐私和回滚

- 主动 C2C notification 对稳定 Case/binding natural key 只有一个 transport attempt。accepted、rejected、rate-limit、timeout、disconnect 和 unknown 都关闭该预算。
- 私聊和最终群回复先持久化 intent，再按 source `msg_id`、固定 `msg_seq`、Case、binding、version 和内容 hash 对账；已有 accepted/duplicate/unknown/expired 结果不会产生第二条可见消息。
- 不保存群/C2C transcript、原始 provider event、原始身份、凭据、Authorization header、客户问题或候选正文到日志、ledger、fixture 或报告。不要上传 `.weflow/qq-sandbox.sqlite3`。
- 回滚时先 `Ctrl+C` 停止专用进程，然后移除全部 `WEFLOW_QQ_*` 与上面的通用开关。停止命令即撤销运行时能力；binding 与私有 locator 最多 24 小时到期，受限 artifact 在拒绝、替换、最终 provider acceptance 或 24 小时上限时删除。
- 如果怀疑 AppSecret 泄露，在 QQ 管理端立即轮换凭据并把机器人移出测试群。不要删除本地 journal 来掩盖 unknown 写入，因为这会破坏对账证据。

### 7.1 Stage 1 locator 先于处理人 binding 到期

如果命令返回 `pairing_locator_not_current`，先停止正在运行的专用 Stage 2 进程。不要修改或删除 SQLite。按 Stage 1 手册重新完成同一个 App、tenant 和测试群的 `WFPAIR-...`，然后在当前 PowerShell 恢复 Stage 2 配置：

```powershell
$env:WEFLOW_QQ_SANDBOX_PAIRING_ID = '<new qqpair_...>'
Remove-Item Env:WEFLOW_QQ_TENANT_ID -ErrorAction SilentlyContinue
$env:WEFLOW_QQ_IDENTITY_SALT = $handlerIdentitySalt
$env:WEFLOW_QQ_CAPABILITIES = @(
    'qq.group_at.read'
    'qq.c2c.read'
    'qq.c2c.notification.execute'
    'qq.c2c.passive_reply.execute'
    'qq.handler_approval.decide'
    'qq.final_reply.execute'
) -join ','
```

仅在新 Stage 1 pairing 与旧 binding 的 App、tenant、群哈希完全匹配时，执行本地撤销：

```powershell
uv run python scripts/dev.py qq-sandbox-handler-approval `
  --confirm-live-qq `
  --revoke-handler-binding `
  --handler-binding-id '<old qqhbind_...>' `
  --output reports/add-qq-handler-approval-and-delivery-binding-revocation.json
```

终端要求确认时输入：

```text
CONFIRM-LOCAL-QQ-HANDLER-REVOCATION
```

成功报告必须同时满足 `revoked=true`、`network_contacted=false`、`qq_write_attempted=false`、`external_write_attempted=false`、`case_mutation=false`、`model_invocation=false` 和 `production_ready=false`。撤销不会改写不可变 binding；它只追加一个脱敏终止事件，并立即清空、停用旧 binding 的两条私有 locator。重复执行返回 `already_revoked=true`，不追加第二个事件。

随后移除旧的 `$env:WEFLOW_QQ_HANDLER_BINDING_ID`，重新运行 `--pair-handler`，完成新的群/C2C 双挑战和本机确认。直接更新 `qq_handler_bindings`、`qq_handler_private_locators` 或删除 `.weflow/qq-sandbox.sqlite3` 都不属于允许的恢复路径。

最后清理 SecureString 指针：

```powershell
Remove-Item Env:WEFLOW_QQ_APP_ID -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_CLIENT_SECRET -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_QQ_IDENTITY_SALT -ErrorAction SilentlyContinue
Remove-Item Env:WEFLOW_PROVIDER_MODE -ErrorAction SilentlyContinue
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($weflowQqSecretPtr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($weflowQqSaltPtr)

uv run python scripts/scan_secrets.py
uv run python scripts/dev.py contracts
```

面试展示只使用已通过独立 verifier 的脱敏 JSON 报告和上述状态机说明，不展示真实 QQ 身份、群 locator、聊天截图中的私密正文、终端环境或 SQLite 文件。
