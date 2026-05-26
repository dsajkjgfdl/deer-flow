from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_repo_src() -> Path:
    repo_raw = os.getenv("GRAPHRAG_MCP_REPO")
    if not repo_raw:
        raise RuntimeError("GRAPHRAG_MCP_REPO is required")

    repo_root = Path(repo_raw).expanduser().resolve()
    src_dir = (repo_root / "src").resolve()
    if not src_dir.exists():
        raise RuntimeError(f"GRAPHRAG_MCP_REPO does not contain src/: {repo_root}")

    return src_dir


def ensure_repo_on_path() -> Path:
    src_dir = resolve_repo_src()
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    return src_dir


def main() -> None:
    ensure_repo_on_path()
    from graphrag_mcp.server import main as server_main

    server_main()


if __name__ == "__main__":
    main()
