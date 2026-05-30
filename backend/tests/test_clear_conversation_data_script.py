from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "backend" / "scripts" / "clear_conversation_data.py"
POWERSHELL_SCRIPT_PATH = REPO_ROOT / "scripts" / "clear-conversation-data.ps1"

spec = importlib.util.spec_from_file_location("clear_conversation_data", SCRIPT_PATH)
assert spec is not None
assert spec.loader is not None
clear_script = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = clear_script
spec.loader.exec_module(clear_script)


def _write_config(path: Path, sqlite_dir: Path, *, run_events_backend: str = "memory") -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "database": {"backend": "sqlite", "sqlite_dir": str(sqlite_dir)},
                "run_events": {"backend": run_events_backend},
            }
        ),
        encoding="utf-8",
    )


def _seed_sqlite(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT);
            CREATE TABLE runs (run_id TEXT PRIMARY KEY, thread_id TEXT);
            CREATE TABLE run_events (id INTEGER PRIMARY KEY, thread_id TEXT, run_id TEXT);
            CREATE TABLE feedback (feedback_id TEXT PRIMARY KEY, thread_id TEXT, run_id TEXT);
            CREATE TABLE threads_meta (thread_id TEXT PRIMARY KEY, metadata_json TEXT);
            CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT);
            CREATE TABLE checkpoint_writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT);
            CREATE TABLE checkpoint_blobs (thread_id TEXT, checkpoint_ns TEXT, channel TEXT, version TEXT);
            CREATE TABLE checkpoint_migrations (v INTEGER PRIMARY KEY);
            INSERT INTO users VALUES ('u1', 'boss@example.com');
            INSERT INTO runs VALUES ('r1', 't1');
            INSERT INTO run_events VALUES (1, 't1', 'r1');
            INSERT INTO feedback VALUES ('f1', 't1', 'r1');
            INSERT INTO threads_meta VALUES ('t1', '{}');
            INSERT INTO checkpoints VALUES ('t1', '', 'c1');
            INSERT INTO checkpoint_writes VALUES ('t1', '', 'c1');
            INSERT INTO checkpoint_blobs VALUES ('t1', '', 'messages', '1');
            INSERT INTO checkpoint_migrations VALUES (1);
            """
        )


def _count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_dry_run_reports_targets_without_deleting_sqlite_rows(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    sqlite_dir = tmp_path / "data"
    db_path = sqlite_dir / "deerflow.db"
    _write_config(config_path, sqlite_dir)
    _seed_sqlite(db_path)

    exit_code = clear_script.main(["--config", str(config_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert "feedback: 1" in output
    assert _count(db_path, "users") == 1
    assert _count(db_path, "feedback") == 1
    assert _count(db_path, "runs") == 1


def test_yes_clears_conversation_tables_but_preserves_users(tmp_path):
    config_path = tmp_path / "config.yaml"
    sqlite_dir = tmp_path / "data"
    db_path = sqlite_dir / "deerflow.db"
    _write_config(config_path, sqlite_dir)
    _seed_sqlite(db_path)

    exit_code = clear_script.main(["--config", str(config_path), "--yes"])

    assert exit_code == 0
    assert _count(db_path, "users") == 1
    for table in (
        "feedback",
        "run_events",
        "runs",
        "threads_meta",
        "checkpoints",
        "checkpoint_writes",
        "checkpoint_blobs",
    ):
        assert _count(db_path, table) == 0
    assert _count(db_path, "checkpoint_migrations") == 1


def test_yes_removes_jsonl_thread_history_when_configured(tmp_path):
    config_path = tmp_path / "config.yaml"
    sqlite_dir = tmp_path / "data"
    db_path = sqlite_dir / "deerflow.db"
    threads_dir = tmp_path / ".deer-flow" / "threads"
    run_file = threads_dir / "t1" / "runs" / "r1.jsonl"
    _write_config(config_path, sqlite_dir, run_events_backend="jsonl")
    _seed_sqlite(db_path)
    run_file.parent.mkdir(parents=True)
    run_file.write_text('{"thread_id":"t1","run_id":"r1"}\n', encoding="utf-8")

    exit_code = clear_script.main(
        [
            "--config",
            str(config_path),
            "--project-root",
            str(tmp_path),
            "--yes",
        ]
    )

    assert exit_code == 0
    assert not threads_dir.exists()


def test_powershell_wrapper_invokes_real_delete_mode():
    content = POWERSHELL_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "clear_conversation_data.py" in content
    assert "--yes" in content
