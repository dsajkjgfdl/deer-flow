from types import SimpleNamespace

import pytest


class FakePlatformRepo:
    def __init__(self, assigned: set[str] | None = None):
        self.assigned = assigned or set()

    async def user_has_agent(self, _user_id: str, agent_name: str) -> bool:
        return agent_name in self.assigned


def _user(role: str = "user"):
    from app.gateway.auth.models import User

    return User(email=f"{role}@example.com", system_role=role)


def _catalog_entry(name: str = "hr-boss-agent"):
    from deerflow.agents.catalog import AgentCatalogEntry

    return AgentCatalogEntry(
        name=name,
        display_name="HR Boss Agent",
        description="HR demo",
        model="qwen3.5-plus",
        tool_groups=["file:read"],
        skills=["hr-boss"],
        mcp_servers=["hr-graphrag-qa", "text2cypher", "disabled-mcp"],
        allowed_tools=["ask_clarification", "text2cypher_answer_question"],
        config_path="/tmp/config.yaml",
        config_hash="config-hash",
        soul_hash="soul-hash",
        status="valid",
    )


@pytest.mark.anyio
async def test_admin_can_resolve_any_valid_agent(monkeypatch):
    import deerflow.agents.runtime_resolver as resolver
    from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig

    monkeypatch.setattr(resolver, "scan_agent_catalog", lambda **_: [_catalog_entry()])
    monkeypatch.setattr(
        resolver.ExtensionsConfig,
        "from_file",
        lambda: ExtensionsConfig(
            mcpServers={
                "hr-graphrag-qa": McpServerConfig(enabled=True, command="qa"),
                "text2cypher": McpServerConfig(enabled=True, command="t2c"),
                "disabled-mcp": McpServerConfig(enabled=False, command="disabled"),
            }
        ),
    )

    effective = await resolver.resolve_effective_agent_runtime(
        user=_user("admin"),
        requested_agent_name="hr-boss-agent",
        platform_repo=FakePlatformRepo(),
        app_config=SimpleNamespace(),
    )

    assert effective.agent_name == "hr-boss-agent"
    assert effective.effective_skills == ["hr-boss"]
    assert effective.effective_mcp_servers == ["hr-graphrag-qa", "text2cypher"]
    assert effective.effective_allowed_tools == ["ask_clarification", "text2cypher_answer_question"]
    assert effective.config_hash == "config-hash"
    assert effective.soul_hash == "soul-hash"


@pytest.mark.anyio
async def test_internal_user_can_resolve_any_valid_agent(monkeypatch):
    import deerflow.agents.runtime_resolver as resolver
    from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig

    monkeypatch.setattr(resolver, "scan_agent_catalog", lambda **_: [_catalog_entry()])
    monkeypatch.setattr(
        resolver.ExtensionsConfig,
        "from_file",
        lambda: ExtensionsConfig(mcpServers={"text2cypher": McpServerConfig(enabled=True, command="t2c")}),
    )

    effective = await resolver.resolve_effective_agent_runtime(
        user=SimpleNamespace(id="default", system_role="internal"),
        requested_agent_name="hr-boss-agent",
        platform_repo=FakePlatformRepo(),
        app_config=SimpleNamespace(),
    )

    assert effective.agent_name == "hr-boss-agent"
    assert effective.user_id == "default"
    assert effective.effective_mcp_servers == ["text2cypher"]


@pytest.mark.anyio
async def test_normal_user_can_resolve_assigned_agent(monkeypatch):
    import deerflow.agents.runtime_resolver as resolver
    from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig

    monkeypatch.setattr(resolver, "scan_agent_catalog", lambda **_: [_catalog_entry()])
    monkeypatch.setattr(
        resolver.ExtensionsConfig,
        "from_file",
        lambda: ExtensionsConfig(mcpServers={"text2cypher": McpServerConfig(enabled=True, command="t2c")}),
    )

    effective = await resolver.resolve_effective_agent_runtime(
        user=_user("user"),
        requested_agent_name="hr-boss-agent",
        platform_repo=FakePlatformRepo({"hr-boss-agent"}),
        app_config=SimpleNamespace(),
    )

    assert effective.agent_name == "hr-boss-agent"
    assert effective.effective_mcp_servers == ["text2cypher"]


@pytest.mark.anyio
async def test_normal_user_cannot_resolve_unassigned_agent(monkeypatch):
    import deerflow.agents.runtime_resolver as resolver

    monkeypatch.setattr(resolver, "scan_agent_catalog", lambda **_: [_catalog_entry()])

    with pytest.raises(PermissionError):
        await resolver.resolve_effective_agent_runtime(
            user=_user("user"),
            requested_agent_name="hr-boss-agent",
            platform_repo=FakePlatformRepo(),
            app_config=SimpleNamespace(),
        )


@pytest.mark.anyio
async def test_normal_user_without_requested_agent_uses_default_runtime(monkeypatch):
    import deerflow.agents.runtime_resolver as resolver

    monkeypatch.setattr(resolver, "scan_agent_catalog", lambda **_: [_catalog_entry()])

    effective = await resolver.resolve_effective_agent_runtime(
        user=_user("user"),
        requested_agent_name=None,
        platform_repo=FakePlatformRepo(),
        app_config=SimpleNamespace(platform=resolver.PlatformConfig(base_agent_name=None)),
    )

    assert effective.agent_name is None
    assert effective.effective_skills is None
    assert effective.effective_mcp_servers == []
    assert effective.trace_metadata["agent_name"] == "default"
