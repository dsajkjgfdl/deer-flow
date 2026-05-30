from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONVERSATION_TABLES = (
    "feedback",
    "run_events",
    "runs",
    "threads_meta",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
)


@dataclass(frozen=True)
class ClearPlan:
    database_backend: str
    sqlite_path: Path | None
    run_events_backend: str
    jsonl_threads_dirs: tuple[Path, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    cwd_config = Path.cwd() / "config.yaml"
    if cwd_config.exists():
        return cwd_config
    return _repo_root() / "config.yaml"


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def _sqlite_candidates(config_path: Path, sqlite_dir: str, project_root: Path | None) -> list[Path]:
    raw = Path(sqlite_dir)
    bases: list[Path] = []
    if raw.is_absolute():
        return [raw / "deerflow.db"]
    if project_root is not None:
        bases.extend([project_root, project_root / "backend"])
    bases.extend([Path.cwd(), config_path.parent, config_path.parent / "backend", _repo_root(), _repo_root() / "backend"])

    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        path = (base / raw / "deerflow.db").resolve()
        if path not in seen:
            candidates.append(path)
            seen.add(path)
    return candidates


def _resolve_sqlite_path(config_path: Path, database_config: dict[str, Any], project_root: Path | None) -> Path:
    sqlite_dir = str(database_config.get("sqlite_dir") or ".deer-flow/data")
    candidates = _sqlite_candidates(config_path, sqlite_dir, project_root)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _jsonl_threads_dirs(config_path: Path, project_root: Path | None) -> tuple[Path, ...]:
    bases = [project_root] if project_root is not None else []
    bases.extend([Path.cwd(), config_path.parent, config_path.parent / "backend", _repo_root(), _repo_root() / "backend"])
    dirs: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        path = (base / ".deer-flow" / "threads").resolve()
        if path not in seen:
            dirs.append(path)
            seen.add(path)
    return tuple(dirs)


def build_plan(config_path: Path, project_root: Path | None = None) -> ClearPlan:
    config = _load_config(config_path)
    database_config = config.get("database") or {}
    run_events_config = config.get("run_events") or {}
    if not isinstance(database_config, dict):
        raise ValueError("config.database must be a mapping")
    if not isinstance(run_events_config, dict):
        raise ValueError("config.run_events must be a mapping")

    database_backend = str(database_config.get("backend") or "memory")
    sqlite_path = None
    if database_backend == "sqlite":
        sqlite_path = _resolve_sqlite_path(config_path, database_config, project_root)

    return ClearPlan(
        database_backend=database_backend,
        sqlite_path=sqlite_path,
        run_events_backend=str(run_events_config.get("backend") or "memory"),
        jsonl_threads_dirs=_jsonl_threads_dirs(config_path, project_root),
    )


def _existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def inspect_sqlite(sqlite_path: Path) -> dict[str, int]:
    if not sqlite_path.exists():
        return {}
    with sqlite3.connect(sqlite_path) as conn:
        tables = _existing_tables(conn)
        return {table: _count_table(conn, table) for table in CONVERSATION_TABLES if table in tables}


def clear_sqlite(sqlite_path: Path) -> dict[str, int]:
    if not sqlite_path.exists():
        return {}
    with sqlite3.connect(sqlite_path) as conn:
        tables = _existing_tables(conn)
        counts = {table: _count_table(conn, table) for table in CONVERSATION_TABLES if table in tables}
        with conn:
            for table in CONVERSATION_TABLES:
                if table in tables:
                    conn.execute(f'DELETE FROM "{table}"')
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
        return counts


def _count_jsonl_files(threads_dir: Path) -> int:
    if not threads_dir.exists():
        return 0
    return sum(1 for path in threads_dir.rglob("*.jsonl") if path.is_file())


def inspect_jsonl(dirs: tuple[Path, ...]) -> dict[str, int]:
    return {str(path): _count_jsonl_files(path) for path in dirs if path.exists()}


def clear_jsonl(dirs: tuple[Path, ...]) -> dict[str, int]:
    counts = inspect_jsonl(dirs)
    for raw_path in counts:
        path = Path(raw_path)
        if path.exists():
            shutil.rmtree(path)
    return counts


def _print_counts(title: str, counts: dict[str, int]) -> None:
    print(title)
    if not counts:
        print("  (nothing found)")
        return
    for key, value in counts.items():
        print(f"  {key}: {value}")


def run(plan: ClearPlan, *, yes: bool) -> int:
    if plan.database_backend not in {"memory", "sqlite"}:
        print(f"Unsupported database backend for this local cleanup script: {plan.database_backend}")
        return 2

    sqlite_counts: dict[str, int] = {}
    if plan.sqlite_path is not None:
        sqlite_counts = inspect_sqlite(plan.sqlite_path)
        print(f"SQLite database: {plan.sqlite_path}")
    elif plan.database_backend == "memory":
        print("Database backend is memory; no SQL tables to clear.")

    jsonl_counts: dict[str, int] = {}
    if plan.run_events_backend == "jsonl":
        jsonl_counts = inspect_jsonl(plan.jsonl_threads_dirs)

    if not yes:
        print("DRY RUN: pass --yes to clear these records.")
        _print_counts("SQL tables", sqlite_counts)
        if plan.run_events_backend == "jsonl":
            _print_counts("JSONL thread files", jsonl_counts)
        return 0

    cleared_sqlite: dict[str, int] = {}
    if plan.sqlite_path is not None:
        cleared_sqlite = clear_sqlite(plan.sqlite_path)
    cleared_jsonl: dict[str, int] = {}
    if plan.run_events_backend == "jsonl":
        cleared_jsonl = clear_jsonl(plan.jsonl_threads_dirs)

    _print_counts("Cleared SQL rows", cleared_sqlite)
    if plan.run_events_backend == "jsonl":
        _print_counts("Removed JSONL files", cleared_jsonl)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clear local DeerFlow conversation, run, checkpoint, and feedback data.")
    parser.add_argument("--config", type=Path, default=_default_config_path(), help="Path to config.yaml.")
    parser.add_argument("--project-root", type=Path, default=None, help="Project root used to locate .deer-flow JSONL data.")
    parser.add_argument("--yes", action="store_true", help="Actually delete data. Without this flag the script is a dry run.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = args.config.resolve()
    project_root = args.project_root.resolve() if args.project_root is not None else None
    plan = build_plan(config_path, project_root=project_root)
    return run(plan, yes=args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
