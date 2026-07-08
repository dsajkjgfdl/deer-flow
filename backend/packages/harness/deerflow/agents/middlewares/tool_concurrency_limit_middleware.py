"""Middleware for limiting concurrent executions of selected tools."""

import asyncio
import threading
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import Future
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

DEFAULT_TOOL_CONCURRENCY_LIMITS = {
    "text2cypher_answer_question": 4,
    "hr-graphrag-qa_query_global": 1,
}
DEFAULT_TOOL_PER_RUN_LIMITS = {"hr-graphrag-qa_query_global": 1}


class ToolConcurrencyLimitMiddleware(AgentMiddleware[AgentState]):
    """Queue calls when a configured tool already has too many executions."""

    def __init__(
        self,
        limits: Mapping[str, int],
        *,
        per_run_limits: Mapping[str, int] | None = None,
        max_tracked_runs: int = 1024,
    ) -> None:
        super().__init__()
        self._limits = {str(name): int(limit) for name, limit in limits.items() if int(limit) > 0}
        self._per_run_limits = {str(name): int(limit) for name, limit in (per_run_limits or {}).items() if int(limit) > 0}
        if any(limit != 1 for limit in self._per_run_limits.values()):
            raise ValueError("per_run_limits currently supports only a limit of 1")
        self._max_tracked_runs = max(1, int(max_tracked_runs))
        self._per_run_results: OrderedDict[tuple[str, str, str], Future] = OrderedDict()
        self._async_semaphores: dict[str, asyncio.Semaphore] = {}
        self._sync_semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._lock = threading.Lock()

    def _get_limit(self, request: ToolCallRequest) -> tuple[str, int] | None:
        tool_name = str(request.tool_call.get("name") or "")
        limit = self._limits.get(tool_name)
        if limit is None:
            return None
        return tool_name, limit

    def _get_sync_semaphore(self, tool_name: str, limit: int) -> threading.BoundedSemaphore:
        with self._lock:
            semaphore = self._sync_semaphores.get(tool_name)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(limit)
                self._sync_semaphores[tool_name] = semaphore
            return semaphore

    def _get_async_semaphore(self, tool_name: str, limit: int) -> asyncio.Semaphore:
        with self._lock:
            semaphore = self._async_semaphores.get(tool_name)
            if semaphore is None:
                semaphore = asyncio.Semaphore(limit)
                self._async_semaphores[tool_name] = semaphore
            return semaphore

    @staticmethod
    def _runtime_context(request: ToolCallRequest) -> Mapping[str, object]:
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        return context if isinstance(context, Mapping) else {}

    @staticmethod
    def _latest_human_message_id(request: ToolCallRequest) -> str | None:
        state = getattr(request, "state", None)
        messages = state.get("messages", []) if isinstance(state, Mapping) else []
        for message in reversed(messages):
            if getattr(message, "type", None) == "human":
                message_id = getattr(message, "id", None)
                if message_id:
                    return str(message_id)
        return None

    def _run_key(self, request: ToolCallRequest, tool_name: str) -> tuple[str, str, str]:
        context = self._runtime_context(request)
        thread_id = str(context.get("thread_id") or "default")
        run_scope = context.get("run_id") or self._latest_human_message_id(request) or "default"
        return thread_id, str(run_scope), tool_name

    def _get_per_run_result(
        self,
        request: ToolCallRequest,
    ) -> tuple[Future, bool] | None:
        tool_name = str(request.tool_call.get("name") or "")
        limit = self._per_run_limits.get(tool_name)
        if limit is None:
            return None

        key = self._run_key(request, tool_name)
        with self._lock:
            existing = self._per_run_results.get(key)
            if existing is not None:
                self._per_run_results.move_to_end(key)
                return existing, False

            result_future: Future = Future()
            self._per_run_results[key] = result_future
            while len(self._per_run_results) > self._max_tracked_runs:
                completed_key = next(
                    (candidate for candidate, future in self._per_run_results.items() if future.done()),
                    None,
                )
                if completed_key is None:
                    break
                self._per_run_results.pop(completed_key, None)
            return result_future, True

    @staticmethod
    def _rebind_result(result: ToolMessage | Command, request: ToolCallRequest) -> ToolMessage | Command:
        if not isinstance(result, ToolMessage):
            return result
        return result.model_copy(
            update={
                "tool_call_id": str(request.tool_call.get("id") or "missing_tool_call_id"),
                "name": str(request.tool_call.get("name") or result.name or ""),
            }
        )

    @staticmethod
    def _merge_parallel_global_questions(request: ToolCallRequest) -> ToolCallRequest:
        tool_name = str(request.tool_call.get("name") or "")
        if tool_name != "hr-graphrag-qa_query_global":
            return request

        state = getattr(request, "state", None)
        messages = state.get("messages", []) if isinstance(state, Mapping) else []
        parallel_calls = []
        for message in reversed(messages):
            if getattr(message, "type", None) != "ai":
                continue
            parallel_calls = [
                call
                for call in (getattr(message, "tool_calls", None) or [])
                if isinstance(call, dict) and call.get("name") == tool_name
            ]
            break

        questions: list[str] = []
        for call in parallel_calls:
            args = call.get("args")
            question = args.get("question") if isinstance(args, Mapping) else None
            normalized = str(question or "").strip()
            if normalized and normalized not in questions:
                questions.append(normalized)
        if len(questions) <= 1:
            return request

        merged_question = "请综合回答以下相关问题：\n" + "\n".join(f"{index}. {question}" for index, question in enumerate(questions, start=1))
        args = request.tool_call.get("args")
        merged_args = dict(args) if isinstance(args, Mapping) else {}
        merged_args["question"] = merged_question
        return request.override(
            tool_call={
                **request.tool_call,
                "args": merged_args,
            }
        )

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        per_run_result = self._get_per_run_result(request)
        if per_run_result is not None and not per_run_result[1]:
            return self._rebind_result(per_run_result[0].result(), request)

        execution_request = self._merge_parallel_global_questions(request)
        limited_tool = self._get_limit(execution_request)
        try:
            if limited_tool is None:
                result = handler(execution_request)
            else:
                tool_name, limit = limited_tool
                semaphore = self._get_sync_semaphore(tool_name, limit)
                semaphore.acquire()
                try:
                    result = handler(execution_request)
                finally:
                    semaphore.release()
        except BaseException as exc:
            if per_run_result is not None:
                per_run_result[0].set_exception(exc)
            raise

        if per_run_result is not None:
            per_run_result[0].set_result(result)
        return result

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        per_run_result = self._get_per_run_result(request)
        if per_run_result is not None and not per_run_result[1]:
            result = await asyncio.wrap_future(per_run_result[0])
            return self._rebind_result(result, request)

        execution_request = self._merge_parallel_global_questions(request)
        limited_tool = self._get_limit(execution_request)
        try:
            if limited_tool is None:
                result = await handler(execution_request)
            else:
                tool_name, limit = limited_tool
                semaphore = self._get_async_semaphore(tool_name, limit)
                async with semaphore:
                    result = await handler(execution_request)
        except BaseException as exc:
            if per_run_result is not None:
                per_run_result[0].set_exception(exc)
            raise

        if per_run_result is not None:
            per_run_result[0].set_result(result)
        return result
