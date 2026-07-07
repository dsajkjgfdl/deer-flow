from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.gateway.routers import platform_agents
from deerflow.agents.catalog import AgentCatalogEntry


def _entry(name: str, *, status: str = "valid") -> AgentCatalogEntry:
    return AgentCatalogEntry(
        name=name,
        description=f"{name} agent",
        config_path=f"/tmp/{name}/config.yaml",
        config_hash=f"{name}-hash",
        status=status,
    )


def _request(*, user_id: str = "user-1", system_role: str = "user", repo=None) -> SimpleNamespace:
    return SimpleNamespace(
        _deerflow_test_bypass_auth=True,
        state=SimpleNamespace(user=SimpleNamespace(id=user_id, system_role=system_role)),
        app=SimpleNamespace(state=SimpleNamespace(platform_repo=repo) if repo is not None else SimpleNamespace()),
    )


class _Repo:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.seen_user_id: str | None = None

    async def list_user_agents(self, user_id: str) -> list[str]:
        self.seen_user_id = user_id
        return self.names


def test_platform_agents_router_metadata() -> None:
    assert platform_agents.router.prefix == "/api/platform/agents"
    assert "platform-agents" in platform_agents.router.tags


@pytest.mark.asyncio
async def test_admin_can_list_all_valid_catalog_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_agents, "scan_agent_catalog", lambda: [_entry("alpha"), _entry("broken", status="invalid")])

    response = await platform_agents.list_runnable_agents(request=_request(system_role="admin"))

    assert [agent.name for agent in response.agents] == ["alpha"]


@pytest.mark.asyncio
async def test_user_can_only_list_assigned_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _Repo(["beta"])
    monkeypatch.setattr(platform_agents, "scan_agent_catalog", lambda: [_entry("alpha"), _entry("beta")])

    response = await platform_agents.list_runnable_agents(request=_request(user_id="u-42", repo=repo))

    assert repo.seen_user_id == "u-42"
    assert [agent.name for agent in response.agents] == ["beta"]


@pytest.mark.asyncio
async def test_non_admin_requires_platform_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform_agents, "scan_agent_catalog", lambda: [_entry("alpha")])

    with pytest.raises(HTTPException) as exc:
        await platform_agents.list_runnable_agents(request=_request())

    assert exc.value.status_code == 503
