"""Regression tests for MCP tool cache initialization."""

from __future__ import annotations

import asyncio
import concurrent.futures

import pytest


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
