from types import SimpleNamespace


def test_filter_mcp_tools_by_server_names_keeps_only_allowed_prefixes():
    from deerflow.tools.tools import filter_mcp_tools_by_server_names

    tools = [
        SimpleNamespace(name="hr-graphrag-qa_query_basic"),
        SimpleNamespace(name="text2cypher_answer_question"),
        SimpleNamespace(name="browser_open"),
    ]

    filtered = filter_mcp_tools_by_server_names(tools, ["hr-graphrag-qa", "text2cypher"])

    assert [tool.name for tool in filtered] == [
        "hr-graphrag-qa_query_basic",
        "text2cypher_answer_question",
    ]


def test_filter_mcp_tools_by_server_names_allows_all_when_none():
    from deerflow.tools.tools import filter_mcp_tools_by_server_names

    tools = [
        SimpleNamespace(name="hr-graphrag-qa_query_basic"),
        SimpleNamespace(name="browser_open"),
    ]

    assert filter_mcp_tools_by_server_names(tools, None) == tools


def test_get_available_tools_filters_allowed_tools_before_deferred_registration(monkeypatch):
    from deerflow.config.tool_search_config import ToolSearchConfig
    from deerflow.tools.builtins.tool_search import get_deferred_registry, reset_deferred_registry
    from deerflow.tools.tools import get_available_tools

    reset_deferred_registry()

    mcp_tools = [
        SimpleNamespace(name="text2cypher_answer_question", description="Answer HR questions"),
        SimpleNamespace(name="text2cypher_execute_cypher", description="Execute raw Cypher"),
        SimpleNamespace(name="hr-graphrag-qa_query_basic", description="Find evidence"),
    ]
    app_config = SimpleNamespace(
        tools=[],
        models=[],
        tool_search=ToolSearchConfig(enabled=True),
        skill_evolution=SimpleNamespace(enabled=False),
        acp_agents={},
    )

    monkeypatch.setattr(
        "deerflow.config.extensions_config.ExtensionsConfig.from_file",
        classmethod(
            lambda cls: SimpleNamespace(
                get_enabled_mcp_servers=lambda: {"text2cypher": object(), "hr-graphrag-qa": object()}
            )
        ),
    )
    monkeypatch.setattr("deerflow.mcp.cache.get_cached_mcp_tools", lambda: mcp_tools)

    tools = get_available_tools(
        app_config=app_config,
        mcp_servers=["text2cypher", "hr-graphrag-qa"],
        allowed_tools=["ask_clarification", "text2cypher_answer_question"],
    )

    tool_names = [tool.name for tool in tools]
    assert "text2cypher_answer_question" in tool_names
    assert "text2cypher_execute_cypher" not in tool_names
    assert "tool_search" not in tool_names

    registry = get_deferred_registry()
    assert registry is None

    reset_deferred_registry()
