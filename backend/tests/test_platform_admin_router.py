from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.gateway.routers import platform_admin
from deerflow.agents.catalog import AgentCatalogEntry


def _request(repo=None) -> SimpleNamespace:
    return SimpleNamespace(
        _deerflow_test_bypass_auth=True,
        state=SimpleNamespace(user=SimpleNamespace(id="admin-1", system_role="admin")),
        app=SimpleNamespace(state=SimpleNamespace(platform_repo=repo) if repo is not None else SimpleNamespace()),
    )


def test_platform_admin_router_metadata() -> None:
    assert platform_admin.router.prefix == "/api/platform/admin"
    assert "platform-admin" in platform_admin.router.tags


@pytest.mark.asyncio
async def test_list_agent_catalog_returns_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = AgentCatalogEntry(
        name="hr-boss-agent",
        display_name="HR Boss",
        config_path="/tmp/hr-boss-agent/config.yaml",
        config_hash="hash",
        status="valid",
    )
    monkeypatch.setattr(platform_admin, "scan_agent_catalog", lambda: [entry])

    response = await platform_admin.list_agent_catalog(request=_request())

    assert response.agents[0].name == "hr-boss-agent"
    assert response.agents[0].display_name == "HR Boss"


@pytest.mark.asyncio
async def test_user_assignment_api_requires_platform_repo() -> None:
    with pytest.raises(HTTPException) as exc:
        await platform_admin.list_user_agent_assignments("u-1", request=_request())

    assert exc.value.status_code == 503
