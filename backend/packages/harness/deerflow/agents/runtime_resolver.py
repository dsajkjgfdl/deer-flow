from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from deerflow.agents.catalog import AgentCatalogEntry, scan_agent_catalog
from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.config.platform_config import PlatformConfig


class EffectiveAgentRuntime(BaseModel):
    user_id: str
    requested_agent_name: str | None = None
    agent_name: str | None = None
    display_name: str | None = None
    model: str | None = None
    tool_groups: list[str] | None = None
    effective_skills: list[str] | None = None
    effective_mcp_servers: list[str] = Field(default_factory=list)
    config_hash: str | None = None
    soul_hash: str | None = None
    trace_metadata: dict[str, Any] = Field(default_factory=dict)


def _platform_config(app_config: Any | None) -> PlatformConfig:
    config = getattr(app_config, "platform", None)
    if isinstance(config, PlatformConfig):
        return config
    if isinstance(config, dict):
        return PlatformConfig(**config)
    return PlatformConfig()


def _catalog_by_name(*, app_config: Any | None = None) -> dict[str, AgentCatalogEntry]:
    return {entry.name: entry for entry in scan_agent_catalog(app_config=app_config)}


def _enabled_mcp_server_names() -> set[str]:
    return set(ExtensionsConfig.from_file().get_enabled_mcp_servers())


def _effective_mcp_servers(entry: AgentCatalogEntry) -> list[str]:
    declared = entry.mcp_servers or []
    enabled = _enabled_mcp_server_names()
    return [server_name for server_name in declared if server_name in enabled]


def _default_runtime(user_id: str, requested_agent_name: str | None = None) -> EffectiveAgentRuntime:
    return EffectiveAgentRuntime(
        user_id=user_id,
        requested_agent_name=requested_agent_name,
        agent_name=None,
        display_name=None,
        model=None,
        tool_groups=None,
        effective_skills=None,
        effective_mcp_servers=[],
        trace_metadata={"agent_name": "default"},
    )


def _runtime_from_entry(user_id: str, requested_agent_name: str | None, entry: AgentCatalogEntry) -> EffectiveAgentRuntime:
    return EffectiveAgentRuntime(
        user_id=user_id,
        requested_agent_name=requested_agent_name,
        agent_name=entry.name,
        display_name=entry.display_name,
        model=entry.model,
        tool_groups=entry.tool_groups,
        effective_skills=entry.skills,
        effective_mcp_servers=_effective_mcp_servers(entry),
        config_hash=entry.config_hash,
        soul_hash=entry.soul_hash,
        trace_metadata={
            "agent_name": entry.name,
            "agent_config_hash": entry.config_hash,
            "agent_soul_hash": entry.soul_hash,
            "effective_mcp_servers": _effective_mcp_servers(entry),
            "effective_skills": entry.skills,
        },
    )


async def resolve_effective_agent_runtime(
    *,
    user: Any,
    requested_agent_name: str | None,
    platform_repo: Any | None = None,
    app_config: Any | None = None,
) -> EffectiveAgentRuntime:
    user_id = str(user.id)
    role = getattr(user, "system_role", "user")
    platform = _platform_config(app_config)

    if requested_agent_name is None:
        if platform.base_agent_name:
            requested_agent_name = platform.base_agent_name
        elif platform.normal_user_default_to_base_agent:
            return _default_runtime(user_id)

    if requested_agent_name is None:
        raise PermissionError("No agent requested and no base agent is configured")

    catalog = _catalog_by_name(app_config=app_config)
    entry = catalog.get(requested_agent_name)
    if entry is None:
        raise FileNotFoundError(f"Agent '{requested_agent_name}' not found")
    if entry.status == "invalid":
        raise ValueError(f"Agent '{requested_agent_name}' is invalid: {entry.validation_errors}")

    if role not in {"admin", "internal"}:
        if platform_repo is None:
            raise PermissionError("Agent assignment repository is required for normal users")
        if not await platform_repo.user_has_agent(user_id, requested_agent_name):
            raise PermissionError(f"User is not assigned to agent '{requested_agent_name}'")

    return _runtime_from_entry(user_id, requested_agent_name, entry)


__all__ = ["EffectiveAgentRuntime", "PlatformConfig", "resolve_effective_agent_runtime"]
