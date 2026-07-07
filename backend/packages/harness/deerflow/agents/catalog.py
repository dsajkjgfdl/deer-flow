from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from deerflow.config.agents_config import AgentConfig
from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.config.paths import get_paths
from deerflow.skills.storage import get_or_new_skill_storage


class AgentCatalogEntry(BaseModel):
    name: str
    display_name: str | None = None
    description: str = ""
    model: str | None = None
    tool_groups: list[str] | None = None
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None
    allowed_tools: list[str] | None = None
    config_path: str
    soul_path: str | None = None
    config_hash: str
    soul_hash: str | None = None
    git_commit: str | None = None
    status: Literal["valid", "warning", "invalid"]
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit_for_path(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path.parent,
            capture_output=True,
            check=True,
            text=True,
        )
    except Exception:
        return None
    commit = result.stdout.strip()
    return commit or None


def _load_agent_config_from_dir(agent_dir: Path) -> AgentConfig:
    config_path = agent_dir / "config.yaml"
    with config_path.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    if "name" not in data:
        data["name"] = agent_dir.name
    known_fields = set(AgentConfig.model_fields.keys())
    return AgentConfig(**{k: v for k, v in data.items() if k in known_fields})


def load_available_skills(*, app_config: Any | None = None) -> set[str]:
    storage = get_or_new_skill_storage(app_config=app_config)
    return {skill.name for skill in storage.load_skills(enabled_only=False)}


def _configured_tool_groups(*, app_config: Any | None = None) -> set[str]:
    if app_config is None:
        return set()

    groups: set[str] = set()
    for tool in getattr(app_config, "tools", []) or []:
        group = getattr(tool, "group", None)
        if group:
            groups.add(str(group))
    for tool_group in getattr(app_config, "tool_groups", []) or []:
        name = getattr(tool_group, "name", None)
        if name:
            groups.add(str(name))
    return groups


def validate_agent_entry(agent_config: AgentConfig, *, app_config: Any | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    available_skills = load_available_skills(app_config=app_config)
    for skill_name in agent_config.skills or []:
        if skill_name not in available_skills:
            errors.append(f"Skill not found: {skill_name}")

    extensions_config = ExtensionsConfig.from_file()
    configured_servers = extensions_config.mcp_servers
    enabled_servers = extensions_config.get_enabled_mcp_servers()
    for server_name in agent_config.mcp_servers or []:
        if server_name not in configured_servers:
            errors.append(f"MCP server not found: {server_name}")
        elif server_name not in enabled_servers:
            errors.append(f"MCP server disabled: {server_name}")

    configured_tool_groups = _configured_tool_groups(app_config=app_config)
    for group_name in agent_config.tool_groups or []:
        if configured_tool_groups and group_name not in configured_tool_groups:
            errors.append(f"Tool group not found: {group_name}")

    return errors, warnings


def _status(errors: list[str], warnings: list[str]) -> Literal["valid", "warning", "invalid"]:
    if errors:
        return "invalid"
    if warnings:
        return "warning"
    return "valid"


def _agent_dirs(*, user_id: str | None = None) -> list[Path]:
    paths = get_paths()
    roots = [paths.agents_dir]
    if user_id is not None:
        roots.insert(0, paths.user_agents_dir(user_id))

    dirs: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name in seen:
                continue
            if (entry / "config.yaml").exists():
                dirs.append(entry)
                seen.add(entry.name)
    return dirs


def scan_agent_catalog(*, app_config: Any | None = None, user_id: str | None = None) -> list[AgentCatalogEntry]:
    entries: list[AgentCatalogEntry] = []
    for agent_dir in _agent_dirs(user_id=user_id):
        config_path = agent_dir / "config.yaml"
        soul_path = agent_dir / "SOUL.md"
        errors: list[str] = []
        warnings: list[str] = []

        try:
            agent_config = _load_agent_config_from_dir(agent_dir)
        except Exception as exc:
            config_hash = _sha256_file(config_path) if config_path.exists() else ""
            entries.append(
                AgentCatalogEntry(
                    name=agent_dir.name,
                    config_path=str(config_path),
                    config_hash=config_hash,
                    git_commit=_git_commit_for_path(config_path),
                    status="invalid",
                    validation_errors=[f"Agent config failed to load: {exc}"],
                )
            )
            continue

        errors, validation_warnings = validate_agent_entry(agent_config, app_config=app_config)
        warnings.extend(validation_warnings)
        if not soul_path.exists():
            warnings.append("SOUL.md not found")

        entries.append(
            AgentCatalogEntry(
                name=agent_config.name,
                display_name=agent_config.display_name,
                description=agent_config.description,
                model=agent_config.model,
                tool_groups=agent_config.tool_groups,
                skills=agent_config.skills,
                mcp_servers=agent_config.mcp_servers,
                allowed_tools=agent_config.allowed_tools,
                config_path=str(config_path),
                soul_path=str(soul_path) if soul_path.exists() else None,
                config_hash=_sha256_file(config_path),
                soul_hash=_sha256_file(soul_path) if soul_path.exists() else None,
                git_commit=_git_commit_for_path(config_path),
                status=_status(errors, warnings),
                validation_errors=errors,
                validation_warnings=warnings,
            )
        )

    return entries
