# 智能体细粒度监控页面设计

## 背景

管理后台需要新增一个面向运维排障的智能体细粒度监控页面。运维人员通常从“某个用户反馈某条回答有问题”开始排查，因此页面应优先展示所有用户最近对话，并支持从用户身份、对话、run 一路下钻到具体动作和工具调用。

当前系统已有可复用基础：

- 平台管理员 API：`backend/app/gateway/routers/platform_admin.py`
- run 元数据：`backend/packages/harness/deerflow/persistence/run/model.py`
- run 事件流：`backend/packages/harness/deerflow/runtime/events/store/base.py`
- 工具审计：`backend/packages/harness/deerflow/persistence/platform/model.py`
- IM 对话映射：`backend/app/channels/store.py`

## 目标

1. 默认展示所有来源的最近对话，包括 Web 登录用户和 IM channel 用户。
2. 能定位到具体用户身份、对话 `thread_id`、run `run_id`。
3. 能查看 run 内智能体所有关键动作，按时间顺序展示。
4. 能看到每个工具调用的工具名、MCP server、状态、耗时、错误摘要。
5. 页面展示时间统一为北京时间，原始 UTC 时间保留在详情数据中。

## 非目标

1. 第一版不把 IM 用户绑定到平台用户、员工、邮箱或姓名。
2. 第一版不替代 Langfuse、LangSmith 等外部 trace 系统。
3. 第一版不暴露完整敏感工具入参，默认只展示参数键和脱敏摘要。
4. 第一版不提供修改、重跑、取消 run 等操作，只做只读排障。

## 用户身份口径

页面统一使用 `identity` 展示用户来源，但不做归并。

Web 用户：

```json
{
  "identity_type": "web",
  "identity_source": "web",
  "identity_display": "reviewer@example.com",
  "raw_identity": {
    "user_id": "uuid",
    "email": "reviewer@example.com"
  }
}
```

IM channel 用户：

```json
{
  "identity_type": "channel",
  "identity_source": "feishu",
  "identity_display": "feishu: ou_xxx",
  "raw_identity": {
    "channel_user_id": "ou_xxx",
    "chat_id": "oc_xxx",
    "topic_id": "msg_xxx",
    "thread_ts": null
  }
}
```

IM 用户身份只展示渠道原始字段。例如飞书展示 `open_id/chat_id/topic_id`，钉钉展示 `user_id/conversation_id`，Slack 展示 `user_id/channel_id/thread_ts`。不要尝试显示员工姓名、平台邮箱或平台 user_id，除非未来有明确绑定关系。

## 页面信息架构

管理监控页使用独立前端路径 `/admin/monitoring`。页面复用 workspace 侧栏壳层，并在管理员左侧导航中提供与“管理后台”同级的“智能体监控”入口；入口仅对管理员可见，在监控路径下保持选中。页面仍复用现有管理员鉴权能力，只有管理员可见。

页面采用三段下钻：

```text
最近对话列表
  -> 对话详情与 run 列表
  -> run 动作时间线
  -> 动作 Inspector
```

### 默认首页

默认展示“所有用户最近 50 条对话”，不默认限制时间范围，按最近更新时间倒序。每条对话卡片展示：

- 身份来源：`web`、`feishu`、`dingtalk`、`wecom`、`wechat`、`slack`、`telegram`、`discord`
- 原始身份摘要
- `thread_id`
- 最新 `run_id`
- agent 名称
- 最近问题或首条用户消息摘要
- 最新 run 状态
- 异常标记：失败、运行中、超时、慢工具
- 北京时间更新时间

左侧提供筛选：

- 来源：全部、Web、各 IM channel
- Agent
- 时间范围
- 状态
- 工具名
- MCP server

顶部提供全局搜索：

- email
- 平台 user_id
- channel user_id
- chat_id
- topic_id
- thread_id
- run_id
- 工具名

顶部还提供“导入 run timeline JSON”入口，用于离线排障。导入后进入临时查看模式，复用同一套 run 时间线与动作 Inspector，不写入数据库。

### 对话详情

点击最近对话后，中间区域展示：

- identity 原始字段
- `thread_id`
- 对话最近消息摘要
- run 列表，按创建时间倒序
- 每个 run 的用户问题摘要、状态、耗时、token、工具数量、错误摘要。用户问题优先使用可信的 `first_human_message`，并过滤内部上下文抽取 prompt；如果没有可信问题，应明确显示不可用。

### Run 时间线

点击 run 后，打开接近全屏的 Run inspection 弹窗。弹窗左侧展示动作时间线，右侧展示当前事件的 Inspector；两侧独立滚动，避免长时间线和 JSON 详情在主页面中互相挤压。关闭弹窗后保留已选 run 和事件，再次点击该 run 或顶部 `Inspect run` 可继续排障。导入单个 run timeline JSON 成功后也自动打开此弹窗。

主页面仅保留“最近对话”和“对话详情 / run 列表”两栏。时间线以北京时间展示，格式建议为 `YYYY-MM-DD HH:mm:ss`，并在详情中保留原始 ISO 时间。

动作类型包括：

- `run.start`
- `run.end`
- `run.error`
- `llm.human.input`
- `llm.ai.response`
- `llm.error`
- `llm.tool.result`
- `tool.start`
- `tool.end`
- `tool.error`
- `middleware.start`
- `middleware.end`
- `middleware.error`

第一版可先展示现有事件和工具审计中能还原的动作，后续补齐缺失采集点。

### Inspector

选中弹窗左侧时间线动作后，右侧 Inspector 展示：

- action kind
- status
- event source：`run_event` 或 `tool_audit`
- tool name
- MCP server
- latency
- error 摘要
- content 摘要
- metadata JSON
- 原始 UTC 时间
- 北京时间

## 后端接口设计

所有接口挂在 `/api/platform/admin/monitoring` 下，并使用 `@require_admin`。

### 最近对话

`GET /api/platform/admin/monitoring/conversations/recent`

查询参数：

- `limit`: 默认 50，最大 200。默认请求只取最近 50 条，不默认附加时间范围。
- `offset` 或 cursor
- `source`
- `agent_name`
- `status`
- `tool_name`
- `mcp_server_name`
- `q`
- `from`
- `to`

响应：

```json
{
  "items": [
    {
      "identity_type": "channel",
      "identity_source": "feishu",
      "identity_display": "feishu: ou_xxx",
      "raw_identity": {
        "channel_user_id": "ou_xxx",
        "chat_id": "oc_xxx",
        "topic_id": "msg_xxx"
      },
      "thread_id": "thread-1",
      "latest_run_id": "run-2",
      "agent_name": "hr-boss-agent",
      "last_message": "研发部门有多少人？",
      "status": "error",
      "error_summary": "text2cypher backend unavailable",
      "updated_at": "2026-06-08T05:39:22Z",
      "updated_at_bj": "2026-06-08 13:39:22"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

数据来源：

- Web 用户对话来自 `runs`、thread metadata、run event messages。
- IM channel 对话来自 `ChannelStore.list_entries()` 与对应 `thread_id` 的 runs。
- 最新状态优先使用最新 run 的 `RunRow.status`。

### 对话详情

`GET /api/platform/admin/monitoring/conversations/{thread_id}`

返回：

- identity
- thread summary
- run list
- message preview
- channel mapping, if any

### Run 时间线

`GET /api/platform/admin/monitoring/runs/{run_id}/timeline`

返回：

```json
{
  "run": {
    "run_id": "run-2",
    "thread_id": "thread-1",
    "agent_name": "hr-boss-agent",
    "status": "error"
  },
  "identity": {
    "identity_type": "channel",
    "identity_source": "feishu",
    "identity_display": "feishu: ou_xxx",
    "raw_identity": {
      "channel_user_id": "ou_xxx",
      "chat_id": "oc_xxx"
    }
  },
  "events": [
    {
      "seq": 12,
      "occurred_at": "2026-06-08T05:39:24Z",
      "occurred_at_bj": "2026-06-08 13:39:24",
      "kind": "tool.error",
      "title": "text2cypher_answer_question 调用失败",
      "status": "error",
      "duration_ms": 842,
      "source": "tool_audit",
      "content": {},
      "metadata": {}
    }
  ]
}
```

合并规则：

1. 从 `RunRow` 查 run 和 `thread_id`。
2. 从 `RunEventStore.list_events(thread_id, run_id, user_id=None)` 读取 run events。
3. 从 `ToolAuditLogRow` 查询同一 `run_id` 的工具审计。
4. 归一化为统一 timeline event。
5. 按 `occurred_at` 升序排序，同一时间按 `seq` 排序。

### Run Timeline JSON 导入

前端需要支持导入单个 run timeline JSON，用于把线上导出的单 run 排障包、IM channel 问题复盘包或其他环境中的 run 时间线放到本地管理后台查看。

导入入口：

- `/admin/monitoring` 顶部操作按钮。
- run 时间线页右上角操作按钮。

导入方式：

- 上传 `.json` 文件。
- 粘贴 JSON 文本。

导入范围：

- 只支持单个 run timeline JSON。
- JSON schema 与 `GET /api/platform/admin/monitoring/runs/{run_id}/timeline` 响应保持一致。
- 必须包含 `run.run_id`、`run.thread_id`、`events[]`。
- `identity` 可为空；为空时展示为 `unknown/imported`。

导入行为：

- 默认只在前端内存中解析和展示，不写入数据库。
- 导入后的页面进入 `imported` 临时状态，明确标识“导入视图”。
- 时间线排序、北京时间展示、事件详情 Inspector 与真实 run 一致。
- schema 不匹配时展示具体字段错误，不进入时间线。
- 导入 JSON 中的敏感字段仍按 Inspector 脱敏规则展示。

导入后的 URL 可使用本地状态或 session storage 保持刷新可见，但不要求生成可分享链接。若未来需要保存导入记录，应另行设计带审计的持久化接口。

### Run 消息

`GET /api/platform/admin/monitoring/runs/{run_id}/messages`

可复用已有 run message 查询逻辑，但管理员通道需要 `user_id=None`，避免 internal channel run 因平台用户过滤被漏掉。

## 数据模型与采集补强

第一版可直接使用现有数据：

- `RunRow`: run 状态、token、首条用户消息、最后 AI 消息、错误摘要。
- `RunEventStore`: run 内消息、LLM 响应、run lifecycle。
- `ToolAuditLogRow`: MCP 工具调用、状态、耗时、错误。
- `ChannelStore`: IM 原始身份到 `thread_id` 的映射。

建议后续补强：

1. `RunJournal.on_tool_start` 写入 `tool.start`。
2. `RunJournal.on_tool_end` 写入 `tool.end` 或保留 `llm.tool.result` 并补 metadata。
3. `RunJournal.on_tool_error` 写入 `tool.error`。
4. 关键 middleware 写入 `middleware.*`。
5. agent 路由决策写入 `agent.route`，例如选择 Text2Cypher 或 GraphRAG。

## 时区处理

数据库和事件存储继续使用 UTC ISO 时间。后端响应中可附加 `*_bj` 展示字段，也可以由前端统一格式化为 `Asia/Shanghai`。为了避免前端时区环境差异，建议后端在管理后台 API 中直接返回北京时间字符串，同时保留原始 `occurred_at`。

## 权限与安全

1. 所有接口使用 `@require_admin`。
2. 默认隐藏完整工具入参，只展示参数 key。
3. Inspector 中的 JSON 对敏感字段做脱敏或折叠。
4. IM 原始身份可以展示，但不做员工身份推断。
5. 管理页为只读，不提供修改 run、删除数据、重跑等动作。

## 前端实现建议

新增管理监控模块：

- `frontend/src/app/admin/monitoring/page.tsx`
- `frontend/src/core/platform-admin/monitoring/api.ts`
- `frontend/src/core/platform-admin/monitoring/types.ts`
- `frontend/src/core/platform-admin/monitoring/hooks.ts`
- `frontend/src/components/platform-admin/monitoring/*`

第一版即使用独立管理后台路径 `/admin/monitoring`。独立 admin layout 复用 workspace 侧栏壳层，并在管理员导航中提供“智能体监控”入口，以支持运维人员在管理功能之间快速切换。

## 测试计划

后端：

- 管理员能查询最近对话。
- 普通用户访问被拒绝。
- Web 用户对话能出现在最近列表。
- IM channel 对话能出现在最近列表。
- IM identity 只包含渠道原始身份。
- run timeline 能合并 run events 和 tool audit。
- 北京时间字段正确。
- `run_id/thread_id/channel_user_id` 搜索可命中。

前端：

- 默认展示最近对话。
- 来源筛选正确。
- 点击对话加载 run 列表。
- 点击 run 加载时间线。
- 点击事件展示 Inspector。
- 导入单个 run timeline JSON 后能进入临时查看模式。
- 导入 JSON schema 错误时能展示字段级错误。
- 空状态、错误状态、加载状态完整。

## 落地顺序

1. 后端实现最近对话聚合接口。
2. 后端实现 run timeline 接口。
3. 前端实现监控页基础三栏布局。
4. 前端接入筛选、搜索、下钻。
5. 前端实现单个 run timeline JSON 导入查看。
6. 补 tool start/error 等事件采集。
7. 完成测试和权限校验。
