# QQ Sandbox Intake And Fixed Acknowledgement Guide / QQ 沙箱接收与固定确认指南

## 1. What this increment proves / 1. 此增量变更证明的内容

`add-qq-sandbox-intake-and-ack` is WeFlow's first real QQ vertical slice. One explicitly
started control-worker command may connect one QQ robot application to one operator-owned
sandbox group, consume `GROUP_AT_MESSAGE_CREATE` text events, create the existing
tenant-scoped Case ledger state, and send one fixed passive acknowledgement:

> `add-qq-sandbox-intake-and-ack` 是 WeFlow 首个真实的 QQ 垂直切片。一个显式启动的 control-worker 命令可以将一个 QQ 机器人应用连接到一个由运维人员拥有的沙箱群组，消费 `GROUP_AT_MESSAGE_CREATE` 文本事件，创建现有租户范围内的 Case 账本状态，并发送一条固定的被动确认回复：

```text
已受理，工单编号：{case_id}。当前仅确认已进入处理流程，不代表问题已解决。
```

The Case stores a content hash, not readable customer text. This stage does not invoke a
model, investigate the incident, notify a handler, retain a transcript, request approval,
send a final answer, verify that the customer read anything, or resolve/complete the Case.
QQ is an input/output surface; deterministic WeFlow code still owns identity, authority,
deduplication, state, retries, evidence, and completion classification.

> Case 存储的是内容哈希值，而非可读的客户文本。此阶段不会调用模型、调查事件、通知处理人、保留对话记录、请求审批、发送最终答复、验证客户是否已读任何内容，也不会解决/完成 Case。QQ 仅作为输入/输出界面；确定性的 WeFlow 代码仍然拥有身份、权限、去重、状态、重试、证据和完成分类的控制权。

Normal startup, Replay, the Agent Runtime, Business Simulator, benchmarks,
investigations, and live-model evaluation do not import or register the real QQ adapter.
If QQ configuration is visible to an ordinary `scripts/dev.py` command, that command
fails before its handler runs.

> 正常启动、回放（Replay）、Agent 运行时、业务模拟器、基准测试、调查以及线上模型评估均不会导入或注册真实的 QQ 适配器。如果 QQ 配置对普通的 `scripts/dev.py` 命令可见，该命令将在其处理器运行之前失败。

## 2. Current official QQ protocol assumptions / 2. 当前官方 QQ 协议假设

These bindings were checked against the QQ robot documentation on 2026-08-10:

> 以下绑定已在 2026-08-10 对照 QQ 机器人文档验证：

- server API origin: `https://api.bot.qq.com`;
- token request: `POST /app/getAppAccessToken` with portal-issued AppID/AppSecret;
- OpenAPI authorization: `Authorization: QQBot {access_token}`;
- gateway discovery: `GET /gateway`;
- WebSocket event intent: `GROUP_AND_C2C_EVENT (1 << 25)`;
- accepted event: `GROUP_AT_MESSAGE_CREATE`; its `content` field already excludes the
  robot mention prefix in current QQ payloads;
- passive group reply: `POST /v2/groups/{group_openid}/messages`, plain text
  `msg_type=0`, original event `d.id` as `msg_id`, and deterministic `msg_seq=1`;
- a group passive reply is valid for five minutes and QQ permits at most five replies to
  one source message; this increment intentionally uses only one;
- QQ can redeliver a source `msg_id`; `msg_id + msg_seq` is the provider deduplication
  tuple, and provider code `40054005` means the message was deduplicated;
- the access-token lifetime is at most 7200 seconds and must remain server-side.

> - 服务器 API 源地址：`https://api.bot.qq.com`；
> - Token 请求：`POST /app/getAppAccessToken`，使用平台颁发的 AppID/AppSecret；
> - OpenAPI 鉴权：`Authorization: QQBot {access_token}`；
> - 网关发现：`GET /gateway`；
> - WebSocket 事件意图：`GROUP_AND_C2C_EVENT (1 << 25)`；
> - 接受的事件：`GROUP_AT_MESSAGE_CREATE`；其 `content` 字段在当前 QQ 负载中已排除机器人提及前缀；
> - 群被动回复：`POST /v2/groups/{group_openid}/messages`，纯文本 `msg_type=0`，原始事件 `d.id` 作为 `msg_id`，确定性 `msg_seq=1`；
> - 群被动回复有效期为五分钟，QQ 允许对一条源消息最多回复五次；本次增量变更有意仅使用一次；
> - QQ 可能重传相同的源 `msg_id`；`msg_id + msg_seq` 构成提供方去重元组，提供方错误码 `40054005` 表示消息已被去重；
> - Access Token 有效期最长为 7200 秒，且必须保留在服务端。

Primary references / 主要参考资料：

> - [QQ 机器人启动与 AppID/AppSecret](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/getting-started.html)
> - [Access Token 与 OpenAPI 鉴权](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/api-use.html)
> - [WebSocket 负载、心跳、恢复与意图](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html)
> - [群 @机器人 事件](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_at_message_create.html)
> - [被动群消息请求与错误码](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_messages.post.html)

If these provider semantics change, update and revalidate the OpenSpec artifacts and
adapter before another live run. Do not silently reinterpret old evidence.

> 如果这些提供方语义发生变化，请在进行下一次线上运行之前更新并重新验证 OpenSpec 产物和适配器。不要静默地重新解读旧的证据。

## 3. QQ portal and group prerequisites / 3. QQ 平台与群组前置条件

The operator must control all of the following before live verification:

> 运营人员在线上验证之前必须掌控以下所有事项：

1. a QQ Open Platform account and one robot application created for development;
2. its current AppID and AppSecret, with Access Token authentication enabled;
3. permission for the application to receive the group/C2C intent and send group
   messages;
4. one non-production test group whose owner or administrator can add/configure the
   robot and control the test participants;
5. the exact `group_openid` for that group and one preselected WeFlow `tenant_id`;
6. a fresh high-entropy identity salt used only for server-side member hashing.

> 1. 一个 QQ 开放平台账号以及一个用于开发创建的机器人应用；
> 2. 该应用当前的 AppID 和 AppSecret，并已启用 Access Token 鉴权；
> 3. 应用具有接收群/C2C 意图以及发送群消息的权限；
> 4. 一个非生产环境测试群，其群主或管理员可以添加/配置机器人并控制测试参与人员；
> 5. 该群的确切 `group_openid` 以及一个预先选定的 WeFlow `tenant_id`；
> 6. 一个新高熵身份盐值，仅用于服务端成员哈希计算。

Do not test in a customer or production group. Do not infer authority from QQ nickname,
member display name, or QQ-reported member role. This change maps exactly one configured
application/group to exactly one server-owned tenant.

> 不要在客户群或生产群中测试。不要根据 QQ 昵称、成员显示名称或 QQ 报告的成员角色来推断权限。本次变更将一个已配置的应用/群组精确映射到一个服务端拥有的租户。

## 4. Offline acceptance first / 4. 首先进行离线验收

No QQ credential or network access is needed:

> 无需 QQ 凭据或网络访问：

```powershell
uv run python scripts/dev.py qq-sandbox-offline-acceptance
uv run python scripts/dev.py qq-sandbox-acceptance-verify `
  --report reports/add-qq-sandbox-intake-and-ack-offline-acceptance.json `
  --mode offline
```

The accepted report must say:

> 验收报告必须包含以下内容：

> - `fake_transport_verified=true`；
> - `qq_sandbox_live_verified=false`；
> - `customer_receipt_verified=false`；
> - `case_completion=false`；
> - `model_invocation=false`；
> - `production_ready=false`。

It covers duplicate/gapped/out-of-order events, concurrent intake, reconnect/replay,
restart after receipt or intent, lost provider response, timeout/disconnect, provider
deduplication, conflicting/unreadable results, expiry, and revoked capability.

> 它涵盖了重复/丢失/乱序事件、并发接收、重连/回放、接收或意图之后的重启、提供方响应丢失、超时/断连、提供方去重、冲突/不可读结果、过期以及权限撤销等场景。

## 5. Pre-contact denial and credential setup / 5. 连接前拒绝机制与凭据设置

Without the exact live confirmation flag, the command exits before constructing an HTTP
or WebSocket client:

> 在没有确切的线上确认标志的情况下，命令会在构造 HTTP 或 WebSocket 客户端之前退出：

```powershell
uv run python scripts/dev.py qq-sandbox-intake-ack
```

Supply values only in the current operator process. If the group has already completed
`add-secure-qq-first-group-pairing`, use the safe `qqpair_...` selector shown below;
do not copy the private `group_openid` out of the local pairing journal. Never add real
credentials, identity salt, or private group locators to `.env`, shell history, source
control, fixtures, prompts, screenshots, or reports:

> 仅在当前运维进程环境中提供这些值。以下名称即为完整支持的配置界面；切勿将真实值添加到 `.env`、Shell 历史记录、源码控制、fixtures、prompts、截图或报告中：

```powershell
$weflowQqSecret = Read-Host "QQ AppSecret" -AsSecureString
$weflowQqSalt = Read-Host "WeFlow QQ identity salt" -AsSecureString
$weflowQqSecretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($weflowQqSecret)
$weflowQqSaltPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($weflowQqSalt)

try {
    $env:WEFLOW_QQ_APP_ID = Read-Host "QQ AppID"
    $env:WEFLOW_QQ_CLIENT_SECRET =
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($weflowQqSecretPtr)
    Remove-Item Env:WEFLOW_QQ_SANDBOX_GROUP_OPENID -ErrorAction SilentlyContinue
    Remove-Item Env:WEFLOW_QQ_TENANT_ID -ErrorAction SilentlyContinue
    $env:WEFLOW_QQ_SANDBOX_PAIRING_ID = Read-Host "Verified safe pairing ID (qqpair_...)"
    $env:WEFLOW_QQ_IDENTITY_SALT =
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($weflowQqSaltPtr)
    $env:WEFLOW_QQ_CAPABILITIES = "qq.group_at.read,qq.passive_ack.execute"

    uv run python scripts/dev.py qq-sandbox-intake-ack `
      --confirm-live-qq `
      --output reports/add-qq-sandbox-intake-and-ack-live-acceptance.json
}
finally {
    Remove-Item Env:WEFLOW_QQ_APP_ID -ErrorAction SilentlyContinue
    Remove-Item Env:WEFLOW_QQ_CLIENT_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:WEFLOW_QQ_SANDBOX_PAIRING_ID -ErrorAction SilentlyContinue
    Remove-Item Env:WEFLOW_QQ_IDENTITY_SALT -ErrorAction SilentlyContinue
    Remove-Item Env:WEFLOW_QQ_CAPABILITIES -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($weflowQqSecretPtr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($weflowQqSaltPtr)
}
```

The command resolves the safe pairing ID to the private group locator and server-owned
tenant inside `.weflow/qq-sandbox.sqlite3`. It also rejects a simultaneous direct-group
selector or tenant override, live-model configuration, general external-write
enablement, multi-agent enablement, extra QQ capabilities, CLI-supplied
destinations/bodies, and a store path outside the repository before network contact.
Redacted readiness prints only application/group/tenant/capability hashes.

> 该命令会在 `.weflow/qq-sandbox.sqlite3` 内把安全配对 ID 解析为私有群定位符和服务端租户。它还会在发起网络连接之前拒绝同时存在的原始群选择器或租户覆盖、线上模型配置、通用外部写入启用、多智能体启用、额外的 QQ 能力、CLI 提供的目的地/消息体以及仓库外部的存储路径。脱敏的就绪打印仅包含应用/群组/租户/能力的哈希值。

## 6. One-message live acceptance / 6. 单消息线上验收

After the readiness report appears, use a test QQ account in the allowlisted group to
send exactly one message equivalent to:

> 在就绪报告出现后，使用许可名单内群组中的测试 QQ 账号发送恰好一条消息，内容类似：

```text
@机器人 广告系统出现了API 503错误
```

The command handles one accepted event and exits. It should create one Case, one immutable
revision, three initial business events, one acknowledgement intent, and one validated
accepted/present completion. Re-running the same provider event or a resumed replay must
return the original Case and logical acknowledgement. If QQ cannot prove acceptance or
deduplication, the intent stays `NEEDS_RECONCILIATION`; do not edit the report to success.

> 该命令处理一条已接受的事件后即退出。它应当创建一个 Case、一个不可变修订版、三个初始业务事件、一个确认意图以及一个已验证的已接受/已呈现完成记录。重新运行相同的提供方事件或恢复回放必须返回原始 Case 和逻辑确认。如果 QQ 无法证明接受或去重，意图将保持 `NEEDS_RECONCILIATION` 状态；不要将报告编辑为成功。

Verify a successful live report separately:

> 单独验证成功的线上报告：

```powershell
uv run python scripts/dev.py qq-sandbox-acceptance-verify `
  --report reports/add-qq-sandbox-intake-and-ack-live-acceptance.json `
  --mode live
```

The live verifier requires real-adapter evidence and still requires
`customer_receipt_verified=false`, `case_completion=false`, `issue_resolution=false`,
`final_delivery=false`, and `production_ready=false`.

> 线上验证器要求真实适配器证据，并且仍然要求 `customer_receipt_verified=false`、`case_completion=false`、`issue_resolution=false`、`final_delivery=false` 和 `production_ready=false`。

### 6.1 Bounded live same-event deduplication / 6.1 有界真实同事件去重

A completed command cannot reconstruct its discarded raw QQ event. Keep the same
process-only credentials and safe pairing selector, start one explicit deduplication
run, and send exactly one new test mention after readiness:

> 已结束的命令不能重建已经丢弃的 QQ 原始事件。请保留当前 PowerShell 中的凭据、身份盐和安全配对 ID，启动显式去重验收，并在 readiness 后只发送一条新的测试 mention：

```powershell
uv run python scripts/dev.py qq-sandbox-intake-ack `
  --confirm-live-qq `
  --verify-live-event-dedup `
  --output reports/add-qq-sandbox-intake-and-ack-live-dedup.json
```

The command accepts and acknowledges the event once, then replays that identical frame
only inside deterministic memory. The second pass must reuse the same Case and intent
and stop at the existing completion without another QQ transport call. Do not send the
chat message twice.

> 命令只接收和回复一次真实事件，然后仅在确定性内存路径中重放同一个事件帧。第二次处理必须复用同一 Case 和意图，并在已有完成记录处停止。不要在群里把消息发送两遍。

```powershell
uv run python scripts/dev.py qq-sandbox-acceptance-verify `
  --report reports/add-qq-sandbox-intake-and-ack-live-dedup.json `
  --mode live-dedup
```

The verifier requires `same_event_deduplication_verified=true`,
`duplicate_event_count=1`, all four per-run Case/acknowledgement deltas equal to one,
`second_qq_write_attempted=false`, and `second_logical_acknowledgement=false`.
## 7. Stop, disable, privacy, and retention / 7. 停止、禁用、隐私与保留

Before a message is accepted, stop the listener with `Ctrl+C`. It has at most three
automatic reconnect attempts per disconnect and uses QQ heartbeat/resume frames with the
last safe sequence. To disable QQ completely, stop the process and remove every
`WEFLOW_QQ_*` variable as shown above; no normal service starts the adapter.

> 在消息被接受之前，使用 `Ctrl+C` 停止监听器。它每次断连最多进行三次自动重连尝试，并使用 QQ 心跳/恢复帧以及上一个安全的序列号。要完全禁用 QQ，请停止进程并移除所有 `WEFLOW_QQ_*` 变量（如上所示）；没有任何常规服务会启动该适配器。

The durable business ledger contains hashes and safe IDs only. Raw customer text,
display names, member OpenIDs, session IDs, credentials, authorization headers, and raw
provider bodies are not written to the ledger, logs, fixtures, or reports. The bounded
local adapter journal `.weflow/qq-sandbox.sqlite3` retains only the configured group and
source-message locators needed for passive-reply recovery, and deletes expired locators
after 24 hours on the next dedicated start. The immutable intent/observation/completion
hash evidence remains for audit.

> 持久化业务账本仅包含哈希值和安全 ID。原始客户文本、显示名称、成员 OpenID、会话 ID、凭据、鉴权头以及原始提供方消息体不会被写入账本、日志、fixtures 或报告。有界本地适配器日志 `.weflow/qq-sandbox.sqlite3` 仅保留被动回复恢复所需的已配置群组和源消息定位符，并在下一次专用启动后 24 小时删除过期定位符。不可变的意图/观察/完成哈希证据保留用于审计。

After a run / 运行后：

```powershell
uv run python scripts/scan_secrets.py
uv run python scripts/dev.py contracts
```

Do not attach the SQLite journal, terminal environment dump, raw QQ event, or provider
response to an issue or interview portfolio. Use only the verified safe report.

> 不要将 SQLite 日志、终端环境转储、原始 QQ 事件或提供方响应附加到 issue 或面试作品集中。仅使用已验证的安全报告。

## 8. Failure meanings and troubleshooting / 8. 故障含义与排查

> - `explicit_confirmation_required`：检查真实的读写范围，然后添加确切的确认标志。
> - `qq_configuration_missing`：缺少一个必需的进程环境变量。
> - `qq_capability_scope_denied`：请求了模型、其他写入、多智能体或额外的 QQ 权限。
> - `qq_group_not_allowlisted`：事件并非来自唯一已配置的测试群组。
> - `qq_gateway_sequence_gap` / `qq_gateway_reconciliation_required`：未记录的序列号之后不会创建任何 Case 或确认；需要恢复/重连。
> - `qq_provider_outcome_unknown`：超时、断连、过大/不可读的响应或服务器故障不等于成功，且保持未完成状态。
> - `qq_provider_message_deduplicated`：QQ 针对原始 `msg_id + msg_seq` 返回了其文档记录的去重错误码；这可以完成一次逻辑确认。
> - `qq_passive_reply_deadline_expired`：五分钟回复窗口已关闭；不会进行提供方调用或 Case 完成。
> - `qq_gateway_reconnect_exhausted`：停止，仅检查安全的原因/计数证据，然后启动一个新的显式确认会话。

- `explicit_confirmation_required`: review the real read/write scope, then add the exact
  confirmation flag.
- `qq_configuration_missing`: one required process environment value is absent.
- `qq_capability_scope_denied`: model, other write, multi-agent, or extra QQ authority was
  requested.
- `qq_group_not_allowlisted`: the event is not from the single configured test group.
- `qq_gateway_sequence_gap` / `qq_gateway_reconciliation_required`: no Case or
  acknowledgement is created past an unaccounted sequence; resume/reconnect is required.
- `qq_provider_outcome_unknown`: timeout, disconnect, oversized/unreadable response, or
  server failure is not success and stays incomplete.
- `pairing_token_transport_unreachable`: first-group pairing could not obtain a token;
  Gateway is not connected and no challenge is displayed.
- `pairing_gateway_transport_unreachable`: the token stage passed but the Gateway endpoint
  request was unreachable; no challenge is displayed.
- `pairing_challenge_expired`: the five-minute listening deadline elapsed and the command
  stopped safely; rerun for a new challenge and never resend the old one.
- `qq_provider_message_deduplicated`: QQ returned its documented deduplication code for
  the original `msg_id + msg_seq`; this can complete the one logical acknowledgement.
- `qq_passive_reply_deadline_expired`: the five-minute reply window closed; no provider
  call or Case completion follows.
- `qq_gateway_reconnect_exhausted`: stop, inspect only safe reason/count evidence, then
  start a new explicitly confirmed session.

## 9. Rollback / 9. 回滚

Rollback is operationally simple and does not rewrite audit facts:

> 回滚在操作上很简单，且不会重写审计事实：

1. stop the dedicated process;
2. remove all six `WEFLOW_QQ_*` environment values;
3. rotate/revoke the AppSecret in the QQ portal if exposure is suspected;
4. remove the robot from the sandbox group or revoke its group event/message permission;
5. leave Case, revision, business-event, acknowledgement intent/observation/completion,
   and accepted reports append-only.

> 1. 停止专用进程；
> 2. 移除所有六个 `WEFLOW_QQ_*` 环境变量；
> 3. 如果怀疑凭据泄露，在 QQ 平台中轮换/撤销 AppSecret；
> 4. 将机器人从沙箱群中移除，或撤销其群事件/消息权限；
> 5. 保持 Case、修订版、业务事件、确认意图/观察/完成记录以及验收报告为只追加模式。

Do not delete or rewrite the ledger to "undo" a received Case. Deleting a local adapter
journal while a passive acknowledgement is unknown destroys reconciliation evidence and
is not an approved rollback. A future production rollout, readable handler context,
handler notification/approval, final customer answer, multiple groups/tenants,
attachments, QQ mail, and model use each require later OpenSpec changes.

> 不要删除或重写账本来"撤销"已接收的 Case。在被动确认未知的情况下删除本地适配器日志会破坏对账证据，不属于批准的回滚方式。未来的生产环境部署、可读的处理人上下文、处理人通知/审批、最终客户答复、多群组/多租户、附件、QQ 邮件以及模型使用均需通过后续的 OpenSpec 变更来实现。
## 10. 首次安全配对：管理端没有 `group_openid` 时怎么办

QQ 机器人管理端通常不会直接展示群的 `group_openid`。这个值只在机器人真正收到
`GROUP_AT_MESSAGE_CREATE` 事件时由 QQ 提供，因此不能用普通 QQ 群号代替，也不要把原始
OpenID 写进 `.env`、报告、截图或面试材料。首次配对命令只读群事件，不发送 QQ 消息，
也不会创建 Case、启动 workflow、调用模型或绑定处理人。

### 10.1 启动专用配对监听

只在当前 PowerShell 进程中设置沙箱 AppID/AppSecret 和服务端选择的 tenant：

```powershell
$env:WEFLOW_QQ_APP_ID = '<sandbox AppID>'
$env:WEFLOW_QQ_CLIENT_SECRET = '<process-only AppSecret>'
$env:WEFLOW_QQ_TENANT_ID = 'tenant-qq-sandbox'
$env:WEFLOW_QQ_CAPABILITIES = 'qq.group_pair.read'
uv run python scripts/dev.py qq-sandbox-pair-group `
  --confirm-live-qq-pairing `
  --output reports/add-secure-qq-first-group-pairing-live.json
```

命令会先输出脱敏 readiness。只有 Token、Gateway、WebSocket 鉴权均成功并收到 `READY`
后，才会输出 `gateway_ready=true` 和如下挑战：

```text
在唯一测试群发送：@机器人 WFPAIR-...
```

在 QQ 输入框中从成员列表选择蓝色的真实机器人 mention，然后紧跟本次显示的完整
`WFPAIR-...`；不要手打一个看起来像 `@机器人` 的普通字符串，不要添加其他文字、附件或
卡片。挑战只显示一次，五分钟后命令以 `pairing_challenge_expired` 安全退出；到期后重新
运行命令获取新挑战，旧挑战不能复用。

如果 Token 或 Gateway HTTP 阶段不可达，命令分别报告
`pairing_token_transport_unreachable` 或 `pairing_gateway_transport_unreachable`，此时不会
显示挑战，也不应在群里发送任何配对消息。

### 10.2 验证真实配对报告

成功报告只包含哈希、安全 pairing ID 和固定为 false 的越权效果字段。独立验证：

```powershell
uv run python scripts/dev.py qq-sandbox-pairing-verify `
  --report reports/add-secure-qq-first-group-pairing-live.json `
  --mode qq-sandbox-live
```

只有验证器输出 `passed=true` 且 `qq_group_pairing_live_verified=true`，才能把报告里的
`qqpair_...` 交给 Stage 1；这不代表 Stage 1 intake/ack 已验证。

### 10.3 只做 Stage 1 配对选择器与门禁检查

移除 pairing 命令使用的 tenant，切换为安全 pairing ID，并使用 `--readiness-only`：

```powershell
Remove-Item Env:WEFLOW_QQ_TENANT_ID -ErrorAction SilentlyContinue
$env:WEFLOW_QQ_SANDBOX_PAIRING_ID = '<qqpair_...>'
$env:WEFLOW_QQ_IDENTITY_SALT = '<process-only random salt>'
$env:WEFLOW_QQ_CAPABILITIES = 'qq.group_at.read,qq.passive_ack.execute'
uv run python scripts/dev.py qq-sandbox-intake-ack `
  --confirm-live-qq `
  --readiness-only
```

该模式会在构造 Gateway runner、Case ledger 和 QQ sender 之前退出，必须报告
`selector_mode=safe-pairing-id`、`selector_resolved=true`、`network_contacted=false`、
`case_creation=false`、`qq_write_attempted=false` 和 `stage1_verified=false`。不要在本步骤
移除 `--readiness-only`，也不要发送 API-503 测试消息；真实 intake/ack 仍属于独立变更
`add-qq-sandbox-intake-and-ack` 的任务 5.2/5.3。

### 10.4 到期、撤销与回滚
安全 pairing ID 的私有 locator 最多保留 24 小时，并在下一次专用命令启动时清理。需要立即撤销时只使用安全 ID：

```powershell
uv run python scripts/dev.py qq-sandbox-pairing-revoke --pairing-id '<qqpair_...>'
```

撤销后该 ID 不能再解析为 Stage 1 群组；不可变的 challenge/completion 哈希事实仍保留，不能通过删除账本伪造“从未配对”。不要打印、复制或导出 `.weflow/qq-sandbox.sqlite3` 中的原始 locator。

完整回滚步骤是：停止专用进程，移除所有 `WEFLOW_QQ_*` 进程变量；若怀疑 AppSecret 泄露，在 QQ 管理端轮换凭据并将机器人移出测试群。离线 fake 报告只能证明确定性边界；只有真实命令和独立验证器通过，才能声明首次群配对 live-verified。该结论仍不等于 Stage 1 intake/ack、客户已读、问题已解决或生产可用。
