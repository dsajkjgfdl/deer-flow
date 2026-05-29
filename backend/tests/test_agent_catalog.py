from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from deerflow.config.extensions_config import ExtensionsConfig, McpServerConfig

def _make_paths(base_dir: Path):
    from deerflow.config.paths import Paths

    return Paths(base_dir=base_dir)


def _write_agent(base_dir: Path, name: str, config: dict, soul: str | None = "Soul") -> None:
    agent_dir = base_dir / "agents" / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "config.yaml").write_text(yaml.safe_dump({"name": name, **config}, allow_unicode=True), encoding="utf-8")
    if soul is not None:
        (agent_dir / "SOUL.md").write_text(soul, encoding="utf-8")


def test_scan_agent_catalog_returns_valid_file_backed_agent(tmp_path):
    _write_agent(
        tmp_path,
        "hr-boss-agent",
        {
            "display_name": "HR Boss Agent",
            "description": "HR demo",
            "model": "qwen3.5-plus",
            "tool_groups": ["file:read"],
            "mcp_servers": ["hr-graphrag-qa", "text2cypher"],
            "skills": ["hr-boss"],
        },
    )
    skill_dir = tmp_path / "skills" / "custom" / "hr-boss"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: hr-boss\n---\n", encoding="utf-8")

    app_config = SimpleNamespace(
        tools=[SimpleNamespace(group="file:read")],
    )
    extensions = ExtensionsConfig(
        mcpServers={
            "hr-graphrag-qa": McpServerConfig(enabled=True, command="qa"),
            "text2cypher": McpServerConfig(enabled=True, command="t2c"),
        }
    )

    with (
        patch("deerflow.agents.catalog.get_paths", return_value=_make_paths(tmp_path)),
        patch("deerflow.agents.catalog.load_available_skills", return_value={"hr-boss"}),
        patch("deerflow.agents.catalog.ExtensionsConfig.from_file", return_value=extensions),
    ):
        from deerflow.agents.catalog import scan_agent_catalog

        entries = scan_agent_catalog(app_config=app_config)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "hr-boss-agent"
    assert entry.display_name == "HR Boss Agent"
    assert entry.status == "valid"
    assert entry.validation_errors == []
    assert entry.skills == ["hr-boss"]
    assert entry.mcp_servers == ["hr-graphrag-qa", "text2cypher"]
    assert entry.config_hash
    assert entry.soul_hash


def test_scan_agent_catalog_reports_invalid_references(tmp_path):
    _write_agent(
        tmp_path,
        "broken-agent",
        {
            "tool_groups": ["missing-group"],
            "mcp_servers": ["disabled-mcp", "missing-mcp"],
            "skills": ["missing-skill"],
        },
        soul=None,
    )
    app_config = SimpleNamespace(tools=[SimpleNamespace(group="file:read")])
    extensions = ExtensionsConfig(mcpServers={"disabled-mcp": McpServerConfig(enabled=False, command="disabled")})

    with (
        patch("deerflow.agents.catalog.get_paths", return_value=_make_paths(tmp_path)),
        patch("deerflow.agents.catalog.load_available_skills", return_value={"hr-boss"}),
        patch("deerflow.agents.catalog.ExtensionsConfig.from_file", return_value=extensions),
    ):
        from deerflow.agents.catalog import scan_agent_catalog

        entries = scan_agent_catalog(app_config=app_config)

    entry = entries[0]
    assert entry.status == "invalid"
    assert "Skill not found: missing-skill" in entry.validation_errors
    assert "MCP server disabled: disabled-mcp" in entry.validation_errors
    assert "MCP server not found: missing-mcp" in entry.validation_errors
    assert "Tool group not found: missing-group" in entry.validation_errors
    assert "SOUL.md not found" in entry.validation_warnings
