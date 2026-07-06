from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sqlite3
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
HR_MCP_ROOT = Path("D:/study/my-mcp/hr-mcp-suite")
DEFAULT_QUESTIONS = REPO_ROOT / "tmp_xxx.txt"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "hr-boss-model-benchmark"


@dataclass(frozen=True)
class ModelCase:
    profile: str
    model_name: str
    label: str


CASES = [
    ModelCase(profile="qwen", model_name="hr-qwen", label="公司部署Qwen"),
    ModelCase(profile="deepseek", model_name="hr-deepseek", label="DeepSeek"),
]

PROVIDER_UNAVAILABLE_MARKERS = (
    "configured llm provider is temporarily unavailable",
    "provider request failed temporarily",
)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _add_no_proxy_host(host: str | None) -> None:
    if not host:
        return

    clean_host = host.strip()
    if not clean_host:
        return

    items = [item.strip() for item in os.environ.get("NO_PROXY", "").split(",") if item.strip()]
    if clean_host not in items:
        items.append(clean_host)
    value = ",".join(items)
    os.environ["NO_PROXY"] = value
    os.environ["no_proxy"] = value


def _add_no_proxy_url_host(url: str | None) -> None:
    if not url:
        return

    parsed = urlparse(url)
    _add_no_proxy_host(parsed.hostname)


def _configure_no_proxy() -> None:
    _add_no_proxy_url_host(os.environ.get("QWEN_CHAT_API_BASE"))
    _add_no_proxy_url_host(os.environ.get("DEEPSEEK_API_BASE"))
    _add_no_proxy_host("127.0.0.1")
    _add_no_proxy_host("localhost")


def _classify_run_error(error: str | None, final_answer: str) -> str | None:
    if error:
        return error

    normalized_answer = final_answer.lower()
    if any(marker in normalized_answer for marker in PROVIDER_UNAVAILABLE_MARKERS):
        return "provider_unavailable"
    return None


def _benchmark_memory_config(config: Any, *, disable_injection: bool) -> Any:
    if not disable_injection:
        return config
    return config.model_copy(update={"injection_enabled": False})


def _set_default_env() -> None:
    _load_dotenv(REPO_ROOT / ".env")
    os.environ.setdefault("DEER_FLOW_PROJECT_ROOT", str(REPO_ROOT))
    os.environ.setdefault("DEER_FLOW_CONFIG_PATH", str(REPO_ROOT / "config.yaml"))
    os.environ.setdefault("DEER_FLOW_EXTENSIONS_CONFIG_PATH", str(REPO_ROOT / "extensions_config.json"))
    os.environ.setdefault("DEER_FLOW_HOME", str(BACKEND_DIR / ".deer-flow"))
    os.environ["PYTHONPATH"] = str(BACKEND_DIR)

    os.environ.setdefault("QWEN_CHAT_API_BASE", os.environ.get("VLLM_CHAT_API_BASE", "http://36.212.39.231:11435/v1"))
    os.environ.setdefault("QWEN_CHAT_MODEL", os.environ.get("VLLM_CHAT_MODEL", "Qwen3"))
    if "QWEN_API_KEY" not in os.environ:
        if os.environ.get("VLLM_API_KEY"):
            os.environ["QWEN_API_KEY"] = os.environ["VLLM_API_KEY"]
        elif os.environ.get("OPENAI_API_KEY"):
            os.environ["QWEN_API_KEY"] = os.environ["OPENAI_API_KEY"]

    os.environ.setdefault("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    os.environ.setdefault("DEEPSEEK_MODEL", "deepseek-v4-pro")
    if "DEEPSEEK_API_KEY" not in os.environ and os.environ.get("DASHSCOPE_API_KEY"):
        os.environ["DEEPSEEK_API_KEY"] = os.environ["DASHSCOPE_API_KEY"]

    if os.environ.get("DASHSCOPE_API_KEY") and not os.environ.get("ALIBABA_API_KEY"):
        os.environ["ALIBABA_API_KEY"] = os.environ["DASHSCOPE_API_KEY"]

    _configure_no_proxy()

    missing = [
        key
        for key in ("QWEN_API_KEY", "QWEN_CHAT_API_BASE", "QWEN_CHAT_MODEL", "DEEPSEEK_API_KEY", "DEEPSEEK_API_BASE", "DEEPSEEK_MODEL")
        if not os.environ.get(key)
    ]
    if missing:
        raise RuntimeError(f"Missing required model environment variables: {', '.join(missing)}")


def _load_questions(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _query_tool_audits(thread_id: str) -> list[dict[str, Any]]:
    db_path = BACKEND_DIR / ".deer-flow" / "data" / "deerflow.db"
    if not db_path.is_file():
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                select id, thread_id, run_id, tool_name, mcp_server_name, status,
                       latency_ms, error, metadata_json, content_json, created_at, updated_at
                from tool_audit_logs
                where thread_id = ?
                order by id asc
                """,
                (thread_id,),
            ).fetchall()
    except sqlite3.Error:
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("metadata_json", "content_json"):
            if isinstance(item.get(key), str):
                try:
                    item[key] = json.loads(item[key])
                except json.JSONDecodeError:
                    pass
        result.append(item)
    return result


def _safe_event_data(data: Any) -> Any:
    try:
        json.dumps(data, ensure_ascii=False, default=str)
        return data
    except TypeError:
        return repr(data)


def _normalize_tool_call(call: Any) -> dict[str, Any] | None:
    if not isinstance(call, dict):
        return None

    name = str(call.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "args": call.get("args"),
        "id": call.get("id"),
    }


def _parse_tool_content(content: Any) -> Any:
    if isinstance(content, (dict, list)):
        return content
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def _extract_tool_duration_ms(parsed_content: Any) -> float | None:
    if not isinstance(parsed_content, dict):
        return None

    for key in ("duration_ms", "latency_ms"):
        value = parsed_content.get(key)
        if isinstance(value, int | float):
            return float(value)

    timing = parsed_content.get("timing")
    if isinstance(timing, dict):
        value = timing.get("total_ms")
        if isinstance(value, int | float):
            return float(value)
    return None


def _summarize_tool_result(*, name: str | None, tool_call_id: str | None, content: Any) -> dict[str, Any]:
    parsed_content = _parse_tool_content(content)
    preview = json.dumps(parsed_content, ensure_ascii=False, default=str) if parsed_content is not None else str(content)
    result: dict[str, Any] = {
        "name": name,
        "tool_call_id": tool_call_id,
        "content_preview": preview[:2000],
        "duration_ms": _extract_tool_duration_ms(parsed_content),
    }

    if isinstance(parsed_content, dict):
        for key in (
            "status",
            "answerable",
            "employee_count",
            "returned_count",
            "has_more",
            "selected_values",
            "limitation",
            "error",
        ):
            if key in parsed_content:
                result[key] = parsed_content[key]
    return result


def _run_one(
    client: Any,
    *,
    case: ModelCase,
    question: str,
    question_index: int,
    output_dir: Path,
    thread_id: str | None = None,
    recursion_limit: int = 100,
) -> dict[str, Any]:
    thread_id = thread_id or f"bench-{case.profile}-{question_index:02d}-{uuid.uuid4().hex[:8]}"
    started = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    events_path = output_dir / "raw_events.jsonl"

    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    ai_chunks: dict[str, list[str]] = {}
    usage: dict[str, Any] | None = None
    error: str | None = None

    try:
        for event in client.stream(
            question,
            thread_id=thread_id,
            model_name=case.model_name,
            thinking_enabled=False,
            subagent_enabled=False,
            recursion_limit=recursion_limit,
        ):
            event_payload = {"type": event.type, "data": _safe_event_data(event.data)}
            _append_jsonl(
                events_path,
                {
                    "profile": case.profile,
                    "model_name": case.model_name,
                    "question_index": question_index,
                    "thread_id": thread_id,
                    "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                    "event": event_payload,
                },
            )

            data = event.data if isinstance(event.data, dict) else {}
            if event.type == "messages-tuple":
                if data.get("type") == "ai":
                    msg_id = data.get("id") or "unknown"
                    if data.get("content"):
                        ai_chunks.setdefault(str(msg_id), []).append(str(data["content"]))
                    for call in data.get("tool_calls") or []:
                        normalized_call = _normalize_tool_call(call)
                        if normalized_call is not None:
                            tool_calls.append(normalized_call)
                elif data.get("type") == "tool":
                    tool_results.append(
                        _summarize_tool_result(
                            name=data.get("name"),
                            tool_call_id=data.get("tool_call_id"),
                            content=data.get("content"),
                        )
                    )
            elif event.type == "end":
                usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    except Exception as exc:  # noqa: BLE001 - benchmark must record failures.
        error = f"{type(exc).__name__}: {exc}"
        _append_jsonl(
            events_path,
            {
                "profile": case.profile,
                "model_name": case.model_name,
                "question_index": question_index,
                "thread_id": thread_id,
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "error": error,
                "traceback": traceback.format_exc(),
            },
        )

    total_ms = max(0, int((time.perf_counter() - started) * 1000))
    final_answer = ""
    if ai_chunks:
        final_answer = "".join(ai_chunks[sorted(ai_chunks)[-1]]).strip()
    error = _classify_run_error(error, final_answer)

    audit_rows = _query_tool_audits(thread_id)
    audited_tool_latency_ms = sum(row.get("latency_ms") or 0 for row in audit_rows)
    streamed_tool_latency_ms = sum(result.get("duration_ms") or 0 for result in tool_results)
    tool_latency_ms = audited_tool_latency_ms or streamed_tool_latency_ms
    return {
        "profile": case.profile,
        "model_name": case.model_name,
        "label": case.label,
        "question_index": question_index,
        "question": question,
        "thread_id": thread_id,
        "started_at": started_at,
        "total_duration_ms": total_ms,
        "status": "failed" if error else "ok",
        "error": error,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "tool_audits": audit_rows,
        "tool_call_count": len(tool_calls),
        "tool_result_count": len(tool_results),
        "tool_audit_count": len(audit_rows),
        "tool_latency_ms": tool_latency_ms,
        "usage": usage,
        "final_answer": final_answer,
        "final_answer_chars": len(final_answer),
    }


def _failure_result(
    *,
    case: ModelCase,
    question: str,
    question_index: int,
    thread_id: str,
    started_at: str,
    total_ms: int,
    error: str,
) -> dict[str, Any]:
    return {
        "profile": case.profile,
        "model_name": case.model_name,
        "label": case.label,
        "question_index": question_index,
        "question": question,
        "thread_id": thread_id,
        "started_at": started_at,
        "total_duration_ms": total_ms,
        "status": "failed",
        "error": error,
        "tool_calls": [],
        "tool_results": [],
        "tool_audits": [],
        "tool_call_count": 0,
        "tool_result_count": 0,
        "tool_audit_count": 0,
        "tool_latency_ms": 0,
        "usage": None,
        "final_answer": "",
        "final_answer_chars": 0,
    }


def _timeout_result(
    *,
    case: ModelCase,
    question: str,
    question_index: int,
    thread_id: str,
    started_at: str,
    total_ms: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    return _failure_result(
        case=case,
        question=question,
        question_index=question_index,
        thread_id=thread_id,
        started_at=started_at,
        total_ms=total_ms,
        error=f"question_timeout_{timeout_seconds}s",
    )


def _reload_deerflow_config(*, disable_memory_injection: bool) -> None:
    for path in (str(BACKEND_DIR), str(BACKEND_DIR / "packages" / "harness"), str(REPO_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    from deerflow.config.app_config import reload_app_config
    from deerflow.config.extensions_config import reload_extensions_config
    from deerflow.config.memory_config import set_memory_config

    app_config = reload_app_config(str(REPO_ROOT / "config.yaml"))
    if disable_memory_injection:
        app_config.memory = _benchmark_memory_config(app_config.memory, disable_injection=True)
        set_memory_config(app_config.memory)
    reload_extensions_config(str(REPO_ROOT / "extensions_config.json"))


def _make_client() -> Any:
    from deerflow.client import DeerFlowClient

    return DeerFlowClient(
        config_path=REPO_ROOT / "config.yaml",
        agent_name="hr-boss-agent",
        thinking_enabled=False,
        subagent_enabled=False,
        environment="hr-boss-benchmark",
    )


def _single_run_worker(
    *,
    case: ModelCase,
    question: str,
    question_index: int,
    output_dir: Path,
    result_path: Path,
    thread_id: str,
    disable_memory_injection: bool,
    recursion_limit: int,
) -> None:
    started = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        _set_default_env()
        os.environ["HR_LLM_PROFILE"] = case.profile
        _reload_deerflow_config(disable_memory_injection=disable_memory_injection)
        client = _make_client()
        result = _run_one(
            client,
            case=case,
            question=question,
            question_index=question_index,
            output_dir=output_dir,
            thread_id=thread_id,
            recursion_limit=recursion_limit,
        )
    except Exception as exc:  # noqa: BLE001 - benchmark worker must record failures.
        total_ms = max(0, int((time.perf_counter() - started) * 1000))
        result = _failure_result(
            case=case,
            question=question,
            question_index=question_index,
            thread_id=thread_id,
            started_at=started_at,
            total_ms=total_ms,
            error=f"{type(exc).__name__}: {exc}",
        )
        _append_jsonl(
            output_dir / "raw_events.jsonl",
            {
                "profile": case.profile,
                "model_name": case.model_name,
                "question_index": question_index,
                "thread_id": thread_id,
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "error": result["error"],
                "traceback": traceback.format_exc(),
            },
        )
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _terminate_process_tree(process: mp.Process) -> None:
    if process.pid is None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    process.join(timeout=10)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)


def _run_one_with_timeout(
    *,
    case: ModelCase,
    question: str,
    question_index: int,
    output_dir: Path,
    timeout_seconds: int,
    disable_memory_injection: bool,
    recursion_limit: int,
) -> dict[str, Any]:
    thread_id = f"bench-{case.profile}-{question_index:02d}-{uuid.uuid4().hex[:8]}"
    started = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    result_path = output_dir / f".{thread_id}.result.json"
    process = mp.Process(
        target=_single_run_worker,
        kwargs={
            "case": case,
            "question": question,
            "question_index": question_index,
            "output_dir": output_dir,
            "result_path": result_path,
            "thread_id": thread_id,
            "disable_memory_injection": disable_memory_injection,
            "recursion_limit": recursion_limit,
        },
    )
    process.start()
    process.join(timeout=timeout_seconds)

    if process.is_alive():
        _terminate_process_tree(process)
        total_ms = max(0, int((time.perf_counter() - started) * 1000))
        result = _timeout_result(
            case=case,
            question=question,
            question_index=question_index,
            thread_id=thread_id,
            started_at=started_at,
            total_ms=total_ms,
            timeout_seconds=timeout_seconds,
        )
        _append_jsonl(
            output_dir / "raw_events.jsonl",
            {
                "profile": case.profile,
                "model_name": case.model_name,
                "question_index": question_index,
                "thread_id": thread_id,
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "error": result["error"],
            },
        )
        return result

    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        total_ms = max(0, int((time.perf_counter() - started) * 1000))
        result = _failure_result(
            case=case,
            question=question,
            question_index=question_index,
            thread_id=thread_id,
            started_at=started_at,
            total_ms=total_ms,
            error=f"worker_result_error: {exc}",
        )
    finally:
        try:
            result_path.unlink()
        except OSError:
            pass
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark hr-boss-agent across HR LLM providers.")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Limit questions for smoke tests; 0 means all.")
    parser.add_argument("--profiles", nargs="+", choices=[case.profile for case in CASES], default=[case.profile for case in CASES])
    parser.add_argument("--keep-memory", action="store_true", help="Keep memory injection enabled during benchmark runs.")
    parser.add_argument("--question-timeout-seconds", type=int, default=300)
    parser.add_argument("--recursion-limit", type=int, default=100)
    args = parser.parse_args()

    _set_default_env()
    questions = _load_questions(args.questions)
    if args.limit and args.limit > 0:
        questions = questions[: args.limit]
    cases = [case for case in CASES if case.profile in set(args.profiles)]

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.jsonl"

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "questions_path": str(args.questions),
        "question_count": len(questions),
        "profiles": [case.profile for case in cases],
        "memory_injection_enabled": bool(args.keep_memory),
        "question_timeout_seconds": args.question_timeout_seconds,
        "recursion_limit": args.recursion_limit,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    all_results: list[dict[str, Any]] = []
    for case in cases:
        for index, question in enumerate(questions, start=1):
            print(f"[{case.profile}] {index}/{len(questions)} {question}", flush=True)
            result = _run_one_with_timeout(
                case=case,
                question=question,
                question_index=index,
                output_dir=output_dir,
                timeout_seconds=args.question_timeout_seconds,
                disable_memory_injection=not args.keep_memory,
                recursion_limit=args.recursion_limit,
            )
            all_results.append(result)
            _append_jsonl(summary_path, result)
            print(
                f"  duration={result['total_duration_ms']}ms tools={result['tool_call_count']} "
                f"audits={result['tool_audit_count']} error={result['error'] or '-'}",
                flush=True,
            )

    (output_dir / "summary.json").write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"OUTPUT_DIR={output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
