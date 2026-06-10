import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = REPO_ROOT / "scripts" / "run_text2cypher_mcp.py"
spec = importlib.util.spec_from_file_location("run_text2cypher_mcp_root", LAUNCHER_PATH)
assert spec and spec.loader
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_employee_query_flag_defaults_disabled(monkeypatch) -> None:
    monkeypatch.delenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", raising=False)

    assert launcher.employee_query_enabled() is False


def test_employee_query_flag_accepts_true(monkeypatch) -> None:
    monkeypatch.setenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", "true")

    assert launcher.employee_query_enabled() is True


def test_hr_boss_text2cypher_configs_enable_employee_query() -> None:
    config_paths = [
        REPO_ROOT / "extensions_config.example.json",
        REPO_ROOT / "deployment" / "hr-boss" / "extensions_config.docker.json",
    ]

    for path in config_paths:
        config = json.loads(path.read_text(encoding="utf-8"))
        assert (
            config["mcpServers"]["text2cypher"]["env"]["TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED"]
            == "true"
        )
