from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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


def test_write_tool_audit_from_runtime_falls_back_to_langgraph_config(monkeypatch):
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
    monkeypatch.setattr(
        mcp_tools,
        "get_config",
        lambda: {
            "context": {
                "thread_id": "thread-from-langgraph-config",
                "run_id": "run-from-langgraph-config",
                "user_id": "user-from-langgraph-config",
                "agent_name": "hr-boss-agent",
            }
        },
    )

    asyncio.run(
        mcp_tools.write_tool_audit_from_runtime(
            None,
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="success",
            latency_ms=17,
        )
    )

    assert captured["thread_id"] == "thread-from-langgraph-config"
    assert captured["run_id"] == "run-from-langgraph-config"
    assert captured["user_id"] == "user-from-langgraph-config"
    assert captured["agent_name"] == "hr-boss-agent"


def test_mcp_wrapper_audits_success_without_raw_arguments(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    calls: list[tuple[str, dict]] = []
    audit_rows: list[dict] = []

    class Session:
        async def call_tool(self, name, args):
            calls.append((name, args))
            return object()

    class Pool:
        async def get_session(self, server_name, scope_key, connection):
            assert server_name == "text2cypher"
            assert scope_key == "shared"
            return Session()

    async def placeholder(question: str) -> str:
        """Placeholder."""
        return question

    async def fake_write_tool_audit_from_runtime(runtime, **kwargs):
        audit_rows.append({"runtime": runtime, **kwargs})

    monkeypatch.setattr(mcp_tools, "get_session_pool", lambda: Pool())
    monkeypatch.setattr(mcp_tools, "_convert_call_tool_result", lambda result: ("ok", None))
    monkeypatch.setattr(mcp_tools, "write_tool_audit_from_runtime", fake_write_tool_audit_from_runtime)

    tool = StructuredTool.from_function(
        coroutine=placeholder,
        name="text2cypher_answer_question",
        description="Answer a HR question.",
    )
    wrapped = mcp_tools._make_session_pool_tool(tool, "text2cypher", {"transport": "stdio"})

    result = asyncio.run(wrapped.coroutine(runtime=_runtime_context(), question="raw secret"))

    assert result == ("ok", None)
    assert calls == [("answer_question", {"question": "raw secret"})]
    assert audit_rows[0]["tool_name"] == "text2cypher_answer_question"
    assert audit_rows[0]["mcp_server_name"] == "text2cypher"
    assert audit_rows[0]["status"] == "success"
    assert audit_rows[0]["metadata"] == {"argument_keys": ["question"]}
    assert "raw secret" not in str(audit_rows[0]["metadata"])
    assert isinstance(audit_rows[0]["latency_ms"], int)


def test_mcp_wrapper_audits_error(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    audit_rows: list[dict] = []
    invalidated: list[tuple[str, str]] = []

    class Session:
        async def call_tool(self, name, args):
            raise RuntimeError("backend unavailable")

    class Pool:
        async def get_session(self, server_name, thread_id, connection):
            return Session()

        async def invalidate(self, server_name, scope_key):
            invalidated.append((server_name, scope_key))

    async def placeholder(question: str) -> str:
        """Placeholder."""
        return question

    async def fake_write_tool_audit_from_runtime(runtime, **kwargs):
        audit_rows.append(kwargs)

    monkeypatch.setattr(mcp_tools, "get_session_pool", lambda: Pool())
    monkeypatch.setattr(mcp_tools, "write_tool_audit_from_runtime", fake_write_tool_audit_from_runtime)

    tool = StructuredTool.from_function(
        coroutine=placeholder,
        name="text2cypher_answer_question",
        description="Answer a HR question.",
    )
    wrapped = mcp_tools._make_session_pool_tool(tool, "text2cypher", {"transport": "stdio"})

    with pytest.raises(RuntimeError, match="backend unavailable"):
        asyncio.run(wrapped.coroutine(runtime=_runtime_context(), question="raw secret"))

    assert audit_rows[0]["status"] == "error"
    assert audit_rows[0]["error"] == "backend unavailable"
    assert audit_rows[0]["metadata"] == {"argument_keys": ["question"]}
    assert invalidated == [("text2cypher", "shared")]


def test_http_mcp_config_forwards_transport_and_session_timeouts():
    from deerflow.config.extensions_config import McpServerConfig
    from deerflow.mcp.client import build_server_params

    config = McpServerConfig(
        type="http",
        url="http://127.0.0.1:8102/mcp",
        timeout=30,
        sse_read_timeout=210,
        read_timeout_seconds=200,
    )

    params = build_server_params("hr-graphrag-qa", config)

    assert params["timeout"] == 30
    assert params["sse_read_timeout"] == 210
    assert params["session_kwargs"]["read_timeout_seconds"] == timedelta(seconds=200)


@pytest.mark.asyncio
async def test_persistent_session_is_entered_and_closed_by_same_owner_task():
    from deerflow.mcp.session_pool import MCPSessionPool

    entered_by = None
    closed_by = None
    session = AsyncMock()

    class ContextManager:
        async def __aenter__(self):
            nonlocal entered_by
            entered_by = asyncio.current_task()
            return session

        async def __aexit__(self, *_args):
            nonlocal closed_by
            closed_by = asyncio.current_task()
            return False

    pool = MCPSessionPool()
    with patch("langchain_mcp_adapters.sessions.create_session", return_value=ContextManager()):
        assert await pool.get_session("hr-graphrag-qa", "shared", {"transport": "http"}) is session
        await pool.close_all()

    assert entered_by is not None
    assert entered_by is closed_by


@pytest.mark.asyncio
async def test_mcp_wrapper_rewarms_shared_session_after_transport_error(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    calls = 0
    invalidated: list[tuple[str, str]] = []
    rewarmed = asyncio.Event()

    class BrokenSession:
        async def call_tool(self, name, args):
            raise RuntimeError("connection closed")

    class HealthySession:
        pass

    class Pool:
        async def get_session(self, server_name, scope_key, connection):
            nonlocal calls
            calls += 1
            if calls == 1:
                return BrokenSession()
            rewarmed.set()
            return HealthySession()

        async def invalidate(self, server_name, scope_key):
            invalidated.append((server_name, scope_key))

    async def placeholder(question: str) -> str:
        """Placeholder."""
        return question

    async def ignore_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mcp_tools, "get_session_pool", lambda: Pool())
    monkeypatch.setattr(mcp_tools, "write_tool_audit_from_runtime", ignore_audit)

    tool = StructuredTool.from_function(
        coroutine=placeholder,
        name="hr-graphrag-qa_query_global",
        description="Analyze the HR graph.",
    )
    wrapped = mcp_tools._make_session_pool_tool(
        tool,
        "hr-graphrag-qa",
        {"transport": "http", "url": "http://127.0.0.1:8102/mcp"},
    )

    with pytest.raises(RuntimeError, match="connection closed"):
        await wrapped.coroutine(runtime=_runtime_context(), question="analyze")

    await asyncio.wait_for(rewarmed.wait(), timeout=1)
    assert invalidated == [("hr-graphrag-qa", "shared")]
    assert calls == 2


@pytest.mark.asyncio
async def test_mcp_wrapper_rewarms_shared_session_after_mcp_error_result(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    calls = 0
    invalidated: list[tuple[str, str]] = []
    rewarmed = asyncio.Event()

    class ErrorSession:
        async def call_tool(self, name, args):
            return SimpleNamespace(isError=True)

    class HealthySession:
        pass

    class Pool:
        async def get_session(self, server_name, scope_key, connection):
            nonlocal calls
            calls += 1
            if calls == 1:
                return ErrorSession()
            rewarmed.set()
            return HealthySession()

        async def invalidate(self, server_name, scope_key):
            invalidated.append((server_name, scope_key))

    async def placeholder(question: str) -> str:
        """Placeholder."""
        return question

    async def ignore_audit(*_args, **_kwargs):
        return None

    def raise_tool_error(_result):
        raise RuntimeError("tool timed out")

    monkeypatch.setattr(mcp_tools, "get_session_pool", lambda: Pool())
    monkeypatch.setattr(mcp_tools, "write_tool_audit_from_runtime", ignore_audit)
    monkeypatch.setattr(mcp_tools, "_convert_call_tool_result", raise_tool_error)

    tool = StructuredTool.from_function(
        coroutine=placeholder,
        name="hr-graphrag-qa_query_global",
        description="Analyze the HR graph.",
    )
    wrapped = mcp_tools._make_session_pool_tool(
        tool,
        "hr-graphrag-qa",
        {"transport": "http", "url": "http://127.0.0.1:8102/mcp"},
    )

    with pytest.raises(RuntimeError, match="tool timed out"):
        await wrapped.coroutine(runtime=_runtime_context(), question="analyze")

    await asyncio.wait_for(rewarmed.wait(), timeout=1)
    assert invalidated == [("hr-graphrag-qa", "shared")]
    assert calls == 2
