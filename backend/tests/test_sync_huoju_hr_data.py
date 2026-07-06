from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "deployment" / "hr-boss" / "sync_huoju_hr_data.py"


def load_sync_script():
    spec = importlib.util.spec_from_file_location("sync_huoju_hr_data_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sync_requires_force_for_destructive_graph_refresh() -> None:
    sync_script = load_sync_script()

    with pytest.raises(RuntimeError, match="Re-run with --force"):
        sync_script.main([])


def test_sync_runs_huoju_import_clean_and_byog_sync_in_order(monkeypatch, tmp_path: Path) -> None:
    sync_script = load_sync_script()
    apifox_dir = tmp_path / "apifox"
    apifox_dir.mkdir()
    (apifox_dir / "火炬hr.Apifox.json").write_text("{}", encoding="utf-8")
    (apifox_dir / "火炬token.Apifox.json").write_text("{}", encoding="utf-8")
    graphrag_root = tmp_path / "byog"
    graphrag_root.mkdir()

    for name, value in {
        "HUOJU_APIFOX_DIR": str(apifox_dir),
        "DEER_FLOW_PROJECT_ROOT": str(REPO_ROOT),
        "GRAPHRAG_DATA_ROOT": str(graphrag_root),
        "HUOJU_API_BASE_URL": "http://hr-api.local",
        "MYSQL_HOST": "mysql",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "hr",
        "MYSQL_PASSWORD": "secret",
        "MYSQL_DATABASE": "huoju_hr",
        "TEXT2CYPHER_NEO4J_URI": "bolt://neo4j:7687",
        "TEXT2CYPHER_NEO4J_USERNAME": "neo4j",
        "TEXT2CYPHER_NEO4J_PASSWORD": "neo4j-secret",
        "TEXT2CYPHER_NEO4J_DATABASE": "neo4j",
    }.items():
        monkeypatch.setenv(name, value)

    calls: list[str] = []
    monkeypatch.setattr(sync_script, "run", lambda command, cwd=None: calls.append(" ".join(command)))
    monkeypatch.setattr(sync_script, "clear_neo4j", lambda: calls.append("clear_neo4j"))
    monkeypatch.setattr(sync_script, "clear_graphrag_dirs", lambda: calls.append("clear_graphrag_dirs"))

    assert sync_script.main(["--force"]) == 0

    assert len(calls) == 5
    assert "import_huoju_hr_mysql.py" in calls[0]
    assert "--apifox" in calls[0]
    assert "火炬hr.Apifox.json" in calls[0]
    assert "--api-base-url http://hr-api.local" in calls[0]
    assert "--database huoju_hr" in calls[0]
    assert "clean_huoju_hr_mysql.py" in calls[1]
    assert "--database huoju_hr" in calls[1]
    assert calls[2:] == [
        "clear_neo4j",
        "clear_graphrag_dirs",
        " ".join(
            [
                sys.executable,
                "-m",
                "byog_graphrag.cli",
                "strict-sync-all",
                "--root",
                str(graphrag_root.resolve()),
                "--mysql-host",
                "mysql",
                "--mysql-port",
                "3306",
                "--mysql-user",
                "hr",
                "--mysql-database",
                "huoju_hr",
                "--mysql-password",
                "secret",
                "--neo4j-uri",
                "bolt://neo4j:7687",
                "--neo4j-user",
                "neo4j",
                "--neo4j-password",
                "neo4j-secret",
                "--neo4j-database",
                "neo4j",
            ]
        ),
    ]
