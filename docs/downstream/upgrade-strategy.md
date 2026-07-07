# DeerFlow Downstream Upgrade Strategy

本文档定义本仓库基于 `bytedance/deer-flow` 二次开发时的长期升级策略。目标是让官方 DeerFlow 后续更新时，本地 HR Boss、火炬 HR 数据层、部署脚本和少量平台能力能够以可重复、可验证、低冲突的方式重新适配。

## Goals

- 保持官方 DeerFlow 主体尽量干净，减少长期冲突面。
- 将 HR Boss、Huoju HR 清洗层、HR MCP 启动和部署能力放在清晰的扩展层。
- 必须修改官方核心时，把改动收敛成小 patch，并记录原因、验证命令和后续迁移方式。
- 每次官方升级都通过固定分支、固定文档、固定测试完成，而不是临时手工合并。

## Branch Model

- `upstream/main`: 官方 `https://github.com/bytedance/deer-flow.git`，只 fetch，不直接提交。
- `main`: 当前本地二开稳定分支，升级完成前不要直接覆盖。
- `codex/upstream-sync-YYYYMMDD`: 每次官方升级的集成试验分支，必须从 `upstream/main` 创建。
- `backup-before-upstream-sync-YYYYMMDD`: 升级前给本地稳定分支打的保护 tag。
- `patch/<topic>`: 可选，用于单独迁移某个高风险核心 patch。

当前 2026-07-06 迁移分支：

```text
codex/upstream-sync-20260706
```

当前保护 tag：

```text
backup-before-upstream-sync-20260706
```

## Repository Shape

二开内容按以下四层维护。

### Extension Layer

这类内容应尽量独立于官方核心，未来升级时优先直接迁移：

- `backend/.deer-flow/agents/hr-boss-agent/*`
- `skills/custom/hr-boss/*`
- `backend/scripts/import_huoju_hr_mysql.py`
- `backend/scripts/clean_huoju_hr_mysql.py`
- `backend/scripts/run_hr_boss_eval.py`
- `backend/scripts/probe_hr_boss_latency.py`
- `scripts/run_text2cypher_mcp.py`
- `scripts/run_graphrag_mcp.py`
- `scripts/run_xiyan_text2sql_mcp.py`
- `scripts/hr_mcp_transport.py`
- `deployment/hr-boss/*`
- `docker/docker-compose.hr-boss*.yaml`
- `extensions_config.local-http.json`

### External Service Layer

HR MCP 服务以 `D:/study/my-mcp/hr-mcp-suite` 为唯一源码来源，不应复制进 DeerFlow 主仓：

- Text2Cypher: `D:/study/my-mcp/hr-mcp-suite/services/text2cypher`
- GraphRAG MCP: `D:/study/my-mcp/hr-mcp-suite/services/graphrag-mcp`
- GraphRAG data pipeline: `D:/study/my-mcp/hr-mcp-suite/data/byog_graphrag`

DeerFlow 只通过 MCP 配置、启动脚本和部署文件连接这些服务。

### Adapter Patch Layer

这类改动可以进入 DeerFlow 主体，但必须小而集中：

- 额外 agent 注册或发现机制。
- 额外 gateway router 注册。
- MCP HTTP/stdio 启动适配。
- 本地模型配置变量兼容。
- 生产 Docker 启动安全修正，例如 `uv run --no-sync`。

### Core Patch Layer

这类改动风险最高，必须逐个迁移、逐个验证：

- `backend/packages/harness/deerflow/agents/lead_agent/*`
- `backend/packages/harness/deerflow/agents/middlewares/*`
- `backend/packages/harness/deerflow/runtime/*`
- `backend/packages/harness/deerflow/mcp/*`
- `backend/app/gateway/services.py`
- `backend/app/gateway/routers/thread_runs.py`
- `frontend/src/components/workspace/messages/*`
- `frontend/src/core/threads/*`

原则：能外置就外置；不能外置时，先记录在 `docs/downstream/patch-inventory.md`，再迁移。

## Upgrade Runbook

每次官方升级按以下步骤执行。

### 1. Protect Current Stable Branch

```powershell
cd D:\python_project\deer-flow
git status --short --branch
git tag backup-before-upstream-sync-YYYYMMDD main
```

如果工作区不干净，先提交或单独处理，不要带脏工作区进入升级。

### 2. Fetch Official Upstream

```powershell
git remote add upstream https://github.com/bytedance/deer-flow.git
git fetch upstream main --no-tags
```

如果 `upstream` 已存在，只运行 `git fetch upstream main --no-tags`。

### 3. Create Isolated Worktree

```powershell
git worktree add .worktrees/upstream-sync-YYYYMMDD -b codex/upstream-sync-YYYYMMDD upstream/main
cd .worktrees/upstream-sync-YYYYMMDD
```

不要在原 `main` 工作区直接合并官方更新。

### 4. Restore Extension Layer First

优先迁移低冲突扩展层，避免一开始就处理核心冲突：

```powershell
git restore --source main -- backend/.deer-flow/agents/hr-boss-agent
git restore --source main -- skills/custom/hr-boss
git restore --source main -- backend/scripts/import_huoju_hr_mysql.py
git restore --source main -- backend/scripts/clean_huoju_hr_mysql.py
git restore --source main -- deployment/hr-boss
git restore --source main -- docker/docker-compose.hr-boss.yaml
git restore --source main -- docker/docker-compose.hr-boss.offline.yaml
```

如果这些路径被 `.gitignore` 忽略，使用精确路径强制暂存：

```powershell
git add -f backend/.deer-flow/agents/hr-boss-agent skills/custom/hr-boss
```

### 5. Add Minimal Dependency Deltas

只追加本地脚本确实需要的依赖，不要用旧分支的 `pyproject.toml` 覆盖上游新版。

当前 HR 扩展需要：

```toml
"neo4j>=5.28.2"
"pymysql>=1.1.1"
```

更新锁文件：

```powershell
cd backend
uv lock
```

### 6. Run Extension Verification

```powershell
cd D:\python_project\deer-flow\.worktrees\upstream-sync-YYYYMMDD
python -m py_compile backend/scripts/clean_huoju_hr_mysql.py backend/scripts/import_huoju_hr_mysql.py deployment/hr-boss/sync_huoju_hr_data.py scripts/run_text2cypher_mcp.py scripts/run_graphrag_mcp.py

cd backend
$env:PYTHONPATH=".;packages/harness"
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8="1"
.\.venv\Scripts\python.exe -m pytest tests/test_clean_huoju_hr_mysql.py tests/test_import_huoju_hr_mysql.py tests/test_huoju_hr_offline_deployment.py tests/test_sync_huoju_hr_data.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_hr_boss_prompt_contract.py tests/test_hr_boss_vllm_llm_config.py tests/test_hr_mcp_http_launchers.py tests/test_hr_boss_eval_runner.py tests/test_hr_boss_latency_policy.py tests/test_hr_boss_model_benchmark.py tests/test_text2cypher_employee_query_launcher.py tests/test_clear_conversation_data_script.py -q
```

### 7. Commit Extension Layer

```powershell
git add -A
git add -f backend/.deer-flow/agents/hr-boss-agent skills/custom/hr-boss
git diff --cached --check
git commit -m "迁移HR定制资产"
```

### 8. Migrate Core Patches In Small Batches

推荐顺序：

1. 平台管理和监控导出。
2. 本地模型和上下文预检。
3. 工具收束、MCP 生命周期和工具并发。
4. 前端管理页和消息体验。
5. Docker、CI 和文档收尾。

每批只解决一个主题，每批都提交一次。

## Required Verification Before Merge

升级分支合入稳定分支前，至少完成：

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_clean_huoju_hr_mysql.py tests/test_import_huoju_hr_mysql.py tests/test_huoju_hr_offline_deployment.py tests/test_sync_huoju_hr_data.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_hr_boss_prompt_contract.py tests/test_hr_boss_vllm_llm_config.py tests/test_hr_mcp_http_launchers.py tests/test_hr_boss_eval_runner.py tests/test_hr_boss_latency_policy.py tests/test_hr_boss_model_benchmark.py tests/test_text2cypher_employee_query_launcher.py tests/test_clear_conversation_data_script.py -q
```

如果迁移了前端：

```powershell
cd frontend
pnpm check
pnpm test
```

如果迁移了 gateway 或 runtime：

```powershell
cd backend
$env:PYTHONPATH=".;packages/harness"
.\.venv\Scripts\python.exe -m pytest tests/test_gateway_services.py tests/test_runs_api_endpoints.py tests/test_mcp_session_pool.py tests/test_runtime_lifecycle_e2e.py -q
```

## Rules For Future Custom Work

- 不要把 HR 业务口径写进 DeerFlow 核心 runtime。
- 不要直接复制旧分支的大文件覆盖上游新版文件。
- 每个核心 patch 必须有对应测试或手工验证命令。
- 修改 `lead_agent`、middleware、runtime、message stream、thread hooks 前，先在 `patch-inventory.md` 登记。
- 新增业务能力优先选择 MCP、skill、agent config、deployment script，而不是改官方核心。

