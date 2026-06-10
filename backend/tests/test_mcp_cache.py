"""Regression tests for MCP tool cache initialization."""

from __future__ import annotations

import asyncio
import builtins
import concurrent.futures
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_get_mcp_tools_propagates_missing_adapter(monkeypatch):
    """A missing required MCP adapter must fail startup instead of caching no tools."""
    from deerflow.mcp import tools as mcp_tools

    original_import = builtins.__import__

    def fail_adapter_import(name, *args, **kwargs):
        if name == "langchain_mcp_adapters.client":
            raise ImportError("adapter unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_adapter_import)

    with pytest.raises(ImportError, match="adapter unavailable"):
        await mcp_tools.get_mcp_tools()


@pytest.mark.asyncio
async def test_get_mcp_tools_propagates_discovery_failure(monkeypatch):
    """Tool discovery failures must reach the cache layer so startup can retry."""
    from langchain_mcp_adapters import client as mcp_client

    from deerflow.mcp import tools as mcp_tools

    class FailingClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def get_tools(self, *, server_name):
            raise RuntimeError(f"{server_name} unavailable")

    async def no_oauth_headers(_extensions_config):
        return {}

    monkeypatch.setattr(mcp_tools.ExtensionsConfig, "from_file", lambda: SimpleNamespace(model_extra={}))
    monkeypatch.setattr(
        mcp_tools,
        "build_servers_config",
        lambda _extensions_config: {"text2cypher": {"transport": "stdio", "command": "x", "args": []}},
    )
    monkeypatch.setattr(mcp_tools, "get_initial_oauth_headers", no_oauth_headers)
    monkeypatch.setattr(mcp_tools, "build_oauth_tool_interceptor", lambda _extensions_config: None)
    monkeypatch.setattr(mcp_client, "MultiServerMCPClient", FailingClient)

    with pytest.raises(RuntimeError, match="text2cypher unavailable"):
        await mcp_tools.get_mcp_tools()


@pytest.mark.asyncio
async def test_initialize_mcp_tools_does_not_cache_loading_failure(monkeypatch):
    """A transient load failure must remain retryable."""
    from deerflow.mcp import cache
    from deerflow.mcp import tools as mcp_tools

    monkeypatch.setattr(cache, "_cache_initialized", False)
    monkeypatch.setattr(cache, "_mcp_tools_cache", None)
    monkeypatch.setattr(cache, "_config_mtime", None)

    async def fail_loading():
        raise RuntimeError("temporary MCP startup failure")

    monkeypatch.setattr(mcp_tools, "get_mcp_tools", fail_loading)

    with pytest.raises(RuntimeError, match="temporary MCP startup failure"):
        await cache.initialize_mcp_tools()

    assert cache._cache_initialized is False
    assert cache._mcp_tools_cache is None


def test_get_cached_mcp_tools_never_blocks_a_running_event_loop(monkeypatch):
    """A synchronous cache read must fail fast while async initialization runs."""
    from deerflow.mcp import cache

    monkeypatch.setattr(cache, "_cache_initialized", False)
    monkeypatch.setattr(cache, "_mcp_tools_cache", None)
    monkeypatch.setattr(cache, "_is_cache_stale", lambda: False)

    class RejectingExecutor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def submit(self, *_args, **_kwargs):
            raise AssertionError("blocking lazy initialization attempted")

    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", RejectingExecutor)

    async def read_cache() -> None:
        with pytest.raises(RuntimeError, match="MCP tools are not initialized"):
            cache.get_cached_mcp_tools()

    asyncio.run(read_cache())
