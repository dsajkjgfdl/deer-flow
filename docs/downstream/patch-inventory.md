# DeerFlow Downstream Patch Inventory

本文档记录本地二开相对官方 `bytedance/deer-flow` 的补丁分类。每次官方升级时，先更新本清单，再决定迁移、外置、放弃或延后。

## Status Legend

- `Migrated`: 已迁移到当前上游基底。
- `Keep`: 必须继续迁移。
- `Externalize`: 应尽量移到 MCP、skill、配置或独立脚本。
- `Drop`: 不再迁移，优先采用官方新版能力。
- `Review`: 需要业务或技术确认。

## Already Migrated In `codex/upstream-sync-20260706`

| Area | Status | Paths | Notes |
| --- | --- | --- | --- |
| HR Boss agent config | Migrated | `backend/.deer-flow/agents/hr-boss-agent/*` | 通过 `git add -f` 纳入版本控制，因为路径可能被 ignore。 |
| HR Boss orchestration skill | Migrated | `skills/custom/hr-boss/SKILL.md` | 作为业务编排层保留，不直接挂底层 Text2Cypher/GraphRAG skill。 |
| Huoju HR MySQL import/clean | Migrated | `backend/scripts/import_huoju_hr_mysql.py`, `backend/scripts/clean_huoju_hr_mysql.py` | 依赖 `pymysql`。 |
| HR Boss evaluation scripts | Migrated | `backend/scripts/run_hr_boss_eval.py`, `backend/scripts/probe_hr_boss_latency.py`, `scripts/benchmark_hr_boss_models.py` | 保留为本地评测和压测工具。 |
| HR MCP launchers | Migrated | `scripts/run_text2cypher_mcp.py`, `scripts/run_graphrag_mcp.py`, `scripts/run_xiyan_text2sql_mcp.py`, `scripts/hr_mcp_transport.py` | 依赖外部 `hr-mcp-suite`。 |
| HR offline deployment | Migrated | `deployment/hr-boss/*`, `docker/docker-compose.hr-boss*.yaml` | 用于火炬 HR 离线部署。 |
| HR extension config examples | Migrated | `extensions_config.example.json`, `extensions_config.local-http.json`, `deployment/hr-boss/extensions_config.docker.json` | 保留 HTTP 和 stdio 两种连接方式。 |
| Production Docker no-sync | Migrated | `docker/docker-compose.yaml` | gateway 启动使用 `uv run --no-sync`，避免生产启动时重新同步依赖。 |
| HR test suite | Migrated | `backend/tests/test_hr_*`, `backend/tests/test_*huoju*`, `backend/tests/test_sync_huoju_hr_data.py` | 当前验证通过：HR Boss 60 passed, Huoju 40 passed。 |
| Dependency delta | Migrated | `backend/pyproject.toml`, `backend/uv.lock` | 新增 `neo4j`, `pymysql`。 |

## Candidate: Platform Management And Monitoring

该批次已迁移到当前上游基底。后续官方升级时保留平台管理的独立 router、persistence、migration 和前端页面，不要用旧分支整文件覆盖新版上游。

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Platform admin routers | Migrated | `backend/app/gateway/routers/platform_admin.py`, `backend/app/gateway/routers/platform_agents.py` | 已按新版 router 注册方式增量接入。 |
| Platform persistence | Migrated | `backend/packages/harness/deerflow/persistence/platform/*` | 已接入当前 persistence bootstrap 和 repository 测试。 |
| Platform config | Migrated | `backend/packages/harness/deerflow/config/platform_config.py` | 作为独立 platform config section 保留。 |
| Platform migrations | Migrated | `backend/packages/harness/deerflow/persistence/migrations/versions/0004_agent_platform_mvp.py` | 已改用当前上游 revision 序列，避免旧分支 revision 冲突。 |
| Monitoring frontend | Migrated | `frontend/src/components/platform-admin/monitoring/*`, `frontend/src/core/platform/*`, `frontend/src/app/admin/*` | 已迁移平台监控页面、导入导出、详情和时间线组件。 |
| Workspace admin frontend | Migrated | `frontend/src/components/workspace/admin/*`, `frontend/src/app/workspace/admin/page.tsx` | 已迁移 workspace 管理入口、agent catalog、assignment、feedback 和 audit 页面。 |

Recommended verification:

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_*platform* tests/test_*monitoring* tests/test_*feedback* -q

cd ..\frontend
pnpm check
pnpm test -- platform
```

## Candidate: Model Switching And Context Budget

该批次已迁移到当前上游基底。保留现有上游模型工厂修复，仅增量接入 HR Qwen/vLLM 所需的最终请求上下文预算预检。

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Qwen/VLLM model provider | Migrated | `backend/packages/harness/deerflow/models/vllm_provider.py`, `backend/packages/harness/deerflow/models/factory.py` | 保留当前分支的 `api_base -> base_url`、`stream_usage`、`stream_chunk_timeout` 和未知参数告警逻辑，增量接入 vLLM context preflight。 |
| Context budget model | Migrated | `backend/packages/harness/deerflow/models/context_budget.py`, `backend/tests/test_context_budget.py` | 恢复最终 chat payload token 估算、超限报错和 `trim` 策略，作为 vLLM 请求前保护层。 |
| Context preflight config | Migrated | `backend/packages/harness/deerflow/config/model_config.py` | `max_context_tokens` 与 `context_preflight` 进入模型配置 schema；模型工厂会过滤不支持这些内部字段的 provider。 |
| Dynamic context and summarization | Migrated | `backend/packages/harness/deerflow/agents/middlewares/dynamic_context_middleware.py`, `backend/packages/harness/deerflow/agents/middlewares/summarization_middleware.py` | 已在当前分支保留，并纳入本批回归测试。 |
| HR model tests | Migrated | `backend/tests/test_hr_boss_vllm_llm_config.py`, `backend/tests/test_hr_boss_model_benchmark.py` | 继续作为 HR Qwen/DeepSeek 配置回归锚点。 |

Recommended verification:

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_context_budget.py tests/test_vllm_provider.py tests/test_model_factory.py tests/test_dynamic_context_middleware.py tests/test_summarization_middleware.py tests/test_hr_boss_vllm_llm_config.py tests/test_hr_boss_model_benchmark.py -q
```

## Candidate: Tool And MCP Runtime Adaptations

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Tool concurrency limit | Migrated | `backend/packages/harness/deerflow/agents/middlewares/tool_concurrency_limit_middleware.py`, `backend/tests/test_tool_concurrency_limit_middleware.py` | 已作为通用 middleware 接入 lead runtime 和 SDK factory，在 `ToolErrorHandlingMiddleware` 前执行。 |
| Tool error handling | Migrated | `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py`, `backend/tests/test_tool_error_handling_middleware.py` | 保留当前上游/本地的新子代理状态、skill metadata 和 runtime builder 结构，只增量接入并发限制。 |
| MCP lifecycle fixes | Drop | `backend/packages/harness/deerflow/mcp/session_pool.py`, `mcp/tools.py`, `mcp/cache.py` | 当前上游基底已有更完整的 `_inflight`/owner-task session pool、stdio pooling + HTTP/SSE one-shot 逻辑和 `test_mcp_session_pool.py` 覆盖；不迁旧版 MCP 文件。 |
| Tool audit content | Migrated | `backend/packages/harness/deerflow/persistence/migrations/versions/0005_tool_audit_content.py`, `backend/packages/harness/deerflow/mcp/tools.py`, `backend/tests/test_tool_audit.py` | 已迁移：MCP tool 调用审计内容、Text2Cypher debug 入审计不入 agent 返回、HTTP MCP one-shot 审计 wrapper。 |

Recommended verification:

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_session_pool.py tests/test_tool_error_handling_middleware.py tests/test_tool_concurrency_limit_middleware.py tests/test_create_deerflow_agent.py -q
```

## Candidate: Gateway And Runtime

这部分最容易产生冲突，必须最后按功能迁移。

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Gateway services | Review | `backend/app/gateway/services.py` | 上游新增 wait disconnect、workspace changes、scheduled tasks 等逻辑，不能用旧文件覆盖。 |
| Thread runs router | Review | `backend/app/gateway/routers/thread_runs.py` | 先确认本地改动是否仍有必要。 |
| Agent factory/runtime resolver | Migrated | `backend/app/gateway/services.py`, `backend/packages/harness/deerflow/agents/runtime_resolver.py`, `backend/packages/harness/deerflow/agents/lead_agent/agent.py`, `backend/packages/harness/deerflow/tools/tools.py`, `backend/tests/test_agent_runtime_resolver.py`, `backend/tests/test_tools_runtime_policy.py` | 运行时 agent 分配生效链路已迁移：平台分配解析有效 agent，并把 MCP/技能/工具白名单写入运行配置供 lead agent 消费。 |
| Run journal/tool audit | Migrated | `backend/packages/harness/deerflow/runtime/journal.py`, `backend/packages/harness/deerflow/runtime/runs/worker.py`, `backend/tests/test_run_journal_llm_requests.py` | 已迁移：RunJournal 支持可配置 LLM request 捕获、tool start/error trace，worker 透传 run_events 配置。 |

Recommended verification:

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_gateway_services.py tests/test_runs_api_endpoints.py tests/test_runtime_lifecycle_e2e.py tests/test_run_journal.py -q
```

## Candidate: Frontend Customization

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Landing/nav changes | Migrated | `frontend/src/app/page.tsx`, `frontend/tests/unit/app/root-page.test.ts` | 二开版本固定不要官方导航页，`/` 必须直接跳转到 `/workspace/chats/new`；后续同步上游时保留该回归测试。 |
| Agent cards/display names | Migrated | `frontend/src/components/workspace/agents/agent-card.tsx`, `frontend/src/components/workspace/agent-welcome.tsx`, `frontend/src/app/workspace/agents/[agent_name]/chats/[thread_id]/page.tsx`, `frontend/src/core/agents/*`, `frontend/tests/unit/core/agents/display-name.test.ts` | 已接入后端 `display_name` 字段；HR Boss 可显示“人岗匹配智能体”，缺失或空白时回退内部 agent name。 |
| Message list changes | Drop | `frontend/src/components/workspace/messages/*`, `frontend/src/core/messages/*` | 当前上游基底已包含 sidecar 选区、分支/重生成、反馈按钮、token attribution、隐藏消息过滤等更完整实现；不迁旧版 message-list 覆盖。 |
| Thread hooks | Drop | `frontend/src/core/threads/*` | 当前上游基底已包含 hidden sidecar context、onSent guard、infinite history、thread search、branch/regenerate 和 sidecar 删除级联；不迁旧版 hooks 覆盖。 |
| Platform admin UI | Migrated | `frontend/src/components/platform-admin/*`, `frontend/src/core/platform/*` | 已随平台管理后端一起迁移。 |

Recommended verification:

```powershell
cd frontend
pnpm check
pnpm test
```

## Candidate: Docs, CI, And Public Skills

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Root docs | Drop | `README*.md`, `CHANGELOG*.md`, `AGENTS.md`, `CLAUDE.md` | 不从旧分支覆盖上游新版主文档；本地说明放在 `docs/downstream/*` 和 HR 部署文档。 |
| CI workflows | Drop | `.github/workflows/*` | 不迁旧分支 workflow；默认保留上游 CI，除非后续有明确内网 CI 需求再新增独立 workflow。 |
| Public skills | Drop | `skills/public/*` | 不按旧分支删除或覆盖上游 public skills；HR/二开能力放在 `skills/custom/*`。 |
| Agent maintenance skills | Drop | `.agent/skills/blocking-io-guard/*`, `.agent/skills/deerflow-maintainer-orchestrator/*` | 旧分支删除不代表新基底也要删，默认保留上游。 |

## Do Not Migrate By Default

以下类型默认不迁移，除非有明确业务理由：

- 旧分支删除上游新增文件的 delete-only diff。
- 旧分支对 README、CHANGELOG、CI 的大规模覆盖。
- 旧分支对测试目录的批量删除。
- 已被上游新版替代的 runtime workaround。

## Next Migration Batch

建议下一批提交：

```text
收尾验证和合并准备
```

Scope:

- Run final backend/frontend regression commands.
- Review optional `Gateway services` and `Thread runs router` review-only rows.
- Prepare merge or PR from `codex/upstream-sync-20260706`.

Exit criteria:

- Worktree is clean.
- All required migration rows are `Migrated` or intentionally `Drop`.
- Review-only rows have a clear owner or are deferred to future upstream-sync rounds.
