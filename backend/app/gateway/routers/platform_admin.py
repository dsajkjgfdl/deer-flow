from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.gateway.authz import require_admin
from app.gateway.deps import get_local_provider
from deerflow.agents.catalog import AgentCatalogEntry, scan_agent_catalog

router = APIRouter(prefix="/api/platform/admin", tags=["platform-admin"])


class AgentCatalogResponse(BaseModel):
    agents: list[AgentCatalogEntry]


class UserAgentAssignmentsResponse(BaseModel):
    user_id: str
    agent_names: list[str]


class PlatformUserResponse(BaseModel):
    id: str
    email: str
    system_role: str
    needs_setup: bool = False
    created_at: str


class PlatformUsersResponse(BaseModel):
    items: list[PlatformUserResponse]
    total: int
    limit: int
    offset: int


class GrantAgentResponse(BaseModel):
    user_id: str
    agent_name: str
    granted: bool


class RevokeAgentResponse(BaseModel):
    user_id: str
    agent_name: str
    revoked: bool


class AdminAuditResponse(BaseModel):
    items: list[dict[str, Any]]


class RunMonitoringResponse(BaseModel):
    items: list[dict[str, Any]]


class ToolMonitoringResponse(BaseModel):
    items: list[dict[str, Any]]
    recent_failures: list[dict[str, Any]] = Field(default_factory=list)


def _platform_repo(request: Request):
    repo = getattr(request.app.state, "platform_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Platform repository not available")
    return repo


def _actor_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user is None:
        auth = getattr(request.state, "auth", None)
        user = getattr(auth, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(user.id)


def _catalog_by_name() -> dict[str, AgentCatalogEntry]:
    return {entry.name: entry for entry in scan_agent_catalog()}


def _assignable_agent(agent_name: str) -> AgentCatalogEntry:
    entry = _catalog_by_name().get(agent_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    if entry.status == "invalid":
        raise HTTPException(status_code=400, detail=f"Agent '{agent_name}' is invalid: {entry.validation_errors}")
    return entry


@router.get("/agents/catalog", response_model=AgentCatalogResponse)
@require_admin
async def list_agent_catalog(request: Request) -> AgentCatalogResponse:
    return AgentCatalogResponse(agents=scan_agent_catalog())


@router.get("/users", response_model=PlatformUsersResponse)
@require_admin
async def list_platform_users(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlatformUsersResponse:
    users, total = await get_local_provider().list_users(limit=limit, offset=offset)
    return PlatformUsersResponse(
        items=[
            PlatformUserResponse(
                id=str(user.id),
                email=user.email,
                system_role=user.system_role,
                needs_setup=user.needs_setup,
                created_at=user.created_at.isoformat(),
            )
            for user in users
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}/agents", response_model=UserAgentAssignmentsResponse)
@require_admin
async def list_user_agent_assignments(user_id: str, request: Request) -> UserAgentAssignmentsResponse:
    agent_names = await _platform_repo(request).list_user_agents(user_id)
    return UserAgentAssignmentsResponse(user_id=user_id, agent_names=agent_names)


@router.put("/users/{user_id}/agents/{agent_name}", response_model=GrantAgentResponse)
@require_admin
async def grant_user_agent(user_id: str, agent_name: str, request: Request) -> GrantAgentResponse:
    _assignable_agent(agent_name)
    granted = await _platform_repo(request).grant_agent(
        user_id,
        agent_name,
        actor_user_id=_actor_user_id(request),
    )
    return GrantAgentResponse(user_id=user_id, agent_name=agent_name, granted=granted)


@router.delete("/users/{user_id}/agents/{agent_name}", response_model=RevokeAgentResponse)
@require_admin
async def revoke_user_agent(user_id: str, agent_name: str, request: Request) -> RevokeAgentResponse:
    revoked = await _platform_repo(request).revoke_agent(
        user_id,
        agent_name,
        actor_user_id=_actor_user_id(request),
    )
    return RevokeAgentResponse(user_id=user_id, agent_name=agent_name, revoked=revoked)


@router.get("/audit", response_model=AdminAuditResponse)
@require_admin
async def list_admin_audit(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> AdminAuditResponse:
    return AdminAuditResponse(items=await _platform_repo(request).list_admin_audit(limit=limit))


@router.get("/monitoring/runs", response_model=RunMonitoringResponse)
@require_admin
async def summarize_runs(request: Request) -> RunMonitoringResponse:
    return RunMonitoringResponse(items=await _platform_repo(request).summarize_runs_by_agent())


@router.get("/monitoring/tools", response_model=ToolMonitoringResponse)
@require_admin
async def summarize_tools(request: Request, failure_limit: int = Query(default=20, ge=1, le=100)) -> ToolMonitoringResponse:
    repo = _platform_repo(request)
    return ToolMonitoringResponse(
        items=await repo.summarize_tools_by_agent(),
        recent_failures=await repo.recent_tool_failures(limit=failure_limit),
    )
