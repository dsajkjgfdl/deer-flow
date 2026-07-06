from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


MANAGED_GRAPHRAG_DIRS = ("cache", "hr_agent", "logs", "output")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


def log(message: str) -> None:
    print(message, flush=True)


def bool_env(name: str, default: str = "false") -> bool:
    return env(name, default).strip().lower() in {"1", "true", "yes", "on"}


def repo_root() -> Path:
    return Path(env("DEER_FLOW_PROJECT_ROOT", "/app")).resolve()


def backend_root() -> Path:
    return repo_root() / "backend"


def apifox_dir_path() -> Path:
    return Path(env("HUOJU_APIFOX_DIR", "/data/hr/apifox")).resolve()


def huoju_hr_apifox_path() -> Path:
    explicit = env("HUOJU_HR_APIFOX_PATH")
    if explicit:
        return Path(explicit).resolve()
    return (apifox_dir_path() / env("HUOJU_HR_APIFOX_FILE", "火炬hr.Apifox.json")).resolve()


def huoju_token_apifox_path() -> Path:
    explicit = env("HUOJU_TOKEN_APIFOX_PATH")
    if explicit:
        return Path(explicit).resolve()
    return (apifox_dir_path() / env("HUOJU_TOKEN_APIFOX_FILE", "火炬token.Apifox.json")).resolve()


def graphrag_root_path() -> Path:
    return Path(env("GRAPHRAG_DATA_ROOT", "/data/hr/graphrag/byog_graphrag")).resolve()


def mysql_database() -> str:
    return env("HUOJU_MYSQL_DATABASE", env("MYSQL_DATABASE", "huoju_hr")) or "huoju_hr"


def import_script_path() -> Path:
    return backend_root() / "scripts" / "import_huoju_hr_mysql.py"


def clean_script_path() -> Path:
    return backend_root() / "scripts" / "clean_huoju_hr_mysql.py"


def preflight() -> None:
    checks = {
        "Huoju HR Apifox export": huoju_hr_apifox_path(),
        "Huoju token Apifox export": huoju_token_apifox_path(),
        "GraphRAG root": graphrag_root_path(),
        "Huoju import script": import_script_path(),
        "Huoju clean script": clean_script_path(),
    }
    for label, path in checks.items():
        if label == "GraphRAG root":
            if not path.is_dir():
                raise RuntimeError(f"{label} does not exist: {path}")
        elif not path.is_file():
            raise RuntimeError(f"{label} does not exist: {path}")
        log(f"Preflight OK: {label}={path}")


def run(command: list[str], *, cwd: Path | None = None) -> None:
    log("$ " + " ".join(command))
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def build_import_command() -> list[str]:
    command = [
        sys.executable,
        str(import_script_path()),
        "--apifox",
        str(huoju_hr_apifox_path()),
        "--token-apifox",
        str(huoju_token_apifox_path()),
        "--api-base-url",
        env("HUOJU_API_BASE_URL", "http://192.168.180.51:31606"),
        "--mysql-host",
        env("MYSQL_HOST", "mysql"),
        "--mysql-port",
        env("MYSQL_PORT", "3306"),
        "--mysql-user",
        env("MYSQL_USER", required=True),
        "--mysql-password",
        env("MYSQL_PASSWORD", ""),
        "--database",
        mysql_database(),
        "--table-prefix",
        env("HUOJU_RAW_TABLE_PREFIX", "hr_"),
        "--timeout",
        env("HUOJU_API_TIMEOUT_SECONDS", "30"),
    ]
    api_token = env("HUOJU_API_TOKEN")
    if api_token:
        command.extend(["--api-token", api_token])
    if bool_env("HUOJU_IMPORT_APPEND"):
        command.append("--append")
    if bool_env("HUOJU_IMPORT_TRUST_ENV"):
        command.append("--trust-env")
    return command


def build_clean_command() -> list[str]:
    return [
        sys.executable,
        str(clean_script_path()),
        "--mysql-host",
        env("MYSQL_HOST", "mysql"),
        "--mysql-port",
        env("MYSQL_PORT", "3306"),
        "--mysql-user",
        env("MYSQL_USER", required=True),
        "--mysql-password",
        env("MYSQL_PASSWORD", ""),
        "--database",
        mysql_database(),
        "--raw-table-prefix",
        env("HUOJU_RAW_TABLE_PREFIX", "hr_"),
    ]


def quote_cypher_name(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def clear_neo4j() -> None:
    uri = env("BYOG_NEO4J_URI", env("TEXT2CYPHER_NEO4J_URI", "bolt://neo4j:7687"))
    user = env("BYOG_NEO4J_USERNAME", env("TEXT2CYPHER_NEO4J_USERNAME", "neo4j"))
    password = env("BYOG_NEO4J_PASSWORD", env("TEXT2CYPHER_NEO4J_PASSWORD", ""), required=True)
    database = env("BYOG_NEO4J_DATABASE", env("TEXT2CYPHER_NEO4J_DATABASE", "neo4j")) or None

    log(f"Clear Neo4j graph: {uri}/{database or ''}")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            before = session.run("MATCH (n) RETURN count(n) AS count").single()["count"]
            session.run("MATCH (n) DETACH DELETE n").consume()

            constraints = session.run("SHOW CONSTRAINTS YIELD name RETURN name").data()
            for row in constraints:
                session.run(f"DROP CONSTRAINT {quote_cypher_name(row['name'])} IF EXISTS").consume()

            indexes = session.run(
                "SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name"
            ).data()
            for row in indexes:
                session.run(f"DROP INDEX {quote_cypher_name(row['name'])} IF EXISTS").consume()

            log(
                "Neo4j cleared: "
                f"deleted_nodes={before} constraints={len(constraints)} indexes={len(indexes)}"
            )
    finally:
        driver.close()


def clear_graphrag_dirs() -> None:
    root = graphrag_root_path()
    if not root.exists():
        raise RuntimeError(f"GRAPHRAG_DATA_ROOT does not exist: {root}")
    for name in MANAGED_GRAPHRAG_DIRS:
        target = (root / name).resolve()
        if root not in target.parents:
            raise RuntimeError(f"Refusing to remove path outside GraphRAG root: {target}")
        if target.exists():
            log(f"Remove GraphRAG generated directory: {target}")
            shutil.rmtree(target)
        else:
            log(f"Skip missing GraphRAG generated directory: {target}")


def build_strict_sync_command() -> list[str]:
    command = [
        sys.executable,
        "-m",
        "byog_graphrag.cli",
        "strict-sync-all",
        "--root",
        str(graphrag_root_path()),
        "--mysql-host",
        env("MYSQL_HOST", "mysql"),
        "--mysql-port",
        env("MYSQL_PORT", "3306"),
        "--mysql-user",
        env("MYSQL_USER", required=True),
        "--mysql-database",
        mysql_database(),
        "--mysql-password",
        env("MYSQL_PASSWORD", ""),
        "--neo4j-uri",
        env("BYOG_NEO4J_URI", env("TEXT2CYPHER_NEO4J_URI", "bolt://neo4j:7687")),
        "--neo4j-user",
        env("BYOG_NEO4J_USERNAME", env("TEXT2CYPHER_NEO4J_USERNAME", "neo4j")),
        "--neo4j-password",
        env("BYOG_NEO4J_PASSWORD", env("TEXT2CYPHER_NEO4J_PASSWORD", ""), required=True),
        "--neo4j-database",
        env("BYOG_NEO4J_DATABASE", env("TEXT2CYPHER_NEO4J_DATABASE", "neo4j")),
    ]
    if bool_env("HUOJU_SYNC_DRY_RUN"):
        command.append("--dry-run")
    return command


def sync_huoju_hr_data() -> None:
    log("Huoju HR sync start")
    preflight()
    run(build_import_command(), cwd=backend_root())
    run(build_clean_command(), cwd=backend_root())
    clear_neo4j()
    clear_graphrag_dirs()
    run(build_strict_sync_command(), cwd=graphrag_root_path())
    log("Huoju HR sync complete")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Huoju HR API data into MySQL, then rebuild Neo4j and GraphRAG."
    )
    parser.add_argument("--force", action="store_true", help="Required because this refresh clears Neo4j and GraphRAG generated folders.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.force:
        raise RuntimeError("This sync clears Neo4j and GraphRAG generated folders. Re-run with --force.")
    sync_huoju_hr_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
