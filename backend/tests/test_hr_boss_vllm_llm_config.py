import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
QWEN_BASE_URL = "http://36.212.39.231:11435/v1"


def _load_local_config_yaml() -> dict:
    config_path = REPO_ROOT / "config.yaml"
    if not config_path.exists():
        pytest.skip("Local config.yaml is not present")
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def _extensions_config_paths() -> list[Path]:
    paths = [REPO_ROOT / "extensions_config.example.json"]
    local_path = REPO_ROOT / "extensions_config.json"
    if local_path.exists():
        paths.append(local_path)
    return paths


def test_hr_boss_agent_registers_qwen_and_deepseek_models() -> None:
    app_config = _load_local_config_yaml()
    agent_config = yaml.safe_load(
        (
            REPO_ROOT
            / "backend"
            / ".deer-flow"
            / "agents"
            / "hr-boss-agent"
            / "config.yaml"
        ).read_text(encoding="utf-8")
    )

    models_by_name = {model["name"]: model for model in app_config["models"]}
    assert list(models_by_name)[:2] == ["hr-qwen", "hr-deepseek"]

    qwen_model = models_by_name["hr-qwen"]
    assert qwen_model["use"] == "deerflow.models.vllm_provider:VllmChatModel"
    assert qwen_model["model"] == "$QWEN_CHAT_MODEL"
    assert qwen_model["api_key"] == "$QWEN_API_KEY"
    assert qwen_model["base_url"] == "$QWEN_CHAT_API_BASE"
    assert qwen_model["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert qwen_model["max_context_tokens"] == 38912
    assert qwen_model["context_preflight"] == {
        "enabled": True,
        "safety_margin_tokens": 512,
        "template_overhead_tokens": 800,
        "tokenizer": "cl100k_base",
        "on_overflow": "trim",
    }
    assert qwen_model["supports_thinking"] is False

    deepseek_model = models_by_name["hr-deepseek"]
    assert deepseek_model["use"] == "deerflow.models.patched_deepseek:PatchedChatDeepSeek"
    assert deepseek_model["model"] == "$DEEPSEEK_MODEL"
    assert deepseek_model["api_base"] == "$DEEPSEEK_API_BASE"
    assert deepseek_model["api_key"] == "$DEEPSEEK_API_KEY"
    assert deepseek_model["supports_thinking"] is True

    assert agent_config["model"] == "hr-qwen"


def test_local_extensions_pass_profile_variables_to_hr_mcp_services() -> None:
    for path in _extensions_config_paths():
        config = json.loads(path.read_text(encoding="utf-8"))
        graphrag_env = config["mcpServers"]["hr-graphrag-qa"]["env"]
        text2cypher_env = config["mcpServers"]["text2cypher"]["env"]

        for env in (graphrag_env, text2cypher_env):
            assert env["HR_LLM_PROFILE"] == "$HR_LLM_PROFILE", path
            assert env["QWEN_API_KEY"] == "$QWEN_API_KEY", path
            assert env["QWEN_CHAT_API_BASE"] == "$QWEN_CHAT_API_BASE", path
            assert env["QWEN_CHAT_MODEL"] == "$QWEN_CHAT_MODEL", path
            assert env["DEEPSEEK_API_KEY"] == "$DEEPSEEK_API_KEY", path
            assert env["DEEPSEEK_API_BASE"] == "$DEEPSEEK_API_BASE", path
            assert env["DEEPSEEK_MODEL"] == "$DEEPSEEK_MODEL", path

        assert graphrag_env["GRAPHRAG_EMBEDDING_API_BASE"] == "http://36.138.220.105:11434/v1", path
        assert graphrag_env["GRAPHRAG_EMBEDDING_API_KEY"] == "ollama", path
        assert graphrag_env["GRAPHRAG_EMBEDDING_MODEL"] == "bge-m3", path

        assert "TEXT2CYPHER_OPENAI_API_KEY" not in text2cypher_env, path
        assert "TEXT2CYPHER_OPENAI_BASE_URL" not in text2cypher_env, path
        assert "TEXT2CYPHER_OPENAI_MODEL" not in text2cypher_env, path


def test_hr_boss_compose_passes_profile_variables_and_uses_company_bge_embeddings() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker" / "docker-compose.hr-boss.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    graphrag_env = services["hr-graphrag-mcp"]["environment"]
    text2cypher_env = services["text2cypher-mcp"]["environment"]

    for env in (graphrag_env, text2cypher_env):
        assert env["HR_LLM_PROFILE"] == "${HR_LLM_PROFILE:-qwen}"
        assert env["QWEN_API_KEY"] == "${QWEN_API_KEY:?set QWEN_API_KEY}"
        assert env["QWEN_CHAT_API_BASE"] == f"${{QWEN_CHAT_API_BASE:-{QWEN_BASE_URL}}}"
        assert env["QWEN_CHAT_MODEL"] == "${QWEN_CHAT_MODEL:-Qwen3}"
        assert env["DEEPSEEK_API_KEY"] == "${DEEPSEEK_API_KEY:?set DEEPSEEK_API_KEY}"
        assert env["DEEPSEEK_API_BASE"] == "${DEEPSEEK_API_BASE:-https://api.deepseek.com}"
        assert env["DEEPSEEK_MODEL"] == "${DEEPSEEK_MODEL:-deepseek-v4-pro}"

    assert graphrag_env["GRAPHRAG_EMBEDDING_API_BASE"] == "${GRAPHRAG_EMBEDDING_API_BASE:-http://36.138.220.105:11434/v1}"
    assert graphrag_env["GRAPHRAG_EMBEDDING_API_KEY"] == "${GRAPHRAG_EMBEDDING_API_KEY:-ollama}"
    assert graphrag_env["GRAPHRAG_EMBEDDING_MODEL"] == "${GRAPHRAG_EMBEDDING_MODEL:-bge-m3}"

    assert "TEXT2CYPHER_OPENAI_API_KEY" not in text2cypher_env
    assert "TEXT2CYPHER_OPENAI_BASE_URL" not in text2cypher_env
    assert "TEXT2CYPHER_OPENAI_MODEL" not in text2cypher_env
    assert "GRAPHRAG_COMPLETION_API_KEY" not in graphrag_env
    assert "GRAPHRAG_COMPLETION_API_BASE" not in graphrag_env
    assert "GRAPHRAG_COMPLETION_MODEL" not in graphrag_env


def test_hr_boss_deployment_example_enables_qwen_context_preflight() -> None:
    deployment_config = yaml.safe_load((REPO_ROOT / "deployment" / "hr-boss" / "config.hr-boss.example.yaml").read_text(encoding="utf-8"))
    models_by_name = {model["name"]: model for model in deployment_config["models"]}

    qwen_model = models_by_name["hr-qwen"]
    assert qwen_model["max_context_tokens"] == 38912
    assert qwen_model["context_preflight"] == {
        "enabled": True,
        "safety_margin_tokens": 512,
        "template_overhead_tokens": 800,
        "tokenizer": "cl100k_base",
        "on_overflow": "trim",
    }


def test_gateway_http_launcher_sets_provider_aliases_before_startup() -> None:
    source = (REPO_ROOT / "scripts" / "start-gateway-http-mcp.ps1").read_text(encoding="utf-8")

    assert 'function Require-EnvironmentVariable' in source
    assert '$env:QWEN_API_KEY = $env:VLLM_API_KEY' in source
    assert '$env:QWEN_CHAT_API_BASE = $env:VLLM_CHAT_API_BASE' in source
    assert '$env:DEEPSEEK_API_KEY = $env:DASHSCOPE_API_KEY' in source
    assert 'Require-EnvironmentVariable "QWEN_API_KEY"' in source
    assert 'Require-EnvironmentVariable "DEEPSEEK_API_KEY"' in source
