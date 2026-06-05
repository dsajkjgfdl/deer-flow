from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pymysql
from neo4j import GraphDatabase


MANAGED_GRAPHRAG_DIRS = ("cache", "hr_agent", "logs", "output")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


def quote_mysql_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def quote_cypher_name(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def log(message: str) -> None:
    print(message, flush=True)


def excel_path() -> Path:
    return Path(env("HR_EXCEL_PATH", "/app/hr-kg-source/基本信息_filled_new.xlsx")).resolve()


def import_script_path() -> Path:
    return Path(env("HR_IMPORT_SCRIPT", "/app/hr-kg-source/import_compressed.py")).resolve()


def graphrag_root_path() -> Path:
    return Path(env("GRAPHRAG_DATA_ROOT", "/app/byog_graphrag")).resolve()


def preflight() -> None:
    excel = excel_path()
    if not excel.is_file():
        raise RuntimeError(f"Excel file does not exist: {excel}")

    import_script = import_script_path()
    if not import_script.is_file():
        raise RuntimeError(f"Import script does not exist: {import_script}")

    graphrag_root = graphrag_root_path()
    if not graphrag_root.is_dir():
        raise RuntimeError(f"GRAPHRAG_DATA_ROOT does not exist: {graphrag_root}")

    log(f"Preflight OK: excel={excel}")
    log(f"Preflight OK: import_script={import_script}")
    log(f"Preflight OK: graphrag_root={graphrag_root}")


def run(command: list[str], *, cwd: Path | None = None) -> None:
    log("$ " + " ".join(command))
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def clear_mysql() -> None:
    host = env("MYSQL_HOST", "mysql")
    port = int(env("MYSQL_PORT", "3306"))
    user = env("MYSQL_USER", required=True)
    password = env("MYSQL_PASSWORD", "")
    database = env("MYSQL_DATABASE", required=True)
    charset = env("MYSQL_CHARSET", "utf8mb4")

    log(f"Clear MySQL schema: {user}@{host}:{port}/{database}")
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset=charset,
        autocommit=False,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            cursor.execute(
                """
                SELECT TABLE_NAME, TABLE_TYPE
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_TYPE DESC, TABLE_NAME
                """,
                (database,),
            )
            rows = cursor.fetchall()
            views = [name for name, table_type in rows if table_type == "VIEW"]
            tables = [name for name, table_type in rows if table_type != "VIEW"]
            for name in views:
                cursor.execute(f"DROP VIEW IF EXISTS {quote_mysql_identifier(name)}")
            for name in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {quote_mysql_identifier(name)}")
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
        log(f"MySQL cleared: tables={len(tables)} views={len(views)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def import_excel_to_mysql() -> None:
    excel = excel_path()
    import_script = import_script_path()

    command = [
        sys.executable,
        str(import_script),
        str(excel),
        "--host",
        env("MYSQL_HOST", "mysql"),
        "--port",
        env("MYSQL_PORT", "3306"),
        "--user",
        env("MYSQL_USER", required=True),
        "--password",
        env("MYSQL_PASSWORD", ""),
        "--database",
        env("MYSQL_DATABASE", required=True),
        "--charset",
        env("MYSQL_CHARSET", "utf8mb4"),
    ]
    run(command, cwd=import_script.parent)


def strict_sync_all() -> None:
    root = graphrag_root_path()
    command = [
        sys.executable,
        "-m",
        "byog_graphrag.cli",
        "strict-sync-all",
        "--root",
        str(root),
        "--mysql-host",
        env("MYSQL_HOST", "mysql"),
        "--mysql-port",
        env("MYSQL_PORT", "3306"),
        "--mysql-user",
        env("MYSQL_USER", required=True),
        "--mysql-database",
        env("MYSQL_DATABASE", required=True),
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
    if env("HR_REBUILD_DRY_RUN", "false").lower() in {"1", "true", "yes"}:
        command.append("--dry-run")
    run(command, cwd=root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild HR MySQL, Neo4j and GraphRAG data from one Excel file.")
    parser.add_argument("--force", action="store_true", help="Required because this clears MySQL, Neo4j and GraphRAG generated folders.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.force:
        raise RuntimeError("This rebuild is destructive. Re-run with --force.")

    log("HR KG rebuild start")
    preflight()
    clear_mysql()
    clear_neo4j()
    clear_graphrag_dirs()
    import_excel_to_mysql()
    strict_sync_all()
    log("HR KG rebuild complete")


if __name__ == "__main__":
    main()
