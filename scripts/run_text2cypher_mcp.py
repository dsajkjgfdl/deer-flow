from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def resolve_repo_root() -> Path:
    raw = os.getenv("TEXT2CYPHER_REPO", "D:/study/my-mcp/text2cypher")
    repo_root = Path(raw).expanduser().resolve()
    if not repo_root.exists():
        raise RuntimeError(f"TEXT2CYPHER_REPO does not exist: {repo_root}")
    script_path = repo_root / "scripts" / "run_text2cypher_mcp.py"
    if script_path.exists():
        return repo_root

    worktrees_dir = repo_root / ".worktrees"
    if worktrees_dir.exists():
        candidates = sorted(worktrees_dir.glob("*/scripts/run_text2cypher_mcp.py"))
        if candidates:
            return candidates[0].parent.parent

    raise RuntimeError(f"Text2Cypher launcher not found under: {repo_root}")


def main() -> None:
    repo_root = resolve_repo_root()
    repo_path = str(repo_root)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)
    script_path = repo_root / "scripts" / "run_text2cypher_mcp.py"
    runpy.run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    main()
