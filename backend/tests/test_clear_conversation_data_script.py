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


def _write_config(path: Path, sqlite_dir: Path, *, checkpointer: dict | None = None) -> None:
    config: dict = {
        "database": {"backend": "sqlite", "sqlite_dir": str(sqlite_dir)},
        "run_events": {"backend": "db"},
    }
    if checkpointer is not None:
        config["checkpointer"] = checkpointer
    path.write_text(yaml.safe_dump(config), encoding="utf-8")


def _seed_main_sqlite(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT);
            CREATE TABLE admin_audit_logs (id INTEGER PRIMARY KEY, action TEXT);
            CREATE TABLE runs (run_id TEXT PRIMARY KEY, thread_id TEXT);
            CREATE TABLE run_events (id INTEGER PRIMARY KEY, thread_id TEXT, run_id TEXT);
            CREATE TABLE feedback (feedback_id TEXT PRIMARY KEY, thread_id TEXT, run_id TEXT);
            CREATE TABLE channel_feedback_targets (id INTEGER PRIMARY KEY, thread_id TEXT, run_id TEXT);
            CREATE TABLE threads_meta (thread_id TEXT PRIMARY KEY, metadata_json TEXT);
            CREATE TABLE tool_audit_logs (id INTEGER PRIMARY KEY, thread_id TEXT, run_id TEXT);
            CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT);
            CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT);
            CREATE TABLE checkpoint_writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT);
            CREATE TABLE checkpoint_blobs (thread_id TEXT, checkpoint_ns TEXT, channel TEXT, version TEXT);
            CREATE TABLE checkpoint_migrations (v INTEGER PRIMARY KEY);
            INSERT INTO users VALUES ('u1', 'boss@example.com');
            INSERT INTO admin_audit_logs VALUES (1, 'login');
            INSERT INTO runs VALUES ('r1', 't1');
            INSERT INTO run_events VALUES (1, 't1', 'r1');
            INSERT INTO feedback VALUES ('f1', 't1', 'r1');
            INSERT INTO channel_feedback_targets VALUES (1, 't1', 'r1');
            INSERT INTO threads_meta VALUES ('t1', '{}');
            INSERT INTO tool_audit_logs VALUES (1, 't1', 'r1');
            INSERT INTO checkpoints VALUES ('t1', '', 'c1');
            INSERT INTO writes VALUES ('t1', '', 'c1');
            INSERT INTO checkpoint_writes VALUES ('t1', '', 'c1');
            INSERT INTO checkpoint_blobs VALUES ('t1', '', 'messages', '1');
            INSERT INTO checkpoint_migrations VALUES (1);
            """
        )


def _seed_checkpointer_sqlite(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT);
            CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT);
            INSERT INTO checkpoints VALUES ('legacy-thread', '', 'c1');
            INSERT INTO writes VALUES ('legacy-thread', '', 'c1');
            """
        )


def _count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def test_dry_run_reports_all_sql_targets_without_deleting_rows(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "data" / "deerflow.db"
    _write_config(config_path, db_path.parent)
    _seed_main_sqlite(db_path)

    exit_code = clear_script.main(["--config", str(config_path), "--project-root", str(tmp_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert "tool_audit_logs: 1" in output
    assert "writes: 1" in output
    assert _count(db_path, "users") == 1
    assert _count(db_path, "runs") == 1


def test_yes_clears_conversation_tables_but_preserves_non_conversation_tables(tmp_path):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "data" / "deerflow.db"
    _write_config(config_path, db_path.parent)
    _seed_main_sqlite(db_path)

    exit_code = clear_script.main(["--config", str(config_path), "--project-root", str(tmp_path), "--yes"])

    assert exit_code == 0
    assert _count(db_path, "users") == 1
    assert _count(db_path, "admin_audit_logs") == 1
    assert _count(db_path, "checkpoint_migrations") == 1
    for table in (
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
    ):
        assert _count(db_path, table) == 0


def test_yes_clears_independent_legacy_checkpointer_database(tmp_path):
    config_path = tmp_path / "config.yaml"
    main_db_path = tmp_path / "data" / "deerflow.db"
    legacy_db_path = tmp_path / ".deer-flow" / "checkpoints.db"
    _write_config(
        config_path,
        main_db_path.parent,
        checkpointer={"type": "sqlite", "connection_string": "checkpoints.db"},
    )
    _seed_main_sqlite(main_db_path)
    _seed_checkpointer_sqlite(legacy_db_path)

    exit_code = clear_script.main(["--config", str(config_path), "--project-root", str(tmp_path), "--yes"])

    assert exit_code == 0
    assert _count(legacy_db_path, "checkpoints") == 0
    assert _count(legacy_db_path, "writes") == 0


def test_yes_clears_all_existing_project_database_candidates(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"database": {"backend": "sqlite", "sqlite_dir": ".deer-flow/data"}}),
        encoding="utf-8",
    )
    root_db_path = tmp_path / ".deer-flow" / "data" / "deerflow.db"
    backend_db_path = tmp_path / "backend" / ".deer-flow" / "data" / "deerflow.db"
    _seed_main_sqlite(root_db_path)
    _seed_main_sqlite(backend_db_path)

    exit_code = clear_script.main(["--config", str(config_path), "--project-root", str(tmp_path), "--yes"])

    assert exit_code == 0
    assert _count(root_db_path, "runs") == 0
    assert _count(backend_db_path, "runs") == 0


def test_yes_removes_conversation_files_but_preserves_user_profile_and_agents(tmp_path):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "data" / "deerflow.db"
    home = tmp_path / ".deer-flow"
    legacy_thread_file = home / "threads" / "legacy-thread" / "user-data" / "outputs" / "answer.md"
    user_thread_file = home / "users" / "u1" / "threads" / "user-thread" / "user-data" / "uploads" / "input.txt"
    user_memory_file = home / "users" / "u1" / "memory.json"
    agent_config_file = home / "users" / "u1" / "agents" / "boss" / "config.yaml"
    channel_store_file = home / "channels" / "store.json"
    discord_store_file = home / "channels" / "discord_threads.json"
    _write_config(config_path, db_path.parent)
    _seed_main_sqlite(db_path)
    for path in (
        legacy_thread_file,
        user_thread_file,
        user_memory_file,
        agent_config_file,
        channel_store_file,
        discord_store_file,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep" if path in {user_memory_file, agent_config_file} else "conversation", encoding="utf-8")

    exit_code = clear_script.main(["--config", str(config_path), "--project-root", str(tmp_path), "--yes"])

    assert exit_code == 0
    assert not (home / "threads").exists()
    assert not (home / "users" / "u1" / "threads").exists()
    assert not channel_store_file.exists()
    assert not discord_store_file.exists()
    assert user_memory_file.read_text(encoding="utf-8") == "keep"
    assert agent_config_file.read_text(encoding="utf-8") == "keep"


def test_explicit_project_root_keeps_cleanup_plan_within_that_project(tmp_path):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "data" / "deerflow.db"
    _write_config(config_path, db_path.parent)
    _seed_main_sqlite(db_path)

    plan = clear_script.build_plan(config_path, project_root=tmp_path)

    scoped_paths = (*plan.sqlite_paths, *plan.thread_dirs, *plan.channel_state_files)
    assert scoped_paths
    assert all(path.is_relative_to(tmp_path.resolve()) for path in scoped_paths)


def test_omitted_database_section_uses_runtime_sqlite_default(tmp_path):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / ".deer-flow" / "data" / "deerflow.db"
    config_path.write_text("{}\n", encoding="utf-8")
    _seed_main_sqlite(db_path)

    plan = clear_script.build_plan(config_path, project_root=tmp_path)

    assert plan.database_backend == "sqlite"
    assert db_path.resolve() in plan.sqlite_paths


def test_powershell_wrapper_invokes_real_delete_mode():
    content = POWERSHELL_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "clear_conversation_data.py" in content
    assert "--yes" in content
