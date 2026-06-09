"""Run lifecycle service layer.

Centralizes the business logic for creating runs, formatting SSE
frames, and consuming stream bridge events.  Router modules
(``thread_runs``, ``runs``) are thin HTTP handlers that delegate here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import convert_to_messages

from app.gateway.deps import get_run_context, get_run_manager, get_stream_bridge
from app.gateway.utils import sanitize_log_param
from deerflow.agents.runtime_resolver import resolve_effective_agent_runtime
from deerflow.config.app_config import get_app_config
from deerflow.runtime import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    ConflictError,
    DisconnectMode,
    RunManager,
    RunRecord,
    RunStatus,
    StreamBridge,
    UnsupportedStrategyError,
    run_agent,
)
from deerflow.runtime.runs.naming import resolve_root_run_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------


def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """Format a single SSE frame.

    Field order: ``event:`` -> ``data:`` -> ``id:`` (optional) -> blank line.
    This matches the LangGraph Platform wire format consumed by the
    ``useStream`` React hook and the Python ``langgraph-sdk`` SSE decoder.
    """
    payload = json.dumps(data, default=str, ensure_ascii=False)
    parts = [f"event: {event}", f"data: {payload}"]
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Input / config helpers
# ---------------------------------------------------------------------------


_HR_BOSS_AGENT_ID = "hr-boss-agent"


def _truthy_context_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _is_hr_boss_run(assistant_id: str | None, context: Mapping[str, Any] | None) -> bool:
    if assistant_id == _HR_BOSS_AGENT_ID:
        return True
    if isinstance(context, Mapping):
        return context.get("agent_name") == _HR_BOSS_AGENT_ID
    return False


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _latest_input_text(raw_input: dict[str, Any] | None) -> str:
    if not isinstance(raw_input, Mapping):
        return ""
    messages = raw_input.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, BaseMessage):
            text = _content_to_text(message.content)
            if text.strip():
                return text
        elif isinstance(message, Mapping):
            text = _content_to_text(message.get("content"))
            if text.strip():
                return text
    return ""


def should_use_hr_boss_recommendation_fast_path(
    raw_input: dict[str, Any] | None,
    *,
    assistant_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> bool:
    """Detect HR Boss person/job recommendation prompts."""

    if isinstance(context, Mapping) and context.get("hr_boss_recommendation_fast_path") is True:
        return True
    if not _is_hr_boss_run(assistant_id, context):
        return False

    text = _latest_input_text(raw_input)
    if not text.strip():
        return False

    recommendation_terms = ("推荐", "候选", "人选", "人岗匹配", "匹配", "适合", "帮我找", "找一个", "找一名", "需要一个", "需要一名")
    talent_terms = ("经理", "主管", "负责人", "工程师", "研发", "销售", "人才", "岗位", "人员", "员工", "瓷粉")
    return any(term in text for term in recommendation_terms) and any(term in text for term in talent_terms)


def apply_hr_boss_recommendation_fast_path_context(body: Any) -> dict[str, Any]:
    """Stamp low-latency defaults for HR Boss recommendation runs."""

    body_context = getattr(body, "context", None)
    if not isinstance(body_context, dict):
        body_context = {}
        body.context = body_context

    body_context["hr_boss_recommendation_fast_path"] = True
    body_context.setdefault("thinking_enabled", False)
    return body_context


def normalize_stream_modes(
    raw: list[str] | str | None,
    *,
    assistant_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> list[str]:
    """Normalize the stream_mode parameter to a list.

    HR Boss runs are long and tool-heavy, so by default they use incremental
    message streaming instead of repeatedly sending full ``values`` snapshots.
    A caller can set ``context.include_values_stream=true`` to opt back in.
    """
    if raw is None:
        modes = ["values"]
    if isinstance(raw, str):
        modes = [raw]
    elif raw is not None:
        modes = raw if raw else ["values"]

    if _is_hr_boss_run(assistant_id, context):
        include_values = isinstance(context, Mapping) and _truthy_context_flag(context.get("include_values_stream"))
        if not include_values:
            if raw is None or raw == []:
                return ["messages-tuple"]
            if any(mode in {"messages", "messages-tuple"} for mode in modes):
                slimmed = [mode for mode in modes if mode != "values"]
                return slimmed or modes

    return modes


def normalize_input(raw_input: dict[str, Any] | None) -> dict[str, Any]:
    """Convert LangGraph Platform input format to LangChain state dict.

    Delegates dict→message coercion to ``langchain_core.messages.utils.convert_to_messages``
    so that ``additional_kwargs`` (e.g. uploaded-file metadata — gh #3132), ``id``,
    ``name``, and non-human roles (ai/system/tool) survive unchanged.  An earlier
    hand-rolled version only forwarded ``content`` and collapsed every role to
    ``HumanMessage``, which silently stripped frontend-supplied attachments.

    Malformed message dicts (missing ``role``/``type``/``content``, unsupported
    role, etc.) raise ``HTTPException(400)`` with the offending index, instead
    of bubbling up as a 500.  The gateway is a system boundary, so per-entry
    validation errors are the right shape for clients to retry against.
    """
    if raw_input is None:
        return {}
    messages = raw_input.get("messages")
    if messages and isinstance(messages, list):
        converted: list[Any] = []
        for index, msg in enumerate(messages):
            if isinstance(msg, BaseMessage):
                converted.append(msg)
            elif isinstance(msg, dict):
                try:
                    converted.extend(convert_to_messages([msg]))
                except (ValueError, TypeError, NotImplementedError) as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid message at input.messages[{index}]: {exc}",
                    ) from exc
            else:
                converted.append(msg)
        return {**raw_input, "messages": converted}
    return raw_input


_DEFAULT_ASSISTANT_ID = "lead_agent"


# Whitelist of run-context keys that the langgraph-compat layer forwards from
# ``body.context`` into the run config. ``config["context"]`` exists in
# LangGraph >=0.6, but these values must be written to both ``configurable``
# (for legacy ``_get_runtime_config`` consumers) and ``context`` because
# LangGraph >=1.1.9 no longer makes ``ToolRuntime.context`` fall back to
# ``configurable`` for consumers like ``setup_agent``.
_CONTEXT_CONFIGURABLE_KEYS: frozenset[str] = frozenset(
    {
        "model_name",
        "mode",
        "thinking_enabled",
        "reasoning_effort",
        "is_plan_mode",
        "subagent_enabled",
        "max_concurrent_subagents",
        "agent_name",
        "effective_mcp_servers",
        "effective_skills",
        "hr_boss_recommendation_fast_path",
        "is_bootstrap",
    }
)


def merge_run_context_overrides(config: dict[str, Any], context: Mapping[str, Any] | None) -> None:
    """Merge whitelisted keys from ``body.context`` into both ``config['configurable']``
    and ``config['context']`` so they are visible to legacy configurable readers and
    to LangGraph ``ToolRuntime.context`` consumers (e.g. the ``setup_agent`` tool —
    see issue #2677)."""
    if not context:
        return
    configurable = config.setdefault("configurable", {})
    runtime_context = config.setdefault("context", {})
    for key in _CONTEXT_CONFIGURABLE_KEYS:
        if key in context:
            if isinstance(configurable, dict):
                configurable.setdefault(key, context[key])
            if isinstance(runtime_context, dict):
                runtime_context.setdefault(key, context[key])


def inject_authenticated_user_context(config: dict[str, Any], request: Request) -> None:
    """Stamp the authenticated user into the run context for background tools.

    Tool execution may happen after the request handler has returned, so tools
    that persist user-scoped files should not rely only on ambient ContextVars.
    The value comes from server-side auth state, never from client context.
    """

    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    if user_id is None:
        return

    runtime_context = config.setdefault("context", {})
    if isinstance(runtime_context, dict):
        runtime_context["user_id"] = str(user_id)


def _normalize_custom_assistant_id(assistant_id: str) -> str:
    normalized = assistant_id.strip().lower().replace("_", "-")
    if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
        raise ValueError(f"Invalid assistant_id {assistant_id!r}: must contain only letters, digits, and hyphens after normalization.")
    return normalized


def _normalize_requested_agent_name(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return _normalize_custom_assistant_id(value)


def _is_bootstrap_request(body: Any) -> bool:
    body_context = getattr(body, "context", None)
    if isinstance(body_context, Mapping) and body_context.get("is_bootstrap") is True:
        return True

    request_config = getattr(body, "config", None)
    if isinstance(request_config, Mapping):
        for key in ("context", "configurable"):
            config_context = request_config.get(key)
            if isinstance(config_context, Mapping) and config_context.get("is_bootstrap") is True:
                return True

    return False


def _requested_agent_name_from_body(body: Any) -> str | None:
    if _is_bootstrap_request(body):
        return None

    body_context = getattr(body, "context", None)
    if isinstance(body_context, Mapping) and body_context.get("agent_name") is not None:
        return _normalize_requested_agent_name(body_context["agent_name"])

    request_config = getattr(body, "config", None)
    if isinstance(request_config, Mapping):
        config_context = request_config.get("context")
        if isinstance(config_context, Mapping) and config_context.get("agent_name") is not None:
            return _normalize_requested_agent_name(config_context["agent_name"])

        configurable = request_config.get("configurable")
        if isinstance(configurable, Mapping) and configurable.get("agent_name") is not None:
            return _normalize_requested_agent_name(configurable["agent_name"])

    assistant_id = getattr(body, "assistant_id", None)
    if assistant_id and assistant_id != _DEFAULT_ASSISTANT_ID:
        return _normalize_custom_assistant_id(str(assistant_id))
    return None


def _platform_repo_from_request(request: Request) -> Any | None:
    state = getattr(request, "state", None)
    repo = getattr(state, "platform_repo", None)
    if repo is not None:
        return repo

    app = getattr(request, "app", None)
    app_state = getattr(app, "state", None)
    return getattr(app_state, "platform_repo", None)


def _authenticated_user_from_request(request: Request) -> Any | None:
    state = getattr(request, "state", None)
    user = getattr(state, "user", None)
    if user is not None:
        return user

    auth = getattr(state, "auth", None)
    return getattr(auth, "user", None)


async def resolve_and_apply_effective_runtime(body: Any, request: Request):
    """Resolve the authorized agent runtime and stamp it onto the run body."""

    user = _authenticated_user_from_request(request)
    if user is None:
        return None

    effective_runtime = await resolve_effective_agent_runtime(
        user=user,
        requested_agent_name=_requested_agent_name_from_body(body),
        platform_repo=_platform_repo_from_request(request),
        app_config=get_app_config(),
    )

    body_context = getattr(body, "context", None)
    if not isinstance(body_context, dict):
        body_context = {}
        body.context = body_context
    if effective_runtime.agent_name is not None:
        body_context["agent_name"] = effective_runtime.agent_name
    body_context["effective_mcp_servers"] = effective_runtime.effective_mcp_servers
    body_context["effective_skills"] = effective_runtime.effective_skills
    body_context["effective_allowed_tools"] = effective_runtime.effective_allowed_tools

    metadata = getattr(body, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        body.metadata = metadata
    metadata.update(effective_runtime.trace_metadata)

    return effective_runtime


def resolve_agent_factory(assistant_id: str | None):
    """Resolve the agent factory callable from config.

    Custom agents are implemented as ``lead_agent`` + an ``agent_name``
    injected into ``configurable`` or ``context`` — see
    :func:`build_run_config`.  All ``assistant_id`` values therefore map to the
    same factory; the routing happens inside ``make_lead_agent`` when it reads
    ``cfg["agent_name"]``.
    """
    from deerflow.agents.lead_agent.agent import make_lead_agent

    return make_lead_agent


def build_run_config(
    thread_id: str,
    request_config: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    *,
    assistant_id: str | None = None,
) -> dict[str, Any]:
    """Build a RunnableConfig dict for the agent.

    When *assistant_id* refers to a custom agent (anything other than
    ``"lead_agent"`` / ``None``), the name is forwarded as ``agent_name`` in
    whichever runtime options container is active: ``context`` for
    LangGraph >= 0.6.0 requests, otherwise ``configurable``.
    ``make_lead_agent`` reads this key to load the matching
    ``agents/<name>/SOUL.md`` and per-agent config — without it the agent
    silently runs as the default lead agent.

    This mirrors the channel manager's ``_resolve_run_params`` logic so that
    the LangGraph Platform-compatible HTTP API and the IM channel path behave
    identically.
    """
    config: dict[str, Any] = {"recursion_limit": 100}
    if request_config:
        # LangGraph >= 0.6.0 introduced ``context`` as the preferred way to
        # pass thread-level data and rejects requests that include both
        # ``configurable`` and ``context``.  If the caller already sends
        # ``context``, honour it and skip our own ``configurable`` dict.
        if "context" in request_config:
            if "configurable" in request_config:
                logger.warning(
                    "build_run_config: client sent both 'context' and 'configurable'; preferring 'context' (LangGraph >= 0.6.0). thread_id=%s, caller_configurable keys=%s",
                    thread_id,
                    list(request_config.get("configurable", {}).keys()),
                )
            context_value = request_config["context"]
            if context_value is None:
                context = {}
            elif isinstance(context_value, Mapping):
                context = dict(context_value)
            else:
                raise ValueError("request config 'context' must be a mapping or null.")
            config["context"] = context
        else:
            configurable = {"thread_id": thread_id}
            configurable.update(request_config.get("configurable", {}))
            config["configurable"] = configurable
        for k, v in request_config.items():
            if k not in ("configurable", "context"):
                config[k] = v
    else:
        config["configurable"] = {"thread_id": thread_id}

    # Inject custom agent name when the caller specified a non-default assistant.
    # Honour an explicit agent_name in the active runtime options container.
    if assistant_id and assistant_id != _DEFAULT_ASSISTANT_ID:
        normalized = _normalize_custom_assistant_id(assistant_id)
        if "configurable" in config:
            target = config["configurable"]
        elif "context" in config:
            target = config["context"]
        else:
            target = config.setdefault("configurable", {})
        if target is not None and "agent_name" not in target:
            target["agent_name"] = normalized
        config.setdefault("run_name", resolve_root_run_name(config, normalized))
    if metadata:
        config.setdefault("metadata", {}).update(metadata)
    return config


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


async def start_run(
    body: Any,
    thread_id: str,
    request: Request,
) -> RunRecord:
    """Create a RunRecord and launch the background agent task.

    Parameters
    ----------
    body : RunCreateRequest
        The validated request body (typed as Any to avoid circular import
        with the router module that defines the Pydantic model).
    thread_id : str
        Target thread.
    request : Request
        FastAPI request — used to retrieve singletons from ``app.state``.
    """
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    run_ctx = get_run_context(request)

    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    body_context = getattr(body, "context", None) or {}
    model_name = body_context.get("model_name")

    # Coerce non-string model_name values to str before truncation.
    if model_name is not None and not isinstance(model_name, str):
        model_name = str(model_name)

    # Validate model against the allowlist when a model_name is provided.
    if model_name:
        app_config = get_app_config()
        resolved = app_config.get_model_config(model_name)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"Model {model_name!r} is not in the configured model allowlist",
            )

    try:
        await resolve_and_apply_effective_runtime(body, request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        record = await run_mgr.create_or_reject(
            thread_id,
            body.assistant_id,
            on_disconnect=disconnect,
            metadata=body.metadata or {},
            kwargs={"input": body.input, "config": body.config},
            multitask_strategy=body.multitask_strategy,
            model_name=model_name,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedStrategyError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    # Upsert thread metadata so the thread appears in /threads/search,
    # even for threads that were never explicitly created via POST /threads
    # (e.g. stateless runs).
    try:
        existing = await run_ctx.thread_store.get(thread_id)
        if existing is None:
            await run_ctx.thread_store.create(
                thread_id,
                assistant_id=body.assistant_id,
                metadata=body.metadata,
            )
        else:
            await run_ctx.thread_store.update_status(thread_id, "running")
    except Exception:
        logger.warning("Failed to upsert thread_meta for %s (non-fatal)", sanitize_log_param(thread_id))

    agent_factory = resolve_agent_factory(body.assistant_id)
    graph_input = normalize_input(body.input)
    if should_use_hr_boss_recommendation_fast_path(
        graph_input,
        assistant_id=body.assistant_id,
        context=getattr(body, "context", None),
    ):
        apply_hr_boss_recommendation_fast_path_context(body)

    config = build_run_config(thread_id, body.config, body.metadata, assistant_id=body.assistant_id)

    # Merge DeerFlow-specific context overrides into both ``configurable`` and ``context``.
    # The ``context`` field is a custom extension for the langgraph-compat layer
    # that carries agent configuration (model_name, thinking_enabled, etc.).
    # Only agent-relevant keys are forwarded; unknown keys (e.g. thread_id) are ignored.
    merge_run_context_overrides(config, getattr(body, "context", None))
    inject_authenticated_user_context(config, request)

    stream_modes = normalize_stream_modes(
        body.stream_mode,
        assistant_id=body.assistant_id,
        context=getattr(body, "context", None),
    )

    task = asyncio.create_task(
        run_agent(
            bridge,
            run_mgr,
            record,
            ctx=run_ctx,
            agent_factory=agent_factory,
            graph_input=graph_input,
            config=config,
            stream_modes=stream_modes,
            stream_subgraphs=body.stream_subgraphs,
            interrupt_before=body.interrupt_before,
            interrupt_after=body.interrupt_after,
        )
    )
    record.task = task

    # Title sync is handled by worker.py's finally block which reads the
    # title from the checkpoint and calls thread_store.update_display_name
    # after the run completes.

    return record


async def sse_consumer(
    bridge: StreamBridge,
    record: RunRecord,
    request: Request,
    run_mgr: RunManager,
):
    """Async generator that yields SSE frames from the bridge.

    The ``finally`` block implements ``on_disconnect`` semantics:
    - ``cancel``: abort the background task on client disconnect.
    - ``continue``: let the task run; events are discarded.
    """
    last_event_id = request.headers.get("Last-Event-ID")
    try:
        async for entry in bridge.subscribe(record.run_id, last_event_id=last_event_id):
            if await request.is_disconnected():
                break

            if entry is HEARTBEAT_SENTINEL:
                yield ": heartbeat\n\n"
                continue

            if entry is END_SENTINEL:
                yield format_sse("end", None, event_id=entry.id or None)
                return

            yield format_sse(entry.event, entry.data, event_id=entry.id or None)

    finally:
        if record.status in (RunStatus.pending, RunStatus.running):
            if record.on_disconnect == DisconnectMode.cancel:
                await run_mgr.cancel(record.run_id)
