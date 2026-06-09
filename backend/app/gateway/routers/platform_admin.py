from __future__ import annotations

from datetime import UTC, datetime
from inspect import isawaitable, signature
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.gateway.authz import require_admin
from app.gateway.deps import get_feedback_repo, get_local_provider, get_run_event_store
from deerflow.agents.catalog import AgentCatalogEntry, scan_agent_catalog

router = APIRouter(prefix="/api/platform/admin", tags=["platform-admin"])


class AgentCatalogResponse(BaseModel):
    agents: list[AgentCatalogEntry]


class UserAgentAssignmentsResponse(BaseModel):
    user_id: str
    agent_names: list[str]


class PlatformUserResponse(BaseModel):
    id: str
    email: str
    system_role: str
    needs_setup: bool = False
    created_at: str


class PlatformUsersResponse(BaseModel):
    items: list[PlatformUserResponse]
    total: int
    limit: int
    offset: int


class GrantAgentResponse(BaseModel):
    user_id: str
    agent_name: str
    granted: bool


class RevokeAgentResponse(BaseModel):
    user_id: str
    agent_name: str
    revoked: bool


class AdminAuditResponse(BaseModel):
    items: list[dict[str, Any]]


class RunMonitoringResponse(BaseModel):
    items: list[dict[str, Any]]


class ToolMonitoringResponse(BaseModel):
    items: list[dict[str, Any]]
    recent_failures: list[dict[str, Any]] = Field(default_factory=list)


class MonitoringIdentityResponse(BaseModel):
    identity_type: str
    identity_source: str | None = None
    identity_display: str | None = None
    raw_identity: dict[str, Any] = Field(default_factory=dict)


class MonitoringConversationItemResponse(BaseModel):
    thread_id: str
    run_id: str | None = None
    user_id: str | None = None
    agent_name: str | None = None
    status: str | None = None
    message_count: int | None = None
    message_preview: str | None = None
    error: str | None = None
    updated_at: str | None = None
    updated_at_bj: str | None = None
    identity: MonitoringIdentityResponse


class MonitoringConversationsResponse(BaseModel):
    items: list[MonitoringConversationItemResponse]
    total: int
    limit: int
    offset: int


class MonitoringConversationResponse(BaseModel):
    thread_id: str
    identity: MonitoringIdentityResponse
    runs: list[dict[str, Any]]
    message_preview: str | None = None


class MonitoringTimelineResponse(BaseModel):
    run: dict[str, Any]
    identity: MonitoringIdentityResponse
    events: list[dict[str, Any]]


class RecentFeedbackResponse(BaseModel):
    items: list[dict[str, Any]]


class FeedbackConversationResponse(BaseModel):
    feedback: dict[str, Any]
    messages: list[dict[str, Any]]


_BJ_TZ = ZoneInfo("Asia/Shanghai")
_RECENT_SCAN_CHUNK_SIZE = 200
_MISSING_SEQ_SORT_VALUE = 1_000_000


def _platform_repo(request: Request):
    repo = getattr(request.app.state, "platform_repo", None)
    if repo is None:
        raise HTTPException(status_code=503, detail="Platform repository not available")
    return repo


def _actor_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user is None:
        auth = getattr(request.state, "auth", None)
        user = getattr(auth, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return str(user.id)


def _catalog_by_name() -> dict[str, AgentCatalogEntry]:
    return {entry.name: entry for entry in scan_agent_catalog()}


def _datetime_from_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, int | float):
        dt = datetime.fromtimestamp(value, UTC)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _monitoring_filter_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid monitoring time: {value}") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_BJ_TZ)
    return dt.astimezone(UTC)


def _iso_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    dt = _datetime_from_value(value)
    if dt is not None:
        return dt.isoformat()
    text = str(value).strip()
    return text or None


def _bj_text(value: Any) -> str | None:
    dt = _datetime_from_value(value)
    if dt is None:
        return None
    return dt.astimezone(_BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _assignable_agent(agent_name: str) -> AgentCatalogEntry:
    entry = _catalog_by_name().get(agent_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    if entry.status == "invalid":
        raise HTTPException(status_code=400, detail=f"Agent '{agent_name}' is invalid: {entry.validation_errors}")
    return entry


def _channel_store(request: Request):
    store = getattr(request.app.state, "channel_store", None)
    if store is not None:
        return store
    try:
        from app.channels.service import get_channel_service

        service = get_channel_service()
    except Exception:
        return None
    return getattr(service, "store", None) if service is not None else None


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


async def _channel_entries_by_thread(request: Request) -> dict[str, dict[str, Any]]:
    store = _channel_store(request)
    if store is None:
        return {}
    try:
        entries = await _maybe_await(store.list_entries())
    except Exception:
        return {}
    by_thread: dict[str, dict[str, Any]] = {}
    for entry in entries or []:
        thread_id = entry.get("thread_id")
        if thread_id:
            by_thread[str(thread_id)] = dict(entry)
    return by_thread


def _identity_for_thread(
    thread_id: str,
    user_id: Any,
    channel_entries: dict[str, dict[str, Any]],
) -> MonitoringIdentityResponse:
    entry = channel_entries.get(thread_id)
    if entry is not None:
        channel_name = str(entry.get("channel_name") or "channel")
        channel_user_id = entry.get("user_id")
        chat_id = entry.get("chat_id")
        topic_id = entry.get("topic_id")
        display_value = channel_user_id or chat_id or thread_id
        raw_identity = {}
        if channel_user_id:
            raw_identity["channel_user_id"] = str(channel_user_id)
        if chat_id:
            raw_identity["chat_id"] = str(chat_id)
        if topic_id:
            raw_identity["topic_id"] = str(topic_id)
        return MonitoringIdentityResponse(
            identity_type="channel",
            identity_source=channel_name,
            identity_display=f"{channel_name}: {display_value}",
            raw_identity=raw_identity,
        )

    if user_id:
        user_id_text = str(user_id)
        return MonitoringIdentityResponse(
            identity_type="web",
            identity_source="web",
            identity_display=user_id_text,
            raw_identity={"user_id": user_id_text},
        )

    return MonitoringIdentityResponse(
        identity_type="unknown",
        identity_source=None,
        identity_display=thread_id,
        raw_identity={},
    )


async def _with_feedback_user_email(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    provider = get_local_provider()
    user_cache: dict[str, Any] = {}
    enriched: list[dict[str, Any]] = []
    for item in items:
        data = dict(item)
        user_id = data.get("user_id")
        user_email = None
        if user_id:
            user_id_text = str(user_id)
            if user_id_text not in user_cache:
                user_cache[user_id_text] = await provider.get_user(user_id_text)
            user = user_cache[user_id_text]
            user_email = getattr(user, "email", None) if user is not None else None
        data["user_email"] = user_email
        enriched.append(data)
    return enriched


async def _list_run_messages_for_admin(
    request: Request,
    *,
    thread_id: str,
    run_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    event_store = get_run_event_store(request)
    kwargs: dict[str, Any] = {"limit": limit}
    if "user_id" in signature(event_store.list_messages_by_run).parameters:
        kwargs["user_id"] = None
    return await event_store.list_messages_by_run(thread_id, run_id, **kwargs)


def _messages_from_feedback_summary(feedback: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    thread_id = str(feedback["thread_id"])
    run_id = str(feedback["run_id"])
    first_human_message = feedback.get("first_human_message")
    if first_human_message:
        messages.append(
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "event_type": "human_message",
                "category": "message",
                "content": {"type": "human", "content": str(first_human_message)},
                "metadata": {"source": "run_summary"},
                "seq": 1,
            }
        )
    last_ai_message = feedback.get("last_ai_message")
    if last_ai_message:
        messages.append(
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "event_type": "ai_message",
                "category": "message",
                "content": {"type": "ai", "content": str(last_ai_message)},
                "metadata": {"source": "run_summary"},
                "seq": len(messages) + 1,
            }
        )
    return messages


def _monitoring_run_id(row: dict[str, Any]) -> str | None:
    value = row.get("run_id") or row.get("latest_run_id")
    return str(value) if value else None


_INTERNAL_PROMPT_MARKERS = (
    "<role>",
    "<primary_objective>",
    "context extraction assistant",
    "your sole objective",
)


def _is_internal_prompt(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.lower()
    return any(marker in normalized for marker in _INTERNAL_PROMPT_MARKERS)


def _message_content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                value = block.get("text") or block.get("content")
                if isinstance(value, str):
                    parts.append(value)
        return "".join(parts).strip() or None
    if isinstance(content, dict):
        value = content.get("text") or content.get("content")
        return value.strip() if isinstance(value, str) and value.strip() else None
    return None


def _question_from_run_input(row: dict[str, Any]) -> str | None:
    kwargs = row.get("kwargs") or row.get("kwargs_json")
    if not isinstance(kwargs, dict):
        return None
    graph_input = kwargs.get("input")
    if not isinstance(graph_input, dict):
        return None
    messages = graph_input.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        role = message.get("role") or message.get("type")
        if role not in {"human", "user"} or message.get("name") == "summary":
            continue
        text = _message_content_text(message.get("content"))
        if text and not _is_internal_prompt(text):
            return text[:2000]
    return None


def _monitoring_question(row: dict[str, Any]) -> str | None:
    first_human_message = row.get("first_human_message")
    if first_human_message and not _is_internal_prompt(first_human_message):
        return str(first_human_message)
    return _question_from_run_input(row)


def _message_preview(row: dict[str, Any]) -> str | None:
    value = _monitoring_question(row) or row.get("last_message") or row.get("last_ai_message")
    return str(value) if value else None


def _error_summary(row: dict[str, Any]) -> str | None:
    value = row.get("error_summary") or row.get("error")
    return str(value) if value else None


def _normalize_monitoring_run(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    run_id = _monitoring_run_id(data)
    if run_id is not None:
        data["run_id"] = run_id
    if "model" not in data and data.get("model_name") is not None:
        data["model"] = data.get("model_name")
    data["created_at"] = _iso_text(data.get("created_at"))
    data["updated_at"] = _iso_text(data.get("updated_at"))
    data["created_at_bj"] = _bj_text(data.get("created_at"))
    data["updated_at_bj"] = _bj_text(data.get("updated_at"))
    question = _monitoring_question(data)
    if question is not None:
        data["first_human_message"] = question
    data["message_preview"] = _message_preview(data)
    data["error_summary"] = _error_summary(data)
    return data


def _conversation_item_from_row(
    row: dict[str, Any],
    channel_entries: dict[str, dict[str, Any]],
) -> MonitoringConversationItemResponse:
    thread_id = str(row["thread_id"])
    updated_at = _iso_text(row.get("updated_at"))
    return MonitoringConversationItemResponse(
        thread_id=thread_id,
        run_id=_monitoring_run_id(row),
        user_id=str(row["user_id"]) if row.get("user_id") else None,
        agent_name=str(row["agent_name"]) if row.get("agent_name") else None,
        status=str(row["status"]) if row.get("status") else None,
        message_count=row.get("message_count"),
        message_preview=_message_preview(row),
        error=_error_summary(row),
        updated_at=updated_at,
        updated_at_bj=_bj_text(updated_at),
        identity=_identity_for_thread(thread_id, row.get("user_id"), channel_entries),
    )


def _source_matches(
    source: str | None,
    thread_id: str,
    channel_entries: dict[str, dict[str, Any]],
) -> bool:
    if not source:
        return True
    source_key = source.strip().lower()
    entry = channel_entries.get(thread_id)
    if source_key == "web":
        return entry is None
    if source_key in {"im", "channel"}:
        return entry is not None
    return entry is not None and str(entry.get("channel_name") or "").lower() == source_key


def _source_thread_ids_for_filter(
    source: str | None,
    channel_entries: dict[str, dict[str, Any]],
) -> list[str] | None:
    if not source:
        return None
    source_key = source.strip().lower()
    if not source_key or source_key == "web":
        return None
    if source_key in {"im", "channel"}:
        return sorted(channel_entries)
    return sorted(thread_id for thread_id, entry in channel_entries.items() if str(entry.get("channel_name") or "").lower() == source_key)


def _intersect_thread_ids(*thread_id_filters: list[str] | None) -> list[str] | None:
    constrained = [set(thread_ids) for thread_ids in thread_id_filters if thread_ids is not None]
    if not constrained:
        return None
    result = constrained[0]
    for thread_ids in constrained[1:]:
        result &= thread_ids
    return sorted(result)


async def _monitoring_tool_thread_ids(
    repo: Any,
    *,
    tool_name: str | None = None,
    mcp_server_name: str | None = None,
    q: str | None = None,
) -> set[str]:
    method = getattr(repo, "list_monitoring_tool_thread_ids", None)
    if method is None:
        return set()
    result = await _maybe_await(
        method(
            tool_name=tool_name,
            mcp_server_name=mcp_server_name,
            q=q,
        )
    )
    return {str(thread_id) for thread_id in result or [] if thread_id}


def _normalized_query(q: str | None) -> str | None:
    if q is None:
        return None
    text = q.strip().lower()
    return text or None


def _scalar_text_values(data: dict[str, Any]) -> list[str]:
    return [str(value) for value in data.values() if isinstance(value, str | int | float | bool)]


def _contains_query(values: list[Any], query: str | None) -> bool:
    if query is None:
        return True
    return any(query in str(value).lower() for value in values if value is not None)


def _conversation_matches_query(
    row: dict[str, Any],
    *,
    query: str | None,
    channel_entries: dict[str, dict[str, Any]],
    tool_query_thread_ids: set[str],
) -> bool:
    if query is None:
        return True

    row_values = [
        row.get("thread_id"),
        row.get("run_id"),
        row.get("latest_run_id"),
        row.get("user_id"),
        row.get("agent_name"),
        row.get("status"),
        row.get("last_message"),
        row.get("message_preview"),
        row.get("error"),
        row.get("error_summary"),
        _message_preview(row),
        _error_summary(row),
    ]
    thread_id = str(row.get("thread_id") or "")
    channel_values = _scalar_text_values(channel_entries.get(thread_id, {}))
    return thread_id in tool_query_thread_ids or _contains_query(row_values + channel_values, query)


def _conversation_matches_time_range(
    row: dict[str, Any],
    *,
    from_time: datetime | None,
    to_time: datetime | None,
) -> bool:
    occurred_at = _datetime_from_value(row.get("updated_at") or row.get("created_at"))
    if occurred_at is None:
        return from_time is None and to_time is None
    if from_time is not None and occurred_at < from_time:
        return False
    if to_time is not None and occurred_at > to_time:
        return False
    return True


def _conversation_matches_filters(
    row: dict[str, Any],
    *,
    source: str | None,
    agent_name: str | None,
    status: str | None,
    q: str | None,
    channel_entries: dict[str, dict[str, Any]],
    tool_query_thread_ids: set[str],
    allowed_thread_ids: set[str] | None,
    from_time: datetime | None,
    to_time: datetime | None,
) -> bool:
    thread_id = str(row.get("thread_id") or "")
    if allowed_thread_ids is not None and thread_id not in allowed_thread_ids:
        return False
    if not _source_matches(source, thread_id, channel_entries):
        return False
    if agent_name and row.get("agent_name") != agent_name:
        return False
    if status and row.get("status") != status:
        return False
    if not _conversation_matches_query(
        row,
        query=_normalized_query(q),
        channel_entries=channel_entries,
        tool_query_thread_ids=tool_query_thread_ids,
    ):
        return False
    if not _conversation_matches_time_range(row, from_time=from_time, to_time=to_time):
        return False
    return True


def _repo_recent_kwargs(
    repo: Any,
    *,
    limit: int,
    offset: int,
    q: str | None,
    agent_name: str | None = None,
    status: str | None = None,
    source_thread_ids: list[str] | None = None,
) -> dict[str, Any]:
    params = signature(repo.list_recent_monitoring_conversations).parameters
    supports_kwargs = any(param.kind == param.VAR_KEYWORD for param in params.values())
    kwargs: dict[str, Any] = {}
    values = {
        "limit": limit,
        "offset": offset,
        "q": q,
        "agent_name": agent_name,
        "status": status,
        "source_thread_ids": source_thread_ids,
    }
    for key, value in values.items():
        if value is None and key in {"agent_name", "status", "source_thread_ids"}:
            continue
        if supports_kwargs or key in params:
            kwargs[key] = value
    return kwargs


def _normalize_recent_result(result: Any) -> tuple[list[dict[str, Any]], int, int, int]:
    if isinstance(result, dict):
        items = list(result.get("items") or [])
        total = int(result.get("total") or len(items))
        limit = int(result.get("limit") or len(items))
        offset = int(result.get("offset") or 0)
        return items, total, limit, offset
    items = list(result or [])
    return items, len(items), len(items), 0


async def _recent_conversations_page(
    repo: Any,
    *,
    limit: int,
    offset: int,
    q: str | None,
    agent_name: str | None,
    status: str | None,
    source_thread_ids: list[str] | None,
) -> tuple[list[dict[str, Any]], int, int, int]:
    result = await repo.list_recent_monitoring_conversations(
        **_repo_recent_kwargs(
            repo,
            limit=limit,
            offset=offset,
            q=q,
            agent_name=agent_name,
            status=status,
            source_thread_ids=source_thread_ids,
        )
    )
    return _normalize_recent_result(result)


def _needs_local_recent_filter(
    repo_kwargs: dict[str, Any],
    *,
    source: str | None,
    source_thread_ids: list[str] | None,
    agent_name: str | None,
    status: str | None,
    q: str | None,
    from_time: datetime | None,
    to_time: datetime | None,
    thread_filter_required: bool,
) -> bool:
    if thread_filter_required or _normalized_query(q) or from_time is not None or to_time is not None:
        return True
    source_key = source.strip().lower() if source else ""
    if source_key == "web":
        return True
    if source_thread_ids is not None and "source_thread_ids" not in repo_kwargs:
        return True
    if agent_name and "agent_name" not in repo_kwargs:
        return True
    if status and "status" not in repo_kwargs:
        return True
    return False


async def _scan_recent_conversations(
    repo: Any,
    *,
    q: str | None,
    agent_name: str | None,
    status: str | None,
    source_thread_ids: list[str] | None,
    source: str | None,
    channel_entries: dict[str, dict[str, Any]],
    tool_query_thread_ids: set[str],
    allowed_thread_ids: set[str] | None,
    from_time: datetime | None,
    to_time: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    collected: list[dict[str, Any]] = []
    matched_total = 0
    repo_offset = 0
    while True:
        rows, repo_total, _repo_limit, _repo_offset = await _recent_conversations_page(
            repo,
            limit=_RECENT_SCAN_CHUNK_SIZE,
            offset=repo_offset,
            q=None,
            agent_name=agent_name,
            status=status,
            source_thread_ids=source_thread_ids,
        )
        if not rows:
            break

        for row in rows:
            if not _conversation_matches_filters(
                row,
                source=source,
                agent_name=agent_name,
                status=status,
                q=q,
                channel_entries=channel_entries,
                tool_query_thread_ids=tool_query_thread_ids,
                allowed_thread_ids=allowed_thread_ids,
                from_time=from_time,
                to_time=to_time,
            ):
                continue
            if matched_total >= offset and len(collected) < limit:
                collected.append(row)
            matched_total += 1

        repo_offset += _RECENT_SCAN_CHUNK_SIZE
        if len(rows) < _RECENT_SCAN_CHUNK_SIZE:
            break
        if repo_total and repo_offset >= repo_total:
            break

    return collected, matched_total


async def _list_run_events_for_admin(
    request: Request,
    *,
    thread_id: str,
    run_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    event_store = get_run_event_store(request)
    kwargs: dict[str, Any] = {"limit": limit}
    if "user_id" in signature(event_store.list_events).parameters:
        kwargs["user_id"] = None
    return await event_store.list_events(thread_id, run_id, **kwargs)


def _timeline_run_event(event: dict[str, Any]) -> dict[str, Any]:
    occurred_at = _iso_text(event.get("created_at") or event.get("occurred_at"))
    return {
        "kind": str(event.get("event_type") or event.get("kind") or "event"),
        "source": "run_event",
        "thread_id": event.get("thread_id"),
        "run_id": event.get("run_id"),
        "category": event.get("category"),
        "seq": event.get("seq"),
        "occurred_at": occurred_at,
        "occurred_at_bj": _bj_text(occurred_at),
        "content": event.get("content"),
        "metadata": event.get("metadata") or {},
    }


def _timeline_tool_audit(audit: dict[str, Any]) -> dict[str, Any]:
    status = str(audit.get("status") or "")
    occurred_at = _iso_text(audit.get("created_at") or audit.get("updated_at"))
    error = audit.get("error")
    content = audit.get("content") if isinstance(audit.get("content"), dict) else {}
    if error:
        content = {**content, "error": str(error)}
    return {
        "kind": "tool.error" if status == "error" else "tool.end",
        "source": "tool_audit",
        "thread_id": audit.get("thread_id"),
        "run_id": audit.get("run_id"),
        "tool_name": audit.get("tool_name"),
        "mcp_server_name": audit.get("mcp_server_name"),
        "status": status or None,
        "duration_ms": audit.get("duration_ms") if audit.get("duration_ms") is not None else audit.get("latency_ms"),
        "seq": audit.get("seq"),
        "occurred_at": occurred_at,
        "occurred_at_bj": _bj_text(occurred_at),
        "content": content,
        "metadata": audit.get("metadata_json") or audit.get("metadata") or {},
    }


def _timeline_sort_key(event: dict[str, Any]) -> tuple[datetime, int]:
    occurred_at = _datetime_from_value(event.get("occurred_at")) or datetime.max.replace(tzinfo=UTC)
    seq = event.get("seq")
    return occurred_at, seq if isinstance(seq, int) else _MISSING_SEQ_SORT_VALUE


def _merge_timeline_events(
    run_events: list[dict[str, Any]],
    tool_audits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events = [_timeline_run_event(event) for event in run_events]
    events.extend(_timeline_tool_audit(audit) for audit in tool_audits)
    return sorted(events, key=_timeline_sort_key)


def _summary_timeline_event(
    run: dict[str, Any],
    *,
    kind: str,
    seq: int,
    occurred_at: Any,
    content: dict[str, Any],
    status: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    occurred_at_text = _iso_text(occurred_at)
    metadata = {
        "source": "run_summary",
        "trace_available": False,
    }
    return {
        "kind": kind,
        "source": "run_event",
        "thread_id": run.get("thread_id"),
        "run_id": run.get("run_id"),
        "category": "summary",
        "status": status,
        "duration_ms": duration_ms,
        "seq": seq,
        "occurred_at": occurred_at_text,
        "occurred_at_bj": _bj_text(occurred_at_text),
        "content": content,
        "metadata": metadata,
    }


def _summary_timeline_events(run: dict[str, Any]) -> list[dict[str, Any]]:
    created_at = run.get("created_at")
    updated_at = run.get("updated_at") or created_at
    status = str(run.get("status")) if run.get("status") is not None else None
    events: list[dict[str, Any]] = [
        _summary_timeline_event(
            run,
            kind="run.start",
            seq=1,
            occurred_at=created_at,
            content={"status": status},
            status="running",
        )
    ]

    first_human_message = _monitoring_question(run)
    if first_human_message:
        events.append(
            _summary_timeline_event(
                run,
                kind="human_message",
                seq=len(events) + 1,
                occurred_at=created_at,
                content={"type": "human", "content": str(first_human_message)},
            )
        )

    last_ai_message = run.get("last_ai_message")
    if last_ai_message:
        events.append(
            _summary_timeline_event(
                run,
                kind="ai_message",
                seq=len(events) + 1,
                occurred_at=updated_at,
                content={"type": "ai", "content": str(last_ai_message)},
            )
        )

    started_at = _datetime_from_value(created_at)
    ended_at = _datetime_from_value(updated_at)
    duration_ms = None
    if started_at is not None and ended_at is not None:
        duration_ms = max(0, int((ended_at - started_at).total_seconds() * 1000))

    end_content: dict[str, Any] = {"status": status}
    error = run.get("error_summary") or run.get("error")
    if error:
        end_content["error"] = str(error)
    events.append(
        _summary_timeline_event(
            run,
            kind="run.end",
            seq=len(events) + 1,
            occurred_at=updated_at,
            content=end_content,
            status=status,
            duration_ms=duration_ms,
        )
    )
    return events


@router.get("/agents/catalog", response_model=AgentCatalogResponse)
@require_admin
async def list_agent_catalog(request: Request) -> AgentCatalogResponse:
    return AgentCatalogResponse(agents=scan_agent_catalog())


@router.get("/users", response_model=PlatformUsersResponse)
@require_admin
async def list_platform_users(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PlatformUsersResponse:
    users, total = await get_local_provider().list_users(limit=limit, offset=offset)
    return PlatformUsersResponse(
        items=[
            PlatformUserResponse(
                id=str(user.id),
                email=user.email,
                system_role=user.system_role,
                needs_setup=user.needs_setup,
                created_at=user.created_at.isoformat(),
            )
            for user in users
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}/agents", response_model=UserAgentAssignmentsResponse)
@require_admin
async def list_user_agent_assignments(user_id: str, request: Request) -> UserAgentAssignmentsResponse:
    agent_names = await _platform_repo(request).list_user_agents(user_id)
    return UserAgentAssignmentsResponse(user_id=user_id, agent_names=agent_names)


@router.put("/users/{user_id}/agents/{agent_name}", response_model=GrantAgentResponse)
@require_admin
async def grant_user_agent(user_id: str, agent_name: str, request: Request) -> GrantAgentResponse:
    _assignable_agent(agent_name)
    granted = await _platform_repo(request).grant_agent(
        user_id,
        agent_name,
        actor_user_id=_actor_user_id(request),
    )
    return GrantAgentResponse(user_id=user_id, agent_name=agent_name, granted=granted)


@router.delete("/users/{user_id}/agents/{agent_name}", response_model=RevokeAgentResponse)
@require_admin
async def revoke_user_agent(user_id: str, agent_name: str, request: Request) -> RevokeAgentResponse:
    revoked = await _platform_repo(request).revoke_agent(
        user_id,
        agent_name,
        actor_user_id=_actor_user_id(request),
    )
    return RevokeAgentResponse(user_id=user_id, agent_name=agent_name, revoked=revoked)


@router.get("/audit", response_model=AdminAuditResponse)
@require_admin
async def list_admin_audit(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> AdminAuditResponse:
    return AdminAuditResponse(items=await _platform_repo(request).list_admin_audit(limit=limit))


@router.get("/monitoring/conversations/recent", response_model=MonitoringConversationsResponse)
@require_admin
async def recent_monitoring_conversations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    mcp_server_name: str | None = Query(default=None),
    q: str | None = Query(default=None),
    from_time_text: str | None = Query(default=None, alias="from"),
    to_time_text: str | None = Query(default=None, alias="to"),
) -> MonitoringConversationsResponse:
    repo = _platform_repo(request)
    channel_entries = await _channel_entries_by_thread(request)
    from_time = _monitoring_filter_datetime(from_time_text)
    to_time = _monitoring_filter_datetime(to_time_text)
    if from_time is not None and to_time is not None and from_time > to_time:
        raise HTTPException(status_code=422, detail="Monitoring 'from' time must not be after 'to' time")

    source_thread_ids = _source_thread_ids_for_filter(source, channel_entries)
    tool_filter_requested = bool((tool_name and tool_name.strip()) or (mcp_server_name and mcp_server_name.strip()))
    tool_filter_thread_ids = (
        await _monitoring_tool_thread_ids(
            repo,
            tool_name=tool_name,
            mcp_server_name=mcp_server_name,
        )
        if tool_filter_requested
        else None
    )
    if tool_filter_requested and not tool_filter_thread_ids:
        return MonitoringConversationsResponse(items=[], total=0, limit=limit, offset=offset)
    source_thread_ids = _intersect_thread_ids(
        source_thread_ids,
        sorted(tool_filter_thread_ids) if tool_filter_thread_ids is not None else None,
    )
    if source_thread_ids == []:
        return MonitoringConversationsResponse(items=[], total=0, limit=limit, offset=offset)

    tool_query_thread_ids = await _monitoring_tool_thread_ids(repo, q=q) if _normalized_query(q) else set()
    repo_kwargs = _repo_recent_kwargs(
        repo,
        limit=limit,
        offset=offset,
        q=q,
        agent_name=agent_name,
        status=status,
        source_thread_ids=source_thread_ids,
    )
    if _needs_local_recent_filter(
        repo_kwargs,
        source=source,
        source_thread_ids=source_thread_ids,
        agent_name=agent_name,
        status=status,
        q=q,
        from_time=from_time,
        to_time=to_time,
        thread_filter_required=tool_filter_requested,
    ):
        rows, total = await _scan_recent_conversations(
            repo,
            q=q,
            agent_name=agent_name,
            status=status,
            source_thread_ids=source_thread_ids,
            source=source,
            channel_entries=channel_entries,
            tool_query_thread_ids=tool_query_thread_ids,
            allowed_thread_ids=set(source_thread_ids) if source_thread_ids is not None else None,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            offset=offset,
        )
    else:
        rows, total, _repo_limit, _repo_offset = await _recent_conversations_page(
            repo,
            limit=limit,
            offset=offset,
            q=q,
            agent_name=agent_name,
            status=status,
            source_thread_ids=source_thread_ids,
        )

    return MonitoringConversationsResponse(
        items=[_conversation_item_from_row(row, channel_entries) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/monitoring/conversations/{thread_id}", response_model=MonitoringConversationResponse)
@require_admin
async def monitoring_conversation_detail(
    thread_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
) -> MonitoringConversationResponse:
    repo = _platform_repo(request)
    runs = await repo.list_runs_for_thread(thread_id, limit=limit)
    if not runs:
        raise HTTPException(status_code=404, detail="Conversation not found")
    normalized_runs = [_normalize_monitoring_run(run) for run in runs]
    channel_entries = await _channel_entries_by_thread(request)
    identity = _identity_for_thread(thread_id, runs[0].get("user_id"), channel_entries)
    preview = next((run.get("message_preview") for run in normalized_runs if run.get("message_preview")), None)
    return MonitoringConversationResponse(
        thread_id=thread_id,
        identity=identity,
        runs=normalized_runs,
        message_preview=preview,
    )


@router.get("/monitoring/runs/{run_id}/timeline", response_model=MonitoringTimelineResponse)
@require_admin
async def monitoring_run_timeline(
    run_id: str,
    request: Request,
    limit: int = Query(default=500, ge=1, le=2000),
) -> MonitoringTimelineResponse:
    repo = _platform_repo(request)
    run = await repo.get_run_for_admin(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    normalized_run = _normalize_monitoring_run(run)
    thread_id = str(normalized_run["thread_id"])
    channel_entries = await _channel_entries_by_thread(request)
    run_events = await _list_run_events_for_admin(request, thread_id=thread_id, run_id=run_id, limit=limit)
    tool_audits = await repo.list_tool_audits_for_run(run_id)
    events = _merge_timeline_events(run_events, tool_audits)
    if not events:
        events = _summary_timeline_events(normalized_run)
    return MonitoringTimelineResponse(
        run=normalized_run,
        identity=_identity_for_thread(thread_id, run.get("user_id"), channel_entries),
        events=events[:limit],
    )


@router.get("/monitoring/runs/{run_id}/messages")
@require_admin
async def monitoring_run_messages(
    run_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    repo = _platform_repo(request)
    run = await repo.get_run_for_admin(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    normalized_run = _normalize_monitoring_run(run)
    thread_id = str(normalized_run["thread_id"])
    channel_entries = await _channel_entries_by_thread(request)
    messages = await _list_run_messages_for_admin(
        request,
        thread_id=thread_id,
        run_id=run_id,
        limit=limit,
    )
    return {
        "run": normalized_run,
        "identity": _identity_for_thread(thread_id, run.get("user_id"), channel_entries),
        "messages": messages,
    }


@router.get("/monitoring/runs", response_model=RunMonitoringResponse)
@require_admin
async def summarize_runs(request: Request) -> RunMonitoringResponse:
    return RunMonitoringResponse(items=await _platform_repo(request).summarize_runs_by_agent())


@router.get("/monitoring/tools", response_model=ToolMonitoringResponse)
@require_admin
async def summarize_tools(request: Request, failure_limit: int = Query(default=20, ge=1, le=100)) -> ToolMonitoringResponse:
    repo = _platform_repo(request)
    return ToolMonitoringResponse(
        items=await repo.summarize_tools_by_agent(),
        recent_failures=await repo.recent_tool_failures(limit=failure_limit),
    )


@router.get("/feedback/summary")
@require_admin
async def feedback_summary(request: Request) -> dict[str, Any]:
    return await get_feedback_repo(request).summarize_for_admin()


@router.get("/feedback/recent", response_model=RecentFeedbackResponse)
@require_admin
async def recent_feedback(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> RecentFeedbackResponse:
    items = await get_feedback_repo(request).recent_for_admin(limit=limit)
    return RecentFeedbackResponse(items=await _with_feedback_user_email(items))


@router.get("/feedback/{feedback_id}/conversation", response_model=FeedbackConversationResponse)
@require_admin
async def feedback_conversation(
    feedback_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
) -> FeedbackConversationResponse:
    feedback = await get_feedback_repo(request).get_for_admin(feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    enriched = await _with_feedback_user_email([feedback])
    messages = await _list_run_messages_for_admin(
        request,
        thread_id=str(feedback["thread_id"]),
        run_id=str(feedback["run_id"]),
        limit=limit,
    )
    if not messages:
        messages = _messages_from_feedback_summary(feedback)
    return FeedbackConversationResponse(feedback=enriched[0], messages=messages)
