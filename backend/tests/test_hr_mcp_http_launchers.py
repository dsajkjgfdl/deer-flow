import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_script(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = load_script("hr_mcp_transport_test", "scripts/hr_mcp_transport.py")
graphrag_launcher = load_script("run_graphrag_mcp_http_test", "scripts/run_graphrag_mcp.py")


def test_http_transport_uses_streamable_http_and_network_settings(monkeypatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORT", "8123")
    monkeypatch.setenv("MCP_LOG_LEVEL", "warning")

    assert transport.server_run_kwargs() == {
        "transport": "streamable-http",
        "show_banner": False,
        "log_level": "warning",
        "host": "0.0.0.0",
        "port": 8123,
    }


def test_stdio_transport_does_not_include_network_settings(monkeypatch) -> None:
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.setenv("MCP_HOST", "must-not-be-used")
    monkeypatch.setenv("MCP_PORT", "8123")

    assert transport.server_run_kwargs() == {
        "transport": "stdio",
        "show_banner": False,
        "log_level": "error",
    }


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MCP_TRANSPORT", "websocket", "Unsupported MCP transport"),
        ("MCP_PORT", "not-a-port", "MCP_PORT must be an integer"),
        ("MCP_PORT", "70000", "MCP_PORT must be between 1 and 65535"),
    ],
)
def test_invalid_http_settings_fail_explicitly(monkeypatch, name: str, value: str, message: str) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=message):
        transport.server_run_kwargs()


def test_run_server_passes_resolved_settings(monkeypatch) -> None:
    calls = []

    class FakeServer:
        def run(self, **kwargs) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(transport, "server_run_kwargs", lambda: {"transport": "sse", "port": 9000})

    transport.run_server(FakeServer())

    assert calls == [{"transport": "sse", "port": 9000}]


def test_graphrag_launcher_builds_server_instead_of_calling_stdio_main(monkeypatch) -> None:
    calls = []
    fake_server_module = ModuleType("graphrag_mcp.server")
    fake_server_module.build_server = lambda: "server"
    fake_server_module.main = lambda: calls.append("stdio-main")
    monkeypatch.setitem(sys.modules, "graphrag_mcp.server", fake_server_module)
    monkeypatch.setattr(graphrag_launcher, "ensure_repo_on_path", lambda: REPO_ROOT)
    monkeypatch.setattr(graphrag_launcher, "run_server", lambda server: calls.append(server), raising=False)

    graphrag_launcher.main()

    assert calls == ["server"]


def test_hr_boss_docker_mcp_config_uses_http_services() -> None:
    config = json.loads((REPO_ROOT / "deployment" / "hr-boss" / "extensions_config.docker.json").read_text(encoding="utf-8"))

    assert config["mcpServers"]["text2cypher"] == {
        "enabled": True,
        "type": "http",
        "url": "http://text2cypher-mcp:8000/mcp",
        "timeout": 30,
        "sse_read_timeout": 90,
        "read_timeout_seconds": 60,
        "description": "Text2Cypher engine via independent HTTP MCP service",
    }
    assert config["mcpServers"]["hr-graphrag-qa"] == {
        "enabled": True,
        "type": "http",
        "url": "http://hr-graphrag-mcp:8000/mcp",
        "timeout": 30,
        "sse_read_timeout": 210,
        "read_timeout_seconds": 200,
        "description": "HR GraphRAG QA via independent HTTP MCP service",
    }


def test_hr_boss_compose_runs_independent_http_mcp_services() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker" / "docker-compose.hr-boss.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["text2cypher-mcp"]["environment"]["MCP_TRANSPORT"] == "streamable-http"
    assert services["hr-graphrag-mcp"]["environment"]["MCP_TRANSPORT"] == "streamable-http"
    assert services["hr-graphrag-mcp"]["environment"]["GRAPHRAG_GLOBAL_PRIMARY_TIMEOUT_SECONDS"] == "${GRAPHRAG_GLOBAL_PRIMARY_TIMEOUT_SECONDS:-120}"
    assert services["hr-graphrag-mcp"]["environment"]["GRAPHRAG_GLOBAL_FALLBACK_TIMEOUT_SECONDS"] == "${GRAPHRAG_GLOBAL_FALLBACK_TIMEOUT_SECONDS:-45}"
    assert services["hr-graphrag-mcp"]["environment"]["GRAPHRAG_GLOBAL_TOTAL_TIMEOUT_SECONDS"] == "${GRAPHRAG_GLOBAL_TOTAL_TIMEOUT_SECONDS:-180}"
    assert services["gateway"]["depends_on"]["text2cypher-mcp"]["condition"] == "service_healthy"
    assert services["gateway"]["depends_on"]["hr-graphrag-mcp"]["condition"] == "service_healthy"


def test_production_gateway_does_not_sync_dependencies_at_startup() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker" / "docker-compose.yaml").read_text(encoding="utf-8"))

    assert "uv run --no-sync uvicorn" in compose["services"]["gateway"]["command"]
