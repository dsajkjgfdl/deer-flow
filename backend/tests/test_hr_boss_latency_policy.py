from __future__ import annotations

import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_hr_boss_recommendation_runtime_fast_path_is_removed():
    source_paths = [
        REPO_ROOT / "app" / "gateway" / "services.py",
        REPO_ROOT / "packages" / "harness" / "deerflow" / "agents" / "lead_agent" / "agent.py",
        REPO_ROOT / "packages" / "harness" / "deerflow" / "agents" / "lead_agent" / "prompt.py",
        REPO_ROOT / "packages" / "harness" / "deerflow" / "agents" / "middlewares" / "dynamic_context_middleware.py",
    ]

    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        assert "hr_boss_recommendation_fast_path" not in source
        assert "should_use_hr_boss_recommendation_fast_path" not in source
        assert "_wrap_hr_boss_recommendation_direct_tool" not in source


def test_hr_boss_prompt_uses_the_regular_full_skill_path():
    from deerflow.agents.lead_agent.prompt import apply_prompt_template
    from deerflow.config.app_config import AppConfig

    assert "hr_boss_recommendation_fast_path" not in inspect.signature(apply_prompt_template).parameters

    prompt = apply_prompt_template(
        agent_name="hr-boss-agent",
        available_skills={"hr-boss"},
        app_config=AppConfig.from_file(REPO_ROOT.parent / "config.example.yaml"),
    )

    assert "<hr_boss_recommendation_fast_path>" not in prompt
    assert "Skill First: Always load the relevant skill" in prompt
    assert "immediately call `read_file` on the skill's main file" in prompt


def test_title_middleware_runs_for_all_hr_boss_queries():
    from deerflow.agents.lead_agent.agent import build_middlewares
    from deerflow.agents.middlewares.title_middleware import TitleMiddleware
    from deerflow.config.app_config import AppConfig

    app_config = AppConfig.from_file(REPO_ROOT.parent / "config.example.yaml")
    app_config.summarization.enabled = False

    middlewares = build_middlewares(
        {"configurable": {"agent_name": "hr-boss-agent"}},
        model_name=None,
        agent_name="hr-boss-agent",
        app_config=app_config,
    )

    assert any(isinstance(middleware, TitleMiddleware) for middleware in middlewares)
