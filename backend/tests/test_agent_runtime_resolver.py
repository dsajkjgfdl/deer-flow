from __future__ import annotations

from types import SimpleNamespace

import pytest

from deerflow.agents.catalog import AgentCatalogEntry


def _entry(
    name: str,
    *,
    status: str = "valid",
    mcp_servers: list[str] | None = None,
    skills: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> AgentCatalogEntry:
    return AgentCatalogEntry(
        name=name,
        display_name=f"{name} display",
        description=f"{name} agent",
        mcp_servers=mcp_servers,
        skills=skills,
        allowed_tools=allowed_tools,
        config_path=f"/tmp/{name}/config.yaml",
        config_hash=f"{name}-config",
        soul_hash=f"{name}-soul",
        status=status,
    )


class _PlatformRepo:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str]] = []

    async def user_has_agent(self, user_id: str, agent_name: str) -> bool:
        self.calls.append((user_id, agent_name))
        return self.allowed


@pytest.mark.asyncio
async def test_runtime_resolver_allows_assigned_user_and_filters_enabled_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.agents import runtime_resolver

    monkeypatch.setattr(
        runtime_resolver,
        "scan_agent_catalog",
        lambda *, app_config=None, user_id=None: [
            _entry(
                "hr-boss-agent",
                mcp_servers=["text2cypher", "disabled-mcp"],
                skills=["hr-boss"],
                allowed_tools=["text2cypher_answer_question"],
            )
        ],
    )
    monkeypatch.setattr(
        runtime_resolver,
        "_enabled_mcp_server_names",
        lambda: {"text2cypher"},
    )
    repo = _PlatformRepo(allowed=True)

    runtime = await runtime_resolver.resolve_effective_agent_runtime(
        user=SimpleNamespace(id="u-1", system_role="user"),
        requested_agent_name="hr-boss-agent",
        platform_repo=repo,
        app_config=SimpleNamespace(platform={}),
    )

    assert repo.calls == [("u-1", "hr-boss-agent")]
    assert runtime.agent_name == "hr-boss-agent"
    assert runtime.effective_mcp_servers == ["text2cypher"]
    assert runtime.effective_skills == ["hr-boss"]
    assert runtime.effective_allowed_tools == ["text2cypher_answer_question"]
    assert runtime.trace_metadata["agent_name"] == "hr-boss-agent"
    assert runtime.trace_metadata["effective_mcp_servers"] == ["text2cypher"]


@pytest.mark.asyncio
async def test_runtime_resolver_rejects_unassigned_normal_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.agents import runtime_resolver

    monkeypatch.setattr(
        runtime_resolver,
        "scan_agent_catalog",
        lambda *, app_config=None, user_id=None: [_entry("hr-boss-agent")],
    )
    repo = _PlatformRepo(allowed=False)

    with pytest.raises(PermissionError, match="not assigned"):
        await runtime_resolver.resolve_effective_agent_runtime(
            user=SimpleNamespace(id="u-1", system_role="user"),
            requested_agent_name="hr-boss-agent",
            platform_repo=repo,
            app_config=SimpleNamespace(platform={}),
        )


@pytest.mark.asyncio
async def test_runtime_resolver_allows_admin_without_assignment_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.agents import runtime_resolver

    monkeypatch.setattr(
        runtime_resolver,
        "scan_agent_catalog",
        lambda *, app_config=None, user_id=None: [_entry("hr-boss-agent")],
    )

    runtime = await runtime_resolver.resolve_effective_agent_runtime(
        user=SimpleNamespace(id="admin-1", system_role="admin"),
        requested_agent_name="hr-boss-agent",
        platform_repo=None,
        app_config=SimpleNamespace(platform={}),
    )

    assert runtime.agent_name == "hr-boss-agent"
