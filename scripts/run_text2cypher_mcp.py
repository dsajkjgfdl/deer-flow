from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def resolve_repo_root() -> tuple[Path, Path | None]:
    raw = os.getenv("TEXT2CYPHER_REPO", "D:/study/my-mcp/text2cypher")
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
    from text2cypher.core.engine import Text2CypherEngine
    from text2cypher.core.executor import CypherExecutor
    from text2cypher.core.generator import CypherGenerator
    from text2cypher.core.schema_service import SchemaService
    from text2cypher.core.term_resolver import TermResolver
    from text2cypher.core.validator import CypherValidator

    settings = AppSettings.from_env()
    validator = CypherValidator(settings)
    engine = Text2CypherEngine(
        schema_service=SchemaService(settings),
        generator=CypherGenerator(settings),
        validator=validator,
        executor=CypherExecutor(settings, validator=validator),
        term_resolver=TermResolver(settings),
    )
    server = create_server(engine)
    server.run()


def main() -> None:
    repo_root, script_path = resolve_repo_root()
    repo_path = str(repo_root)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)
    if script_path is not None:
        runpy.run_path(str(script_path), run_name="__main__")
        return
    run_packaged_server()


if __name__ == "__main__":
    main()
