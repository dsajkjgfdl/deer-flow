from __future__ import annotations

import argparse
import ast
import inspect
import json
import os
import re
import tempfile
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "docs" / "evaluation" / "hr-boss"
DEFAULT_TRACKS = ("text2cypher.strict", "graphrag.logic")
TRACK_CHOICES = DEFAULT_TRACKS + ("boss.e2e", "term_resolution.strict")
DEFAULT_CUSTOM_TRACK_MCP_SERVERS = ["text2cypher", "hr-graphrag-qa"]
TEXT2CYPHER_SERVER = "text2cypher"
TEXT2CYPHER_ANSWER_TOOL = "text2cypher_answer_question"
XIYAN_TEXT2SQL_SERVER = "xiyan-text2sql"
XIYAN_TEXT2SQL_ANSWER_TOOL = f"{XIYAN_TEXT2SQL_SERVER}_answer_question"
TEXT2CYPHER_FAST_ROUTE = [TEXT2CYPHER_ANSWER_TOOL]
TEXT2CYPHER_TERM_ROUTE = ["text2cypher_resolve_terms"]
TEXT2CYPHER_LOW_LEVEL_ROUTE = [
    "text2cypher_prepare_schema",
    "text2cypher_get_schema",
    "text2cypher_generate_cypher",
    "text2cypher_validate_cypher",
    "text2cypher_execute_cypher",
]
TEXT2CYPHER_ROUTE = TEXT2CYPHER_FAST_ROUTE
TEXT2CYPHER_ROUTES = [TEXT2CYPHER_FAST_ROUTE, TEXT2CYPHER_LOW_LEVEL_ROUTE]
TERM_RESOLUTION_ROUTES = [TEXT2CYPHER_TERM_ROUTE, TEXT2CYPHER_FAST_ROUTE]
GRAPHRAG_ROUTES = [
    "hr-graphrag-qa_query_basic",
    "hr-graphrag-qa_query_local",
    "hr-graphrag-qa_query_global",
    "hr-graphrag-qa_query_drift",
]
TRACK_MCP_SERVERS = {
    "text2cypher.strict": ["text2cypher"],
    "term_resolution.strict": ["text2cypher"],
    "graphrag.logic": ["hr-graphrag-qa"],
    "boss.e2e": ["text2cypher", "hr-graphrag-qa"],
}
LogFn = Callable[[str], None]
ResultsUpdateFn = Callable[[list[dict[str, Any]]], None]
CYPHER_FIELD_NAMES = {"cypher", "generated_cypher", "normalized_cypher"}
CONVERSATION_MODES = ("single", "simulate")


def emit(log: LogFn | None, message: str) -> None:
    if log is not None:
        log(f"[hr-boss-eval] {message}")


def print_log(message: str) -> None:
    print(message, flush=True)


def track_file_stem(track: str) -> str:
    path = Path(track)
    if path.suffix == ".jsonl":
        return path.stem
    return track


def track_file_path(data_dir: Path, track: str) -> Path:
    path = Path(track)
    if path.suffix == ".jsonl":
        return path if path.is_absolute() else data_dir / path
    return data_dir / f"{track}.jsonl"


def load_records(data_dir: Path, tracks: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for track in tracks:
        path = track_file_path(data_dir, track)
        normalized_track = track_file_stem(track)
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            record["track"] = normalized_track
            records.append(record)
    return records


def expected_route_for(track: str) -> list[str]:
    if track == "text2cypher.strict":
        return TEXT2CYPHER_ROUTE
    if track == "graphrag.logic":
        return GRAPHRAG_ROUTES
    return []


def expected_routes_for(track: str) -> list[list[str]]:
    if track == "text2cypher.strict":
        return TEXT2CYPHER_ROUTES
    if track == "term_resolution.strict":
        return TERM_RESOLUTION_ROUTES
    if track == "graphrag.logic":
        return [[route] for route in GRAPHRAG_ROUTES]
    if track == "boss.e2e":
        return TEXT2CYPHER_ROUTES + [[route] for route in GRAPHRAG_ROUTES]
    return []


def is_subsequence(expected: list[str], observed: list[str]) -> bool:
    if not expected:
        return True

    position = 0
    for tool_name in observed:
        if tool_name == expected[position]:
            position += 1
            if position == len(expected):
                return True
    return False


def route_status_for(track: str, tool_calls: list[str]) -> str:
    expected_routes = expected_routes_for(track)
    if not expected_routes:
        return "not_applicable"
    if any(is_subsequence(expected, tool_calls) for expected in expected_routes):
        return "matched"
    return "unmatched"


def parse_tool_payload(content: Any) -> Any:
    if not isinstance(content, str):
        return content

    stripped = content.strip()
    if not stripped:
        return ""

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    try:
        return ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return content


def extract_cypher_trace(tool_name: str | None, source: str, payload: Any) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if not tool_name or not tool_name.startswith("text2cypher_"):
        return entries

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                next_path = f"{path}.{key}" if path else str(key)
                if key in CYPHER_FIELD_NAMES and isinstance(item, str) and item.strip():
                    entries.append(
                        {
                            "tool": tool_name,
                            "source": source,
                            "field": next_path,
                            "cypher": item.strip(),
                        }
                    )
                elif isinstance(item, (dict, list)):
                    walk(item, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]" if path else f"[{index}]")

    walk(payload, "")
    return entries


def select_generated_cypher(cypher_trace: list[dict[str, str]]) -> str | None:
    # Prefer the Cypher that was actually executed. Some runs first call the
    # fast answer tool, then repair or refine the query with the low-level
    # generate/validate/execute path; the final answer follows the executed
    # query, not necessarily the first generated query seen in the trace.
    for entry in reversed(cypher_trace):
        if (
            entry["tool"] == "text2cypher_execute_cypher"
            and entry["source"] == "tool_args"
            and entry["field"].endswith("cypher")
        ):
            return entry["cypher"]
    for entry in reversed(cypher_trace):
        if (
            entry["tool"] == "text2cypher_validate_cypher"
            and entry["source"] == "tool_args"
            and entry["field"].endswith("cypher")
        ):
            return entry["cypher"]
    for entry in reversed(cypher_trace):
        if entry["field"].endswith("generated_cypher"):
            return entry["cypher"]
    for entry in reversed(cypher_trace):
        if entry["field"].endswith("normalized_cypher"):
            return entry["cypher"]
    for entry in reversed(cypher_trace):
        if entry["field"].endswith("cypher"):
            return entry["cypher"]
    return None


def extract_term_resolution_trace(tool_name: str | None, source: str, payload: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not tool_name or not tool_name.startswith("text2cypher_"):
        return entries

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                next_path = f"{path}.{key}" if path else str(key)
                if key == "term_resolution" and isinstance(item, dict):
                    entries.append(
                        {
                            "tool": tool_name,
                            "source": source,
                            "field": next_path,
                            "term_resolution": item,
                        }
                    )
                elif isinstance(item, (dict, list)):
                    walk(item, next_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]" if path else f"[{index}]")

    walk(payload, "")
    return entries


def select_term_resolution(term_resolution_trace: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not term_resolution_trace:
        return None
    return term_resolution_trace[0]["term_resolution"]


class BossUserSimulator:
    def __init__(self, *, model_name: str | None = None, thinking_enabled: bool = False) -> None:
        from deerflow.models import create_chat_model

        self.model_name = model_name or "default"
        self._model = create_chat_model(name=model_name, thinking_enabled=thinking_enabled)

    def decide(self, *, record: dict[str, Any], history: list[dict[str, str]], latest_answer: str) -> dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = self._model.invoke(
            [
                SystemMessage(content=_boss_simulator_system_prompt()),
                HumanMessage(
                    content=json.dumps(
                        {
                            "original_question": record.get("question", ""),
                            "category": record.get("category", ""),
                            "expected": record.get("expected", ""),
                            "history": history,
                            "latest_agent_answer": latest_answer,
                        },
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        payload = _parse_simulator_json(_message_content_text(getattr(response, "content", "")))
        return _normalize_simulator_decision(payload)


def _boss_simulator_system_prompt() -> str:
    return (
        "You simulate the boss/user in an HR evaluation conversation. "
        "You are not a judge. Only provide missing business criteria when the agent asks a clarification question. "
        "If the agent has already answered, or says data is insufficient, stop. "
        "Return strict JSON only: {\"should_continue\": true|false, \"reply\": \"...\", \"reason\": \"...\"}. "
        "Replies should be brief and concrete, like a real boss."
    )


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("output_text")
                if text:
                    parts.append(str(text))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def _extract_clarification_text(args: Any) -> str:
    if not isinstance(args, dict):
        return ""

    question = str(args.get("question") or "").strip()
    context = str(args.get("context") or "").strip()
    options = args.get("options") or []

    parts: list[str] = []
    if context:
        parts.append(context)
    if question:
        parts.append(question)
    if isinstance(options, list):
        option_lines = [f"{index}. {option}" for index, option in enumerate(options, 1) if str(option).strip()]
        if option_lines:
            parts.extend(option_lines)

    return "\n".join(parts).strip()


def _parse_simulator_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = _parse_simulator_json_loose(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Simulator response must be a JSON object")
    return payload


def _parse_simulator_json_loose(text: str) -> dict[str, Any]:
    should_continue_match = re.search(r'"should_continue"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
    reply = _extract_loose_json_string_field(text, "reply")
    reason = _extract_loose_json_string_field(text, "reason")
    if should_continue_match is None and reply is None and reason is None:
        raise ValueError("Simulator response must be a JSON object")
    return {
        "should_continue": bool(should_continue_match and should_continue_match.group(1).lower() == "true"),
        "reply": reply or "",
        "reason": reason or "",
    }


def _extract_loose_json_string_field(text: str, field_name: str) -> str | None:
    field_pattern = re.escape(field_name)
    pattern = rf'"{field_pattern}"\s*:\s*"(.*?)(?=",\s*"(?:should_continue|reply|reason)"\s*:|"\s*}}\s*$)'
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        return None
    return match.group(1).replace('\\"', '"').strip()


def _normalize_simulator_decision(payload: dict[str, Any]) -> dict[str, Any]:
    should_continue = payload.get("should_continue") is True
    reply = str(payload.get("reply") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if should_continue and not reply:
        should_continue = False
        reason = reason or "Simulator did not provide a reply."
    return {"should_continue": should_continue, "reply": reply, "reason": reason}


def _turn_requests_clarification(turn_entry: dict[str, Any]) -> bool:
    term_resolution = turn_entry.get("term_resolution")
    if isinstance(term_resolution, dict) and term_resolution.get("needs_clarification"):
        return True

    answer = str(turn_entry.get("answer") or "")
    if "?" not in answer and "？" not in answer:
        return False
    clarification_markers = (
        "请确认",
        "需要确认",
        "跟您确认",
        "需要跟您确认",
        "您是想",
        "您想",
        "想按哪个",
        "哪个口径",
        "具体口径",
        "还是指定",
        "请您明确",
        "需要补充",
        "补充信息",
    )
    return any(marker in answer for marker in clarification_markers)


def _reconcile_simulator_decision(decision: dict[str, Any], turn_entry: dict[str, Any]) -> dict[str, Any]:
    if decision["should_continue"] or not decision["reply"]:
        return decision
    if _simulator_reply_is_stop_ack(decision["reply"]):
        return decision
    if not _turn_requests_clarification(turn_entry):
        return decision

    reconciled = dict(decision)
    reconciled["should_continue"] = True
    reason = reconciled["reason"]
    suffix = "runner corrected should_continue to true because the agent asked for clarification and simulator supplied a reply."
    reconciled["reason"] = f"{reason} {suffix}".strip()
    return reconciled


def _simulator_reply_is_stop_ack(reply: str) -> bool:
    normalized = re.sub(r"[\s。.!！?？,，、；;：:~～]", "", reply).lower()
    stop_exact = {
        "不用了",
        "不用了谢谢",
        "不用谢谢",
        "不需要",
        "不需要了",
        "谢谢",
        "好的",
        "好的清楚了",
        "好清楚了",
        "清楚了",
        "明白了",
        "好的明白了",
        "好的知道了",
        "知道了",
        "收到了",
        "可以了",
        "够了",
        "没了",
        "先这样",
    }
    if normalized in stop_exact:
        return True
    stop_prefixes = ("不用", "不需要", "先不用", "不用看", "不用查", "暂时不用", "可以了", "够了", "先这样")
    return any(normalized.startswith(prefix) and len(normalized) <= len(prefix) + 4 for prefix in stop_prefixes)


def mcp_servers_for_tracks(
    tracks: list[str] | tuple[str, ...],
    *,
    include_xiyan_sql: bool = False,
) -> list[str]:
    server_names: list[str] = []
    for track in tracks:
        normalized_track = track_file_stem(track)
        required_servers = TRACK_MCP_SERVERS.get(
            normalized_track,
            DEFAULT_CUSTOM_TRACK_MCP_SERVERS,
        )
        for server_name in required_servers:
            if server_name not in server_names:
                server_names.append(server_name)
    if include_xiyan_sql and XIYAN_TEXT2SQL_SERVER not in server_names:
        server_names.append(XIYAN_TEXT2SQL_SERVER)
    return server_names


def write_restricted_extensions_config(source_path: Path, target_path: Path, server_names: list[str]) -> None:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    all_servers = source.get("mcpServers", {})
    missing = [server_name for server_name in server_names if server_name not in all_servers]
    if missing:
        raise ValueError(f"Missing MCP server(s) in {source_path}: {', '.join(missing)}")

    restricted = {
        **source,
        "mcpServers": {server_name: all_servers[server_name] for server_name in server_names},
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(restricted, ensure_ascii=False, indent=2), encoding="utf-8")


def configure_restricted_mcp(
    tracks: list[str],
    *,
    log: LogFn | None,
    include_xiyan_sql: bool = False,
) -> tempfile.TemporaryDirectory[str] | None:
    server_names = mcp_servers_for_tracks(tracks, include_xiyan_sql=include_xiyan_sql)
    emit(log, f"required_mcp_servers={','.join(server_names) or 'none'}")
    if not server_names:
        return None

    from deerflow.config.extensions_config import ExtensionsConfig, reset_extensions_config
    from deerflow.mcp.cache import reset_mcp_tools_cache

    source_path = ExtensionsConfig.resolve_config_path()
    if source_path is None:
        raise FileNotFoundError("No extensions_config.json found; cannot configure required MCP servers.")

    temp_dir = tempfile.TemporaryDirectory(prefix="hr-boss-eval-")
    target_path = Path(temp_dir.name) / "extensions_config.json"
    write_restricted_extensions_config(source_path, target_path, server_names)
    os.environ["DEER_FLOW_EXTENSIONS_CONFIG_PATH"] = str(target_path)
    reset_extensions_config()
    reset_mcp_tools_cache()
    emit(log, f"restricted_extensions_config={target_path}")
    return temp_dir


def select_records(records: list[dict[str, Any]], ids: set[str] | None, limit: int | None) -> list[dict[str, Any]]:
    selected = [record for record in records if ids is None or record["id"] in ids]
    if limit is not None:
        selected = selected[:limit]
    return selected


def get_cached_mcp_tools_compat(*, server_names: list[str] | None = None) -> list[Any]:
    from deerflow.mcp.cache import get_cached_mcp_tools

    if server_names is not None:
        parameters = inspect.signature(get_cached_mcp_tools).parameters
        supports_server_names = "server_names" in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        if supports_server_names:
            return get_cached_mcp_tools(server_names=server_names)

    return get_cached_mcp_tools()


def cleanup_mcp_eval_resources(
    restricted_mcp_temp_dir: tempfile.TemporaryDirectory[str] | None,
    *,
    log: LogFn | None,
) -> None:
    try:
        from deerflow.mcp.cache import reset_mcp_tools_cache

        reset_mcp_tools_cache()
        emit(log, "mcp resources cleaned up")
    except Exception as exc:  # pragma: no cover - defensive cleanup path.
        emit(log, f"mcp cleanup failed: {type(exc).__name__}: {exc}")

    if restricted_mcp_temp_dir is not None:
        try:
            restricted_mcp_temp_dir.cleanup()
            emit(log, "restricted mcp temp dir cleaned up")
        except Exception as exc:  # pragma: no cover - defensive cleanup path.
            emit(log, f"restricted mcp temp dir cleanup failed: {type(exc).__name__}: {exc}")


def preload_mcp_eval_tools(*, log: LogFn | None) -> None:
    tools = get_cached_mcp_tools_compat()
    emit(log, f"preloaded_mcp_tools={len(tools)}")


class Text2CypherDebugMcpRunner:
    def __init__(
        self,
        *,
        max_rows: int = 100,
        auto_repair: bool = True,
        tool_name: str = TEXT2CYPHER_ANSWER_TOOL,
    ) -> None:
        self.max_rows = max_rows
        self.auto_repair = auto_repair
        self.tool_name = tool_name
        self._tool: Any | None = None

    def answer_question(self, question: str) -> dict[str, Any]:
        tool = self._get_tool()
        args = {
            "question": question,
            "max_rows": self.max_rows,
            "auto_repair": self.auto_repair,
            "include_debug": True,
        }
        if hasattr(tool, "invoke"):
            return unwrap_mcp_text_payload(tool.invoke(args))
        if getattr(tool, "func", None) is not None:
            return unwrap_mcp_text_payload(tool.func(**args))
        if getattr(tool, "coroutine", None) is not None:
            import asyncio

            return unwrap_mcp_text_payload(asyncio.run(tool.coroutine(**args)))
        raise RuntimeError(f"Text2Cypher MCP tool is not invokable: {self.tool_name}")

    def _get_tool(self) -> Any:
        if self._tool is not None:
            return self._tool

        tools = get_cached_mcp_tools_compat(server_names=[TEXT2CYPHER_SERVER])
        for tool in tools:
            if getattr(tool, "name", "") == self.tool_name:
                self._tool = tool
                return tool

        available = sorted(
            getattr(tool, "name", "")
            for tool in tools
            if str(getattr(tool, "name", "")).startswith("text2cypher_")
        )
        available_text = ", ".join(available) if available else "none"
        raise RuntimeError(f"Missing Text2Cypher MCP tool: {self.tool_name}; available Text2Cypher tools: {available_text}")


class XiYanSqlMcpRunner:
    def __init__(
        self,
        *,
        database_id: str = "mysql",
        max_rows: int = 100,
        auto_repair: bool = True,
        tool_name: str = XIYAN_TEXT2SQL_ANSWER_TOOL,
    ) -> None:
        self.database_id = database_id
        self.max_rows = max_rows
        self.auto_repair = auto_repair
        self.tool_name = tool_name
        self._tool: Any | None = None

    def answer_question(self, question: str) -> dict[str, Any]:
        tool = self._get_tool()
        args = {
            "database_id": self.database_id,
            "question": question,
            "max_rows": self.max_rows,
            "auto_repair": self.auto_repair,
        }
        if hasattr(tool, "invoke"):
            return parse_tool_payload(tool.invoke(args))
        if getattr(tool, "func", None) is not None:
            return parse_tool_payload(tool.func(**args))
        if getattr(tool, "coroutine", None) is not None:
            import asyncio

            return parse_tool_payload(asyncio.run(tool.coroutine(**args)))
        raise RuntimeError(f"XiYan SQL MCP tool is not invokable: {self.tool_name}")

    def _get_tool(self) -> Any:
        if self._tool is not None:
            return self._tool

        tools = get_cached_mcp_tools_compat(server_names=[XIYAN_TEXT2SQL_SERVER])
        for tool in tools:
            if getattr(tool, "name", "") == self.tool_name:
                self._tool = tool
                return tool

        available = sorted(
            getattr(tool, "name", "")
            for tool in tools
            if str(getattr(tool, "name", "")).startswith(f"{XIYAN_TEXT2SQL_SERVER}_")
        )
        available_text = ", ".join(available) if available else "none"
        raise RuntimeError(f"Missing XiYan SQL MCP tool: {self.tool_name}; available XiYan tools: {available_text}")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def unwrap_mcp_text_payload(value: Any) -> Any:
    payload = parse_tool_payload(value)
    if not isinstance(payload, list):
        return payload

    for item in payload:
        text = None
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content")
        elif hasattr(item, "text"):
            text = getattr(item, "text")

        if not isinstance(text, str) or not text.strip():
            continue

        parsed = parse_tool_payload(text)
        if isinstance(parsed, dict):
            return parsed

    return payload


def normalize_xiyan_sql_result(raw_result: Any) -> dict[str, Any]:
    payload = unwrap_mcp_text_payload(raw_result)
    if not isinstance(payload, dict):
        return {
            "execution_success": False,
            "error": f"Unexpected XiYan SQL result type: {type(payload).__name__}",
            "raw": json_safe(payload),
        }

    payload = json_safe(payload)
    generation = payload.get("generation") if isinstance(payload.get("generation"), dict) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    sql = payload.get("sql") or generation.get("sql") or execution.get("sql") or ""
    error = (
        execution.get("error_message")
        or validation.get("error_message")
        or payload.get("error_message")
        or payload.get("error")
    )

    return {
        "database_id": payload.get("database_id"),
        "question": payload.get("question"),
        "sql": sql,
        "repair_attempted": payload.get("repair_attempted"),
        "validation_valid": validation.get("valid"),
        "execution_success": execution.get("success"),
        "columns": execution.get("columns") or [],
        "rows": execution.get("rows") or execution.get("records") or [],
        "row_count": execution.get("row_count"),
        "truncated": execution.get("truncated"),
        "error": error,
        "validation": validation,
        "execution": execution,
    }


def run_xiyan_sql_question(
    *,
    question: str,
    xiyan_sql_runner: Any,
    record_id: str,
    rnd: int,
    log: LogFn | None = None,
) -> dict[str, Any]:
    emit(log, f"case {record_id} r{rnd} xiyan_sql_start")
    try:
        result = normalize_xiyan_sql_result(xiyan_sql_runner.answer_question(question))
    except Exception as exc:  # pragma: no cover - exercised manually against live MCP.
        result = {
            "question": question,
            "execution_success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    emit(
        log,
        f"case {record_id} r{rnd} xiyan_sql_done "
        f"success={result.get('execution_success')} rows={result.get('row_count')} error={result.get('error') or 'none'}",
    )
    return result


def start_xiyan_sql_question(
    *,
    question: str,
    xiyan_sql_runner: Any,
    record_id: str,
    rnd: int,
    log: LogFn | None = None,
) -> tuple[Future[dict[str, Any]], ThreadPoolExecutor]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hr-boss-xiyan-sql")
    future = executor.submit(
        run_xiyan_sql_question,
        question=question,
        xiyan_sql_runner=xiyan_sql_runner,
        record_id=record_id,
        rnd=rnd,
        log=log,
    )
    return future, executor


def collect_xiyan_sql_question(job: tuple[Future[dict[str, Any]], ThreadPoolExecutor]) -> dict[str, Any]:
    future, executor = job
    try:
        return future.result()
    finally:
        executor.shutdown(wait=True)


def select_text2cypher_debug_question(record: dict[str, Any], message: str, term_resolution: dict[str, Any] | None) -> str:
    if isinstance(term_resolution, dict):
        question = term_resolution.get("question") or term_resolution.get("normalized_question")
        if isinstance(question, str) and question.strip():
            return question.strip()

    record_question = record.get("question")
    if isinstance(record_question, str) and record_question.strip():
        return record_question.strip()

    return message


def run_turn(
    *,
    record: dict[str, Any],
    client: Any,
    message: str,
    thread_id: str,
    rnd: int,
    turn_num: int,
    log: LogFn | None = None,
    seen_message_ids: set[str] | None = None,
    text2cypher_debug_runner: Any | None = None,
) -> dict[str, Any]:
    answer = ""
    clarification_answer = ""
    ai_text_by_id: dict[str, str] = {}
    ai_text_order: list[str] = []
    ai_ids_with_tool_calls: set[str] = set()
    hidden_ai_ids: set[str] = set()
    prior_message_ids = set(seen_message_ids or ())
    observed_message_ids: set[str] = set()
    tool_calls: list[str] = []
    cypher_trace: list[dict[str, str]] = []
    term_resolution_trace: list[dict[str, Any]] = []
    error = None
    event_count = 0

    try:
        if hasattr(client, "_get_runnable_config") and hasattr(client, "_ensure_agent"):
            emit(log, f"case {record['id']} r{rnd} ensure_agent_start")
            config = client._get_runnable_config(thread_id)
            client._ensure_agent(config)
            emit(log, f"case {record['id']} r{rnd} ensure_agent_done")

        stream = iter(client.stream(message, thread_id=thread_id))
        emit(log, f"case {record['id']} r{rnd} stream_iterator_created")

        while True:
            emit(log, f"case {record['id']} r{rnd} waiting_event next_index={event_count + 1}")
            try:
                event = next(stream)
            except StopIteration:
                emit(log, f"case {record['id']} r{rnd} stream_exhausted events={event_count}")
                break

            event_count += 1
            if event_count == 1:
                emit(log, f"case {record['id']} r{rnd} first_event type={event.type}")

            if event.type != "messages-tuple":
                continue

            event_data = event.data
            raw_message_id = event_data.get("id")
            message_id = str(raw_message_id) if raw_message_id else None
            if message_id and message_id in prior_message_ids:
                continue
            if message_id:
                observed_message_ids.add(message_id)

            ai_message_key = message_id or "__default_ai__"

            for call in event.data.get("tool_calls", []) or []:
                ai_ids_with_tool_calls.add(ai_message_key)
                name = call.get("name")
                if name:
                    tool_calls.append(name)
                    args_payload = call.get("args", {})
                    if name == "ask_clarification":
                        clarification_text = _extract_clarification_text(args_payload)
                        if clarification_text:
                            clarification_answer = clarification_text
                            emit(log, f"case {record['id']} r{rnd} clarification_answer chars={len(clarification_answer)}")
                    cypher_trace.extend(extract_cypher_trace(name, "tool_args", args_payload))
                    term_resolution_trace.extend(extract_term_resolution_trace(name, "tool_args", args_payload))
                    emit(log, f"case {record['id']} r{rnd} tool_call={name}")

            if event_data.get("type") == "tool":
                tool_name = event_data.get("name")
                if tool_name == "ask_clarification":
                    clarification_text = _message_content_text(event_data.get("content", "")).strip()
                    if clarification_text:
                        clarification_answer = clarification_text
                        emit(log, f"case {record['id']} r{rnd} clarification_answer chars={len(clarification_answer)}")
                payload = parse_tool_payload(event_data.get("content", ""))
                extracted = extract_cypher_trace(tool_name, "tool_result", payload)
                cypher_trace.extend(extracted)
                term_resolution_extracted = extract_term_resolution_trace(tool_name, "tool_result", payload)
                term_resolution_trace.extend(term_resolution_extracted)
                if extracted:
                    emit(log, f"case {record['id']} r{rnd} captured_cypher tool={tool_name} count={len(extracted)}")
                if term_resolution_extracted:
                    emit(
                        log,
                        f"case {record['id']} r{rnd} captured_term_resolution "
                        f"tool={tool_name} count={len(term_resolution_extracted)}",
                    )

            if event_data.get("type") == "ai" and event_data.get("content"):
                chunk = _message_content_text(event_data["content"])
                if ai_message_key not in ai_text_by_id:
                    ai_text_order.append(ai_message_key)
                    ai_text_by_id[ai_message_key] = ""
                ai_text_by_id[ai_message_key] += chunk

                additional_kwargs = event_data.get("additional_kwargs") or {}
                message_name = str(event_data.get("name") or "")
                if (
                    additional_kwargs.get("hide_from_ui") is True
                    or message_name in {"summary", "loop_warning", "todo_reminder", "todo_completion_reminder"}
                    or ai_text_by_id[ai_message_key].lstrip().startswith("## SESSION INTENT")
                ):
                    hidden_ai_ids.add(ai_message_key)

                emit(
                    log,
                    f"case {record['id']} r{rnd} answer_chunk id={ai_message_key} "
                    f"chars={len(chunk)} total_chars={len(ai_text_by_id[ai_message_key])}",
                )
    except Exception as exc:  # pragma: no cover - exercised manually against live services.
        error = f"{type(exc).__name__}: {exc}"
        emit(log, f"case {record['id']} r{rnd} error={error}")

    for ai_message_key in reversed(ai_text_order):
        if ai_message_key in ai_ids_with_tool_calls or ai_message_key in hidden_ai_ids:
            continue
        candidate = ai_text_by_id.get(ai_message_key, "")
        if candidate:
            answer = candidate
            break
    if not answer:
        answer = clarification_answer

    if seen_message_ids is not None:
        seen_message_ids.update(observed_message_ids)

    term_resolution = select_term_resolution(term_resolution_trace)
    generated_cypher = select_generated_cypher(cypher_trace)
    if generated_cypher is None and text2cypher_debug_runner is not None and TEXT2CYPHER_ANSWER_TOOL in tool_calls:
        debug_question = select_text2cypher_debug_question(record, message, term_resolution)
        try:
            debug_payload = text2cypher_debug_runner.answer_question(debug_question)
            debug_trace = extract_cypher_trace(TEXT2CYPHER_ANSWER_TOOL, "debug_tool_result", debug_payload)
            generated_cypher = select_generated_cypher(debug_trace)
            if generated_cypher:
                emit(log, f"case {record['id']} r{rnd} captured_debug_cypher chars={len(generated_cypher)}")
            else:
                emit(log, f"case {record['id']} r{rnd} debug_cypher_missing")
        except Exception as exc:  # pragma: no cover - defensive path for live MCP failures.
            emit(log, f"case {record['id']} r{rnd} debug_cypher_error={type(exc).__name__}: {exc}")

    turn_entry = {
        "turn": turn_num,
        "user_message": message,
        "answer": answer,
        "generated_cypher": generated_cypher,
        "tool_calls": tool_calls,
        "error": error,
        "event_count": event_count,
    }
    if term_resolution is not None:
        turn_entry["term_resolution"] = term_resolution
    return turn_entry


def run_records(
    records: list[dict[str, Any]],
    client: Any,
    *,
    thread_prefix: str,
    rounds: int = 1,
    conversation_mode: str = "single",
    max_turns: int = 3,
    simulator: Any | None = None,
    xiyan_sql_runner: Any | None = None,
    text2cypher_debug_runner: Any | None = None,
    log: LogFn | None = None,
    on_results_update: ResultsUpdateFn | None = None,
) -> list[dict[str, Any]]:
    if conversation_mode not in CONVERSATION_MODES:
        raise ValueError(f"Unsupported conversation_mode: {conversation_mode}")
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")
    if conversation_mode == "simulate" and simulator is None:
        raise ValueError("simulator is required when conversation_mode='simulate'")

    results: list[dict[str, Any]] = []

    total = len(records)
    emit(log, f"begin running {total} case(s) x {rounds} round(s)")
    for index, record in enumerate(records, start=1):
        round_entries: list[dict[str, Any]] = []

        for rnd in range(1, rounds + 1):
            thread_id = f"{thread_prefix}-{record['id']}-r{rnd}"
            turns: list[dict[str, Any]] = []
            simulator_entries: list[dict[str, Any]] = []
            simulator_error = None
            seen_message_ids: set[str] = set()

            emit(
                log,
                f"case {index}/{total} round {rnd}/{rounds} start id={record['id']} "
                f"track={record['track']} category={record['category']} thread_id={thread_id}",
            )

            xiyan_sql_job = None
            if xiyan_sql_runner is not None:
                xiyan_sql_job = start_xiyan_sql_question(
                    question=record["question"],
                    xiyan_sql_runner=xiyan_sql_runner,
                    record_id=record["id"],
                    rnd=rnd,
                    log=log,
                )

            next_message = record["question"]
            turn_limit = 1 if conversation_mode == "single" else max_turns
            for turn_num in range(1, turn_limit + 1):
                turn_entry = run_turn(
                    record=record,
                    client=client,
                    message=next_message,
                    thread_id=thread_id,
                    rnd=rnd,
                    turn_num=turn_num,
                    log=log,
                    seen_message_ids=seen_message_ids,
                    text2cypher_debug_runner=text2cypher_debug_runner,
                )
                turns.append(turn_entry)
                if conversation_mode == "single" or turn_entry.get("error") or turn_num >= turn_limit:
                    break

                history = [
                    {"user": turn["user_message"], "agent": turn.get("answer") or ""}
                    for turn in turns
                ]
                try:
                    raw_decision = simulator.decide(  # type: ignore[union-attr]
                        record=record,
                        history=history,
                        latest_answer=turn_entry.get("answer") or "",
                    )
                    if not isinstance(raw_decision, dict):
                        raise ValueError("Simulator decision must be a dict")
                    decision = _normalize_simulator_decision(raw_decision)
                    decision = _reconcile_simulator_decision(decision, turn_entry)
                except Exception as exc:
                    simulator_error = f"{type(exc).__name__}: {exc}"
                    emit(log, f"case {record['id']} r{rnd} simulator_error={simulator_error}")
                    break

                simulator_entry = {
                    "after_turn": turn_num,
                    "should_continue": decision["should_continue"],
                    "reply": decision["reply"],
                    "reason": decision["reason"],
                    "model_name": getattr(simulator, "model_name", None),
                }
                simulator_entries.append(simulator_entry)
                if not decision["should_continue"]:
                    break
                next_message = decision["reply"]

            tool_calls = [tool_name for turn in turns for tool_name in turn.get("tool_calls", [])]
            generated_cypher = next(
                (turn.get("generated_cypher") for turn in reversed(turns) if turn.get("generated_cypher")),
                None,
            )
            answer = turns[-1].get("answer", "") if turns else ""
            error = next((turn.get("error") for turn in turns if turn.get("error")), None)

            round_entry = {
                "answer": answer,
                "generated_cypher": generated_cypher,
                "tool_calls": tool_calls,
                "error": error,
            }
            term_resolution = next(
                (turn.get("term_resolution") for turn in reversed(turns) if turn.get("term_resolution")),
                None,
            )
            if term_resolution is not None:
                round_entry["term_resolution"] = term_resolution
            if conversation_mode == "simulate":
                round_entry["turns"] = turns
                round_entry["simulator"] = simulator_entries
                if simulator_error is not None:
                    round_entry["simulator_error"] = simulator_error
            if xiyan_sql_job is not None:
                round_entry["xiyan_sql"] = collect_xiyan_sql_question(xiyan_sql_job)
            round_entries.append(round_entry)
            event_count = sum(int(turn.get("event_count") or 0) for turn in turns)
            emit(
                log,
                f"case {index}/{total} round {rnd}/{rounds} done id={record['id']} events={event_count} "
                f"tool_calls={len(tool_calls)} answer_chars={len(answer)} error={error or 'none'}",
            )

        results.append(build_result(record, round_entries))
        if on_results_update is not None:
            on_results_update(results)

    return results


def build_result(record: dict[str, Any], round_entries: list[dict[str, Any]]) -> dict[str, Any]:
    result = {
        "track": record["track"],
        "id": record["id"],
        "question": record["question"],
        "category": record["category"],
        "rounds": round_entries,
    }
    if "expected" in record:
        result["expected"] = record["expected"]
    return result


def write_jsonl(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(result, ensure_ascii=False) for result in results) + "\n",
        encoding="utf-8",
    )


def write_markdown(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(results), encoding="utf-8")


def render_markdown(results: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for result in results:
        counts[result["track"]] = counts.get(result["track"], 0) + 1

    rounds_val = len(results[0]["rounds"]) if results else 0

    lines = [
        "# HR Boss Agent Batch Run Results",
        "",
        f"- Generated at: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Cases run: `{len(results)}`",
        f"- Rounds per case: `{rounds_val}`",
        "- Scoring policy: no total score, no weighted score. Review each track separately.",
        "",
        "## Track Counts",
        "",
        "| Track | Cases |",
        "| --- | ---: |",
    ]
    for track, count in sorted(counts.items()):
        lines.append(f"| `{track}` | {count} |")

    lines.extend(["", "## Results", ""])
    for index, result in enumerate(results, start=1):
        lines.extend(render_result(index, result))

    return "\n".join(lines).rstrip() + "\n"


def render_result(index: int, result: dict[str, Any]) -> list[str]:
    lines = [
        f"### {index}. {result['id']} - {result['question']}",
        "",
        f"- Category: `{result['category']}`",
    ]
    if result.get("expected"):
        lines.append(f"- Expected: {result['expected']}")

    for rnd_entry in result.get("rounds", []):
        rnd_num = result["rounds"].index(rnd_entry) + 1
        lines.extend(["", f"#### Round {rnd_num}"])

        if rnd_entry.get("turns"):
            if rnd_entry.get("simulator_error"):
                lines.extend(["", "**Simulator error**", "", code_block(rnd_entry["simulator_error"], "text")])
            simulator_entries = rnd_entry.get("simulator", [])
            for turn_entry in rnd_entry.get("turns", []):
                lines.extend(render_turn(turn_entry, simulator_entries))
            if rnd_entry.get("xiyan_sql"):
                lines.extend(render_xiyan_sql(rnd_entry["xiyan_sql"]))
            continue

        if rnd_entry.get("error"):
            lines.extend(["", "**Run error**", "", code_block(rnd_entry["error"], "text")])

        lines.extend(["", "**Agent answer**", "", code_block(rnd_entry.get("answer") or "", "text")])

        if rnd_entry.get("generated_cypher"):
            lines.extend(
                [
                    "",
                    "**Generated Cypher**",
                    "",
                    code_block(rnd_entry["generated_cypher"], "cypher"),
                ]
            )

        if rnd_entry.get("term_resolution"):
            lines.extend(
                [
                    "",
                    "**Term resolution**",
                    "",
                    format_term_resolution(rnd_entry["term_resolution"]),
                ]
            )

        if rnd_entry.get("xiyan_sql"):
            lines.extend(render_xiyan_sql(rnd_entry["xiyan_sql"]))

        lines.extend(
            [
                "",
                "**Tool call trace**",
                "",
                format_bullets(rnd_entry.get("tool_calls", [])),
            ]
        )

    lines.append("")
    return lines


def render_turn(turn_entry: dict[str, Any], simulator_entries: list[dict[str, Any]]) -> list[str]:
    turn_num = turn_entry.get("turn", 0)
    lines = ["", f"##### Turn {turn_num}"]

    lines.extend(["", "**User message**", "", code_block(turn_entry.get("user_message") or "", "text")])

    if turn_entry.get("error"):
        lines.extend(["", "**Run error**", "", code_block(turn_entry["error"], "text")])

    lines.extend(["", "**Agent answer**", "", code_block(turn_entry.get("answer") or "", "text")])

    if turn_entry.get("generated_cypher"):
        lines.extend(["", "**Generated Cypher**", "", code_block(turn_entry["generated_cypher"], "cypher")])

    if turn_entry.get("term_resolution"):
        lines.extend(["", "**Term resolution**", "", format_term_resolution(turn_entry["term_resolution"])])

    lines.extend(["", "**Tool call trace**", "", format_bullets(turn_entry.get("tool_calls", []))])

    simulator_entry = next(
        (entry for entry in simulator_entries if entry.get("after_turn") == turn_num),
        None,
    )
    if simulator_entry is not None:
        lines.extend(
            [
                "",
                "**Simulator reply**",
                "",
                code_block(simulator_entry.get("reply") or "", "text"),
                f"- Continue: `{simulator_entry.get('should_continue')}`",
            ]
        )
        if simulator_entry.get("reason"):
            lines.append(f"- Reason: {simulator_entry['reason']}")
        if simulator_entry.get("model_name"):
            lines.append(f"- Model: `{simulator_entry['model_name']}`")

    return lines


def format_inline_list(values: list[str]) -> str:
    if not values:
        return "`none`"
    return ", ".join(f"`{value}`" for value in values)


def format_route_alternatives(routes: list[list[str]]) -> str:
    if not routes:
        return "`none`"
    return " OR ".join(format_inline_list(route) for route in routes)


def format_bullets(values: list[str]) -> str:
    if not values:
        return "- none"
    return "\n".join(f"- {value}" for value in values)


def format_term_resolution(term_resolution: dict[str, Any]) -> str:
    lines: list[str] = []
    if term_resolution.get("needs_clarification"):
        question = term_resolution.get("clarification_question")
        if question:
            lines.append(f"- needs clarification: {question}")
        else:
            lines.append("- needs clarification")

    for mapping in term_resolution.get("mappings", []) or []:
        source = mapping.get("source", "")
        matched_value = mapping.get("matched_value")
        status = mapping.get("status", "")
        field = ".".join(value for value in [mapping.get("label"), mapping.get("property")] if value)
        confidence = mapping.get("confidence")
        suffix_parts = [part for part in [field, status] if part]
        if isinstance(confidence, (int, float)):
            suffix_parts.append(f"confidence {confidence:.2f}")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        if matched_value:
            lines.append(f"- {source} -> {matched_value}{suffix}")
        elif source:
            candidate_values = [candidate.get("value") for candidate in mapping.get("candidates", []) if candidate.get("value")]
            candidate_text = f"; candidates: {', '.join(candidate_values)}" if candidate_values else ""
            lines.append(f"- {source} unresolved{candidate_text}{suffix}")

    return "\n".join(lines) if lines else "- none"


def render_xiyan_sql(xiyan_sql: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    sql = str(xiyan_sql.get("sql") or "").strip()
    if sql:
        lines.extend(["", "**XiYan SQL**", "", code_block(sql, "sql")])

    lines.extend(
        [
            "",
            "**XiYan SQL result**",
            "",
            code_block(format_xiyan_sql_result(xiyan_sql), "json"),
        ]
    )
    return lines


def format_xiyan_sql_result(xiyan_sql: dict[str, Any]) -> str:
    result = {
        "database_id": xiyan_sql.get("database_id"),
        "validation_valid": xiyan_sql.get("validation_valid"),
        "execution_success": xiyan_sql.get("execution_success"),
        "row_count": xiyan_sql.get("row_count"),
        "columns": xiyan_sql.get("columns") or [],
        "rows": xiyan_sql.get("rows") or [],
        "truncated": xiyan_sql.get("truncated"),
        "repair_attempted": xiyan_sql.get("repair_attempted"),
        "error": xiyan_sql.get("error"),
    }
    return json.dumps(json_safe(result), ensure_ascii=False, indent=2)


def code_block(value: str, language: str) -> str:
    return f"```{language}\n{value}\n```"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run HR Boss Agent evaluation samples and write JSONL plus Markdown results.")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Directory containing hr-boss evaluation JSONL files.")
    parser.add_argument(
        "--track",
        action="append",
        help=(
            "Track or JSONL file to run. Built-ins: "
            f"{', '.join(TRACK_CHOICES)}. Custom values load <track>.jsonl from --data-dir; "
            "paths ending in .jsonl are also accepted."
        ),
    )
    parser.add_argument("--id", action="append", dest="ids", help="Run only one case id. Repeat for multiple ids.")
    parser.add_argument("--limit", type=int, help="Run only the first N selected cases.")
    parser.add_argument("--output-jsonl", type=Path, help="Output JSONL path. Defaults to DATA_DIR/run-results.jsonl.")
    parser.add_argument("--output-md", type=Path, help="Output Markdown path. Defaults to DATA_DIR/run-results.md.")
    parser.add_argument("--thread-prefix", help="Thread id prefix. Defaults to a timestamped hr-eval prefix.")
    parser.add_argument("--rounds", type=int, default=1, help="Number of rounds per case. Defaults to 1.")
    parser.add_argument(
        "--conversation-mode",
        choices=CONVERSATION_MODES,
        default="single",
        help="Conversation mode: single preserves current one-shot behavior; simulate uses an LLM boss simulator.",
    )
    parser.add_argument("--max-turns", type=int, default=3, help="Maximum turns per round in simulate mode. Defaults to 3.")
    parser.add_argument("--simulator-model-name", help="Optional model override for the simulated boss user.")
    parser.add_argument("--model-name", help="Optional model override passed to DeerFlowClient.")
    parser.add_argument("--thinking-enabled", action="store_true", help="Enable model thinking mode for the run.")
    parser.add_argument(
        "--run-xiyan-sql",
        action="store_true",
        help="Also execute xiyan-text2sql_answer_question through the XiYan Text2SQL MCP and include SQL results.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log = print_log
    emit(log, "start")
    tracks = args.track or list(DEFAULT_TRACKS)
    output_jsonl = args.output_jsonl or args.data_dir / "run-results.jsonl"
    output_md = args.output_md or args.data_dir / "run-results.md"
    thread_prefix = args.thread_prefix or f"hr-eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    emit(log, f"data_dir={args.data_dir}")
    emit(log, f"tracks={','.join(tracks)}")
    emit(log, f"thread_prefix={thread_prefix}")
    emit(log, f"conversation_mode={args.conversation_mode}")
    emit(log, f"max_turns={args.max_turns}")
    emit(log, f"run_xiyan_sql={args.run_xiyan_sql}")
    emit(log, f"output_jsonl={output_jsonl}")
    emit(log, f"output_md={output_md}")

    emit(log, "loading records")
    records = load_records(args.data_dir, tracks)
    emit(log, f"loaded_records={len(records)}")
    records = select_records(records, set(args.ids) if args.ids else None, args.limit)
    limit_text = "none" if args.limit is None else str(args.limit)
    emit(log, f"selected_records={len(records)} ids={','.join(args.ids or []) or 'all'} limit={limit_text}")
    selected_tracks = list(dict.fromkeys(record["track"] for record in records))
    restricted_mcp_temp_dir = configure_restricted_mcp(
        selected_tracks,
        log=log,
        include_xiyan_sql=args.run_xiyan_sql,
    )

    try:
        preload_mcp_eval_tools(log=log)

        emit(log, "importing DeerFlowClient")
        from deerflow.client import DeerFlowClient

        emit(log, "creating DeerFlowClient agent_name=hr-boss-agent")
        client = DeerFlowClient(
            agent_name="hr-boss-agent",
            thinking_enabled=args.thinking_enabled,
            model_name=args.model_name,
        )
        emit(log, "client created")

        simulator = None
        if args.conversation_mode == "simulate":
            simulator_model_name = args.simulator_model_name or args.model_name
            emit(log, f"creating BossUserSimulator model={simulator_model_name or 'default'}")
            simulator = BossUserSimulator(model_name=simulator_model_name, thinking_enabled=args.thinking_enabled)
            emit(log, "simulator created")

        xiyan_sql_runner = None
        if args.run_xiyan_sql:
            xiyan_sql_runner = XiYanSqlMcpRunner()
            emit(log, f"xiyan_sql_runner created tool={XIYAN_TEXT2SQL_ANSWER_TOOL} database_id=mysql")

        text2cypher_debug_runner = Text2CypherDebugMcpRunner()
        emit(log, f"text2cypher_debug_runner created tool={TEXT2CYPHER_ANSWER_TOOL} include_debug=True")

        def write_progress(current_results: list[dict[str, Any]]) -> None:
            emit(log, f"incremental write results_completed={len(current_results)} jsonl={output_jsonl}")
            write_jsonl(current_results, output_jsonl)
            emit(log, f"incremental write results_completed={len(current_results)} markdown={output_md}")
            write_markdown(current_results, output_md)

        results = run_records(
            records,
            client,
            thread_prefix=thread_prefix,
            rounds=args.rounds,
            conversation_mode=args.conversation_mode,
            max_turns=args.max_turns,
            simulator=simulator,
            xiyan_sql_runner=xiyan_sql_runner,
            text2cypher_debug_runner=text2cypher_debug_runner,
            log=log,
            on_results_update=write_progress,
        )
        if not results:
            emit(log, f"writing empty JSONL results to {output_jsonl}")
            write_jsonl(results, output_jsonl)
            emit(log, f"writing empty Markdown results to {output_md}")
            write_markdown(results, output_md)

        print(f"Ran {len(results)} cases")
        print(f"JSONL: {output_jsonl}")
        print(f"Markdown: {output_md}")
    finally:
        cleanup_mcp_eval_resources(restricted_mcp_temp_dir, log=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
