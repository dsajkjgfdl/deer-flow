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

建议作为第二阶段优先迁移。该能力相对独立，但会涉及前后端和持久化。

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Platform admin routers | Keep | `backend/app/gateway/routers/platform_admin.py`, `backend/app/gateway/routers/platform_agents.py` | 不要覆盖 `routers/__init__.py`；在新版 router 注册方式下增量接入。 |
| Platform persistence | Keep | `backend/packages/harness/deerflow/persistence/platform/*` | 检查上游新版迁移机制后再接入。 |
| Platform config | Keep | `backend/packages/harness/deerflow/config/platform_config.py` | 尽量作为独立 config section，避免污染通用 config。 |
| Platform migrations | Keep | `backend/packages/harness/deerflow/persistence/migrations/versions/20260529_agent_platform_mvp.py`, `20260602_channel_feedback_targets.py`, `20260615_tool_audit_content.py` | 需要确认与上游现有 Alembic revision 是否冲突。 |
| Monitoring frontend | Keep | `frontend/src/components/platform-admin/monitoring/*`, `frontend/src/core/platform/*`, `frontend/src/app/admin/*` | 前端上游变化大，按页面和 API 类型逐块迁移。 |
| Workspace admin frontend | Review | `frontend/src/components/workspace/admin/*`, `frontend/src/app/workspace/admin/page.tsx` | 确认新版导航和权限模型后再迁。 |

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

这部分与 HR Boss 体验强相关，但可能与上游模型工厂和 memory/context 改动冲突。

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Qwen/VLLM model provider | Keep | `backend/packages/harness/deerflow/models/vllm_provider.py`, `backend/packages/harness/deerflow/models/factory.py` | 先确认上游新版 `api_base -> base_url` 和 thinking support 改动，避免回退官方修复。 |
| Context budget model | Review | `backend/packages/harness/deerflow/models/context_budget.py` | 评估是否还能独立存在，或上游已有替代。 |
| Context preflight | Keep | `backend/packages/harness/deerflow/agents/middlewares/dynamic_context_middleware.py`, `summarization_middleware.py` | 只迁 HR 必需部分，避免覆盖上游 staleness/memory 改动。 |
| HR model tests | Migrated | `backend/tests/test_hr_boss_vllm_llm_config.py`, `backend/tests/test_hr_boss_model_benchmark.py` | 已迁，后续作为回归锚点。 |

Recommended verification:

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_model_factory.py tests/test_hr_boss_vllm_llm_config.py tests/test_hr_boss_model_benchmark.py tests/test_summarization_middleware.py -q
```

## Candidate: Tool And MCP Runtime Adaptations

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Tool concurrency limit | Keep | `backend/packages/harness/deerflow/agents/middlewares/tool_concurrency_limit_middleware.py` | 优先做成通用 middleware，不写 HR 特例。 |
| Tool error handling | Keep | `backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py` | 与上游错误处理合并，不能覆盖新状态码和新子代理结果格式。 |
| MCP lifecycle fixes | Review | `backend/packages/harness/deerflow/mcp/session_pool.py`, `mcp/tools.py`, `mcp/cache.py` | 上游已修 HTTP/SSE session pooling，迁移前逐行比对。 |
| Tool audit content | Review | `backend/packages/harness/deerflow/persistence/migrations/versions/20260615_tool_audit_content.py` | 与平台监控一起迁移。 |

Recommended verification:

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_session_pool.py tests/test_tool_error_handling_middleware.py tests/test_tool_concurrency_limit_middleware.py tests/test_mcp_filtering.py -q
```

## Candidate: Gateway And Runtime

这部分最容易产生冲突，必须最后按功能迁移。

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Gateway services | Review | `backend/app/gateway/services.py` | 上游新增 wait disconnect、workspace changes、scheduled tasks 等逻辑，不能用旧文件覆盖。 |
| Thread runs router | Review | `backend/app/gateway/routers/thread_runs.py` | 先确认本地改动是否仍有必要。 |
| Agent factory/runtime resolver | Keep | `backend/app/gateway/services.py`, `backend/packages/harness/deerflow/agents/runtime_resolver.py`, `backend/packages/harness/deerflow/agents/lead_agent/agent.py`, `backend/packages/harness/deerflow/tools/tools.py`, `backend/tests/test_agent_runtime_resolver.py`, `backend/tests/test_tools_runtime_policy.py` | 运行时 agent 分配生效链路已迁移：平台分配解析有效 agent，并把 MCP/技能/工具白名单写入运行配置供 lead agent 消费。 |
| Run journal/tool audit | Review | `backend/packages/harness/deerflow/runtime/journal.py`, `runtime/runs/*` | 与平台监控需求绑定迁移。 |

Recommended verification:

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_gateway_services.py tests/test_runs_api_endpoints.py tests/test_runtime_lifecycle_e2e.py tests/test_run_journal.py -q
```

## Candidate: Frontend Customization

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Landing/nav changes | Keep | `frontend/src/app/page.tsx`, `frontend/tests/unit/app/root-page.test.ts` | 二开版本固定不要官方导航页，`/` 必须直接跳转到 `/workspace/chats/new`；后续同步上游时保留该回归测试。 |
| Agent cards/display names | Keep | `frontend/src/components/workspace/agents/agent-card.tsx`, `frontend/src/core/agents/*` | 与 HR Boss 展示有关，需适配新版 agent API。 |
| Message list changes | Review | `frontend/src/components/workspace/messages/*`, `frontend/src/core/messages/*` | 上游新增 sidecar、workspace changes、引用等能力，禁止整文件覆盖。 |
| Thread hooks | Review | `frontend/src/core/threads/*` | 与分支会话、workspace changes、反馈历史等上游新增功能冲突概率高。 |
| Platform admin UI | Keep | `frontend/src/components/platform-admin/*`, `frontend/src/core/platform/*` | 与平台管理后端一起迁移。 |

Recommended verification:

```powershell
cd frontend
pnpm check
pnpm test
```

## Candidate: Docs, CI, And Public Skills

| Area | Status | Paths | Migration Notes |
| --- | --- | --- | --- |
| Root docs | Review | `README*.md`, `CHANGELOG*.md`, `AGENTS.md`, `CLAUDE.md` | 保留上游新版主文档；本地说明放在 `docs/downstream/*` 和 HR 部署文档。 |
| CI workflows | Review | `.github/workflows/*` | 本地环境可能不使用 GitHub CI，默认保留上游，除非有明确内网 CI 需求。 |
| Public skills | Review | `skills/public/*` | 上游新增 skill 可能有价值，不要按旧分支删除。 |
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
迁移平台管理
```

Scope:

- Backend platform routers.
- Platform persistence models/repositories.
- Platform migrations after revision conflict check.
- Platform monitoring tests.

Exit criteria:

- Platform-related backend tests pass.
- HR Boss and Huoju regression tests still pass.
- No broad overwrite of gateway/runtime/frontend files.
