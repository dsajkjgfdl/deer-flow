from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.tools import StructuredTool


def _runtime_context() -> SimpleNamespace:
    return SimpleNamespace(
        context={
            "thread_id": "thread-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_name": "hr-boss-agent",
        },
        config={},
    )


def _runtime_config_context() -> SimpleNamespace:
    return SimpleNamespace(
        context=None,
        config={
            "context": {
                "thread_id": "thread-from-config-context",
                "run_id": "run-from-config-context",
                "user_id": "user-from-config-context",
                "agent_name": "hr-boss-agent",
            }
        },
    )


def test_write_tool_audit_from_runtime_extracts_runtime_context(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    captured: dict = {}

    class Repo:
        def __init__(self, session_factory):
            assert session_factory == "sf"

        async def write_tool_audit(self, **kwargs):
            captured.update(kwargs)
            return kwargs

    monkeypatch.setattr(mcp_tools, "get_session_factory", lambda: "sf")
    monkeypatch.setattr(mcp_tools, "PlatformRepository", Repo)

    asyncio.run(
        mcp_tools.write_tool_audit_from_runtime(
            _runtime_context(),
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="success",
            latency_ms=17,
            metadata={"argument_keys": ["question"]},
            content={"request": {"arguments": {"question": "How many engineers?"}}},
        )
    )

    assert captured["user_id"] == "user-1"
    assert captured["agent_name"] == "hr-boss-agent"
    assert captured["thread_id"] == "thread-1"
    assert captured["run_id"] == "run-1"
    assert captured["tool_name"] == "text2cypher_answer_question"
    assert captured["mcp_server_name"] == "text2cypher"
    assert captured["status"] == "success"
    assert captured["latency_ms"] == 17
    assert captured["metadata"] == {"argument_keys": ["question"]}
    assert captured["content"] == {"request": {"arguments": {"question": "How many engineers?"}}}


def test_write_tool_audit_from_runtime_extracts_runtime_config_context(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    captured: dict = {}

    class Repo:
        def __init__(self, session_factory):
            assert session_factory == "sf"

        async def write_tool_audit(self, **kwargs):
            captured.update(kwargs)
            return kwargs

    monkeypatch.setattr(mcp_tools, "get_session_factory", lambda: "sf")
    monkeypatch.setattr(mcp_tools, "PlatformRepository", Repo)

    asyncio.run(
        mcp_tools.write_tool_audit_from_runtime(
            _runtime_config_context(),
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="success",
            latency_ms=17,
        )
    )

    assert captured["thread_id"] == "thread-from-config-context"
    assert captured["run_id"] == "run-from-config-context"
    assert captured["user_id"] == "user-from-config-context"
    assert captured["agent_name"] == "hr-boss-agent"


def test_http_mcp_wrapper_audits_sanitized_arguments_and_text2cypher_trace(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    calls: list[tuple[str, dict, dict]] = []
    audit_rows: list[dict] = []
    exits: list[bool] = []
    full_payload = {
        "status": "success",
        "answerable": True,
        "assumptions": ["current employees"],
        "generation": {
            "question": "How many engineers?",
            "generated_cypher": "MATCH (e:Employee) RETURN count(e)",
            "schema_text": "large private schema",
            "raw_output": "raw model output",
        },
        "validation": {
            "valid": True,
            "normalized_cypher": "MATCH (e:Employee) RETURN count(e)",
            "diagnostics": {},
        },
        "execution": {
            "normalized_cypher": "MATCH (e:Employee) RETURN count(e)",
            "columns": ["count(e)"],
            "records": [{"count(e)": 12}],
            "truncated": False,
        },
    }

    class Session:
        async def initialize(self):
            return None

        async def call_tool(self, name, args, **kwargs):
            calls.append((name, args, kwargs))
            return object()

    class ContextManager:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            exits.append(True)
            return False

    async def placeholder(question: str) -> str:
        """Placeholder."""
        return question

    async def fake_write_tool_audit_from_runtime(runtime, **kwargs):
        audit_rows.append({"runtime": runtime, **kwargs})

    monkeypatch.setattr("langchain_mcp_adapters.sessions.create_session", lambda _connection: ContextManager())
    monkeypatch.setattr(
        mcp_tools,
        "_convert_call_tool_result",
        lambda result, **_kwargs: (
            [{"type": "text", "text": json.dumps(full_payload, ensure_ascii=False)}],
            {"structured_content": full_payload},
        ),
    )
    monkeypatch.setattr(mcp_tools, "write_tool_audit_from_runtime", fake_write_tool_audit_from_runtime)

    tool = StructuredTool.from_function(
        coroutine=placeholder,
        name="text2cypher_answer_question",
        description="Answer a HR question.",
    )
    wrapped = mcp_tools._make_session_pool_tool(tool, "text2cypher", {"transport": "http", "url": "http://127.0.0.1:8101/mcp"})

    result = asyncio.run(
        wrapped.coroutine(
            runtime=_runtime_context(),
            question="How many engineers?",
            api_key="raw secret",
        )
    )

    assert calls == [
        (
            "answer_question",
            {
                "question": "How many engineers?",
                "api_key": "raw secret",
                "include_debug": True,
            },
            {},
        )
    ]
    assert exits == [True]
    assert audit_rows[0]["tool_name"] == "text2cypher_answer_question"
    assert audit_rows[0]["mcp_server_name"] == "text2cypher"
    assert audit_rows[0]["status"] == "success"
    assert audit_rows[0]["metadata"]["argument_keys"] == ["api_key", "question"]
    assert audit_rows[0]["metadata"]["tool_call_id"]
    assert audit_rows[0]["content"]["request"]["arguments"] == {
        "api_key": "[REDACTED]",
        "question": "How many engineers?",
    }
    assert audit_rows[0]["content"]["trace"]["generation"]["generated_cypher"] == "MATCH (e:Employee) RETURN count(e)"
    assert "schema_text" not in audit_rows[0]["content"]["trace"]["generation"]
    assert audit_rows[0]["content"]["trace"]["execution"]["row_count"] == 1
    assert audit_rows[0]["content"]["result"]["execution"]["records"] == [{"count(e)": 12}]
    assert "raw secret" not in str(audit_rows[0]["content"])
    assert isinstance(audit_rows[0]["latency_ms"], int)

    content, artifact = result
    public_payload = json.loads(content[0]["text"])
    assert public_payload["status"] == "success"
    assert public_payload["execution"] == {
        "columns": ["count(e)"],
        "records": [{"count(e)": 12}],
        "truncated": False,
    }
    assert "generation" not in public_payload
    assert "validation" not in public_payload
    assert artifact == {"structured_content": public_payload}


def test_mcp_wrapper_audits_error(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    audit_rows: list[dict] = []
    exits: list[bool] = []

    class Session:
        async def initialize(self):
            return None

        async def call_tool(self, name, args, **kwargs):
            raise RuntimeError("backend unavailable")

    class ContextManager:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            exits.append(True)
            return False

    async def placeholder(question: str) -> str:
        """Placeholder."""
        return question

    async def fake_write_tool_audit_from_runtime(runtime, **kwargs):
        audit_rows.append(kwargs)

    monkeypatch.setattr("langchain_mcp_adapters.sessions.create_session", lambda _connection: ContextManager())
    monkeypatch.setattr(mcp_tools, "write_tool_audit_from_runtime", fake_write_tool_audit_from_runtime)

    tool = StructuredTool.from_function(
        coroutine=placeholder,
        name="text2cypher_answer_question",
        description="Answer a HR question.",
    )
    wrapped = mcp_tools._make_session_pool_tool(tool, "text2cypher", {"transport": "http", "url": "http://127.0.0.1:8101/mcp"})

    with pytest.raises(RuntimeError, match="backend unavailable"):
        asyncio.run(wrapped.coroutine(runtime=_runtime_context(), question="raw secret"))

    assert exits == [True]
    assert audit_rows[0]["status"] == "error"
    assert audit_rows[0]["error"] == "backend unavailable"
    assert audit_rows[0]["metadata"]["argument_keys"] == ["question"]
    assert audit_rows[0]["metadata"]["tool_call_id"]
    assert audit_rows[0]["content"]["request"]["arguments"] == {"question": "raw secret"}


def test_mcp_wrapper_audits_employee_query_steps_without_returning_debug(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    calls: list[tuple[str, dict, dict]] = []
    audit_rows: list[dict] = []
    full_payload = {
        "status": "success",
        "answerable": True,
        "employees": [{"employee_id": "E001", "name": "Alice"}],
        "pagination": {"returned_count": 1, "has_more": False},
        "debug": {
            "queries": [
                {
                    "stage": "page",
                    "generated_cypher": "MATCH (e:Employee) RETURN e.employee_id",
                    "validation": {
                        "valid": True,
                        "normalized_cypher": "MATCH (e:Employee) RETURN e.employee_id",
                    },
                    "execution": {"row_count": 1},
                }
            ]
        },
    }

    class Session:
        async def initialize(self):
            return None

        async def call_tool(self, name, args, **kwargs):
            calls.append((name, args, kwargs))
            return object()

    class ContextManager:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            return False

    async def placeholder(titles: list[str]) -> str:
        """Placeholder."""
        return str(titles)

    async def fake_write_tool_audit_from_runtime(runtime, **kwargs):
        audit_rows.append(kwargs)

    monkeypatch.setattr("langchain_mcp_adapters.sessions.create_session", lambda _connection: ContextManager())
    monkeypatch.setattr(
        mcp_tools,
        "_convert_call_tool_result",
        lambda result, **_kwargs: (
            [{"type": "text", "text": json.dumps(full_payload)}],
            {"structured_content": full_payload},
        ),
    )
    monkeypatch.setattr(mcp_tools, "write_tool_audit_from_runtime", fake_write_tool_audit_from_runtime)

    tool = StructuredTool.from_function(
        coroutine=placeholder,
        name="text2cypher_query_employees",
        description="Query employee cards.",
    )
    wrapped = mcp_tools._make_session_pool_tool(tool, "text2cypher", {"transport": "http", "url": "http://127.0.0.1:8101/mcp"})
    content, artifact = asyncio.run(wrapped.coroutine(runtime=_runtime_context(), titles=["Senior Engineer"]))

    assert calls[0][1]["include_debug"] is True
    assert audit_rows[0]["content"]["trace"]["queries"][0]["stage"] == "page"
    public_payload = json.loads(content[0]["text"])
    assert "debug" not in public_payload
    assert artifact == {"structured_content": public_payload}


def test_build_tool_audit_content_summarizes_graphrag_result():
    from deerflow.mcp import tools as mcp_tools

    payload = {
        "question": "How is organizational risk?",
        "strategy": "global",
        "evidence_status": "sufficient",
        "confidence": "high",
        "answer": "There is cross-team collaboration risk. " * 200,
        "context_counts": {"entities": 12, "relationships": 8},
        "context_data": {"large": ["private"] * 100},
    }

    content = mcp_tools._build_tool_audit_content(
        "hr-graphrag-qa",
        "query_global",
        {"question": "How is organizational risk?"},
        (
            [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            {"structured_content": payload},
        ),
    )

    assert content["request"]["arguments"] == {"question": "How is organizational risk?"}
    assert content["trace"] == {
        "strategy": "global",
        "evidence_status": "sufficient",
        "confidence": "high",
    }
    assert content["result"]["context_counts"] == {"entities": 12, "relationships": 8}
    assert len(content["result"]["answer_preview"]) <= 1000
    assert "context_data" not in content["result"]


def test_text2cypher_public_payload_is_preserved_when_debug_is_unavailable():
    from deerflow.mcp import tools as mcp_tools

    public_payload = {
        "status": "success",
        "answerable": True,
        "custom_notice": "older MCP response",
    }
    converted = (
        [{"type": "text", "text": json.dumps(public_payload)}],
        {"structured_content": public_payload},
    )

    assert mcp_tools._sanitize_converted_result_for_agent("text2cypher", "answer_question", converted) is converted
    assert mcp_tools._sanitize_converted_result_for_agent("text2cypher", "query_employees", converted) is converted


def test_timeline_tool_audit_exposes_stored_content_json():
    from app.gateway.routers.platform_admin import _timeline_tool_audit

    content = {
        "request": {"arguments": {"question": "How many employees?"}},
        "trace": {"generation": {"generated_cypher": "MATCH (e:Employee) RETURN count(e)"}},
    }

    event = _timeline_tool_audit(
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "tool_name": "text2cypher_answer_question",
            "mcp_server_name": "text2cypher",
            "status": "success",
            "latency_ms": 23,
            "content_json": content,
            "metadata_json": {"tool_call_id": "call-1"},
        }
    )

    assert event["content"] == content
    assert event["metadata"] == {"tool_call_id": "call-1"}
    assert event["duration_ms"] == 23
