from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.authz import require_permission
from deerflow.agents.catalog import AgentCatalogEntry, scan_agent_catalog

router = APIRouter(prefix="/api/platform/agents", tags=["platform-agents"])


class RunnableAgentResponse(BaseModel):
    name: str
    display_name: str | None = None
    description: str = ""
    model: str | None = None
    tool_groups: list[str] | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None
    status: str
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


class RunnableAgentsResponse(BaseModel):
    agents: list[RunnableAgentResponse]


def _platform_repo(request: Request):
    repo = getattr(request.app.state, "platform_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Platform repository not available")
    return repo


def _current_user(request: Request):
    user = getattr(request.state, "user", None)
    if user is not None:
        return user
    auth = getattr(request.state, "auth", None)
    user = getattr(auth, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _to_response(entry: AgentCatalogEntry) -> RunnableAgentResponse:
    return RunnableAgentResponse(
        name=entry.name,
        display_name=entry.display_name,
        description=entry.description,
        model=entry.model,
        tool_groups=entry.tool_groups,
        skills=entry.skills,
        mcp_servers=entry.mcp_servers,
        status=entry.status,
        validation_errors=entry.validation_errors,
        validation_warnings=entry.validation_warnings,
    )


def _catalog_by_name() -> dict[str, AgentCatalogEntry]:
    return {entry.name: entry for entry in scan_agent_catalog() if entry.status != "invalid"}


async def _allowed_agent_names(request: Request) -> set[str]:
    user = _current_user(request)
    if getattr(user, "system_role", "user") == "admin":
        return set(_catalog_by_name())
    return set(await _platform_repo(request).list_user_agents(str(user.id)))


@router.get("", response_model=RunnableAgentsResponse)
@require_permission("runs", "create")
async def list_runnable_agents(request: Request) -> RunnableAgentsResponse:
    allowed = await _allowed_agent_names(request)
    entries = [entry for entry in _catalog_by_name().values() if entry.name in allowed]
    return RunnableAgentsResponse(agents=[_to_response(entry) for entry in entries])


@router.get("/{agent_name}", response_model=RunnableAgentResponse)
@require_permission("runs", "create")
async def get_runnable_agent(agent_name: str, request: Request) -> RunnableAgentResponse:
    entry = _catalog_by_name().get(agent_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    allowed = await _allowed_agent_names(request)
    if agent_name not in allowed:
        raise HTTPException(status_code=403, detail=f"User is not assigned to agent '{agent_name}'")
    return _to_response(entry)
