"""Tests for the MCP persistent-session pool."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deerflow.mcp.session_pool import MCPSessionPool, get_session_pool, reset_session_pool


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_session_pool()
    yield
    reset_session_pool()


# ---------------------------------------------------------------------------
# MCPSessionPool unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_creates_new():
    """First call for a key creates a new session."""
    pool = MCPSessionPool()

    mock_session = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm):
        session = await pool.get_session("server", "thread-1", {"transport": "stdio", "command": "x", "args": []})

    assert session is mock_session
    mock_session.initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_session_reuses_existing():
    """Second call for the same key returns the cached session."""
    pool = MCPSessionPool()

    mock_session = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm):
        s1 = await pool.get_session("server", "thread-1", {"transport": "stdio", "command": "x", "args": []})
        s2 = await pool.get_session("server", "thread-1", {"transport": "stdio", "command": "x", "args": []})

    assert s1 is s2
    # Only one session should have been created.
    assert mock_cm.__aenter__.await_count == 1


@pytest.mark.asyncio
async def test_concurrent_get_session_for_same_key_creates_once_and_closes_once():
    """Concurrent callers share one in-flight creation instead of leaking a loser."""
    pool = MCPSessionPool()
    creation_started = asyncio.Event()
    allow_creation = asyncio.Event()
    mock_session = AsyncMock()

    class SlowCm:
        def __init__(self):
            self.closed = False

        async def __aenter__(self):
            creation_started.set()
            await allow_creation.wait()
            return mock_session

        async def __aexit__(self, *args):
            self.closed = True
            return False

    cms: list[SlowCm] = []

    def make_cm(*_args, **_kwargs):
        cm = SlowCm()
        cms.append(cm)
        return cm

    with patch("langchain_mcp_adapters.sessions.create_session", side_effect=make_cm) as create_session:
        first = asyncio.create_task(pool.get_session("text2cypher", "shared", {"transport": "stdio", "command": "x", "args": []}))
        await creation_started.wait()
        second = asyncio.create_task(pool.get_session("text2cypher", "shared", {"transport": "stdio", "command": "x", "args": []}))
        await asyncio.sleep(0)
        allow_creation.set()
        first_session, second_session = await asyncio.gather(first, second)

    assert first_session is mock_session
    assert second_session is mock_session
    assert create_session.call_count == 1
    assert len(cms) == 1

    await pool.close_all()

    assert cms[0].closed is True


@pytest.mark.asyncio
async def test_close_all_cancels_pending_session_creation():
    """Closing the pool must not allow an in-flight creator to register later."""
    pool = MCPSessionPool()
    creation_started = asyncio.Event()
    allow_creation = asyncio.Event()

    class SlowCm:
        def __init__(self):
            self.closed = False

        async def __aenter__(self):
            creation_started.set()
            await allow_creation.wait()
            return AsyncMock()

        async def __aexit__(self, *args):
            self.closed = True
            return False

    cm = SlowCm()
    with patch("langchain_mcp_adapters.sessions.create_session", return_value=cm):
        pending = asyncio.create_task(pool.get_session("text2cypher", "shared", {"transport": "stdio", "command": "x", "args": []}))
        await creation_started.wait()
        await pool.close_all()
        allow_creation.set()

        with pytest.raises(asyncio.CancelledError):
            await pending

    assert len(pool._entries) == 0
    assert len(pool._context_managers) == 0
    assert len(pool._pending_creations) == 0


def test_close_all_sync_cancels_pending_session_creation():
    """Synchronous cache reset must also stop creators owned by another loop."""
    pool = MCPSessionPool()
    creation_started = threading.Event()
    creation_cancelled = threading.Event()

    class SlowCm:
        async def __aenter__(self):
            creation_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                creation_cancelled.set()
                raise

        async def __aexit__(self, *args):
            return False

    async def create_pending():
        with patch("langchain_mcp_adapters.sessions.create_session", return_value=SlowCm()):
            await pool.get_session("text2cypher", "shared", {"transport": "stdio", "command": "x", "args": []})

    def run_loop():
        try:
            asyncio.run(create_pending())
        except asyncio.CancelledError:
            pass

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    assert creation_started.wait(timeout=1)

    pool.close_all_sync()
    thread.join(timeout=0.2)

    assert creation_cancelled.is_set()
    assert not thread.is_alive()
    assert len(pool._entries) == 0
    assert len(pool._pending_creations) == 0


@pytest.mark.asyncio
async def test_failed_session_initialization_closes_context_and_allows_retry():
    """A failed creator does not leak its context or poison later calls."""
    pool = MCPSessionPool()
    failed_session = AsyncMock()
    failed_session.initialize.side_effect = RuntimeError("init failed")
    healthy_session = AsyncMock()

    class Cm:
        def __init__(self, session):
            self.session = session
            self.closed = False

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, *args):
            self.closed = True
            return False

    failed_cm = Cm(failed_session)
    healthy_cm = Cm(healthy_session)

    with patch("langchain_mcp_adapters.sessions.create_session", side_effect=[failed_cm, healthy_cm]):
        with pytest.raises(RuntimeError, match="init failed"):
            await pool.get_session("text2cypher", "shared", {"transport": "stdio", "command": "x", "args": []})
        result = await pool.get_session("text2cypher", "shared", {"transport": "stdio", "command": "x", "args": []})

    assert failed_cm.closed is True
    assert result is healthy_session


@pytest.mark.asyncio
async def test_different_scope_creates_different_session():
    """Different scope keys get different sessions."""
    pool = MCPSessionPool()

    sessions = [AsyncMock(), AsyncMock()]
    idx = 0

    class CmFactory:
        def __init__(self):
            self.enter_count = 0

        async def __aenter__(self):
            nonlocal idx
            s = sessions[idx]
            idx += 1
            self.enter_count += 1
            return s

        async def __aexit__(self, *args):
            return False

    with patch("langchain_mcp_adapters.sessions.create_session", side_effect=lambda *a, **kw: CmFactory()):
        s1 = await pool.get_session("server", "thread-1", {"transport": "stdio", "command": "x", "args": []})
        s2 = await pool.get_session("server", "thread-2", {"transport": "stdio", "command": "x", "args": []})

    assert s1 is not s2
    assert s1 is sessions[0]
    assert s2 is sessions[1]


@pytest.mark.asyncio
async def test_lru_eviction():
    """Oldest entries are evicted when the pool is full."""
    pool = MCPSessionPool()
    pool.MAX_SESSIONS = 2

    class CmFactory:
        def __init__(self):
            self.closed = False

        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            self.closed = True
            return False

    cms: list[CmFactory] = []

    def make_cm(*a, **kw):
        cm = CmFactory()
        cms.append(cm)
        return cm

    with patch("langchain_mcp_adapters.sessions.create_session", side_effect=make_cm):
        await pool.get_session("s", "t1", {"transport": "stdio", "command": "x", "args": []})
        await pool.get_session("s", "t2", {"transport": "stdio", "command": "x", "args": []})
        # Pool is full (2). Adding t3 should evict t1.
        await pool.get_session("s", "t3", {"transport": "stdio", "command": "x", "args": []})

    assert cms[0].closed is True
    assert cms[1].closed is False
    assert cms[2].closed is False


@pytest.mark.asyncio
async def test_close_scope():
    """close_scope shuts down sessions for a specific scope key."""
    pool = MCPSessionPool()

    class CmFactory:
        def __init__(self):
            self.closed = False

        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            self.closed = True
            return False

    cms: list[CmFactory] = []

    def make_cm(*a, **kw):
        cm = CmFactory()
        cms.append(cm)
        return cm

    with patch("langchain_mcp_adapters.sessions.create_session", side_effect=make_cm):
        await pool.get_session("s", "t1", {"transport": "stdio", "command": "x", "args": []})
        await pool.get_session("s", "t2", {"transport": "stdio", "command": "x", "args": []})

    await pool.close_scope("t1")

    assert cms[0].closed is True
    assert cms[1].closed is False

    # t2 session still exists.
    assert ("s", "t2") in pool._entries


@pytest.mark.asyncio
async def test_close_all():
    """close_all shuts down every session."""
    pool = MCPSessionPool()

    class CmFactory:
        def __init__(self):
            self.closed = False

        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, *args):
            self.closed = True
            return False

    cms: list[CmFactory] = []

    def make_cm(*a, **kw):
        cm = CmFactory()
        cms.append(cm)
        return cm

    with patch("langchain_mcp_adapters.sessions.create_session", side_effect=make_cm):
        await pool.get_session("s1", "t1", {"transport": "stdio", "command": "x", "args": []})
        await pool.get_session("s2", "t2", {"transport": "stdio", "command": "x", "args": []})

    await pool.close_all()

    assert all(cm.closed for cm in cms)
    assert len(pool._entries) == 0


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------


def test_get_session_pool_singleton():
    """get_session_pool returns the same instance."""
    p1 = get_session_pool()
    p2 = get_session_pool()
    assert p1 is p2


def test_reset_session_pool():
    """reset_session_pool clears the singleton."""
    p1 = get_session_pool()
    reset_session_pool()
    p2 = get_session_pool()
    assert p1 is not p2


# ---------------------------------------------------------------------------
# Integration: _make_session_pool_tool uses the pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_pool_tool_wrapping():
    """The wrapper tool delegates to a pool-managed session."""
    # Build a dummy StructuredTool (as returned by langchain-mcp-adapters).
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from deerflow.mcp.tools import _make_session_pool_tool

    class Args(BaseModel):
        url: str = Field(..., description="url")

    original_tool = StructuredTool(
        name="playwright_navigate",
        description="Navigate browser",
        args_schema=Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False, structuredContent=None))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    connection = {"transport": "stdio", "command": "pw", "args": []}

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm):
        wrapped = _make_session_pool_tool(original_tool, "playwright", connection)

        # Simulate a tool call with a runtime context containing thread_id.
        mock_runtime = MagicMock()
        mock_runtime.context = {"thread_id": "thread-42"}
        mock_runtime.config = {}

        await wrapped.coroutine(runtime=mock_runtime, url="https://example.com")

    mock_session.call_tool.assert_awaited_once_with("navigate", {"url": "https://example.com"})


@pytest.mark.asyncio
async def test_session_pool_tool_extracts_thread_id():
    """Thread ID is extracted from runtime.config when not in context."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from deerflow.mcp.tools import _make_session_pool_tool

    class Args(BaseModel):
        x: int = Field(..., description="x")

    original_tool = StructuredTool(
        name="server_tool",
        description="test",
        args_schema=Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False, structuredContent=None))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm):
        wrapped = _make_session_pool_tool(original_tool, "server", {"transport": "stdio", "command": "x", "args": []})

        mock_runtime = MagicMock()
        mock_runtime.context = {}
        mock_runtime.config = {"configurable": {"thread_id": "from-config"}}

        await wrapped.coroutine(runtime=mock_runtime, x=1)

    # Verify the session was created with the correct scope key.
    pool = get_session_pool()
    assert ("server", "from-config") in pool._entries


@pytest.mark.asyncio
async def test_session_pool_tool_uses_shared_scope_for_hr_query_servers():
    """Stateless HR MCP servers should not pay a new session startup per thread."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from deerflow.mcp.tools import _make_session_pool_tool

    class Args(BaseModel):
        question: str = Field(..., description="question")

    original_tool = StructuredTool(
        name="text2cypher_answer_question",
        description="Answer HR question.",
        args_schema=Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False, structuredContent=None))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm):
        wrapped = _make_session_pool_tool(original_tool, "text2cypher", {"transport": "stdio", "command": "x", "args": []})

        runtime_a = MagicMock()
        runtime_a.context = {"thread_id": "thread-a"}
        runtime_a.config = {}
        runtime_b = MagicMock()
        runtime_b.context = {"thread_id": "thread-b"}
        runtime_b.config = {}

        await wrapped.coroutine(runtime=runtime_a, question="q1")
        await wrapped.coroutine(runtime=runtime_b, question="q2")

    pool = get_session_pool()
    assert ("text2cypher", "shared") in pool._entries
    assert ("text2cypher", "thread-a") not in pool._entries
    assert ("text2cypher", "thread-b") not in pool._entries
    assert mock_cm.__aenter__.await_count == 1


@pytest.mark.asyncio
async def test_prewarm_shared_mcp_sessions_prioritizes_text2cypher(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    calls: list[tuple[str, str, dict]] = []

    class Pool:
        async def get_session(self, server_name, scope_key, connection):
            calls.append((server_name, scope_key, connection))

    monkeypatch.setattr(mcp_tools, "get_session_pool", lambda: Pool())

    await mcp_tools._prewarm_shared_mcp_sessions(
        {
            "hr-graphrag-qa": {"transport": "stdio", "command": "graphrag"},
            "text2cypher": {"transport": "stdio", "command": "text2cypher"},
            "playwright": {"transport": "stdio", "command": "playwright"},
        }
    )

    assert calls == [
        ("text2cypher", "shared", {"transport": "stdio", "command": "text2cypher"}),
    ]


@pytest.mark.asyncio
async def test_prewarm_shared_mcp_session_does_not_cancel_slow_stdio_startup(monkeypatch):
    from deerflow.mcp import tools as mcp_tools

    completed = False

    class Pool:
        async def get_session(self, _server_name, _scope_key, _connection):
            nonlocal completed
            await asyncio.sleep(0.05)
            completed = True

    monkeypatch.setattr(mcp_tools, "get_session_pool", lambda: Pool())
    monkeypatch.setattr(mcp_tools, "_SHARED_SESSION_PREWARM_TIMEOUT_SECONDS", 0.01, raising=False)

    await mcp_tools._prewarm_shared_mcp_sessions({"text2cypher": {"transport": "stdio", "command": "text2cypher"}})

    assert completed is True


@pytest.mark.asyncio
async def test_session_pool_tool_default_scope():
    """When no thread_id is available, 'default' is used as scope key."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from deerflow.mcp.tools import _make_session_pool_tool

    class Args(BaseModel):
        x: int = Field(..., description="x")

    original_tool = StructuredTool(
        name="server_tool",
        description="test",
        args_schema=Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False, structuredContent=None))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm):
        wrapped = _make_session_pool_tool(original_tool, "server", {"transport": "stdio", "command": "x", "args": []})

        # No thread_id in runtime at all.
        await wrapped.coroutine(runtime=None, x=1)

    pool = get_session_pool()
    assert ("server", "default") in pool._entries


@pytest.mark.asyncio
async def test_session_pool_tool_get_config_fallback():
    """When runtime is None, get_config() provides thread_id as fallback."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from deerflow.mcp.tools import _make_session_pool_tool

    class Args(BaseModel):
        x: int = Field(..., description="x")

    original_tool = StructuredTool(
        name="server_tool",
        description="test",
        args_schema=Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False, structuredContent=None))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    fake_config = {"configurable": {"thread_id": "from-langgraph-config"}}

    with (
        patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm),
        patch("deerflow.mcp.tools.get_config", return_value=fake_config),
    ):
        wrapped = _make_session_pool_tool(original_tool, "server", {"transport": "stdio", "command": "x", "args": []})

        # runtime=None — get_config() fallback should provide thread_id
        await wrapped.coroutine(runtime=None, x=1)

    pool = get_session_pool()
    assert ("server", "from-langgraph-config") in pool._entries


def test_session_pool_tool_sync_wrapper_path_is_safe():
    """Sync wrapper (tool.func) invocation doesn't crash on cross-loop access."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from deerflow.mcp.tools import _make_session_pool_tool
    from deerflow.tools.sync import make_sync_tool_wrapper

    class Args(BaseModel):
        url: str = Field(..., description="url")

    original_tool = StructuredTool(
        name="playwright_navigate",
        description="Navigate browser",
        args_schema=Args,
        coroutine=AsyncMock(),
        response_format="content_and_artifact",
    )

    mock_session = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[], isError=False, structuredContent=None))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    connection = {"transport": "stdio", "command": "pw", "args": []}

    with patch("langchain_mcp_adapters.sessions.create_session", return_value=mock_cm):
        wrapped = _make_session_pool_tool(original_tool, "playwright", connection)
        # Attach the sync wrapper exactly as get_mcp_tools() does.
        wrapped.func = make_sync_tool_wrapper(wrapped.coroutine, wrapped.name)

        # Call via the sync path (asyncio.run in a worker thread).
        # runtime is not supplied so _extract_thread_id falls back to "default".
        wrapped.func(url="https://example.com")

    mock_session.call_tool.assert_called_once_with("navigate", {"url": "https://example.com"})
    mock_cm.__aexit__.assert_awaited_once()
    pool = get_session_pool()
    assert ("playwright", "default") not in pool._entries
