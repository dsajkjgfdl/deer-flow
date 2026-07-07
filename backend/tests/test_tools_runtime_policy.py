from __future__ import annotations

from types import SimpleNamespace


class _NamedTool:
    def __init__(self, name: str) -> None:
        self.name = name


def test_get_available_tools_filters_mcp_servers_and_allowed_tools(monkeypatch):
    from deerflow.tools import tools as tools_module

    monkeypatch.setattr(
        tools_module,
        "resolve_variable",
        lambda use, expected_type: _NamedTool(use),
    )

    class _ExtensionsConfig:
        def get_enabled_mcp_servers(self):
            return {"text2cypher", "other-mcp"}

    monkeypatch.setattr(
        "deerflow.config.extensions_config.ExtensionsConfig.from_file",
        lambda: _ExtensionsConfig(),
    )
    monkeypatch.setattr(
        "deerflow.mcp.cache.get_cached_mcp_tools",
        lambda: [
            _NamedTool("text2cypher_answer_question"),
            _NamedTool("other-mcp_query"),
        ],
    )

    app_config = SimpleNamespace(
        tools=[],
        models=[],
        tool_search=SimpleNamespace(enabled=False),
        skill_evolution=SimpleNamespace(enabled=False),
        sandbox=SimpleNamespace(use="deerflow.sandbox.remote:RemoteSandboxProvider"),
        acp_agents={},
        get_model_config=lambda name: None,
    )

    tools = tools_module.get_available_tools(
        mcp_servers=["text2cypher"],
        allowed_tools=["text2cypher_answer_question"],
        app_config=app_config,
    )

    assert [tool.name for tool in tools] == ["text2cypher_answer_question"]
