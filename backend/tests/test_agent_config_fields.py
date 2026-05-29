from pathlib import Path
from unittest.mock import patch

import yaml


def _make_paths(base_dir: Path):
    from deerflow.config.paths import Paths

    return Paths(base_dir=base_dir)


def test_load_agent_config_preserves_display_name_and_mcp_servers(tmp_path):
    agent_dir = tmp_path / "agents" / "hr-boss-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "hr-boss-agent",
                "display_name": "HR Boss Agent",
                "description": "HR leadership demo agent",
                "model": "qwen3.5-plus",
                "tool_groups": ["file:read"],
                "mcp_servers": ["hr-graphrag-qa", "text2cypher"],
                "skills": ["hr-boss"],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (agent_dir / "SOUL.md").write_text("You are the HR boss agent.", encoding="utf-8")

    import deerflow.config.agents_config as agents_config

    with patch.object(agents_config, "get_paths", return_value=_make_paths(tmp_path)):
        cfg = agents_config.load_agent_config("hr-boss-agent")

    assert cfg.name == "hr-boss-agent"
    assert cfg.display_name == "HR Boss Agent"
    assert cfg.description == "HR leadership demo agent"
    assert cfg.model == "qwen3.5-plus"
    assert cfg.tool_groups == ["file:read"]
    assert cfg.mcp_servers == ["hr-graphrag-qa", "text2cypher"]
    assert cfg.skills == ["hr-boss"]
