#!/usr/bin/env python3
"""Import Huoju HR API data into local MySQL tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_APIFOX_PATH = Path("C:/Users/IT/Desktop/火炬hr.Apifox.json")
DEFAULT_TOKEN_APIFOX_PATH = Path("C:/Users/IT/Desktop/火炬token.Apifox.json")
DEFAULT_API_BASE_URL = "http://192.168.180.51:31606"
DEFAULT_DATABASE = "huoju_hr"
DEFAULT_TABLE_PREFIX = "hr_"
SKIPPED_ENDPOINT_PATHS = frozenset({"/bi-center/hr/api/interviewnotes"})
EXTRA_ENDPOINT_SPECS = (
    ("部门信息", "GET", "/bi-center/hr/api/organizationalstructure"),
)
TECHNICAL_COLUMNS = {"id", "source_endpoint", "source_row_hash", "fetched_at", "raw_payload"}
DATE_FIELD_MARKERS = ("日期", "时间", "年份", "年度", "date", "time", "year")


@dataclass(frozen=True)
class Endpoint:
    name: str
    method: str
    path: str


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    mysql_type: str


@dataclass(frozen=True)
class TokenRequest:
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str]
    data: dict[str, str]


def _walk_endpoints(node: Any, trail: list[str], endpoints: list[Endpoint]) -> None:
    if not isinstance(node, dict):
        return

    node_name = str(node.get("name") or "").strip()
    current_trail = [*trail, node_name] if node_name else trail
    api = node.get("api")
    if isinstance(api, dict):
        path = str(api.get("path") or "").strip()
        if path and path not in SKIPPED_ENDPOINT_PATHS:
            endpoints.append(
                Endpoint(
                    name="/".join(current_trail),
                    method=str(api.get("method") or "GET").upper(),
                    path=path,
                )
            )

    for key in ("apiCollection", "items", "children"):
        children = node.get(key)
        if isinstance(children, list):
            for child in children:
                _walk_endpoints(child, current_trail, endpoints)


def extract_endpoints(apifox_doc: dict[str, Any]) -> list[Endpoint]:
    endpoints: list[Endpoint] = []
    _walk_endpoints(apifox_doc, [], endpoints)
    return endpoints


def resolve_import_endpoints(apifox_doc: dict[str, Any]) -> list[Endpoint]:
    endpoints = extract_endpoints(apifox_doc)
    seen_paths = {endpoint.path for endpoint in endpoints}
    for name, method, path in EXTRA_ENDPOINT_SPECS:
        if path not in seen_paths and path not in SKIPPED_ENDPOINT_PATHS:
            endpoints.append(Endpoint(name=name, method=method, path=path))
            seen_paths.add(path)
    return endpoints


def endpoint_to_table_name(endpoint: Endpoint, *, table_prefix: str = DEFAULT_TABLE_PREFIX) -> str:
    leaf = endpoint.path.rstrip("/").split("/")[-1].strip().lower()
    normalized_leaf = re.sub(r"[^a-z0-9]+", "_", leaf).strip("_")
    normalized_prefix = re.sub(r"[^a-z0-9_]+", "_", table_prefix.lower()).strip("_")
    if normalized_prefix:
        normalized_prefix = f"{normalized_prefix}_"
    table_name = f"{normalized_prefix}{normalized_leaf}".strip("_")
    if not table_name:
        raise ValueError(f"Cannot derive table name from endpoint path: {endpoint.path}")
    quote_identifier(table_name)
    return table_name


def skipped_table_names(*, table_prefix: str = DEFAULT_TABLE_PREFIX) -> list[str]:
    return [
        endpoint_to_table_name(Endpoint(name="", method="GET", path=path), table_prefix=table_prefix)
        for path in sorted(SKIPPED_ENDPOINT_PATHS)
    ]


def extract_data_rows(response_json: Any) -> list[dict[str, Any]]:
    if not isinstance(response_json, dict):
        raise ValueError("API response must be a JSON object")
    data = response_json.get("data")
    if not isinstance(data, list):
        raise ValueError("API response data must be a list")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"API response data[{index}] must be an object")
    return data


def _is_date_like_string(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    patterns = (
        r"^\d{4}$",
        r"^\d{4}[-/]\d{1,2}$",
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$",
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?$",
    )
    return any(re.match(pattern, text) for pattern in patterns)


def _is_date_field(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in DATE_FIELD_MARKERS)


def _infer_mysql_type(name: str, values: Sequence[Any]) -> str:
    non_null_values = [value for value in values if value is not None]
    if not non_null_values:
        return "TEXT"
    if any(isinstance(value, (dict, list)) for value in non_null_values):
        return "JSON"
    if all(isinstance(value, bool) for value in non_null_values):
        return "TINYINT"
    if all(isinstance(value, int) and not isinstance(value, bool) for value in non_null_values):
        unique_values = set(non_null_values)
        if unique_values.issubset({0, 1}):
            return "TINYINT"
        return "BIGINT"
    if all(isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) for value in non_null_values):
        return "DECIMAL(18,4)"
    if all(isinstance(value, str) for value in non_null_values):
        if _is_date_field(name) or all(_is_date_like_string(value) for value in non_null_values):
            return "VARCHAR(32)"
        return "TEXT"
    return "TEXT"


def infer_columns(rows: Sequence[dict[str, Any]]) -> list[ColumnSpec]:
    ordered_names: list[str] = []
    values_by_name: dict[str, list[Any]] = {}
    for row in rows:
        for name, value in row.items():
            if name in TECHNICAL_COLUMNS:
                raise ValueError(f"API field conflicts with technical column name: {name}")
            if name not in values_by_name:
                ordered_names.append(name)
                values_by_name[name] = []
            values_by_name[name].append(value)
    return [ColumnSpec(name=name, mysql_type=_infer_mysql_type(name, values_by_name[name])) for name in ordered_names]


def quote_identifier(identifier: str) -> str:
    if not identifier:
        raise ValueError("SQL identifier cannot be empty")
    if "`" in identifier or "\x00" in identifier:
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    if any(ord(char) < 32 for char in identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f"`{identifier}`"


def _index_name(table_name: str, suffix: str) -> str:
    raw = f"{suffix}_{table_name}_row_hash"
    if len(raw) <= 64:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{suffix}_{digest}_row_hash"


def build_create_table_sql(table_name: str, columns: Sequence[ColumnSpec], endpoint: Endpoint) -> str:
    del endpoint
    table_identifier = quote_identifier(table_name)
    lines = [
        "  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT",
        "  `source_endpoint` VARCHAR(255) NOT NULL",
        "  `source_row_hash` CHAR(64) NOT NULL",
        "  `fetched_at` DATETIME(6) NOT NULL",
        "  `raw_payload` JSON NOT NULL",
    ]
    for column in columns:
        lines.append(f"  {quote_identifier(column.name)} {column.mysql_type} NULL")
    lines.extend(
        [
            "  PRIMARY KEY (`id`)",
            f"  UNIQUE KEY {quote_identifier(_index_name(table_name, 'uk'))} (`source_row_hash`)",
        ]
    )
    columns_sql = ",\n".join(lines)
    return (
        f"CREATE TABLE IF NOT EXISTS {table_identifier} (\n"
        f"{columns_sql}\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _row_hash(endpoint: Endpoint, row_json: str) -> str:
    return hashlib.sha256(f"{endpoint.path}\n{row_json}".encode("utf-8")).hexdigest()


def _mysql_value(column: ColumnSpec, value: Any) -> Any:
    if value is None:
        return None
    if column.mysql_type == "JSON":
        return _json_dumps(value)
    return value


def build_insert_rows(
    endpoint: Endpoint,
    columns: Sequence[ColumnSpec],
    rows: Sequence[dict[str, Any]],
    *,
    fetched_at: datetime | None = None,
) -> tuple[list[str], list[tuple[Any, ...]]]:
    timestamp = fetched_at or datetime.now()
    column_names = ["source_endpoint", "source_row_hash", "fetched_at", "raw_payload", *(column.name for column in columns)]
    values: list[tuple[Any, ...]] = []
    for row in rows:
        raw_payload = _json_dumps(row)
        values.append(
            (
                endpoint.path,
                _row_hash(endpoint, raw_payload),
                timestamp,
                raw_payload,
                *(_mysql_value(column, row.get(column.name)) for column in columns),
            )
        )
    return column_names, values


def build_insert_sql(table_name: str, column_names: Sequence[str]) -> str:
    quoted_columns = ", ".join(quote_identifier(name) for name in column_names)
    placeholders = ", ".join(["%s"] * len(column_names))
    updates = ", ".join(
        f"{quote_identifier(name)} = VALUES({quote_identifier(name)})"
        for name in column_names
        if name not in {"source_row_hash"}
    )
    return (
        f"INSERT INTO {quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )


def build_drop_table_sql(table_name: str) -> str:
    return f"DROP TABLE IF EXISTS {quote_identifier(table_name)}"


def load_apifox(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Apifox export must contain a JSON object: {path}")
    return data


def _walk_api_nodes(node: Any, trail: list[str] | None = None) -> Iterable[tuple[list[str], dict[str, Any], dict[str, Any]]]:
    trail = trail or []
    if not isinstance(node, dict):
        return
    node_name = str(node.get("name") or "").strip()
    current_trail = [*trail, node_name] if node_name else trail
    api = node.get("api")
    if isinstance(api, dict):
        yield current_trail, node, api
    for key in ("apiCollection", "items", "children"):
        children = node.get(key)
        if isinstance(children, list):
            for child in children:
                yield from _walk_api_nodes(child, current_trail)


def _enabled_examples(parameters: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    if not isinstance(parameters, list):
        return values
    for parameter in parameters:
        if not isinstance(parameter, dict) or parameter.get("enable") is False:
            continue
        name = str(parameter.get("name") or "").strip()
        if not name or parameter.get("example") is None:
            continue
        values[name] = str(parameter.get("example"))
    return values


def _token_candidate_score(name: str, params: dict[str, str], data: dict[str, str]) -> int:
    score = 0
    if "密码" in name and "token" in name.lower():
        score += 10
    if params.get("grant_type") == "password":
        score += 5
    if {"username", "password"}.issubset(data):
        score += 3
    if params.get("grant_type") == "refresh_token":
        score -= 10
    return score


def build_token_request_from_apifox(apifox_doc: dict[str, Any]) -> TokenRequest:
    candidates: list[tuple[int, TokenRequest]] = []
    for trail, node, api in _walk_api_nodes(apifox_doc):
        url = str(api.get("path") or "").strip()
        if not url or "/auth/oauth/token" not in url:
            continue
        parameters = api.get("parameters") if isinstance(api.get("parameters"), dict) else {}
        params = _enabled_examples(parameters.get("query"))
        headers = _enabled_examples(parameters.get("header"))
        request_body = api.get("requestBody") if isinstance(api.get("requestBody"), dict) else {}
        data = _enabled_examples(request_body.get("parameters"))
        name = str(node.get("name") or "/".join(trail))
        request = TokenRequest(
            method=str(api.get("method") or "POST").upper(),
            url=url,
            headers=headers,
            params=params,
            data=data,
        )
        candidates.append((_token_candidate_score(name, params, data), request))
    if not candidates:
        raise ValueError("No OAuth token endpoint found in token Apifox export")
    best_score, request = max(candidates, key=lambda item: item[0])
    if best_score <= 0:
        raise ValueError("No password-grant token endpoint found in token Apifox export")
    if not re.match(r"^https?://", request.url, flags=re.IGNORECASE):
        raise ValueError(f"Token endpoint URL must be absolute: {request.url}")
    return request


def extract_access_token(response_json: Any) -> str:
    if not isinstance(response_json, dict):
        raise ValueError("Token response must be a JSON object")
    containers = [response_json]
    data = response_json.get("data")
    if isinstance(data, dict):
        containers.append(data)
    for container in containers:
        for key in ("access_token", "accessToken", "token"):
            token = container.get(key)
            if isinstance(token, str) and token.strip():
                return token.strip()
    raise ValueError("Token response does not contain access_token")


def fetch_api_token(client: Any, *, request: TokenRequest) -> str:
    response = client.request(
        request.method,
        request.url,
        headers=request.headers,
        params=request.params,
        data=request.data,
    )
    response.raise_for_status()
    return extract_access_token(response.json())


def _authorization_header(token: str) -> str:
    token = token.strip()
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def build_endpoint_url(*, api_base_url: str, endpoint_path: str) -> str:
    if re.match(r"^https?://", endpoint_path, flags=re.IGNORECASE):
        return endpoint_path
    return f"{api_base_url.rstrip('/')}/{endpoint_path.lstrip('/')}"


def fetch_endpoint_json(client: Any, *, api_base_url: str, endpoint: Endpoint, token: str) -> Any:
    url = build_endpoint_url(api_base_url=api_base_url, endpoint_path=endpoint.path)
    response = client.request(
        endpoint.method,
        url,
        headers={"Authorization": _authorization_header(token)},
    )
    response.raise_for_status()
    return response.json()


def connect_mysql(*, host: str, port: int, user: str, password: str) -> Any:
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - exercised only without optional runtime dependency.
        raise RuntimeError("Missing dependency pymysql. Install backend dependencies before running this importer.") from exc

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=False,
    )


def prepare_database(connection: Any, database: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS {quote_identifier(database)} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(f"USE {quote_identifier(database)}")
    connection.commit()


def replace_table(connection: Any, table_name: str, create_sql: str, *, append: bool) -> None:
    with connection.cursor() as cursor:
        if not append:
            cursor.execute(f"DROP TABLE IF EXISTS {quote_identifier(table_name)}")
        cursor.execute(create_sql)
    connection.commit()


def drop_skipped_tables(connection: Any, *, table_prefix: str) -> None:
    table_names = skipped_table_names(table_prefix=table_prefix)
    if not table_names:
        return
    with connection.cursor() as cursor:
        for table_name in table_names:
            cursor.execute(build_drop_table_sql(table_name))
    connection.commit()


def insert_rows(connection: Any, table_name: str, column_names: Sequence[str], values: Sequence[tuple[Any, ...]]) -> int:
    if not values:
        return 0
    sql = build_insert_sql(table_name, column_names)
    with connection.cursor() as cursor:
        cursor.executemany(sql, values)
    connection.commit()
    return len(values)


def _print_dry_run(endpoint: Endpoint, table_name: str, rows: Sequence[dict[str, Any]], columns: Sequence[ColumnSpec]) -> None:
    print(f"{table_name} <- {endpoint.path} rows={len(rows)} fields={len(columns)}")
    for column in columns:
        print(f"  {column.name}: {column.mysql_type}")


def import_endpoint(
    *,
    connection: Any | None,
    endpoint: Endpoint,
    response_json: Any,
    table_prefix: str,
    append: bool,
    dry_run: bool,
) -> int:
    table_name = endpoint_to_table_name(endpoint, table_prefix=table_prefix)
    rows = extract_data_rows(response_json)
    columns = infer_columns(rows)
    create_sql = build_create_table_sql(table_name, columns, endpoint)
    if dry_run:
        _print_dry_run(endpoint, table_name, rows, columns)
        return len(rows)
    if connection is None:
        raise ValueError("A MySQL connection is required when dry_run is false")
    replace_table(connection, table_name, create_sql, append=append)
    column_names, values = build_insert_rows(endpoint, columns, rows)
    return insert_rows(connection, table_name, column_names, values)


def _env_default(name: str, default: str) -> str:
    return os.environ.get(name, default)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Huoju HR APIs and import records into local MySQL.")
    parser.add_argument("--apifox", type=Path, default=DEFAULT_APIFOX_PATH, help="Path to the Apifox export JSON.")
    parser.add_argument("--token-apifox", type=Path, default=DEFAULT_TOKEN_APIFOX_PATH, help="Path to the token Apifox export JSON.")
    parser.add_argument("--api-base-url", default=_env_default("HUOJU_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--api-token", help="Bearer token value; may omit the Bearer prefix. Overrides --token-apifox when set.")
    parser.add_argument("--mysql-host", default=_env_default("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(_env_default("MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=_env_default("MYSQL_USER", "root"))
    parser.add_argument("--mysql-password", default=os.environ.get("MYSQL_PASSWORD", "123456"))
    parser.add_argument("--database", default=_env_default("HUOJU_MYSQL_DATABASE", DEFAULT_DATABASE))
    parser.add_argument("--table-prefix", default=DEFAULT_TABLE_PREFIX)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--append", action="store_true", help="Keep existing tables and upsert by row hash.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch APIs and print inferred tables without writing MySQL.")
    parser.add_argument(
        "--trust-env",
        action="store_true",
        help="Let httpx read proxy and SSL settings from environment variables.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    apifox_doc = load_apifox(args.apifox)
    endpoints = resolve_import_endpoints(apifox_doc)
    if not endpoints:
        raise SystemExit(f"No API endpoints found in Apifox export: {args.apifox}")

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - exercised only without runtime dependency.
        raise RuntimeError("Missing dependency httpx. Install backend dependencies before running this importer.") from exc

    connection = None
    total_rows = 0
    try:
        with httpx.Client(timeout=args.timeout, trust_env=args.trust_env) as client:
            api_token = args.api_token
            if not api_token:
                token_apifox_doc = load_apifox(args.token_apifox)
                api_token = fetch_api_token(client, request=build_token_request_from_apifox(token_apifox_doc))
            if not args.dry_run:
                connection = connect_mysql(
                    host=args.mysql_host,
                    port=args.mysql_port,
                    user=args.mysql_user,
                    password=args.mysql_password,
                )
                prepare_database(connection, args.database)
                drop_skipped_tables(connection, table_prefix=args.table_prefix)
            for endpoint in endpoints:
                response_json = fetch_endpoint_json(
                    client,
                    api_base_url=args.api_base_url,
                    endpoint=endpoint,
                    token=api_token,
                )
                imported = import_endpoint(
                    connection=connection,
                    endpoint=endpoint,
                    response_json=response_json,
                    table_prefix=args.table_prefix,
                    append=args.append,
                    dry_run=args.dry_run,
                )
                total_rows += imported
                if not args.dry_run:
                    print(f"{endpoint_to_table_name(endpoint, table_prefix=args.table_prefix)}: imported {imported} rows")
    finally:
        if connection is not None:
            connection.close()

    print(f"TOTAL_ROWS={total_rows}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
