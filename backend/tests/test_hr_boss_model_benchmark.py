import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import benchmark_hr_boss_models as benchmark
from deerflow.config.memory_config import MemoryConfig


def test_provider_unavailable_answer_is_marked_as_error() -> None:
    answer = (
        "The configured LLM provider is temporarily unavailable after multiple "
        "retries. Please wait a moment and continue the conversation."
    )

    assert benchmark._classify_run_error(None, answer) == "provider_unavailable"


def test_configure_no_proxy_adds_model_provider_hosts(monkeypatch) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.setenv("QWEN_CHAT_API_BASE", "http://36.212.39.231:11435/v1")
    monkeypatch.setenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")

    benchmark._configure_no_proxy()

    hosts = {item.strip() for item in benchmark.os.environ["NO_PROXY"].split(",") if item.strip()}
    assert "localhost" in hosts
    assert "127.0.0.1" in hosts
    assert "36.212.39.231" in hosts
    assert "api.deepseek.com" in hosts


def test_benchmark_memory_config_disables_injection_only() -> None:
    config = MemoryConfig(enabled=True, injection_enabled=True, max_injection_tokens=2000)

    benchmark_config = benchmark._benchmark_memory_config(config, disable_injection=True)

    assert config.injection_enabled is True
    assert benchmark_config.enabled is True
    assert benchmark_config.injection_enabled is False
    assert benchmark_config.max_injection_tokens == 2000


def test_normalize_tool_call_ignores_blank_name() -> None:
    assert benchmark._normalize_tool_call({"name": "", "args": {}, "id": None}) is None


def test_summarize_tool_result_extracts_timing() -> None:
    content = json.dumps(
        {
            "status": "success",
            "employee_count": 30,
            "selected_values": {"subsidiaries": ["上海火炬电子科技集团有限公司"]},
            "timing": {"total_ms": 3144.837},
        },
        ensure_ascii=False,
    )

    result = benchmark._summarize_tool_result(
        name="text2cypher_query_employees",
        tool_call_id="call-1",
        content=content,
    )

    assert result["duration_ms"] == 3144.837
    assert result["status"] == "success"
    assert result["employee_count"] == 30
    assert result["selected_values"] == {"subsidiaries": ["上海火炬电子科技集团有限公司"]}


def test_timeout_result_marks_question_failed() -> None:
    case = benchmark.ModelCase(profile="qwen", model_name="hr-qwen", label="Qwen")

    result = benchmark._timeout_result(
        case=case,
        question="q",
        question_index=2,
        thread_id="thread-1",
        started_at="2026-06-18T17:00:00",
        total_ms=123456,
        timeout_seconds=120,
    )

    assert result["status"] == "failed"
    assert result["error"] == "question_timeout_120s"
    assert result["profile"] == "qwen"
    assert result["question_index"] == 2
    assert result["thread_id"] == "thread-1"
    assert result["total_duration_ms"] == 123456
