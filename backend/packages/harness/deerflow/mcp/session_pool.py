"""Persistent MCP session pool for stateful tool calls.

Each session is owned by one long-lived asyncio task. The owner task enters and
exits the MCP context manager, which keeps AnyIO task-group lifecycles valid
while still allowing callers to reuse the initialized ClientSession.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession

logger = logging.getLogger(__name__)


@dataclass
class _SessionEntry:
    session: ClientSession
    loop: asyncio.AbstractEventLoop
    owner_task: asyncio.Task[None]
    close_event: asyncio.Event


class MCPSessionPool:
    """Manage persistent MCP sessions scoped by ``(server_name, scope_key)``."""

    MAX_SESSIONS = 256
    SESSION_CLOSE_TIMEOUT = 5.0

    def __init__(self) -> None:
        self._entries: OrderedDict[tuple[str, str], _SessionEntry] = OrderedDict()
        self._pending_creations: dict[
            tuple[str, str, asyncio.AbstractEventLoop],
            asyncio.Task[ClientSession],
        ] = {}
        self._lock = threading.Lock()

    async def get_session(
        self,
        server_name: str,
        scope_key: str,
        connection: dict[str, Any],
    ) -> ClientSession:
        """Get or create a healthy persistent MCP session."""
        key = (server_name, scope_key)
        current_loop = asyncio.get_running_loop()
        pending_key = (server_name, scope_key, current_loop)
        entry_to_close: _SessionEntry | None = None

        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing.loop is current_loop and not existing.owner_task.done():
                self._entries.move_to_end(key)
                return existing.session
            if existing is not None:
                entry_to_close = self._entries.pop(key)

            creation_task = self._pending_creations.get(pending_key)
            if creation_task is None:
                creation_task = current_loop.create_task(
                    self._create_and_register_session(key, connection, current_loop),
                    name=f"mcp-session-create:{server_name}/{scope_key}",
                )
                self._pending_creations[pending_key] = creation_task
                creation_task.add_done_callback(
                    lambda done, pending_key=pending_key: self._finish_pending_creation(pending_key, done)
                )

        if entry_to_close is not None:
            self._request_close(entry_to_close)

        return await asyncio.shield(creation_task)

    async def _create_and_register_session(
        self,
        key: tuple[str, str],
        connection: dict[str, Any],
        current_loop: asyncio.AbstractEventLoop,
    ) -> ClientSession:
        entries_to_close: list[_SessionEntry] = []
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing.loop is current_loop and not existing.owner_task.done():
                self._entries.move_to_end(key)
                return existing.session
            if existing is not None:
                entries_to_close.append(self._entries.pop(key))

            while len(self._entries) >= self.MAX_SESSIONS:
                oldest_key = next(iter(self._entries))
                entries_to_close.append(self._entries.pop(oldest_key))

        for entry in entries_to_close:
            self._request_close(entry)

        ready: asyncio.Future[ClientSession] = current_loop.create_future()
        close_event = asyncio.Event()
        owner_task = current_loop.create_task(
            self._own_session(key, connection, ready, close_event),
            name=f"mcp-session-owner:{key[0]}/{key[1]}",
        )

        try:
            session = await asyncio.shield(ready)
        except BaseException:
            close_event.set()
            await asyncio.gather(owner_task, return_exceptions=True)
            raise

        entry = _SessionEntry(
            session=session,
            loop=current_loop,
            owner_task=owner_task,
            close_event=close_event,
        )
        winner = entry
        displaced_entry: _SessionEntry | None = None
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing.loop is current_loop and not existing.owner_task.done():
                winner = existing
                self._entries.move_to_end(key)
            else:
                if existing is not None:
                    displaced_entry = self._entries.pop(key)
                self._entries[key] = entry

        if winner is not entry:
            self._request_close(entry)
            return winner.session
        if displaced_entry is not None:
            self._request_close(displaced_entry)

        owner_task.add_done_callback(lambda done, key=key: self._owner_finished(key, done))
        logger.info("Created persistent MCP session for %s/%s", key[0], key[1])
        return session

    async def _own_session(
        self,
        key: tuple[str, str],
        connection: dict[str, Any],
        ready: asyncio.Future[ClientSession],
        close_event: asyncio.Event,
    ) -> None:
        """Enter, maintain, and exit one MCP session within the same task."""
        from langchain_mcp_adapters.sessions import create_session

        try:
            async with create_session(connection) as session:
                await session.initialize()
                if not ready.done():
                    ready.set_result(session)
                await close_event.wait()
        except BaseException as exc:
            if not ready.done():
                if isinstance(exc, asyncio.CancelledError):
                    ready.cancel()
                else:
                    ready.set_exception(exc)
            elif not isinstance(exc, asyncio.CancelledError):
                logger.warning("Persistent MCP session owner stopped for %s", key, exc_info=True)

    def _owner_finished(self, key: tuple[str, str], owner_task: asyncio.Task[None]) -> None:
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing.owner_task is owner_task:
                self._entries.pop(key, None)

    def _finish_pending_creation(
        self,
        pending_key: tuple[str, str, asyncio.AbstractEventLoop],
        task: asyncio.Task[ClientSession],
    ) -> None:
        with self._lock:
            if self._pending_creations.get(pending_key) is task:
                self._pending_creations.pop(pending_key, None)
        if not task.cancelled():
            task.exception()

    @staticmethod
    async def _cancel_task(task: asyncio.Task[ClientSession]) -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _cancel_pending_creations(
        self,
        *,
        server_name: str | None = None,
        scope_key: str | None = None,
    ) -> None:
        current_loop = asyncio.get_running_loop()
        with self._lock:
            matching = [
                (key, task)
                for key, task in self._pending_creations.items()
                if (server_name is None or key[0] == server_name)
                and (scope_key is None or key[1] == scope_key)
            ]
            for key, _ in matching:
                self._pending_creations.pop(key, None)

        local_tasks: list[asyncio.Task[ClientSession]] = []
        foreign_futures: list[asyncio.Future[None]] = []
        for _, task in matching:
            if task.done():
                continue
            owner_loop = task.get_loop()
            if owner_loop is current_loop:
                task.cancel()
                local_tasks.append(task)
            elif not owner_loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(self._cancel_task(task), owner_loop)
                foreign_futures.append(asyncio.wrap_future(future))

        if local_tasks:
            await asyncio.gather(*local_tasks, return_exceptions=True)
        if foreign_futures:
            await asyncio.gather(*foreign_futures, return_exceptions=True)

    @staticmethod
    def _request_close(entry: _SessionEntry) -> None:
        if entry.loop.is_closed() or entry.owner_task.done():
            return
        entry.loop.call_soon_threadsafe(entry.close_event.set)

    async def _wait_closed(self, entry: _SessionEntry) -> None:
        self._request_close(entry)
        if entry.owner_task.done():
            return

        current_loop = asyncio.get_running_loop()
        if entry.loop is current_loop:
            try:
                await asyncio.wait_for(asyncio.shield(entry.owner_task), timeout=self.SESSION_CLOSE_TIMEOUT)
            except TimeoutError:
                logger.warning("Timed out closing persistent MCP session")
            return

        future = asyncio.run_coroutine_threadsafe(self._wait_closed(entry), entry.loop)
        try:
            await asyncio.wait_for(asyncio.wrap_future(future), timeout=self.SESSION_CLOSE_TIMEOUT)
        except TimeoutError:
            logger.warning("Timed out closing persistent MCP session on its owner loop")

    async def invalidate(self, server_name: str, scope_key: str) -> None:
        """Remove a failed session and ask its owner task to close it."""
        key = (server_name, scope_key)
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is not None:
            self._request_close(entry)

    async def close_scope(self, scope_key: str) -> None:
        await self._cancel_pending_creations(scope_key=scope_key)
        with self._lock:
            keys = [key for key in self._entries if key[1] == scope_key]
            entries = [self._entries.pop(key) for key in keys]
        await asyncio.gather(*(self._wait_closed(entry) for entry in entries))

    async def close_server(self, server_name: str) -> None:
        await self._cancel_pending_creations(server_name=server_name)
        with self._lock:
            keys = [key for key in self._entries if key[0] == server_name]
            entries = [self._entries.pop(key) for key in keys]
        await asyncio.gather(*(self._wait_closed(entry) for entry in entries))

    async def close_all(self) -> None:
        await self._cancel_pending_creations()
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        await asyncio.gather(*(self._wait_closed(entry) for entry in entries))

    def close_all_sync(self) -> None:
        """Request closure on each session's owner loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        with self._lock:
            pending_tasks = list(self._pending_creations.values())
            self._pending_creations.clear()
            entries = list(self._entries.values())
            self._entries.clear()

        for task in pending_tasks:
            if task.done():
                continue
            loop = task.get_loop()
            if loop.is_closed():
                continue
            try:
                if loop is current_loop:
                    task.cancel()
                elif loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(self._cancel_task(task), loop)
                    future.result(timeout=self.SESSION_CLOSE_TIMEOUT)
                else:
                    loop.run_until_complete(self._cancel_task(task))
            except Exception:
                logger.debug("Error cancelling pending MCP session during sync close", exc_info=True)

        for entry in entries:
            loop = entry.loop
            if loop.is_closed():
                continue
            try:
                if loop is current_loop:
                    self._request_close(entry)
                elif loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(self._wait_closed(entry), loop)
                    future.result(timeout=self.SESSION_CLOSE_TIMEOUT)
                else:
                    loop.run_until_complete(self._wait_closed(entry))
            except Exception:
                logger.debug("Error closing MCP session during sync close", exc_info=True)


_pool: MCPSessionPool | None = None
_pool_lock = threading.Lock()


def get_session_pool() -> MCPSessionPool:
    """Return the global session-pool singleton."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = MCPSessionPool()
    return _pool


def reset_session_pool() -> None:
    """Reset the singleton (for tests)."""
    global _pool
    _pool = None
