from __future__ import annotations

import atexit
import os
import runpy
import sys
from pathlib import Path

from hr_mcp_transport import run_server, server_run_kwargs

TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
HR_BOSS_PROFILE_RELATIVE_PATH = (
    Path("backend") / ".deer-flow" / "agents" / "hr-boss-agent" / "text2cypher-profile.md"
)


def employee_query_enabled() -> bool:
    return os.getenv("TEXT2CYPHER_EMPLOYEE_QUERY_ENABLED", "").strip().lower() in TRUE_ENV_VALUES


def _usable_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    if not value or value.startswith("$"):
        return None
    return value


def resolve_deerflow_repo_root() -> Path:
    raw = _usable_env_value("DEER_FLOW_REPO_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def ensure_profile_path() -> str | None:
    explicit_path = _usable_env_value("TEXT2CYPHER_PROFILE_PATH")
    if explicit_path:
        return explicit_path

    profile_path = (resolve_deerflow_repo_root() / HR_BOSS_PROFILE_RELATIVE_PATH).resolve()
    if not profile_path.exists():
        return None

    resolved = str(profile_path)
    os.environ["TEXT2CYPHER_PROFILE_PATH"] = resolved
    return resolved


def resolve_repo_root() -> tuple[Path, Path | None]:
    raw = os.getenv(
        "TEXT2CYPHER_REPO",
        "D:/study/my-mcp/hr-mcp-suite/services/text2cypher",
    )
    repo_root = Path(raw).expanduser().resolve()
    if not repo_root.exists():
        raise RuntimeError(f"TEXT2CYPHER_REPO does not exist: {repo_root}")
    script_path = repo_root / "scripts" / "run_text2cypher_mcp.py"
    if script_path.exists():
        return repo_root, script_path

    worktrees_dir = repo_root / ".worktrees"
    if worktrees_dir.exists():
        candidates = sorted(worktrees_dir.glob("*/scripts/run_text2cypher_mcp.py"))
        if candidates:
            return candidates[0].parent.parent, candidates[0]

    package_dir = repo_root / "text2cypher" / "adapters" / "mcp"
    if package_dir.exists():
        return repo_root, None

    raise RuntimeError(
        "Text2Cypher launcher not found under "
        f"{repo_root}. Expected either scripts/run_text2cypher_mcp.py "
        "or text2cypher/adapters/mcp/server.py."
    )


def run_packaged_server() -> None:
    from text2cypher.adapters.mcp.server import create_server
    from text2cypher.config import AppSettings
    from text2cypher.core.employee_profile_builder import EmployeeProfileCypherBuilder
    from text2cypher.core.employee_profile_service import EmployeeProfileService
    from text2cypher.core.employee_filter_resolver import EmployeeFilterResolver
    from text2cypher.core.employee_query_builder import EmployeePresetCypherBuilder
    from text2cypher.core.employee_query_service import EmployeePresetQueryService
    from text2cypher.core.engine import Text2CypherEngine
    from text2cypher.core.executor import CypherExecutor
    from text2cypher.core.generator import CypherGenerator
    from text2cypher.core.planner import SinglePassPlanner
    from text2cypher.core.schema_service import SchemaService
    from text2cypher.core.validator import CypherValidator
    from text2cypher.core.value_catalog import ValueCatalogService
    from neo4j import GraphDatabase

    ensure_profile_path()
    settings = AppSettings.from_env()
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.username, settings.neo4j.password),
    )
    atexit.register(driver.close)
    validator = CypherValidator(settings, driver=driver)
    executor = CypherExecutor(settings, validator=validator, driver=driver)
    employee_query_service = None
    employee_profile_service = None
    if employee_query_enabled():
        employee_query_service = EmployeePresetQueryService(
            resolver=EmployeeFilterResolver(executor=executor),
            builder=EmployeePresetCypherBuilder(),
            validator=validator,
            executor=executor,
        )
        employee_profile_service = EmployeeProfileService(
            builder=EmployeeProfileCypherBuilder(),
            validator=validator,
            executor=executor,
        )
    engine = Text2CypherEngine(
        schema_service=SchemaService(settings),
        generator=CypherGenerator(settings),
        validator=validator,
        executor=executor,
        planner=SinglePassPlanner(settings),
        value_catalog_service=ValueCatalogService(settings),
        employee_query_service=employee_query_service,
        employee_profile_service=employee_profile_service,
        total_timeout_seconds=settings.answer_timeout_seconds,
    )
    server = create_server(engine)
    run_server(server)


def main() -> None:
    repo_root, script_path = resolve_repo_root()
    repo_path = str(repo_root)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)
    if script_path is not None and not employee_query_enabled() and server_run_kwargs()["transport"] == "stdio":
        runpy.run_path(str(script_path), run_name="__main__")
        return
    run_packaged_server()


if __name__ == "__main__":
    main()
