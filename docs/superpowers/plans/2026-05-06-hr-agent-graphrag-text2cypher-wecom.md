# HR Agent GraphRAG + Text2Cypher + WeCom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a DeerFlow HR intelligent agent that routes HR questions across GraphRAG `basic/local/global/drift` and Text2Cypher, then exposes the same agent through the WeCom intelligent bot channel for leadership demos.

**Architecture:** Reuse DeerFlow as the conversation shell and MCP host. Reuse the existing `text2cypher` MCP for Neo4j exact queries, extend the existing `hr-graphrag-qa` MCP so the HR agent can call GraphRAG modes explicitly, and upgrade the existing `hr-boss-agent` as the single leadership-facing entrypoint.

**Tech Stack:** DeerFlow 2.0, LangGraph Server, DeerFlow custom agents, MCP stdio servers, `D:/study/my-mcp/graphrag-mcp`, `D:/study/my-mcp/text2cypher`, Neo4j, Microsoft GraphRAG BYOG data, WeCom intelligent bot WebSocket channel.

---

## Current State

- DeerFlow already has MCP launcher scripts:
  - `D:/study/deer-flow/scripts/run_graphrag_mcp.py`
  - `D:/study/deer-flow/scripts/run_text2cypher_mcp.py`
- DeerFlow already has MCP server configuration in `D:/study/deer-flow/extensions_config.json`:
  - `hr-graphrag-qa`
  - `text2cypher`
- `text2cypher` MCP already exposes:
  - `prepare_schema`
  - `get_schema`
  - `generate_cypher`
  - `validate_cypher`
  - `execute_cypher`
  - `answer_question`
- `hr-graphrag-qa` MCP currently exposes only:
  - `answer_question`
- `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent` already exists and is the best entrypoint to upgrade.

## Target Behavior

Leadership-facing questions should route as follows:

| Question Type | Route | Reason |
| --- | --- | --- |
| Count, average, ratio, ranking, full list, filtered people | Text2Cypher | These require exact database filtering or aggregation. |
| Specific employee profile, department, position, education, project, certificate, title | GraphRAG `local` | These are entity-centered evidence questions. |
| Organization talent structure, trend, risk, group portrait | GraphRAG `global` | These are community-summary questions. |
| Exploratory cross-group analysis or "what else can we discover" questions | GraphRAG `drift` | These need global-to-local exploration. |
| Simple evidence-fragment lookup | GraphRAG `basic` | These only need matching text-unit evidence. |

For examples:

- `福建火炬电子科技股份有限公司平均年龄是多少？` routes to `text2cypher_answer_question`.
- `福建火炬电子科技股份有限公司的高级工程师有哪些？` routes to `text2cypher_answer_question`.
- `福建火炬电子科技股份有限公司的人才结构有什么特点？` routes to `hr-graphrag-qa_query_global`.
- `老王1366的教育和项目经历是什么？` routes to `hr-graphrag-qa_query_local`.
- `制造车间哪些群体可能存在经验断层？` routes to `hr-graphrag-qa_query_drift`.

## File Structure

### DeerFlow Repository

- Modify: `D:/study/deer-flow/extensions_config.json`
  - Keep `text2cypher` and `hr-graphrag-qa` MCP servers enabled.
  - Point `GRAPHRAG_DATA_ROOT` at the active BYOG GraphRAG dataset.
- Modify: `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/config.yaml`
  - Restrict the custom agent to HR skills and MCP servers.
- Modify: `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/SOUL.md`
  - Add explicit HR question routing rules.
- Modify: `D:/study/deer-flow/skills/custom/hr-boss/SKILL.md`
  - Align the skill workflow with GraphRAG four-way routing and Text2Cypher.
- Modify: `D:/study/deer-flow/config.yaml`
  - Add or update WeCom channel settings for `hr-boss-agent`.
- Create: `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`
  - Assert the custom agent loads the intended skills, MCP servers, and routing guardrails.
- Create: `D:/study/deer-flow/backend/tests/test_hr_boss_wecom_session.py`
  - Assert the WeCom channel session resolves to `lead_agent` plus `agent_name=hr-boss-agent`.
- Create: `D:/study/deer-flow/docs/hr-agent-wecom-demo-script.md`
  - Store leadership demo questions, expected routes, and expected answer style.

### GraphRAG MCP Repository

- Modify: `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/formatter.py`
  - Allow `basic` as an answer strategy.
- Modify: `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/service.py`
  - Add explicit strategy query methods.
- Modify: `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/server.py`
  - Register direct MCP tools for `basic/local/global/drift`.
- Modify: `D:/study/my-mcp/graphrag-mcp/tests/test_server.py`
  - Update tool registration tests.
- Modify: `D:/study/my-mcp/graphrag-mcp/tests/test_service.py`
  - Add direct strategy tests.

---

### Task 1: Lock MCP Dataset And Required Environment

**Files:**
- Modify: `D:/study/deer-flow/extensions_config.json`
- Test: `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`

- [ ] **Step 1: Write the failing configuration test**

Create `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py` with:

```python
import json
from pathlib import Path
from unittest.mock import patch

from deerflow.config.agents_config import load_agent_config, load_agent_soul
from deerflow.config.paths import Paths


REPO_ROOT = Path(__file__).resolve().parents[2]
DEERFLOW_BASE_DIR = REPO_ROOT / "backend" / ".deer-flow"


def test_hr_graphrag_mcp_uses_byog_graphrag_dataset() -> None:
    extensions = json.loads((REPO_ROOT / "extensions_config.json").read_text(encoding="utf-8"))
    server = extensions["mcpServers"]["hr-graphrag-qa"]

    assert server["enabled"] is True
    assert server["type"] == "stdio"
    assert server["env"]["GRAPHRAG_MCP_REPO"] == "D:/study/my-mcp/graphrag-mcp"
    assert server["env"]["GRAPHRAG_DATA_ROOT"].replace("\\", "/") == "D:/study/my-mcp/graphrag-data/byog_graphrag"
    assert server["env"]["ALIBABA_API_KEY"] == "$ALIBABA_API_KEY"


def test_text2cypher_mcp_is_enabled_for_hr_graph_queries() -> None:
    extensions = json.loads((REPO_ROOT / "extensions_config.json").read_text(encoding="utf-8"))
    server = extensions["mcpServers"]["text2cypher"]

    assert server["enabled"] is True
    assert server["type"] == "stdio"
    assert server["env"]["TEXT2CYPHER_REPO"] == "D:/study/my-mcp/text2cypher"
    assert server["env"]["TEXT2CYPHER_OPENAI_MODEL"] == "qwen3-max"
    assert server["env"]["TEXT2CYPHER_OPENAI_API_KEY"] == "$DASHSCOPE_API_KEY"
```

- [ ] **Step 2: Run the configuration test to verify the current state**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py::test_hr_graphrag_mcp_uses_byog_graphrag_dataset -v
```

Expected before the dataset switch is active in `extensions_config.json`: FAIL with an assertion showing the configured `GRAPHRAG_DATA_ROOT`.

Expected after the dataset switch is active: PASS.

- [ ] **Step 3: Set the GraphRAG dataset root**

In `D:/study/deer-flow/extensions_config.json`, the `hr-graphrag-qa` server must contain:

```json
{
  "GRAPHRAG_MCP_REPO": "D:/study/my-mcp/graphrag-mcp",
  "GRAPHRAG_DATA_ROOT": "D:/study/my-mcp/graphrag-data/byog_graphrag",
  "ALIBABA_API_KEY": "$ALIBABA_API_KEY"
}
```

Keep the existing `command`, `args`, and `description` values.

- [ ] **Step 4: Verify both MCP configuration tests pass**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py::test_hr_graphrag_mcp_uses_byog_graphrag_dataset tests/test_hr_boss_agent_routing.py::test_text2cypher_mcp_is_enabled_for_hr_graph_queries -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
cd D:\study\deer-flow
git add extensions_config.json backend/tests/test_hr_boss_agent_routing.py
git commit -m "test: lock hr mcp routing configuration"
```

---

### Task 2: Expose Direct GraphRAG Mode Tools

**Files:**
- Modify: `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/formatter.py`
- Modify: `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/service.py`
- Modify: `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/server.py`
- Modify: `D:/study/my-mcp/graphrag-mcp/tests/test_server.py`
- Modify: `D:/study/my-mcp/graphrag-mcp/tests/test_service.py`

- [ ] **Step 1: Write the failing server registration test**

In `D:/study/my-mcp/graphrag-mcp/tests/test_server.py`, replace `test_build_server_registers_only_answer_question` with:

```python
def test_build_server_registers_answer_and_direct_query_tools(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeMCP:
        def __init__(self, name: str) -> None:
            self.name = name
            self.tools = {}

        def tool(self, name=None):
            def decorator(func):
                self.tools[name or func.__name__] = func
                return func
            return decorator

    class FakeService:
        def answer_question_sync(self, question: str):
            calls.append(("answer", question))
            return {"question": question}

        def query_basic_sync(self, question: str):
            calls.append(("basic", question))
            return {"strategy": "basic", "question": question}

        def query_local_sync(self, question: str):
            calls.append(("local", question))
            return {"strategy": "local", "question": question}

        def query_global_sync(self, question: str):
            calls.append(("global", question))
            return {"strategy": "global", "question": question}

        def query_drift_sync(self, question: str):
            calls.append(("drift", question))
            return {"strategy": "drift", "question": question}

    monkeypatch.setattr("graphrag_mcp.server.FastMCP", FakeMCP)
    monkeypatch.setattr("graphrag_mcp.server.build_service", lambda: FakeService())

    server = build_server()

    assert server.name == "hr-graphrag-qa"
    assert sorted(server.tools) == [
        "answer_question",
        "query_basic",
        "query_drift",
        "query_global",
        "query_local",
    ]
    assert server.tools["query_global"]("Summarize talent structure") == {
        "strategy": "global",
        "question": "Summarize talent structure",
    }
    assert calls == [("global", "Summarize talent structure")]
```

- [ ] **Step 2: Write the failing service direct strategy test**

Append this test to `D:/study/my-mcp/graphrag-mcp/tests/test_service.py`:

```python
@pytest.mark.asyncio
async def test_answer_with_strategy_runs_requested_basic_strategy(tmp_path: Path) -> None:
    GraphRAGQAService = _load_service_module().GraphRAGQAService
    settings = _build_settings(tmp_path)

    calls: list[str] = []

    async def fake_query_runner(**kwargs):
        calls.append(kwargs["query_type"])
        return {
            "response": "Matched employee evidence from text units.",
            "context_data": {
                "sources": [
                    {
                        "id": "tu-1",
                        "text": "employee_id=yuangong0001; current_position=运维工程师",
                    }
                ]
            },
            "context_counts": {"sources": 1},
        }

    service = GraphRAGQAService(settings=settings, entity_titles=set(), query_runner=fake_query_runner)
    result = await service.answer_with_strategy("老王1366的基础记录是什么？", "basic")

    assert calls == ["basic"]
    assert result["strategy"] == "basic"
    assert result["confidence"] == "medium"
```

- [ ] **Step 3: Run the new GraphRAG MCP tests to verify they fail**

Run:

```powershell
cd D:\study\my-mcp\graphrag-mcp
.\.venv\Scripts\python.exe -m pytest tests/test_server.py::test_build_server_registers_answer_and_direct_query_tools tests/test_service.py::test_answer_with_strategy_runs_requested_basic_strategy -v
```

Expected: FAIL because `query_basic`, `query_local`, `query_global`, `query_drift`, and `answer_with_strategy` do not exist yet.

- [ ] **Step 4: Allow `basic` in answer payload strategy**

In `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/formatter.py`, add a strategy alias and use it in `AnswerPayload` and `build_answer_payload`:

```python
GraphRAGStrategy = Literal["basic", "local", "global", "drift"]


class AnswerPayload(BaseModel):
    question: str
    answer: str
    evidence_summary: list[EvidenceItem] = Field(default_factory=list)
    evidence_status: Literal["sufficient", "partial", "insufficient", "conflicting"]
    confidence: Literal["high", "medium", "low"]
    strategy: GraphRAGStrategy
    notes: list[str] = Field(default_factory=list)
```

Update the `build_answer_payload` signature:

```python
def build_answer_payload(
    *,
    question: str,
    answer: str,
    strategy: GraphRAGStrategy,
    context_data: dict[str, Any],
    context_counts: dict[str, int],
) -> AnswerPayload:
```

- [ ] **Step 5: Add explicit strategy methods to the service**

In `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/service.py`, add the constant near `QueryRunner`:

```python
SUPPORTED_STRATEGIES = {"basic", "local", "global", "drift"}
```

Add these methods inside `GraphRAGQAService`:

```python
    async def answer_with_strategy(self, question: str, strategy: str) -> dict[str, Any]:
        normalized_strategy = strategy.strip().lower()
        if normalized_strategy not in SUPPORTED_STRATEGIES:
            raise ValueError(f"Unsupported GraphRAG strategy: {strategy}")
        return await self._run_once(question, normalized_strategy)

    def answer_with_strategy_sync(self, question: str, strategy: str) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "answer_with_strategy_sync() cannot be used from a running event loop; await answer_with_strategy() instead"
            )
        return asyncio.run(self.answer_with_strategy(question, strategy))

    def query_basic_sync(self, question: str) -> dict[str, Any]:
        return self.answer_with_strategy_sync(question, "basic")

    def query_local_sync(self, question: str) -> dict[str, Any]:
        return self.answer_with_strategy_sync(question, "local")

    def query_global_sync(self, question: str) -> dict[str, Any]:
        return self.answer_with_strategy_sync(question, "global")

    def query_drift_sync(self, question: str) -> dict[str, Any]:
        return self.answer_with_strategy_sync(question, "drift")
```

- [ ] **Step 6: Register direct GraphRAG tools in the MCP server**

In `D:/study/my-mcp/graphrag-mcp/src/graphrag_mcp/server.py`, update `build_server`:

```python
def build_server() -> FastMCP:
    service = build_service()
    mcp = FastMCP("hr-graphrag-qa")
    mcp.tool(name="answer_question")(service.answer_question_sync)
    mcp.tool(name="query_basic")(service.query_basic_sync)
    mcp.tool(name="query_local")(service.query_local_sync)
    mcp.tool(name="query_global")(service.query_global_sync)
    mcp.tool(name="query_drift")(service.query_drift_sync)
    return mcp
```

- [ ] **Step 7: Run the direct GraphRAG MCP tests**

Run:

```powershell
cd D:\study\my-mcp\graphrag-mcp
.\.venv\Scripts\python.exe -m pytest tests/test_server.py::test_build_server_registers_answer_and_direct_query_tools tests/test_service.py::test_answer_with_strategy_runs_requested_basic_strategy -v
```

Expected: 2 passed.

- [ ] **Step 8: Run the full GraphRAG MCP unit suite**

Run:

```powershell
cd D:\study\my-mcp\graphrag-mcp
.\.venv\Scripts\python.exe -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```powershell
cd D:\study\my-mcp\graphrag-mcp
git add src/graphrag_mcp/formatter.py src/graphrag_mcp/service.py src/graphrag_mcp/server.py tests/test_server.py tests/test_service.py
git commit -m "feat: expose direct graphrag query modes"
```

---

### Task 3: Upgrade The HR Boss Agent Routing Contract

**Files:**
- Modify: `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/config.yaml`
- Modify: `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/SOUL.md`
- Modify: `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`

- [ ] **Step 1: Add agent config and SOUL tests**

Append these tests to `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`:

```python
def test_hr_boss_agent_restricts_skills_and_mcp_servers() -> None:
    with patch("deerflow.config.agents_config.get_paths", return_value=Paths(base_dir=DEERFLOW_BASE_DIR)):
        cfg = load_agent_config("hr-boss-agent")

    assert cfg is not None
    assert cfg.name == "hr-boss-agent"
    assert cfg.tool_groups == []
    assert cfg.mcp_servers == ["hr-graphrag-qa", "text2cypher"]
    assert cfg.skills == ["hr-boss", "text2cypher", "graphrag"]


def test_hr_boss_agent_soul_contains_five_route_rules() -> None:
    with patch("deerflow.config.agents_config.get_paths", return_value=Paths(base_dir=DEERFLOW_BASE_DIR)):
        soul = load_agent_soul("hr-boss-agent")

    assert soul is not None
    assert "text2cypher_answer_question" in soul
    assert "hr-graphrag-qa_query_basic" in soul
    assert "hr-graphrag-qa_query_local" in soul
    assert "hr-graphrag-qa_query_global" in soul
    assert "hr-graphrag-qa_query_drift" in soul
    assert "平均、人数、名单、排名、占比、筛选" in soul
    assert "不要让 GraphRAG 覆盖 Text2Cypher 的精确查询结果" in soul
```

- [ ] **Step 2: Run the agent tests to verify current gaps**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py::test_hr_boss_agent_restricts_skills_and_mcp_servers tests/test_hr_boss_agent_routing.py::test_hr_boss_agent_soul_contains_five_route_rules -v
```

Expected before the agent is upgraded: FAIL because the config does not yet whitelist MCP servers and the SOUL does not yet name the five route tools.

- [ ] **Step 3: Update the HR boss agent config**

Replace `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/config.yaml` with:

```yaml
name: hr-boss-agent
description: 面向领导演示的 HR 智能问答代理，按问题意图路由到 GraphRAG 或 Text2Cypher
model: qwen3.5-plus
tool_groups: []
mcp_servers:
  - hr-graphrag-qa
  - text2cypher
skills:
  - hr-boss
  - text2cypher
  - graphrag
```

- [ ] **Step 4: Update the HR boss agent SOUL**

Replace `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/SOUL.md` with:

```markdown
你是 HR Boss Agent，面向领导演示 HR 智能问答能力。

你的职责是把领导的自然语言 HR 问题路由到正确的数据能力，并用简洁、可信、可追溯的中文回答。

你只能使用当前 agent 暴露的 HR 能力：
- `text2cypher_answer_question`
- `text2cypher_prepare_schema`
- `text2cypher_get_schema`
- `text2cypher_generate_cypher`
- `text2cypher_validate_cypher`
- `text2cypher_execute_cypher`
- `hr-graphrag-qa_query_basic`
- `hr-graphrag-qa_query_local`
- `hr-graphrag-qa_query_global`
- `hr-graphrag-qa_query_drift`
- `hr-graphrag-qa_answer_question`

路由规则：
- 遇到平均、人数、名单、排名、占比、筛选、多少、几个、有哪些人、前十、最高、最低、按条件查员工，使用 `text2cypher_answer_question`。
- 遇到具体员工、具体岗位、具体部门、具体项目、具体证书、具体职称、具体教育经历，使用 `hr-graphrag-qa_query_local`。
- 遇到组织画像、人才结构、群体特征、整体趋势、部门分布、风险概览，使用 `hr-graphrag-qa_query_global`。
- 遇到跨群体探索、原因推断、还有哪些线索、哪些群体可能存在问题，使用 `hr-graphrag-qa_query_drift`。
- 遇到简单证据片段、原始记录片段、某个字段是否出现，使用 `hr-graphrag-qa_query_basic`。
- 如果问题同时包含精确统计和组织分析，先用 `text2cypher_answer_question` 得到确定事实，再用 GraphRAG 对事实做解释。

权威性规则：
- Text2Cypher 的 Neo4j 查询结果优先用于人数、名单、排名、平均值、筛选结果。
- 不要让 GraphRAG 覆盖 Text2Cypher 的精确查询结果。
- GraphRAG 用于解释、画像、趋势、结构和证据补充。
- 当 Text2Cypher 结果与 GraphRAG 分析不一致时，最终回答必须说明差异，并以 Text2Cypher 的结构化结果作为事实口径。

回答格式：
1. 先给直接结论。
2. 再给关键依据。
3. 最后说明数据来源，取值只能是 `Neo4j 精确查询`、`GraphRAG 证据分析` 或 `Neo4j 精确查询 + GraphRAG 证据分析`。

风险控制：
- 不生成或执行写入型 Cypher。
- 不虚构员工、部门、职称、年龄、学历、项目或组织关系。
- 如果底层数据只有年龄段而没有精确年龄，不得直接声称得到精确平均年龄。
- 当证据不足时，明确说明限制，不用确定语气包装猜测。
```

- [ ] **Step 5: Run the HR boss agent routing tests**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py -v
```

Expected: all tests in `test_hr_boss_agent_routing.py` pass.

- [ ] **Step 6: Commit**

```powershell
cd D:\study\deer-flow
git add backend/.deer-flow/agents/hr-boss-agent/config.yaml backend/.deer-flow/agents/hr-boss-agent/SOUL.md backend/tests/test_hr_boss_agent_routing.py
git commit -m "feat: upgrade hr boss agent mcp routing"
```

---

### Task 4: Align HR Boss Skill Documentation

**Files:**
- Modify: `D:/study/deer-flow/skills/custom/hr-boss/SKILL.md`
- Modify: `D:/study/deer-flow/skills/custom/graphrag/SKILL.md`
- Test: `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`

- [ ] **Step 1: Add skill content tests**

Append these tests to `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`:

```python
def test_hr_boss_skill_documents_five_way_routing() -> None:
    content = (REPO_ROOT / "skills" / "custom" / "hr-boss" / "SKILL.md").read_text(encoding="utf-8")

    assert "Text2Cypher" in content
    assert "GraphRAG basic" in content
    assert "GraphRAG local" in content
    assert "GraphRAG global" in content
    assert "GraphRAG drift" in content
    assert "平均、人数、名单、排名、占比、筛选" in content


def test_graphrag_skill_documents_direct_mode_tools() -> None:
    content = (REPO_ROOT / "skills" / "custom" / "graphrag" / "SKILL.md").read_text(encoding="utf-8")

    assert "hr-graphrag-qa_query_basic" in content
    assert "hr-graphrag-qa_query_local" in content
    assert "hr-graphrag-qa_query_global" in content
    assert "hr-graphrag-qa_query_drift" in content
```

- [ ] **Step 2: Run the skill tests to verify current gaps**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py::test_hr_boss_skill_documents_five_way_routing tests/test_hr_boss_agent_routing.py::test_graphrag_skill_documents_direct_mode_tools -v
```

Expected before skill docs are aligned: FAIL.

- [ ] **Step 3: Replace the HR boss skill content**

Replace `D:/study/deer-flow/skills/custom/hr-boss/SKILL.md` with:

```markdown
---
name: hr-boss
description: 面向领导的 HR 问答需要在 Text2Cypher 和 GraphRAG basic/local/global/drift 之间按准确性优先路由时，使用此技能。
---

# HR Boss 编排技能

## 适用场景

当用户提出面向领导的 HR 数据问题，并且需要把问题路由到精确查询或图谱分析时，使用此技能。

## 路由规则

- 平均、人数、名单、排名、占比、筛选、多少、几个、有哪些人、前十、最高、最低、按条件查员工：使用 Text2Cypher。
- 具体员工、具体岗位、具体部门、具体项目、具体证书、具体职称、具体教育经历：使用 GraphRAG local。
- 组织画像、人才结构、群体特征、整体趋势、部门分布、风险概览：使用 GraphRAG global。
- 跨群体探索、原因推断、还有哪些线索、哪些群体可能存在问题：使用 GraphRAG drift。
- 简单证据片段、原始记录片段、某个字段是否出现：使用 GraphRAG basic。

## 工具映射

- Text2Cypher：`text2cypher_answer_question`
- GraphRAG basic：`hr-graphrag-qa_query_basic`
- GraphRAG local：`hr-graphrag-qa_query_local`
- GraphRAG global：`hr-graphrag-qa_query_global`
- GraphRAG drift：`hr-graphrag-qa_query_drift`

## 权威性规则

- Text2Cypher 对人数、名单、排名、平均值、筛选结果具有最高权威性。
- GraphRAG 对解释、画像、趋势、组织结构和证据补充具有最高权威性。
- 不得让 GraphRAG 覆盖 Text2Cypher 的精确查询结果。
- 如果两个路径结果不一致，说明差异，并以结构化查询结果作为事实口径。

## 输出要求

最终回答必须包含：
- 直接结论
- 关键依据
- 数据来源
- 必要的数据口径限制

## 硬性约束

- 不执行写入型 Cypher。
- 不虚构员工、部门、职称、年龄、学历、项目或组织关系。
- 当证据不足时，明确说明限制。
```

- [ ] **Step 4: Replace the GraphRAG skill content**

Replace `D:/study/deer-flow/skills/custom/graphrag/SKILL.md` with:

```markdown
---
name: graphrag
description: 围绕固定 HR GraphRAG 数据集回答自然语言问题，并按 basic/local/global/drift 选择合适查询模式时，使用此技能。
---

# GraphRAG 问答技能

## 查询模式

- `hr-graphrag-qa_query_basic`：适合简单证据片段检索。
- `hr-graphrag-qa_query_local`：适合具体员工、岗位、部门、项目、教育、证书、职称等局部事实。
- `hr-graphrag-qa_query_global`：适合组织画像、人才结构、群体趋势、整体风险和部门分布。
- `hr-graphrag-qa_query_drift`：适合先看群体再下钻的探索型问题。

## 不适合场景

GraphRAG 不负责精确人数、完整名单、平均值、排名、占比和严格筛选。这些问题交给 Text2Cypher。

## 输出要求

回答必须包含：
- 自然语言答案
- 简短证据说明
- `evidence_status` 或等价证据充足性说明
- `confidence` 或等价可信度说明

## 硬性约束

- 不隐藏证据不足。
- 不用 GraphRAG 结果覆盖 Neo4j 精确查询结果。
- 不输出原始 GraphRAG JSON，除非用户明确要求调试信息。
```

- [ ] **Step 5: Run skill documentation tests**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py::test_hr_boss_skill_documents_five_way_routing tests/test_hr_boss_agent_routing.py::test_graphrag_skill_documents_direct_mode_tools -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```powershell
cd D:\study\deer-flow
git add skills/custom/hr-boss/SKILL.md skills/custom/graphrag/SKILL.md backend/tests/test_hr_boss_agent_routing.py
git commit -m "docs: align hr boss routing skills"
```

---

### Task 5: Configure WeCom To Use HR Boss Agent

**Files:**
- Modify: `D:/study/deer-flow/config.yaml`
- Test: `D:/study/deer-flow/backend/tests/test_hr_boss_wecom_session.py`

- [ ] **Step 1: Write the WeCom session resolution test**

Create `D:/study/deer-flow/backend/tests/test_hr_boss_wecom_session.py` with:

```python
from app.channels.manager import ChannelManager
from app.channels.message_bus import InboundMessage, InboundMessageType, MessageBus
from app.channels.store import ChannelStore


def test_wecom_session_routes_custom_agent_through_lead_agent() -> None:
    manager = ChannelManager(
        bus=MessageBus(),
        store=ChannelStore(),
        default_session={
            "assistant_id": "hr-boss-agent",
            "config": {"recursion_limit": 100},
            "context": {
                "thinking_enabled": True,
                "is_plan_mode": False,
                "subagent_enabled": False,
            },
        },
    )
    inbound = InboundMessage(
        channel_name="wecom",
        chat_id="leader-chat",
        user_id="leader-user",
        text="福建火炬电子科技股份有限公司的高级工程师有哪些？",
        msg_type=InboundMessageType.CHAT,
    )

    assistant_id, run_config, run_context = manager._resolve_run_params(inbound, "thread-1")

    assert assistant_id == "lead_agent"
    assert run_config["recursion_limit"] == 100
    assert run_context["agent_name"] == "hr-boss-agent"
    assert run_context["thinking_enabled"] is True
    assert run_context["is_plan_mode"] is False
    assert run_context["subagent_enabled"] is False
```

- [ ] **Step 2: Run the WeCom session test**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_wecom_session.py -v
```

Expected: PASS. This verifies how DeerFlow maps `assistant_id: hr-boss-agent` to `lead_agent` plus `context.agent_name`.

- [ ] **Step 3: Configure WeCom session**

In `D:/study/deer-flow/config.yaml`, set the channel block to:

```yaml
channels:
  langgraph_url: http://localhost:2024
  gateway_url: http://localhost:8001

  session:
    assistant_id: hr-boss-agent
    config:
      recursion_limit: 100
    context:
      thinking_enabled: true
      is_plan_mode: false
      subagent_enabled: false

  wecom:
    enabled: true
    bot_id: $WECOM_BOT_ID
    bot_secret: $WECOM_BOT_SECRET
    working_message: 正在查询 HR 数据，请稍候...
```

Set these values in `D:/study/deer-flow/.env`:

```dotenv
WECOM_BOT_ID=your_wecom_bot_id
WECOM_BOT_SECRET=your_wecom_bot_secret
```

- [ ] **Step 4: Verify channel config still parses**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run python -c "from deerflow.config.app_config import get_app_config; cfg=get_app_config(); print(bool((cfg.model_extra or {}).get('channels', {}).get('wecom', {}).get('enabled')))"
```

Expected output:

```text
True
```

- [ ] **Step 5: Commit**

```powershell
cd D:\study\deer-flow
git add config.yaml backend/tests/test_hr_boss_wecom_session.py
git commit -m "feat: route wecom channel to hr boss agent"
```

---

### Task 6: Add Leadership Demo Script

**Files:**
- Create: `D:/study/deer-flow/docs/hr-agent-wecom-demo-script.md`
- Test: `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`

- [ ] **Step 1: Add demo document test**

Append this test to `D:/study/deer-flow/backend/tests/test_hr_boss_agent_routing.py`:

```python
def test_hr_demo_script_covers_all_routes() -> None:
    content = (REPO_ROOT / "docs" / "hr-agent-wecom-demo-script.md").read_text(encoding="utf-8")

    assert "Text2Cypher" in content
    assert "GraphRAG basic" in content
    assert "GraphRAG local" in content
    assert "GraphRAG global" in content
    assert "GraphRAG drift" in content
    assert "福建火炬电子科技股份有限公司平均年龄是多少？" in content
    assert "福建火炬电子科技股份有限公司的高级工程师有哪些？" in content
```

- [ ] **Step 2: Run the demo document test to verify the file is missing**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py::test_hr_demo_script_covers_all_routes -v
```

Expected before the demo script exists: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Create the demo script**

Create `D:/study/deer-flow/docs/hr-agent-wecom-demo-script.md`:

```markdown
# HR Agent WeCom Demo Script

## Demo Goal

Show that the HR agent can answer leadership questions through WeCom and choose the correct data path automatically.

## Demo Questions

| Order | Question | Expected Route | Expected Answer Style |
| --- | --- | --- | --- |
| 1 | 福建火炬电子科技股份有限公司平均年龄是多少？ | Text2Cypher | Explain exact-query result or state that only age bands are available. |
| 2 | 福建火炬电子科技股份有限公司的高级工程师有哪些？ | Text2Cypher | Return count, names, and query source. |
| 3 | 福建火炬电子各部门员工数排名前十是什么？ | Text2Cypher | Return ranked table-style answer. |
| 4 | 福建火炬电子本科及以上学历员工主要分布在哪些部门？ | Text2Cypher | Return department distribution. |
| 5 | 老王1366的教育和项目经历是什么？ | GraphRAG local | Return employee-centered evidence. |
| 6 | 老王10当前在哪个组织、部门和岗位？ | GraphRAG local | Return direct employee profile. |
| 7 | 福建火炬电子科技股份有限公司的人才结构有什么特点？ | GraphRAG global | Return organization-level talent portrait. |
| 8 | 福建火炬电子有哪些典型人才群体？ | GraphRAG global | Return group categories and evidence. |
| 9 | 制造车间哪些群体可能存在经验断层？ | GraphRAG drift | Return exploratory analysis with evidence limits. |
| 10 | 品质保证部和 MLCC 制造车间的人才结构有什么差异？ | GraphRAG drift | Compare groups and mention uncertainty. |
| 11 | 查询老王1366的基础记录片段。 | GraphRAG basic | Return concise source evidence. |

## Speaking Points

- GraphRAG handles portrait, structure, trend, and evidence analysis.
- Text2Cypher handles exact database questions such as counts, lists, rankings, filters, and averages.
- The WeCom bot is only the entrypoint; routing and answering happen inside DeerFlow.
- For leadership demos, the final answer must include the data source and any limitation.
```

- [ ] **Step 4: Run the demo document test**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py::test_hr_demo_script_covers_all_routes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
cd D:\study\deer-flow
git add docs/hr-agent-wecom-demo-script.md backend/tests/test_hr_boss_agent_routing.py
git commit -m "docs: add hr agent wecom demo script"
```

---

### Task 7: End-To-End Local Verification

**Files:**
- Read: `D:/study/deer-flow/extensions_config.json`
- Read: `D:/study/deer-flow/config.yaml`
- Read: `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/config.yaml`
- Read: `D:/study/deer-flow/backend/.deer-flow/agents/hr-boss-agent/SOUL.md`

- [ ] **Step 1: Run DeerFlow backend tests for the HR integration**

Run:

```powershell
cd D:\study\deer-flow\backend
uv run pytest tests/test_hr_boss_agent_routing.py tests/test_hr_boss_wecom_session.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run GraphRAG MCP tests**

Run:

```powershell
cd D:\study\my-mcp\graphrag-mcp
.\.venv\Scripts\python.exe -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Start LangGraph server**

Run in terminal 1:

```powershell
cd D:\study\deer-flow\backend
uv run langgraph dev --no-browser --no-reload --n-jobs-per-worker 10
```

Expected: LangGraph server listens on `http://localhost:2024`.

- [ ] **Step 4: Start Gateway API**

Run in terminal 2:

```powershell
cd D:\study\deer-flow\backend
$env:PYTHONPATH="."
uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001
```

Expected: Gateway API listens on `http://localhost:8001`.

- [ ] **Step 5: Verify MCP tools are visible through the agent**

Send this question to `hr-boss-agent` in the DeerFlow UI:

```text
福建火炬电子科技股份有限公司的高级工程师有哪些？
```

Expected route: `text2cypher_answer_question`.

Expected answer characteristics:
- It includes a direct result or a clear data limitation.
- It mentions `Neo4j 精确查询` as the data source.
- It does not claim GraphRAG as the source for the exact list.

- [ ] **Step 6: Verify GraphRAG global route**

Send this question to `hr-boss-agent`:

```text
福建火炬电子科技股份有限公司的人才结构有什么特点？
```

Expected route: `hr-graphrag-qa_query_global`.

Expected answer characteristics:
- It summarizes organization-level talent structure.
- It mentions `GraphRAG 证据分析` as the data source.
- It includes evidence sufficiency or confidence wording.

- [ ] **Step 7: Start WeCom channel**

After `config.yaml` and `.env` contain the WeCom settings, restart the Gateway process so `ChannelService` loads the new channel configuration.

Expected log characteristics:
- `WeCom channel started`
- `ChannelService started`

- [ ] **Step 8: Verify WeCom demo question**

Ask in WeCom:

```text
福建火炬电子科技股份有限公司平均年龄是多少？
```

Expected:
- The bot replies through the same WeCom conversation.
- The answer uses Text2Cypher for exact-query handling.
- If exact age is unavailable and only age bands exist, the bot states the limitation.

- [ ] **Step 9: Commit verification-only documentation changes if any were made**

```powershell
cd D:\study\deer-flow
git status --short
```

If only demo or documentation files changed during verification:

```powershell
git add docs/hr-agent-wecom-demo-script.md
git commit -m "docs: refine hr agent demo verification notes"
```

---

## Operational Notes

### Why GraphRAG MCP Needs Direct Mode Tools

The current `hr-graphrag-qa` MCP has a single `answer_question` tool. That service internally decides between `local/global/drift`, and it does not expose `basic` through a dedicated leadership-facing tool. If the target product requirement is an explicit front routing layer with five choices, the agent needs direct tools:

- `hr-graphrag-qa_query_basic`
- `hr-graphrag-qa_query_local`
- `hr-graphrag-qa_query_global`
- `hr-graphrag-qa_query_drift`
- `text2cypher_answer_question`

Without these direct tools, DeerFlow can route only between "GraphRAG as a whole" and "Text2Cypher as a whole".

### Data Source Rule

`D:/study/deer-flow/scripts/run_graphrag_mcp.py` starts the GraphRAG MCP code from `GRAPHRAG_MCP_REPO`; it does not choose the data directory by itself. The data directory is controlled by `GRAPHRAG_DATA_ROOT` in `D:/study/deer-flow/extensions_config.json`.

For this HR BYOG GraphRAG test, use:

```text
D:/study/my-mcp/graphrag-data/byog_graphrag
```

### Leadership Demo Rule

Do not lead the demo with implementation details. Lead with:

```text
领导正常用企业微信提问。系统先判断这个问题是查台账还是看画像。
查台账走 Neo4j 精确查询，保证人数、名单、排名、平均值有数据库口径。
看画像走 GraphRAG，适合总结人才结构、群体特点和风险趋势。
```

### Release Gate

Before showing the WeCom demo:

- `text2cypher` MCP starts successfully.
- `hr-graphrag-qa` MCP starts successfully.
- `hr-boss-agent` can answer one Text2Cypher question.
- `hr-boss-agent` can answer one GraphRAG global question.
- WeCom channel receives and returns a message.
- Demo script questions have been rehearsed once through the same channel used for leadership.
