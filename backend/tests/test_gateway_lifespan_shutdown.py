"""Regression tests for Gateway lifespan shutdown.

These tests guard the invariant that lifespan shutdown is *bounded*: a
misbehaving channel whose ``stop()`` blocks forever must not keep the
uvicorn worker alive. A hung worker is the precondition for the
signal-reentrancy deadlock described in
``app.gateway.app._SHUTDOWN_HOOK_TIMEOUT_SECONDS``.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI


@asynccontextmanager
async def _noop_langgraph_runtime(_app, _startup_config):
    yield


async def _run_lifespan_with_hanging_stop() -> float:
    """Drive the lifespan context with stop_channel_service hanging forever.

    Returns the elapsed wall-clock seconds.
    """
    from app.gateway.app import _SHUTDOWN_HOOK_TIMEOUT_SECONDS, lifespan

    async def hang_forever() -> None:
        await asyncio.sleep(3600)

    app = FastAPI()

    fake_service = MagicMock()
    fake_service.get_status = MagicMock(return_value={})

    async def fake_start():
        return fake_service

    with (
        patch("app.gateway.app.get_app_config"),
        patch("app.gateway.app.get_gateway_config", return_value=MagicMock(host="x", port=0)),
        patch("app.gateway.app.langgraph_runtime", _noop_langgraph_runtime),
        patch("deerflow.mcp.initialize_mcp_tools"),
        patch("app.channels.service.start_channel_service", side_effect=fake_start),
        patch("app.channels.service.stop_channel_service", side_effect=hang_forever),
    ):
        loop = asyncio.get_event_loop()
        start = loop.time()
        async with lifespan(app):
            pass
        elapsed = loop.time() - start

    assert _SHUTDOWN_HOOK_TIMEOUT_SECONDS < 30.0, "Timeout constant must stay modest"
    return elapsed


def test_shutdown_is_bounded_when_channel_stop_hangs():
    """Lifespan exit must complete near the configured timeout, not hang."""
    from app.gateway.app import _SHUTDOWN_HOOK_TIMEOUT_SECONDS

    elapsed = asyncio.run(_run_lifespan_with_hanging_stop())

    # Generous upper bound: timeout + 2s slack for scheduling overhead.
    assert elapsed < _SHUTDOWN_HOOK_TIMEOUT_SECONDS + 2.0, f"Lifespan shutdown took {elapsed:.2f}s; expected <= {_SHUTDOWN_HOOK_TIMEOUT_SECONDS + 2.0:.1f}s"
    # Lower bound: the wait_for should actually have waited.
    assert elapsed >= _SHUTDOWN_HOOK_TIMEOUT_SECONDS - 0.5, f"Lifespan exited too quickly ({elapsed:.2f}s); wait_for may not have been invoked."


def test_lifespan_initializes_mcp_tools_before_starting_channels():
    """Channels must not accept messages until MCP tool discovery completes."""

    from app.gateway.app import lifespan

    async def run() -> None:
        initialization_started = asyncio.Event()
        channel_started = asyncio.Event()
        release = asyncio.Event()
        app = FastAPI()

        fake_service = MagicMock()
        fake_service.get_status = MagicMock(return_value={})

        async def fake_initialize_mcp_tools():
            initialization_started.set()
            await release.wait()
            return []

        async def fake_start(_startup_config):
            channel_started.set()
            return fake_service

        with (
            patch("app.gateway.app.get_app_config"),
            patch("app.gateway.app.get_gateway_config", return_value=MagicMock(host="x", port=0)),
            patch("app.gateway.app.langgraph_runtime", _noop_langgraph_runtime),
            patch("deerflow.mcp.initialize_mcp_tools", side_effect=fake_initialize_mcp_tools),
            patch("app.channels.service.start_channel_service", side_effect=fake_start),
            patch("app.channels.service.stop_channel_service"),
        ):
            lifespan_context = lifespan(app)
            enter_task = asyncio.create_task(lifespan_context.__aenter__())
            entered = False
            try:
                await asyncio.wait_for(initialization_started.wait(), timeout=1.0)
                assert not channel_started.is_set()

                release.set()
                await asyncio.wait_for(enter_task, timeout=1.0)
                entered = True
                assert channel_started.is_set()
            finally:
                release.set()
                if not enter_task.done():
                    await asyncio.wait_for(enter_task, timeout=1.0)
                    entered = True
                if entered:
                    await lifespan_context.__aexit__(None, None, None)

    asyncio.run(run())


def test_lifespan_does_not_start_channels_when_mcp_initialization_fails():
    """A gateway without required MCP tools must not accept channel traffic."""

    from app.gateway.app import lifespan

    async def run() -> None:
        channel_started = False
        app = FastAPI()

        async def fail_initialize_mcp_tools():
            raise RuntimeError("temporary MCP startup failure")

        async def fake_start(_startup_config):
            nonlocal channel_started
            channel_started = True
            return MagicMock()

        with (
            patch("app.gateway.app.get_app_config"),
            patch("app.gateway.app.get_gateway_config", return_value=MagicMock(host="x", port=0)),
            patch("app.gateway.app.langgraph_runtime", _noop_langgraph_runtime),
            patch("deerflow.mcp.initialize_mcp_tools", side_effect=fail_initialize_mcp_tools),
            patch("app.channels.service.start_channel_service", side_effect=fake_start),
        ):
            with pytest.raises(RuntimeError, match="temporary MCP startup failure"):
                async with lifespan(app):
                    pass

        assert channel_started is False

    asyncio.run(run())
