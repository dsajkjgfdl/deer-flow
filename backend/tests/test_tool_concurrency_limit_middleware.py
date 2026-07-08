import asyncio
import importlib
import importlib.util
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest


def _load_middleware_class():
    module_name = "deerflow.agents.middlewares.tool_concurrency_limit_middleware"
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, "tool concurrency limit middleware module is missing"
    module = importlib.import_module(module_name)
    return module.ToolConcurrencyLimitMiddleware


def _request(
    name: str,
    call_id: str,
    *,
    args: dict | None = None,
    run_id: str = "run-1",
    thread_id: str = "thread-1",
    human_id: str = "human-1",
    messages: list | None = None,
):
    return ToolCallRequest(
        tool_call={"name": name, "id": call_id, "args": args or {}},
        tool=None,
        runtime=SimpleNamespace(context={"run_id": run_id, "thread_id": thread_id}),
        state={"messages": messages or [SimpleNamespace(type="human", id=human_id)]},
    )


def test_factory_feature_chain_includes_tool_concurrency_limit_before_error_handler():
    ToolConcurrencyLimitMiddleware = _load_middleware_class()
    from deerflow.agents.factory import _assemble_from_features
    from deerflow.agents.features import RuntimeFeatures
    from deerflow.agents.middlewares.tool_error_handling_middleware import ToolErrorHandlingMiddleware

    chain, _tools = _assemble_from_features(RuntimeFeatures(sandbox=False, loop_detection=False))
    limiter_index = next(
        (index for index, middleware in enumerate(chain) if isinstance(middleware, ToolConcurrencyLimitMiddleware)),
        None,
    )
    error_index = next(index for index, middleware in enumerate(chain) if isinstance(middleware, ToolErrorHandlingMiddleware))

    assert limiter_index is not None
    assert limiter_index < error_index
    limiter = chain[limiter_index]
    assert limiter._limits["hr-graphrag-qa_query_global"] == 1
    assert limiter._per_run_limits["hr-graphrag-qa_query_global"] == 1


def test_lead_runtime_chain_enforces_global_limit_per_run():
    ToolConcurrencyLimitMiddleware = _load_middleware_class()
    from deerflow.agents.middlewares.tool_error_handling_middleware import build_lead_runtime_middlewares
    from deerflow.config import get_app_config

    chain = build_lead_runtime_middlewares(app_config=get_app_config())
    limiter = next(middleware for middleware in chain if isinstance(middleware, ToolConcurrencyLimitMiddleware))

    assert limiter._limits["hr-graphrag-qa_query_global"] == 1
    assert limiter._per_run_limits["hr-graphrag-qa_query_global"] == 1


@pytest.mark.asyncio
async def test_async_tool_calls_for_limited_tool_are_queued_after_limit():
    ToolConcurrencyLimitMiddleware = _load_middleware_class()
    middleware = ToolConcurrencyLimitMiddleware({"text2cypher_answer_question": 4})
    release = asyncio.Event()
    first_batch_started = asyncio.Event()
    active = 0
    peak_active = 0
    started = 0

    async def handler(request):
        nonlocal active, peak_active, started
        active += 1
        started += 1
        peak_active = max(peak_active, active)
        if started == 4:
            first_batch_started.set()

        try:
            await release.wait()
            return ToolMessage(
                content="ok",
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
            )
        finally:
            active -= 1

    tasks = [
        asyncio.create_task(
            middleware.awrap_tool_call(
                _request("text2cypher_answer_question", f"call-{index}"),
                handler,
            )
        )
        for index in range(6)
    ]

    try:
        await asyncio.wait_for(first_batch_started.wait(), timeout=1)
        await asyncio.sleep(0.05)

        assert started == 4
        assert peak_active == 4
        assert all(not task.done() for task in tasks)

        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        assert len(results) == 6
        assert started == 6
        assert peak_active == 4
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_async_limit_applies_only_to_configured_tool_name():
    ToolConcurrencyLimitMiddleware = _load_middleware_class()
    middleware = ToolConcurrencyLimitMiddleware({"text2cypher_answer_question": 1})
    release = asyncio.Event()
    both_started = asyncio.Event()
    active = 0
    peak_active = 0
    started = 0

    async def handler(request):
        nonlocal active, peak_active, started
        active += 1
        started += 1
        peak_active = max(peak_active, active)
        if started == 2:
            both_started.set()

        try:
            await release.wait()
            return ToolMessage(
                content="ok",
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
            )
        finally:
            active -= 1

    tasks = [
        asyncio.create_task(
            middleware.awrap_tool_call(
                _request("text2cypher_answer_question", "limited"),
                handler,
            )
        ),
        asyncio.create_task(
            middleware.awrap_tool_call(
                _request("hr-graphrag-qa_query_local", "unlimited"),
                handler,
            )
        ),
    ]

    try:
        await asyncio.wait_for(both_started.wait(), timeout=1)

        assert started == 2
        assert peak_active == 2

        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)

        assert [result.name for result in results] == [
            "text2cypher_answer_question",
            "hr-graphrag-qa_query_local",
        ]
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_global_tool_executes_once_and_shares_result_for_parallel_calls():
    ToolConcurrencyLimitMiddleware = _load_middleware_class()
    tool_name = "hr-graphrag-qa_query_global"
    middleware = ToolConcurrencyLimitMiddleware(
        {tool_name: 1},
        per_run_limits={tool_name: 1},
    )
    handler_calls: list[str] = []

    async def handler(request):
        handler_calls.append(request.tool_call["id"])
        await asyncio.sleep(0.01)
        return ToolMessage(
            content="ok",
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
        )

    results = await asyncio.gather(
        *[
            middleware.awrap_tool_call(
                _request(tool_name, f"call-{index}"),
                handler,
            )
            for index in range(5)
        ]
    )

    assert len(handler_calls) == 1
    assert all(result.content == "ok" for result in results)
    assert [result.tool_call_id for result in results] == [f"call-{index}" for index in range(5)]


@pytest.mark.asyncio
async def test_global_tool_retry_reuses_same_run_result_but_next_run_executes_again():
    ToolConcurrencyLimitMiddleware = _load_middleware_class()
    tool_name = "hr-graphrag-qa_query_global"
    middleware = ToolConcurrencyLimitMiddleware(
        {tool_name: 1},
        per_run_limits={tool_name: 1},
    )
    handler_calls: list[str] = []

    async def handler(request):
        handler_calls.append(request.tool_call["id"])
        return ToolMessage(
            content="ok",
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
        )

    first = await middleware.awrap_tool_call(
        _request(tool_name, "first", run_id="run-1"),
        handler,
    )
    retry = await middleware.awrap_tool_call(
        _request(tool_name, "retry", run_id="run-1"),
        handler,
    )
    next_run = await middleware.awrap_tool_call(
        _request(tool_name, "next-run", run_id="run-2"),
        handler,
    )

    assert first.content == "ok"
    assert retry.content == "ok"
    assert retry.tool_call_id == "retry"
    assert next_run.content == "ok"
    assert handler_calls == ["first", "next-run"]


@pytest.mark.asyncio
async def test_global_singleflight_merges_parallel_questions_before_execution():
    ToolConcurrencyLimitMiddleware = _load_middleware_class()
    tool_name = "hr-graphrag-qa_query_global"
    middleware = ToolConcurrencyLimitMiddleware(
        {tool_name: 1},
        per_run_limits={tool_name: 1},
    )
    tool_calls = [
        {"name": tool_name, "id": "call-1", "args": {"question": "分析组织画像"}},
        {"name": tool_name, "id": "call-2", "args": {"question": "分析人才结构"}},
        {"name": tool_name, "id": "call-3", "args": {"question": "分析整体风险"}},
    ]
    messages = [
        SimpleNamespace(type="human", id="human-1"),
        SimpleNamespace(type="ai", tool_calls=tool_calls),
    ]
    executed_questions: list[str] = []

    async def handler(request):
        executed_questions.append(request.tool_call["args"]["question"])
        return ToolMessage(
            content="ok",
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
        )

    await asyncio.gather(
        *[
            middleware.awrap_tool_call(
                _request(
                    tool_name,
                    tool_call["id"],
                    args=tool_call["args"],
                    messages=messages,
                ),
                handler,
            )
            for tool_call in tool_calls
        ]
    )

    assert executed_questions == [
        "请综合回答以下相关问题：\n1. 分析组织画像\n2. 分析人才结构\n3. 分析整体风险"
    ]
