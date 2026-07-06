from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONVERSATION_TABLES = (
    "channel_feedback_targets",
    "feedback",
    "tool_audit_logs",
    "run_events",
    "runs",
    "threads_meta",
    "writes",
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
)

CHANNEL_STATE_FILES = ("store.json", "discord_threads.json")


@dataclass(frozen=True)
class ClearPlan:
    database_backend: str
    checkpointer_backend: str | None
    sqlite_paths: tuple[Path, ...]
    thread_dirs: tuple[Path, ...]
    channel_state_files: tuple[Path, ...]


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


def _candidate_bases(config_path: Path, project_root: Path | None) -> tuple[Path, ...]:
    if project_root is not None:
        bases = [project_root, project_root / "backend"]
    else:
        bases = [Path.cwd(), config_path.parent, config_path.parent / "backend", _repo_root(), _repo_root() / "backend"]

    result: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        resolved = base.resolve()
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return tuple(result)


def _state_homes(config_path: Path, project_root: Path | None) -> tuple[Path, ...]:
    homes: list[Path] = []
    if project_root is None:
        if env_home := os.getenv("DEER_FLOW_HOME"):
            homes.append(Path(env_home).resolve())
    homes.extend((base / ".deer-flow").resolve() for base in _candidate_bases(config_path, project_root))

    result: list[Path] = []
    seen: set[Path] = set()
    for home in homes:
        if home not in seen:
            result.append(home)
            seen.add(home)
    return tuple(result)


def _sqlite_candidates(config_path: Path, sqlite_dir: str, project_root: Path | None) -> list[Path]:
    raw = Path(sqlite_dir)
    if raw.is_absolute():
        return [raw / "deerflow.db"]

    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in _candidate_bases(config_path, project_root):
        path = (base / raw / "deerflow.db").resolve()
        if path not in seen:
            candidates.append(path)
            seen.add(path)
    return candidates


def _resolve_sqlite_paths(config_path: Path, database_config: dict[str, Any], project_root: Path | None) -> tuple[Path, ...]:
    sqlite_dir = str(database_config.get("sqlite_dir") or ".deer-flow/data")
    candidates = _sqlite_candidates(config_path, sqlite_dir, project_root)
    existing = tuple(candidate for candidate in candidates if candidate.exists())
    return existing or (candidates[0],)


def _file_candidates(config_path: Path, raw_path: str, project_root: Path | None) -> tuple[Path, ...]:
    raw = Path(raw_path)
    if raw.is_absolute():
        return (raw.resolve(),)

    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in _candidate_bases(config_path, project_root):
        path = (base / raw).resolve()
        if path not in seen:
            candidates.append(path)
            seen.add(path)
    return tuple(candidates)


def _legacy_checkpointer_paths(
    config_path: Path,
    project_root: Path | None,
    checkpointer_config: dict[str, Any] | None,
) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if checkpointer_config is not None and str(checkpointer_config.get("type") or "") == "sqlite":
        connection_string = str(checkpointer_config.get("connection_string") or "store.db")
        if connection_string != ":memory:" and not connection_string.startswith("file:"):
            candidates.extend(_file_candidates(config_path, connection_string, project_root))
            candidates.extend(home / Path(connection_string).name for home in _state_homes(config_path, project_root))

    # Older DeerFlow versions commonly stored a standalone checkpointer here.
    candidates.extend(home / "checkpoints.db" for home in _state_homes(config_path, project_root))

    existing: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path.exists() and path not in seen:
            existing.append(path)
            seen.add(path)
    return tuple(existing)


def _thread_dirs(config_path: Path, project_root: Path | None) -> tuple[Path, ...]:
    dirs: list[Path] = []
    seen: set[Path] = set()
    for home in _state_homes(config_path, project_root):
        legacy_dir = (home / "threads").resolve()
        if legacy_dir not in seen:
            dirs.append(legacy_dir)
            seen.add(legacy_dir)

        users_dir = home / "users"
        if users_dir.exists():
            for user_dir in users_dir.iterdir():
                path = (user_dir / "threads").resolve()
                if user_dir.is_dir() and path not in seen:
                    dirs.append(path)
                    seen.add(path)
    return tuple(dirs)


def _channel_state_files(config_path: Path, project_root: Path | None) -> tuple[Path, ...]:
    files: list[Path] = []
    seen: set[Path] = set()
    for home in _state_homes(config_path, project_root):
        for name in CHANNEL_STATE_FILES:
            path = (home / "channels" / name).resolve()
            if path not in seen:
                files.append(path)
                seen.add(path)
    return tuple(files)


def _dedupe_paths(paths: list[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return tuple(result)


def build_plan(config_path: Path, project_root: Path | None = None) -> ClearPlan:
    config = _load_config(config_path)
    database_config = config.get("database") or {}
    checkpointer_config = config.get("checkpointer")
    if not isinstance(database_config, dict):
        raise ValueError("config.database must be a mapping")
    if checkpointer_config is not None and not isinstance(checkpointer_config, dict):
        raise ValueError("config.checkpointer must be a mapping")

    database_backend = str(database_config.get("backend") or "sqlite")
    sqlite_paths: list[Path] = []
    if database_backend == "sqlite":
        sqlite_paths.extend(_resolve_sqlite_paths(config_path, database_config, project_root))
    sqlite_paths.extend(_legacy_checkpointer_paths(config_path, project_root, checkpointer_config))

    return ClearPlan(
        database_backend=database_backend,
        checkpointer_backend=str(checkpointer_config.get("type") or "memory") if checkpointer_config is not None else None,
        sqlite_paths=_dedupe_paths(sqlite_paths),
        thread_dirs=_thread_dirs(config_path, project_root),
        channel_state_files=_channel_state_files(config_path, project_root),
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


def _count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for path in directory.rglob("*") if path.is_file())


def inspect_dirs(dirs: tuple[Path, ...]) -> dict[str, int]:
    return {str(path): _count_files(path) for path in dirs if path.exists()}


def clear_dirs(dirs: tuple[Path, ...]) -> dict[str, int]:
    counts = inspect_dirs(dirs)
    for raw_path in counts:
        path = Path(raw_path)
        if path.exists():
            shutil.rmtree(path)
    return counts


def inspect_files(files: tuple[Path, ...]) -> dict[str, int]:
    return {str(path): 1 for path in files if path.is_file()}


def clear_files(files: tuple[Path, ...]) -> dict[str, int]:
    counts = inspect_files(files)
    for raw_path in counts:
        path = Path(raw_path)
        if path.exists():
            path.unlink()
    return counts


def _print_counts(title: str, counts: dict[str, int]) -> None:
    print(title)
    if not counts:
        print("  (nothing found)")
        return
    for key, value in counts.items():
        print(f"  {key}: {value}")


def _print_sqlite_counts(title: str, counts_by_path: dict[str, dict[str, int]]) -> None:
    print(title)
    if not counts_by_path:
        print("  (nothing found)")
        return
    for path, counts in counts_by_path.items():
        print(f"  {path}")
        if not counts:
            print("    (no conversation tables found)")
            continue
        for table, value in counts.items():
            print(f"    {table}: {value}")


def run(plan: ClearPlan, *, yes: bool) -> int:
    if plan.database_backend not in {"memory", "sqlite"}:
        print(f"Unsupported database backend for this local cleanup script: {plan.database_backend}")
        return 2
    if plan.checkpointer_backend not in {None, "memory", "sqlite"}:
        print(f"Unsupported checkpointer backend for this local cleanup script: {plan.checkpointer_backend}")
        return 2

    sqlite_counts = {str(path): inspect_sqlite(path) for path in plan.sqlite_paths if path.exists()}
    if plan.sqlite_paths:
        for path in plan.sqlite_paths:
            print(f"SQLite database: {path}")
    elif plan.database_backend == "memory":
        print("Database backend is memory; no SQL tables to clear.")

    thread_counts = inspect_dirs(plan.thread_dirs)
    channel_counts = inspect_files(plan.channel_state_files)

    if not yes:
        print("DRY RUN: pass --yes to clear these records.")
        _print_sqlite_counts("SQL tables", sqlite_counts)
        _print_counts("Thread directories", thread_counts)
        _print_counts("Channel conversation state files", channel_counts)
        return 0

    print("Stop DeerFlow services before cleanup so open databases and in-memory channel sessions cannot restore deleted state.")
    cleared_sqlite = {str(path): clear_sqlite(path) for path in plan.sqlite_paths if path.exists()}
    cleared_threads = clear_dirs(plan.thread_dirs)
    cleared_channels = clear_files(plan.channel_state_files)

    _print_sqlite_counts("Cleared SQL rows", cleared_sqlite)
    _print_counts("Removed thread directories", cleared_threads)
    _print_counts("Removed channel conversation state files", cleared_channels)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear local DeerFlow conversation, run, checkpoint, feedback, audit, thread-file, and channel-session data."
    )
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
