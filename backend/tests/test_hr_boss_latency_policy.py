from __future__ import annotations

from types import SimpleNamespace


def test_hr_boss_recommendation_fast_path_removes_slow_graphrag_tools():
    from deerflow.agents.lead_agent.agent import _filter_hr_boss_recommendation_tools

    tools = [
        SimpleNamespace(name="ask_clarification"),
        SimpleNamespace(name="text2cypher_answer_question"),
        SimpleNamespace(name="hr-graphrag-qa_query_basic"),
        SimpleNamespace(name="hr-graphrag-qa_query_local"),
        SimpleNamespace(name="hr-graphrag-qa_query_global"),
        SimpleNamespace(name="hr-graphrag-qa_query_drift"),
    ]

    filtered = _filter_hr_boss_recommendation_tools(
        tools,
        agent_name="hr-boss-agent",
        runtime_config={"hr_boss_recommendation_fast_path": True},
    )

    assert [tool.name for tool in filtered] == [
        "ask_clarification",
        "text2cypher_answer_question",
    ]


def test_hr_boss_recommendation_filter_preserves_other_agents():
    from deerflow.agents.lead_agent.agent import _filter_hr_boss_recommendation_tools

    tools = [
        SimpleNamespace(name="text2cypher_answer_question"),
        SimpleNamespace(name="hr-graphrag-qa_query_drift"),
    ]

    filtered = _filter_hr_boss_recommendation_tools(
        tools,
        agent_name="finance-agent",
        runtime_config={"hr_boss_recommendation_fast_path": True},
    )

    assert filtered == tools


def test_hr_boss_recommendation_fast_path_skips_title_middleware():
    from deerflow.agents.lead_agent.agent import _build_middlewares
    from deerflow.agents.middlewares.title_middleware import TitleMiddleware

    middlewares = _build_middlewares(
        {
            "configurable": {
                "agent_name": "hr-boss-agent",
                "hr_boss_recommendation_fast_path": True,
            }
        },
        model_name=None,
        agent_name="hr-boss-agent",
    )

    assert not any(isinstance(middleware, TitleMiddleware) for middleware in middlewares)


def test_title_middleware_still_runs_for_regular_hr_boss_queries():
    from deerflow.agents.lead_agent.agent import _build_middlewares
    from deerflow.agents.middlewares.title_middleware import TitleMiddleware

    middlewares = _build_middlewares(
        {"configurable": {"agent_name": "hr-boss-agent"}},
        model_name=None,
        agent_name="hr-boss-agent",
    )

    assert any(isinstance(middleware, TitleMiddleware) for middleware in middlewares)


def test_hr_boss_recommendation_fast_path_limits_model_output_tokens():
    from deerflow.agents.lead_agent.agent import _model_kwargs_for_runtime

    kwargs = _model_kwargs_for_runtime(
        agent_name="hr-boss-agent",
        runtime_config={"hr_boss_recommendation_fast_path": True},
        reasoning_effort=None,
    )

    assert kwargs["max_tokens"] == 700


def test_regular_hr_boss_queries_do_not_limit_model_output_tokens():
    from deerflow.agents.lead_agent.agent import _model_kwargs_for_runtime

    kwargs = _model_kwargs_for_runtime(
        agent_name="hr-boss-agent",
        runtime_config={},
        reasoning_effort=None,
    )

    assert "max_tokens" not in kwargs


def test_hr_boss_recommendation_formatter_returns_concise_leader_answer():
    from deerflow.agents.lead_agent.agent import _format_hr_boss_recommendation_answer

    answer = _format_hr_boss_recommendation_answer(
        {
            "status": "success",
            "answerable": True,
            "execution": {
                "records": [
                    {
                        "employee_id": "HJ1168",
                        "employee_name": "yuangong02771",
                        "current_position": "研发工程师",
                        "current_department": "瓷粉研发组",
                        "current_org": "福建火炬电子科技股份有限公司（本部）",
                        "tenure_years": 3.9,
                        "degrees": ["硕士"],
                        "schools": ["福州大学"],
                        "majors": ["分析化学"],
                        "title_names": ["初级职称"],
                        "related_project_experiences": ["X7R-402贵金属瓷介电容器用陶瓷介质粉料 as  ()"],
                    },
                    {
                        "employee_id": "HJ0163",
                        "employee_name": "yuangong01803",
                        "current_position": "研发工程师",
                        "current_department": "瓷粉研发组",
                        "tenure_years": 15.24,
                        "degrees": ["本科"],
                        "schools": ["泉州师范学院"],
                        "majors": ["材料化学"],
                        "title_names": ["工程师"],
                        "related_project_experiences": ["中试线组建 as 项目协调 ()"],
                    },
                ]
            },
        }
    )

    assert "首推：yuangong02771（HJ1168）" in answer
    assert "备选：yuangong01803（HJ0163）" in answer
    assert "Markdown 表格" not in answer
    assert len(answer) < 500


def test_hr_boss_recommendation_direct_tool_wraps_text2cypher_tool():
    from types import SimpleNamespace

    from langchain_core.messages import ToolMessage
    from langchain_core.tools import StructuredTool

    from deerflow.agents.lead_agent.agent import _wrap_hr_boss_recommendation_direct_tool

    def original_tool(question: str, max_rows: int = 100):
        return {
            "status": "success",
            "answerable": True,
            "execution": {
                "records": [
                    {
                        "employee_id": "HJ1168",
                        "employee_name": "yuangong02771",
                        "current_position": "研发工程师",
                        "current_department": "瓷粉研发组",
                    }
                ]
            },
        }

    tool = StructuredTool.from_function(
        original_tool,
        name="text2cypher_answer_question",
        description="answer HR questions",
    )

    wrapped = _wrap_hr_boss_recommendation_direct_tool(tool)

    assert wrapped.name == "text2cypher_answer_question"
    assert wrapped.return_direct is True
    message = wrapped.invoke(
        {
            "question": "q",
            "runtime": SimpleNamespace(tool_call_id="call-1"),
        }
    )

    assert isinstance(message, ToolMessage)
    assert message.tool_call_id == "call-1"
    assert message.additional_kwargs["display_as_assistant"] is True
    assert "首推：yuangong02771（HJ1168）" in message.content
