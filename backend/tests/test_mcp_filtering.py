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
