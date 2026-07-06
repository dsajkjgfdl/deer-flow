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
    config = json.loads((REPO_ROOT / "extensions_config.example.json").read_text(encoding="utf-8"))

    assert config["mcpServers"]["text2cypher"]["env"]["TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED"] == "true"


def test_launcher_sets_default_hr_boss_profile_path(monkeypatch) -> None:
    monkeypatch.delenv("TEXT2CYPHER_PROFILE_PATH", raising=False)

    profile_path = launcher.ensure_profile_path()

    assert profile_path == str(
        REPO_ROOT / "backend" / ".deer-flow" / "agents" / "hr-boss-agent" / "text2cypher-profile.md"
    )
    assert profile_path == launcher.os.environ["TEXT2CYPHER_PROFILE_PATH"]


def test_packaged_server_resolves_profile_before_loading_settings() -> None:
    source = LAUNCHER_PATH.read_text(encoding="utf-8")

    assert "ensure_profile_path()" in source
    assert source.index("ensure_profile_path()") < source.index("settings = AppSettings.from_env()")


def test_main_uses_packaged_server_when_employee_query_is_enabled(monkeypatch, tmp_path) -> None:
    external_launcher = tmp_path / "scripts" / "run_text2cypher_mcp.py"
    external_launcher.parent.mkdir()
    external_launcher.write_text("raise AssertionError('must not delegate')", encoding="utf-8")
    calls = []
    monkeypatch.setenv("TEXT2CYPHER_REPO", str(tmp_path))
    monkeypatch.setenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", "true")
    monkeypatch.setattr(launcher, "run_packaged_server", lambda: calls.append("packaged"))
    monkeypatch.setattr(launcher.runpy, "run_path", lambda *_args, **_kwargs: calls.append("external"))

    launcher.main()

    assert calls == ["packaged"]


def test_main_uses_packaged_server_for_http_even_when_employee_query_is_disabled(monkeypatch, tmp_path) -> None:
    external_launcher = tmp_path / "scripts" / "run_text2cypher_mcp.py"
    external_launcher.parent.mkdir()
    external_launcher.write_text("raise AssertionError('must not delegate')", encoding="utf-8")
    calls = []
    monkeypatch.setenv("TEXT2CYPHER_REPO", str(tmp_path))
    monkeypatch.setenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", "false")
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setattr(launcher, "run_packaged_server", lambda: calls.append("packaged"))
    monkeypatch.setattr(launcher.runpy, "run_path", lambda *_args, **_kwargs: calls.append("external"))

    launcher.main()

    assert calls == ["packaged"]


def test_packaged_server_wires_employee_profile_service_with_fast_query_flag() -> None:
    source = LAUNCHER_PATH.read_text(encoding="utf-8")

    assert "EmployeeProfileCypherBuilder" in source
    assert "EmployeeProfileService" in source
    assert "employee_profile_service = None" in source
    assert "employee_profile_service=employee_profile_service" in source


def test_packaged_server_shares_one_neo4j_driver() -> None:
    source = LAUNCHER_PATH.read_text(encoding="utf-8")

    assert "driver = GraphDatabase.driver(" in source
    assert "CypherValidator(settings, driver=driver)" in source
    assert "CypherExecutor(settings, validator=validator, driver=driver)" in source
    assert "atexit.register(driver.close)" in source
