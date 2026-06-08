# Agent Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin-only `/admin/monitoring` troubleshooting page that starts from all users' recent conversations, drills into conversation runs, shows a Beijing-time run action timeline, and supports importing one run timeline JSON for offline inspection.

**Architecture:** Extend the existing platform admin backend instead of creating a second admin service. Keep durable query logic in `PlatformRepository`, request composition and identity normalization in `platform_admin.py`, and frontend data access in `frontend/src/core/platform`. The UI is a read-only three-column troubleshooting surface with a client-only imported timeline mode.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, existing `RunEventStore`, `ChannelStore`, Next.js App Router, React Query, Vitest, pytest.

---

## File Structure

- Modify `backend/packages/harness/deerflow/persistence/platform/sql.py`
  - Add run conversation queries, run lookup, run list by thread, and tool audit lookup by run.
- Modify `backend/app/gateway/routers/platform_admin.py`
  - Add response models, channel identity helpers, Beijing-time formatting, recent conversation endpoint, conversation detail endpoint, run timeline endpoint, and run messages endpoint.
- Modify `backend/tests/test_platform_persistence.py`
  - Add repository tests for recent conversations and run tool audit lookup.
- Modify `backend/tests/test_platform_admin_api.py`
  - Add route tests for admin access, IM raw identity, timeline merge, Beijing time, and non-admin rejection.
- Modify `backend/packages/harness/deerflow/runtime/journal.py`
  - Emit `tool.start` and `tool.error` trace events while preserving existing `llm.tool.result` behavior.
- Modify `backend/tests/test_run_journal.py`
  - Replace the no-event tool error expectation with event assertions and add a tool start assertion.
- Modify `frontend/src/core/platform/types.ts`
  - Add monitoring conversation, run, timeline, and imported timeline types.
- Modify `frontend/src/core/platform/api.ts`
  - Add typed functions for recent conversations, conversation detail, run timeline, and run messages.
- Modify `frontend/src/core/platform/hooks.ts`
  - Add React Query hooks for recent conversations, conversation detail, and run timeline.
- Create `frontend/src/core/platform/monitoring-import.ts`
  - Parse and validate one imported run timeline JSON.
- Modify `frontend/src/core/platform/index.ts`
  - Export monitoring import helpers.
- Modify `frontend/tests/unit/core/platform/api.test.ts`
  - Add API URL and response-shape tests.
- Create `frontend/tests/unit/core/platform/monitoring-import.test.ts`
  - Add imported JSON parser tests.
- Create `frontend/src/app/admin/monitoring/page.tsx`
  - Add independent admin route with server-side role guard.
- Create `frontend/src/components/platform-admin/monitoring/agent-monitoring-page.tsx`
  - Compose the page state and layout.
- Create `frontend/src/components/platform-admin/monitoring/conversation-list.tsx`
  - Render recent conversations with source, raw identity, status, agent, run, and Beijing update time.
- Create `frontend/src/components/platform-admin/monitoring/conversation-detail.tsx`
  - Render selected conversation metadata, message preview, and run list.
- Create `frontend/src/components/platform-admin/monitoring/run-timeline.tsx`
  - Render chronological actions with status, tool, latency, and Beijing time.
- Create `frontend/src/components/platform-admin/monitoring/event-inspector.tsx`
  - Render event content and metadata JSON with shallow sensitive-key masking.
- Create `frontend/src/components/platform-admin/monitoring/import-run-dialog.tsx`
  - Upload or paste one run timeline JSON and hand parsed data to the page.
- Create `frontend/src/components/platform-admin/monitoring/format.ts`
  - Add small UI formatting helpers for identity, status, duration, JSON, and short ids.
- Create `frontend/tests/unit/app/admin-monitoring-page.test.ts`
  - Add route guard tests for `/admin/monitoring`.

## Data Contracts

Backend responses use snake_case. Frontend types keep snake_case to match existing `core/platform` conventions.

```ts
export type MonitoringIdentityType = "web" | "channel" | "unknown";

export interface MonitoringIdentity {
  identity_type: MonitoringIdentityType;
  identity_source: string;
  identity_display: string;
  raw_identity: Record<string, string | null>;
}

export interface MonitoringConversationItem {
  identity: MonitoringIdentity;
  thread_id: string;
  latest_run_id: string | null;
  agent_name: string | null;
  last_message: string | null;
  status: string | null;
  error_summary: string | null;
  updated_at: string | null;
  updated_at_bj: string | null;
}

export interface MonitoringRunItem {
  run_id: string;
  thread_id: string;
  agent_name: string | null;
  status: string;
  model_name: string | null;
  message_count: number;
  first_human_message: string | null;
  last_ai_message: string | null;
  total_tokens: number;
  llm_call_count: number;
  error: string | null;
  created_at: string | null;
  created_at_bj: string | null;
  updated_at: string | null;
  updated_at_bj: string | null;
}

export interface MonitoringTimelineEvent {
  seq: number;
  occurred_at: string | null;
  occurred_at_bj: string | null;
  kind: string;
  title: string;
  status: string | null;
  duration_ms: number | null;
  source: "run_event" | "tool_audit";
  tool_name?: string | null;
  mcp_server_name?: string | null;
  content: unknown;
  metadata: Record<string, unknown>;
}
```

## Task 1: Backend Repository Queries

**Files:**
- Modify: `backend/packages/harness/deerflow/persistence/platform/sql.py`
- Modify: `backend/tests/test_platform_persistence.py`

- [ ] **Step 1: Write failing repository tests**

Append these tests to `backend/tests/test_platform_persistence.py`.

```python
@pytest.mark.anyio
async def test_monitoring_recent_conversations_returns_latest_run_per_thread(tmp_path):
    from datetime import UTC, datetime

    from deerflow.persistence.platform.sql import PlatformRepository
    from deerflow.persistence.run.model import RunRow

    engine, sf = await _session_factory(tmp_path)
    try:
        async with sf() as session:
            session.add_all(
                [
                    RunRow(
                        run_id="run-old",
                        thread_id="thread-1",
                        assistant_id="hr-boss-agent",
                        user_id="user-1",
                        status="success",
                        first_human_message="old question",
                        last_ai_message="old answer",
                        message_count=2,
                        total_tokens=10,
                        llm_call_count=1,
                        created_at=datetime(2026, 6, 8, 1, 0, tzinfo=UTC),
                        updated_at=datetime(2026, 6, 8, 1, 1, tzinfo=UTC),
                    ),
                    RunRow(
                        run_id="run-new",
                        thread_id="thread-1",
                        assistant_id="hr-boss-agent",
                        user_id="user-1",
                        status="error",
                        first_human_message="latest question",
                        last_ai_message=None,
                        error="backend unavailable",
                        message_count=1,
                        total_tokens=20,
                        llm_call_count=2,
                        created_at=datetime(2026, 6, 8, 2, 0, tzinfo=UTC),
                        updated_at=datetime(2026, 6, 8, 2, 3, tzinfo=UTC),
                    ),
                    RunRow(
                        run_id="run-2",
                        thread_id="thread-2",
                        assistant_id="finance-agent",
                        user_id="user-2",
                        status="success",
                        first_human_message="finance question",
                        message_count=1,
                        created_at=datetime(2026, 6, 8, 3, 0, tzinfo=UTC),
                        updated_at=datetime(2026, 6, 8, 3, 1, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

        repo = PlatformRepository(sf)
        page = await repo.list_recent_monitoring_conversations(limit=50, offset=0)

        assert page["total"] == 2
        assert [item["thread_id"] for item in page["items"]] == ["thread-2", "thread-1"]
        assert page["items"][1]["latest_run_id"] == "run-new"
        assert page["items"][1]["last_message"] == "latest question"
        assert page["items"][1]["error_summary"] == "backend unavailable"
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_monitoring_run_detail_and_tool_audit_lookup(tmp_path):
    from datetime import UTC, datetime

    from deerflow.persistence.platform.sql import PlatformRepository
    from deerflow.persistence.run.model import RunRow

    engine, sf = await _session_factory(tmp_path)
    try:
        async with sf() as session:
            session.add(
                RunRow(
                    run_id="run-1",
                    thread_id="thread-1",
                    assistant_id="hr-boss-agent",
                    user_id="user-1",
                    status="running",
                    first_human_message="How many people?",
                    message_count=1,
                    created_at=datetime(2026, 6, 8, 5, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 6, 8, 5, 1, tzinfo=UTC),
                )
            )
            await session.commit()

        repo = PlatformRepository(sf)
        await repo.write_tool_audit(
            run_id="run-1",
            thread_id="thread-1",
            user_id="user-1",
            agent_name="hr-boss-agent",
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="error",
            latency_ms=842,
            error="timeout",
            metadata={"argument_keys": ["question"]},
        )

        run = await repo.get_run_for_admin("run-1")
        runs = await repo.list_runs_for_thread("thread-1")
        audits = await repo.list_tool_audits_for_run("run-1")

        assert run is not None
        assert run["run_id"] == "run-1"
        assert runs[0]["run_id"] == "run-1"
        assert audits[0]["tool_name"] == "text2cypher_answer_question"
        assert audits[0]["metadata_json"] == {"argument_keys": ["question"]}
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run repository tests and confirm failure**

Run:

```bash
cd backend
uv run pytest tests/test_platform_persistence.py -q
```

Expected: fails with `AttributeError: 'PlatformRepository' object has no attribute 'list_recent_monitoring_conversations'`.

- [ ] **Step 3: Implement repository methods**

In `backend/packages/harness/deerflow/persistence/platform/sql.py`, update imports and add these methods inside `PlatformRepository`.

```python
from sqlalchemy import delete, desc, func, or_, select

    def _run_row_to_monitoring_dict(self, row: RunRow) -> dict[str, Any]:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        agent_name = metadata.get("agent_name") or row.assistant_id
        return {
            "run_id": row.run_id,
            "thread_id": row.thread_id,
            "user_id": row.user_id,
            "agent_name": str(agent_name) if agent_name is not None else None,
            "status": row.status,
            "model_name": row.model_name,
            "message_count": row.message_count,
            "first_human_message": row.first_human_message,
            "last_ai_message": row.last_ai_message,
            "total_tokens": row.total_tokens,
            "llm_call_count": row.llm_call_count,
            "error": row.error,
            "metadata_json": metadata,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    async def list_recent_monitoring_conversations(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        source_thread_ids: list[str] | None = None,
        agent_name: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(RunRow)
        count_stmt = select(func.count(func.distinct(RunRow.thread_id)))

        filters = []
        if source_thread_ids is not None:
            if not source_thread_ids:
                return {"items": [], "total": 0, "limit": limit, "offset": offset}
            filters.append(RunRow.thread_id.in_(source_thread_ids))
        if agent_name:
            filters.append(RunRow.assistant_id == agent_name)
        if status:
            filters.append(RunRow.status == status)
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    RunRow.run_id.ilike(like),
                    RunRow.thread_id.ilike(like),
                    RunRow.user_id.ilike(like),
                    RunRow.first_human_message.ilike(like),
                    RunRow.last_ai_message.ilike(like),
                    RunRow.error.ilike(like),
                )
            )

        for condition in filters:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(desc(RunRow.updated_at), desc(RunRow.created_at)).limit(max(limit * 4, limit)).offset(offset)

        async with self._sf() as session:
            rows = list((await session.execute(stmt)).scalars())
            total = int((await session.execute(count_stmt)).scalar_one())

        latest_by_thread: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.thread_id in latest_by_thread:
                continue
            latest_by_thread[row.thread_id] = self._run_row_to_monitoring_dict(row)
            if len(latest_by_thread) >= limit:
                break

        items = []
        for row in latest_by_thread.values():
            items.append(
                {
                    "thread_id": row["thread_id"],
                    "latest_run_id": row["run_id"],
                    "user_id": row["user_id"],
                    "agent_name": row["agent_name"],
                    "last_message": row["first_human_message"] or row["last_ai_message"],
                    "status": row["status"],
                    "error_summary": row["error"],
                    "updated_at": row["updated_at"],
                    "latest_run": row,
                }
            )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_run_for_admin(self, run_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = (await session.execute(select(RunRow).where(RunRow.run_id == run_id))).scalar_one_or_none()
        return self._run_row_to_monitoring_dict(row) if row is not None else None

    async def list_runs_for_thread(self, thread_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        stmt = select(RunRow).where(RunRow.thread_id == thread_id).order_by(desc(RunRow.created_at), desc(RunRow.updated_at)).limit(limit)
        async with self._sf() as session:
            rows = list((await session.execute(stmt)).scalars())
        return [self._run_row_to_monitoring_dict(row) for row in rows]

    async def list_tool_audits_for_run(self, run_id: str) -> list[dict[str, Any]]:
        stmt = select(ToolAuditLogRow).where(ToolAuditLogRow.run_id == run_id).order_by(ToolAuditLogRow.created_at.asc(), ToolAuditLogRow.id.asc())
        async with self._sf() as session:
            rows = list((await session.execute(stmt)).scalars())
        return [self._row_to_dict(row) for row in rows]
```

- [ ] **Step 4: Run repository tests and confirm pass**

Run:

```bash
cd backend
uv run pytest tests/test_platform_persistence.py -q
```

Expected: all tests in `test_platform_persistence.py` pass.

- [ ] **Step 5: Commit repository work**

Run:

```bash
git add backend/packages/harness/deerflow/persistence/platform/sql.py backend/tests/test_platform_persistence.py
git commit -m "新增监控查询"
```

## Task 2: Backend Admin Monitoring API

**Files:**
- Modify: `backend/app/gateway/routers/platform_admin.py`
- Modify: `backend/tests/test_platform_admin_api.py`

- [ ] **Step 1: Add route tests**

Append route tests to `backend/tests/test_platform_admin_api.py`. Reuse `make_authed_test_app`, `_user`, and `FakeRunEventStore`. Extend the fake repo with the monitoring methods below.

```python
class FakeMonitoringRepo(FakePlatformRepo):
    async def list_recent_monitoring_conversations(self, **kwargs):
        return {
            "items": [
                {
                    "thread_id": "thread-im",
                    "latest_run_id": "run-im",
                    "user_id": "internal",
                    "agent_name": "hr-boss-agent",
                    "last_message": "研发部门有多少人？",
                    "status": "error",
                    "error_summary": "backend unavailable",
                    "updated_at": "2026-06-08T05:39:22+00:00",
                }
            ],
            "total": 1,
            "limit": kwargs.get("limit", 50),
            "offset": kwargs.get("offset", 0),
        }

    async def list_runs_for_thread(self, thread_id: str, *, limit: int = 100):
        return [
            {
                "run_id": "run-im",
                "thread_id": thread_id,
                "agent_name": "hr-boss-agent",
                "status": "error",
                "model_name": "qwen3.5-plus",
                "message_count": 2,
                "first_human_message": "研发部门有多少人？",
                "last_ai_message": None,
                "total_tokens": 100,
                "llm_call_count": 1,
                "error": "backend unavailable",
                "metadata_json": {},
                "created_at": "2026-06-08T05:39:20+00:00",
                "updated_at": "2026-06-08T05:39:22+00:00",
            }
        ]

    async def get_run_for_admin(self, run_id: str):
        if run_id != "run-im":
            return None
        return (await self.list_runs_for_thread("thread-im"))[0]

    async def list_tool_audits_for_run(self, run_id: str):
        return [
            {
                "id": 1,
                "run_id": run_id,
                "thread_id": "thread-im",
                "user_id": "internal",
                "agent_name": "hr-boss-agent",
                "tool_name": "text2cypher_answer_question",
                "mcp_server_name": "text2cypher",
                "status": "error",
                "latency_ms": 842,
                "error": "timeout",
                "metadata_json": {"argument_keys": ["question"]},
                "created_at": "2026-06-08T05:39:24+00:00",
            }
        ]


class FakeChannelStore:
    def list_entries(self, channel_name=None):
        return [
            {
                "channel_name": "feishu",
                "chat_id": "oc_xxx",
                "topic_id": "msg_xxx",
                "thread_id": "thread-im",
                "user_id": "ou_xxx",
                "created_at": 1780897160.0,
                "updated_at": 1780897162.0,
            }
        ]


class FakeTimelineRunEventStore(FakeRunEventStore):
    async def list_events(self, thread_id, run_id, *, event_types=None, limit=500, user_id=None):
        self.calls.append({"method": "list_events", "thread_id": thread_id, "run_id": run_id, "user_id": user_id})
        return [
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "event_type": "run.start",
                "category": "trace",
                "content": {"chain": "graph"},
                "metadata": {"caller": "lead_agent"},
                "seq": 1,
                "created_at": "2026-06-08T05:39:20+00:00",
            }
        ]
```

Add these assertions.

```python
def test_admin_monitoring_recent_conversations_includes_im_raw_identity(monkeypatch):
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakeMonitoringRepo()
    app.state.channel_store = FakeChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/conversations/recent")

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 50
    assert data["items"][0]["identity"]["identity_type"] == "channel"
    assert data["items"][0]["identity"]["identity_source"] == "feishu"
    assert data["items"][0]["identity"]["raw_identity"] == {
        "channel_user_id": "ou_xxx",
        "chat_id": "oc_xxx",
        "topic_id": "msg_xxx",
    }
    assert data["items"][0]["updated_at_bj"] == "2026-06-08 13:39:22"


def test_admin_monitoring_run_timeline_merges_events_and_tool_audit(monkeypatch):
    from app.gateway.routers import platform_admin

    event_store = FakeTimelineRunEventStore()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakeMonitoringRepo()
    app.state.channel_store = FakeChannelStore()
    app.state.run_event_store = event_store
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/runs/run-im/timeline")

    assert response.status_code == 200
    data = response.json()
    assert data["identity"]["raw_identity"]["channel_user_id"] == "ou_xxx"
    assert [event["kind"] for event in data["events"]] == ["run.start", "tool.error"]
    assert data["events"][1]["tool_name"] == "text2cypher_answer_question"
    assert data["events"][1]["occurred_at_bj"] == "2026-06-08 13:39:24"
    assert event_store.calls[-1]["user_id"] is None


def test_admin_monitoring_rejects_normal_user():
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.state.platform_repo = FakeMonitoringRepo()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/conversations/recent")

    assert response.status_code == 403
```

- [ ] **Step 2: Run route tests and confirm failure**

Run:

```bash
cd backend
uv run pytest tests/test_platform_admin_api.py -q
```

Expected: fails with `404 Not Found` for `/monitoring/conversations/recent`.

- [ ] **Step 3: Implement models and helpers**

In `backend/app/gateway/routers/platform_admin.py`, add these helpers near `_messages_from_feedback_summary`.

```python
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BJ_TZ = ZoneInfo("Asia/Shanghai")


def _iso_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.isoformat()
    return str(value)


def _bj_text(value: Any) -> str | None:
    iso = _iso_text(value)
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _channel_store(request: Request):
    store = getattr(request.app.state, "channel_store", None)
    if store is not None:
        return store
    try:
        from app.channels.service import get_channel_service

        service = get_channel_service()
        return getattr(service, "store", None) if service is not None else None
    except Exception:
        return None


def _channel_entries_by_thread(request: Request) -> dict[str, dict[str, Any]]:
    store = _channel_store(request)
    if store is None:
        return {}
    return {str(item["thread_id"]): item for item in store.list_entries()}


def _identity_for_thread(thread_id: str, user_id: str | None, channel_entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry = channel_entries.get(thread_id)
    if entry is not None:
        raw_identity = {
            "channel_user_id": entry.get("user_id"),
            "chat_id": entry.get("chat_id"),
            "topic_id": entry.get("topic_id"),
        }
        channel_name = str(entry.get("channel_name") or "channel")
        display = raw_identity["channel_user_id"] or raw_identity["chat_id"] or thread_id
        return {
            "identity_type": "channel",
            "identity_source": channel_name,
            "identity_display": f"{channel_name}: {display}",
            "raw_identity": raw_identity,
        }
    if user_id:
        return {
            "identity_type": "web",
            "identity_source": "web",
            "identity_display": str(user_id),
            "raw_identity": {"user_id": str(user_id)},
        }
    return {"identity_type": "unknown", "identity_source": "unknown", "identity_display": thread_id, "raw_identity": {}}
```

Add response models.

```python
class MonitoringIdentityResponse(BaseModel):
    identity_type: str
    identity_source: str
    identity_display: str
    raw_identity: dict[str, Any] = Field(default_factory=dict)


class MonitoringConversationItemResponse(BaseModel):
    identity: MonitoringIdentityResponse
    thread_id: str
    latest_run_id: str | None = None
    agent_name: str | None = None
    last_message: str | None = None
    status: str | None = None
    error_summary: str | None = None
    updated_at: str | None = None
    updated_at_bj: str | None = None


class MonitoringConversationsResponse(BaseModel):
    items: list[MonitoringConversationItemResponse]
    total: int
    limit: int
    offset: int


class MonitoringConversationResponse(BaseModel):
    identity: MonitoringIdentityResponse
    thread_id: str
    runs: list[dict[str, Any]]
    message_preview: list[dict[str, Any]] = Field(default_factory=list)


class MonitoringTimelineResponse(BaseModel):
    run: dict[str, Any]
    identity: MonitoringIdentityResponse
    events: list[dict[str, Any]]
```

- [ ] **Step 4: Implement endpoints**

Add endpoints below the existing `/monitoring/tools` endpoint.

```python
@router.get("/monitoring/conversations/recent", response_model=MonitoringConversationsResponse)
@require_admin
async def recent_monitoring_conversations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    source: str | None = None,
    agent_name: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> MonitoringConversationsResponse:
    channel_entries = _channel_entries_by_thread(request)
    source_thread_ids = None
    if source and source != "web":
        source_thread_ids = [tid for tid, entry in channel_entries.items() if entry.get("channel_name") == source]
    page = await _platform_repo(request).list_recent_monitoring_conversations(
        limit=limit,
        offset=offset,
        source_thread_ids=source_thread_ids,
        agent_name=agent_name,
        status=status,
        q=q,
    )
    items = []
    for item in page["items"]:
        identity = _identity_for_thread(str(item["thread_id"]), item.get("user_id"), channel_entries)
        items.append(
            MonitoringConversationItemResponse(
                identity=identity,
                thread_id=str(item["thread_id"]),
                latest_run_id=item.get("latest_run_id"),
                agent_name=item.get("agent_name"),
                last_message=item.get("last_message"),
                status=item.get("status"),
                error_summary=item.get("error_summary"),
                updated_at=_iso_text(item.get("updated_at")),
                updated_at_bj=_bj_text(item.get("updated_at")),
            )
        )
    return MonitoringConversationsResponse(items=items, total=page["total"], limit=page["limit"], offset=page["offset"])


@router.get("/monitoring/conversations/{thread_id}", response_model=MonitoringConversationResponse)
@require_admin
async def monitoring_conversation(thread_id: str, request: Request, limit: int = Query(default=100, ge=1, le=200)) -> MonitoringConversationResponse:
    runs = await _platform_repo(request).list_runs_for_thread(thread_id, limit=limit)
    if not runs:
        raise HTTPException(status_code=404, detail="Conversation not found")
    channel_entries = _channel_entries_by_thread(request)
    identity = _identity_for_thread(thread_id, runs[0].get("user_id"), channel_entries)
    for run in runs:
        run["created_at"] = _iso_text(run.get("created_at"))
        run["created_at_bj"] = _bj_text(run.get("created_at"))
        run["updated_at"] = _iso_text(run.get("updated_at"))
        run["updated_at_bj"] = _bj_text(run.get("updated_at"))
    message_preview = []
    latest = runs[0]
    try:
        message_preview = await _list_run_messages_for_admin(request, thread_id=thread_id, run_id=str(latest["run_id"]), limit=20)
    except HTTPException:
        message_preview = []
    return MonitoringConversationResponse(identity=identity, thread_id=thread_id, runs=runs, message_preview=message_preview)


@router.get("/monitoring/runs/{run_id}/timeline", response_model=MonitoringTimelineResponse)
@require_admin
async def monitoring_run_timeline(run_id: str, request: Request, limit: int = Query(default=500, ge=1, le=2000)) -> MonitoringTimelineResponse:
    repo = _platform_repo(request)
    run = await repo.get_run_for_admin(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    thread_id = str(run["thread_id"])
    event_store = get_run_event_store(request)
    kwargs: dict[str, Any] = {"limit": limit}
    if "user_id" in signature(event_store.list_events).parameters:
        kwargs["user_id"] = None
    run_events = await event_store.list_events(thread_id, run_id, **kwargs)
    tool_audits = await repo.list_tool_audits_for_run(run_id)
    events = _merge_timeline_events(run_events, tool_audits)
    identity = _identity_for_thread(thread_id, run.get("user_id"), _channel_entries_by_thread(request))
    run["created_at"] = _iso_text(run.get("created_at"))
    run["created_at_bj"] = _bj_text(run.get("created_at"))
    run["updated_at"] = _iso_text(run.get("updated_at"))
    run["updated_at_bj"] = _bj_text(run.get("updated_at"))
    return MonitoringTimelineResponse(run=run, identity=identity, events=events)


@router.get("/monitoring/runs/{run_id}/messages")
@require_admin
async def monitoring_run_messages(run_id: str, request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    run = await _platform_repo(request).get_run_for_admin(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    messages = await _list_run_messages_for_admin(request, thread_id=str(run["thread_id"]), run_id=run_id, limit=limit)
    return {"items": messages, "limit": limit}
```

Add `_merge_timeline_events` above the endpoints.

```python
def _timeline_title(kind: str, content: Any, metadata: dict[str, Any]) -> str:
    if kind.startswith("tool."):
        return str(metadata.get("tool_name") or metadata.get("name") or kind)
    return kind


def _merge_timeline_events(run_events: list[dict[str, Any]], tool_audits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in run_events:
        kind = str(item.get("event_type") or "event")
        created_at = item.get("created_at")
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        events.append(
            {
                "seq": int(item.get("seq") or 0),
                "occurred_at": _iso_text(created_at),
                "occurred_at_bj": _bj_text(created_at),
                "kind": kind,
                "title": _timeline_title(kind, item.get("content"), metadata),
                "status": metadata.get("status"),
                "duration_ms": metadata.get("latency_ms"),
                "source": "run_event",
                "content": item.get("content"),
                "metadata": metadata,
            }
        )
    base_seq = max((event["seq"] for event in events), default=0)
    for index, audit in enumerate(tool_audits, start=1):
        metadata = audit.get("metadata_json") if isinstance(audit.get("metadata_json"), dict) else {}
        status = audit.get("status")
        kind = "tool.error" if status == "error" else "tool.end"
        events.append(
            {
                "seq": base_seq + index,
                "occurred_at": _iso_text(audit.get("created_at")),
                "occurred_at_bj": _bj_text(audit.get("created_at")),
                "kind": kind,
                "title": f"{audit.get('tool_name')} {'调用失败' if status == 'error' else '调用完成'}",
                "status": status,
                "duration_ms": audit.get("latency_ms"),
                "source": "tool_audit",
                "tool_name": audit.get("tool_name"),
                "mcp_server_name": audit.get("mcp_server_name"),
                "content": {"error": audit.get("error")},
                "metadata": metadata,
            }
        )
    return sorted(events, key=lambda event: (event.get("occurred_at") or "", event.get("seq") or 0))
```

- [ ] **Step 5: Run route tests and confirm pass**

Run:

```bash
cd backend
uv run pytest tests/test_platform_admin_api.py -q
```

Expected: all tests in `test_platform_admin_api.py` pass.

- [ ] **Step 6: Commit API work**

Run:

```bash
git add backend/app/gateway/routers/platform_admin.py backend/tests/test_platform_admin_api.py
git commit -m "新增监控接口"
```

## Task 3: Frontend Types, API, Hooks, and Import Parser

**Files:**
- Modify: `frontend/src/core/platform/types.ts`
- Modify: `frontend/src/core/platform/api.ts`
- Modify: `frontend/src/core/platform/hooks.ts`
- Modify: `frontend/src/core/platform/index.ts`
- Create: `frontend/src/core/platform/monitoring-import.ts`
- Modify: `frontend/tests/unit/core/platform/api.test.ts`
- Create: `frontend/tests/unit/core/platform/monitoring-import.test.ts`

- [ ] **Step 1: Add failing frontend API tests**

Append to `frontend/tests/unit/core/platform/api.test.ts`.

```ts
test("fetchRecentMonitoringConversations requests the default recent conversation page", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [
        {
          identity: {
            identity_type: "channel",
            identity_source: "feishu",
            identity_display: "feishu: ou_xxx",
            raw_identity: { channel_user_id: "ou_xxx", chat_id: "oc_xxx" },
          },
          thread_id: "thread-im",
          latest_run_id: "run-im",
          agent_name: "hr-boss-agent",
          last_message: "研发部门有多少人？",
          status: "error",
          error_summary: "backend unavailable",
          updated_at: "2026-06-08T05:39:22+00:00",
          updated_at_bj: "2026-06-08 13:39:22",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    }),
  });

  const { fetchRecentMonitoringConversations } = await import("@/core/platform/api");

  await expect(fetchRecentMonitoringConversations()).resolves.toMatchObject({
    limit: 50,
    items: [{ thread_id: "thread-im", identity: { identity_source: "feishu" } }],
  });
  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/admin/monitoring/conversations/recent?limit=50&offset=0"),
  );
});


test("fetchMonitoringRunTimeline requests one run timeline", async () => {
  fetchWithAuth.mockResolvedValue({
    ok: true,
    json: async () => ({
      run: { run_id: "run-im", thread_id: "thread-im", status: "error" },
      identity: {
        identity_type: "channel",
        identity_source: "feishu",
        identity_display: "feishu: ou_xxx",
        raw_identity: { channel_user_id: "ou_xxx" },
      },
      events: [
        {
          seq: 1,
          occurred_at: "2026-06-08T05:39:24+00:00",
          occurred_at_bj: "2026-06-08 13:39:24",
          kind: "tool.error",
          title: "text2cypher_answer_question 调用失败",
          status: "error",
          duration_ms: 842,
          source: "tool_audit",
          tool_name: "text2cypher_answer_question",
          mcp_server_name: "text2cypher",
          content: { error: "timeout" },
          metadata: {},
        },
      ],
    }),
  });

  const { fetchMonitoringRunTimeline } = await import("@/core/platform/api");

  await expect(fetchMonitoringRunTimeline("run-im")).resolves.toMatchObject({
    run: { run_id: "run-im" },
    events: [{ kind: "tool.error" }],
  });
  expect(fetchWithAuth).toHaveBeenCalledWith(
    expect.stringContaining("/api/platform/admin/monitoring/runs/run-im/timeline"),
  );
});
```

Create `frontend/tests/unit/core/platform/monitoring-import.test.ts`.

```ts
import { expect, test } from "vitest";

import { parseImportedRunTimeline } from "@/core/platform/monitoring-import";

test("parseImportedRunTimeline accepts one valid timeline JSON string", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({
      run: { run_id: "run-1", thread_id: "thread-1", status: "success" },
      events: [{ seq: 1, kind: "run.start", source: "run_event", metadata: {} }],
    }),
  );

  expect(parsed.ok).toBe(true);
  if (parsed.ok) {
    expect(parsed.data.run.run_id).toBe("run-1");
    expect(parsed.data.identity.identity_source).toBe("imported");
  }
});

test("parseImportedRunTimeline rejects missing events", () => {
  const parsed = parseImportedRunTimeline(
    JSON.stringify({ run: { run_id: "run-1", thread_id: "thread-1" } }),
  );

  expect(parsed.ok).toBe(false);
  if (!parsed.ok) {
    expect(parsed.error).toContain("events");
  }
});
```

- [ ] **Step 2: Run frontend unit tests and confirm failure**

Run:

```bash
cd frontend
pnpm test -- tests/unit/core/platform/api.test.ts tests/unit/core/platform/monitoring-import.test.ts
```

Expected: import failure for `monitoring-import` and missing API exports.

- [ ] **Step 3: Add frontend types**

Append the data contract interfaces from this plan to `frontend/src/core/platform/types.ts`. Also add:

```ts
export interface MonitoringConversationsPage {
  items: MonitoringConversationItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface MonitoringConversationDetail {
  identity: MonitoringIdentity;
  thread_id: string;
  runs: MonitoringRunItem[];
  message_preview: FeedbackConversationMessage[];
}

export interface MonitoringRunTimeline {
  run: Partial<MonitoringRunItem> & { run_id: string; thread_id: string };
  identity: MonitoringIdentity;
  events: MonitoringTimelineEvent[];
}
```

- [ ] **Step 4: Add frontend API functions**

In `frontend/src/core/platform/api.ts`, import the new types and add:

```ts
export async function fetchRecentMonitoringConversations({
  limit = 50,
  offset = 0,
  source,
  agent_name,
  status,
  q,
}: {
  limit?: number;
  offset?: number;
  source?: string;
  agent_name?: string;
  status?: string;
  q?: string;
} = {}): Promise<MonitoringConversationsPage> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (source) params.set("source", source);
  if (agent_name) params.set("agent_name", agent_name);
  if (status) params.set("status", status);
  if (q) params.set("q", q);
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/conversations/recent?${params.toString()}`,
  );
  return readJsonOrThrow<MonitoringConversationsPage>(
    res,
    `Failed to load monitoring conversations: ${res.statusText}`,
  );
}

export async function fetchMonitoringConversation(
  threadId: string,
): Promise<MonitoringConversationDetail> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/conversations/${encodeURIComponent(threadId)}`,
  );
  return readJsonOrThrow<MonitoringConversationDetail>(
    res,
    `Failed to load monitoring conversation: ${res.statusText}`,
  );
}

export async function fetchMonitoringRunTimeline(
  runId: string,
): Promise<MonitoringRunTimeline> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/platform/admin/monitoring/runs/${encodeURIComponent(runId)}/timeline`,
  );
  return readJsonOrThrow<MonitoringRunTimeline>(
    res,
    `Failed to load run timeline: ${res.statusText}`,
  );
}
```

- [ ] **Step 5: Add hooks**

In `frontend/src/core/platform/hooks.ts`, import the three functions and add:

```ts
export function useMonitoringConversations(filters: {
  limit?: number;
  offset?: number;
  source?: string;
  agent_name?: string;
  status?: string;
  q?: string;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "monitoring", "conversations", filters],
    queryFn: () => fetchRecentMonitoringConversations(filters),
  });
  return { page: data ?? { items: [], total: 0, limit: filters.limit ?? 50, offset: filters.offset ?? 0 }, isLoading, error };
}

export function useMonitoringConversation(threadId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "monitoring", "conversation", threadId],
    queryFn: () => fetchMonitoringConversation(threadId!),
    enabled: Boolean(threadId),
  });
  return { conversation: data ?? null, isLoading, error };
}

export function useMonitoringRunTimeline(runId: string | null) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["platform", "admin", "monitoring", "run", runId, "timeline"],
    queryFn: () => fetchMonitoringRunTimeline(runId!),
    enabled: Boolean(runId),
  });
  return { timeline: data ?? null, isLoading, error };
}
```

- [ ] **Step 6: Add import parser**

Create `frontend/src/core/platform/monitoring-import.ts`.

```ts
import type { MonitoringIdentity, MonitoringRunTimeline } from "./types";

type ParseResult =
  | { ok: true; data: MonitoringRunTimeline }
  | { ok: false; error: string };

const importedIdentity: MonitoringIdentity = {
  identity_type: "unknown",
  identity_source: "imported",
  identity_display: "unknown/imported",
  raw_identity: {},
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseImportedRunTimeline(input: string): ParseResult {
  let value: unknown;
  try {
    value = JSON.parse(input);
  } catch {
    return { ok: false, error: "JSON 格式无效" };
  }

  if (!isRecord(value)) return { ok: false, error: "根节点必须是对象" };
  if (!isRecord(value.run)) return { ok: false, error: "缺少 run 对象" };
  if (typeof value.run.run_id !== "string" || !value.run.run_id) return { ok: false, error: "缺少 run.run_id" };
  if (typeof value.run.thread_id !== "string" || !value.run.thread_id) return { ok: false, error: "缺少 run.thread_id" };
  if (!Array.isArray(value.events)) return { ok: false, error: "缺少 events 数组" };

  const identity = isRecord(value.identity)
    ? (value.identity as unknown as MonitoringIdentity)
    : importedIdentity;

  return {
    ok: true,
    data: {
      run: value.run as MonitoringRunTimeline["run"],
      identity,
      events: value.events as MonitoringRunTimeline["events"],
    },
  };
}
```

Export it from `frontend/src/core/platform/index.ts`.

```ts
export * from "./monitoring-import";
```

- [ ] **Step 7: Run frontend unit tests and confirm pass**

Run:

```bash
cd frontend
pnpm test -- tests/unit/core/platform/api.test.ts tests/unit/core/platform/monitoring-import.test.ts
```

Expected: selected frontend unit tests pass.

- [ ] **Step 8: Commit frontend data layer**

Run:

```bash
git add frontend/src/core/platform frontend/tests/unit/core/platform
git commit -m "新增监控前端API"
```

## Task 4: Frontend Route and Three-Column Monitoring UI

**Files:**
- Create: `frontend/src/app/admin/monitoring/page.tsx`
- Create: `frontend/src/components/platform-admin/monitoring/agent-monitoring-page.tsx`
- Create: `frontend/src/components/platform-admin/monitoring/conversation-list.tsx`
- Create: `frontend/src/components/platform-admin/monitoring/conversation-detail.tsx`
- Create: `frontend/src/components/platform-admin/monitoring/run-timeline.tsx`
- Create: `frontend/src/components/platform-admin/monitoring/event-inspector.tsx`
- Create: `frontend/src/components/platform-admin/monitoring/import-run-dialog.tsx`
- Create: `frontend/src/components/platform-admin/monitoring/format.ts`
- Create: `frontend/tests/unit/app/admin-monitoring-page.test.ts`

- [ ] **Step 1: Add route guard test**

Create `frontend/tests/unit/app/admin-monitoring-page.test.ts`.

```ts
import { describe, expect, test, vi } from "vitest";

const redirect = vi.fn((path: string) => {
  throw new Error(`NEXT_REDIRECT:${path}`);
});

const getServerSideUser = vi.fn();

vi.mock("next/navigation", () => ({ redirect }));
vi.mock("@/core/auth/server", () => ({ getServerSideUser }));
vi.mock("@/components/platform-admin/monitoring/agent-monitoring-page", () => ({
  AgentMonitoringPage: () => null,
}));

async function loadPage() {
  vi.resetModules();
  redirect.mockClear();
  return await import("@/app/admin/monitoring/page");
}

describe("admin monitoring page route", () => {
  test("redirects normal users away from the standalone admin monitoring page", async () => {
    getServerSideUser.mockResolvedValue({
      tag: "authenticated",
      user: { id: "user-1", email: "user@example.com", system_role: "user", needs_setup: false },
    });
    const { default: AdminMonitoringPage } = await loadPage();

    await expect(Promise.resolve(AdminMonitoringPage())).rejects.toThrow(
      "NEXT_REDIRECT:/workspace/agents",
    );
    expect(redirect).toHaveBeenCalledWith("/workspace/agents");
  });

  test("allows admin users to render standalone admin monitoring page", async () => {
    getServerSideUser.mockResolvedValue({
      tag: "authenticated",
      user: { id: "admin-1", email: "admin@example.com", system_role: "admin", needs_setup: false },
    });
    const { default: AdminMonitoringPage } = await loadPage();

    await expect(Promise.resolve(AdminMonitoringPage())).resolves.toBeTruthy();
    expect(redirect).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run route guard test and confirm failure**

Run:

```bash
cd frontend
pnpm test -- tests/unit/app/admin-monitoring-page.test.ts
```

Expected: import failure for `@/app/admin/monitoring/page`.

- [ ] **Step 3: Create route page**

Create `frontend/src/app/admin/monitoring/page.tsx`.

```tsx
import { redirect } from "next/navigation";

import { AgentMonitoringPage } from "@/components/platform-admin/monitoring/agent-monitoring-page";
import { canAccessPlatformAdmin } from "@/core/auth/roles";
import { getServerSideUser } from "@/core/auth/server";

export default async function AdminMonitoringRoute() {
  const result = await getServerSideUser();
  if (result.tag !== "authenticated" || !canAccessPlatformAdmin(result.user)) {
    redirect("/workspace/agents");
  }

  return <AgentMonitoringPage />;
}
```

- [ ] **Step 4: Create format helpers**

Create `frontend/src/components/platform-admin/monitoring/format.ts`.

```ts
import type { MonitoringIdentity, MonitoringTimelineEvent } from "@/core/platform";

const SENSITIVE_KEYS = ["password", "token", "secret", "api_key", "authorization"];

export function shortId(value: string | null | undefined) {
  if (!value) return "-";
  return value.length <= 12 ? value : `${value.slice(0, 6)}...${value.slice(-4)}`;
}

export function statusVariant(status: string | null | undefined): "default" | "secondary" | "destructive" | "outline" {
  if (status === "error" || status === "timeout") return "destructive";
  if (status === "success") return "default";
  if (status === "running" || status === "pending") return "secondary";
  return "outline";
}

export function identityText(identity: MonitoringIdentity | null | undefined) {
  return identity?.identity_display ?? "unknown/imported";
}

export function durationText(value: number | null | undefined) {
  if (value == null) return "-";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

export function eventTone(event: MonitoringTimelineEvent) {
  if (event.status === "error" || event.kind.endsWith(".error")) return "text-destructive";
  if (event.kind.includes("tool")) return "text-blue-600 dark:text-blue-400";
  return "text-muted-foreground";
}

export function maskSensitiveJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(maskSensitiveJson);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, inner]) => [
      key,
      SENSITIVE_KEYS.some((pattern) => key.toLowerCase().includes(pattern))
        ? "***"
        : maskSensitiveJson(inner),
    ]),
  );
}
```

- [ ] **Step 5: Create imported JSON dialog**

Create `frontend/src/components/platform-admin/monitoring/import-run-dialog.tsx` with a `Dialog`, `Textarea`, and file input. It accepts:

```ts
interface ImportRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: (timeline: MonitoringRunTimeline) => void;
}
```

Core submit logic:

```tsx
const result = parseImportedRunTimeline(jsonText);
if (!result.ok) {
  setError(result.error);
  return;
}
onImported(result.data);
onOpenChange(false);
```

File input logic:

```tsx
const file = event.currentTarget.files?.[0];
if (!file) return;
const text = await file.text();
setJsonText(text);
```

- [ ] **Step 6: Create timeline and inspector components**

`run-timeline.tsx` props:

```ts
interface RunTimelineProps {
  timeline: MonitoringRunTimeline | null;
  selectedSeq: number | null;
  onSelectSeq: (seq: number) => void;
  isLoading: boolean;
  isImported: boolean;
}
```

Render behavior:

```tsx
const events = timeline?.events ?? [];
return (
  <section className="min-h-0 border-l">
    <div className="flex items-center justify-between border-b px-4 py-3">
      <div>
        <h2 className="text-sm font-semibold">Run timeline</h2>
        <p className="text-muted-foreground text-xs">
          {timeline ? shortId(timeline.run.run_id) : "Select a run"}
        </p>
      </div>
      {isImported && <Badge variant="outline">Imported</Badge>}
    </div>
    <div className="min-h-0 overflow-y-auto">
      {isLoading ? (
        <div className="text-muted-foreground p-4 text-sm">Loading...</div>
      ) : events.length === 0 ? (
        <div className="text-muted-foreground p-4 text-sm">No events.</div>
      ) : (
        events.map((event) => (
          <button
            key={`${event.seq}-${event.kind}`}
            className="hover:bg-muted/60 grid w-full grid-cols-[92px_minmax(0,1fr)] gap-3 border-b px-4 py-3 text-left text-sm"
            type="button"
            onClick={() => onSelectSeq(event.seq)}
          >
            <span className="text-muted-foreground font-mono text-xs">{event.occurred_at_bj ?? "-"}</span>
            <span className="min-w-0">
              <span className={eventTone(event)}>{event.kind}</span>
              <span className="mt-1 block truncate">{event.title}</span>
            </span>
          </button>
        ))
      )}
    </div>
  </section>
);
```

`event-inspector.tsx` props:

```ts
interface EventInspectorProps {
  event: MonitoringTimelineEvent | null;
}
```

Render masked JSON:

```tsx
<pre className="bg-muted max-h-[42vh] overflow-auto rounded-md p-3 text-xs">
  {JSON.stringify(maskSensitiveJson(event.metadata), null, 2)}
</pre>
```

- [ ] **Step 7: Create conversation list and detail components**

`conversation-list.tsx` props:

```ts
interface ConversationListProps {
  items: MonitoringConversationItem[];
  selectedThreadId: string | null;
  isLoading: boolean;
  onSelectThread: (threadId: string, latestRunId: string | null) => void;
}
```

Each row must show `identityText(item.identity)`, `thread_id`, `latest_run_id`, `agent_name`, `last_message`, `status`, `updated_at_bj`.

`conversation-detail.tsx` props:

```ts
interface ConversationDetailProps {
  conversation: MonitoringConversationDetail | null;
  selectedRunId: string | null;
  isLoading: boolean;
  onSelectRun: (runId: string) => void;
}
```

Each run row must show `run_id`, `status`, `created_at_bj`, `total_tokens`, `llm_call_count`, and `error`.

- [ ] **Step 8: Create composed page**

Create `frontend/src/components/platform-admin/monitoring/agent-monitoring-page.tsx`.

State shape:

```tsx
const [filters, setFilters] = useState({ limit: 50, offset: 0, q: "", source: "", status: "", agent_name: "" });
const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
const [importDialogOpen, setImportDialogOpen] = useState(false);
const [importedTimeline, setImportedTimeline] = useState<MonitoringRunTimeline | null>(null);
```

Query usage:

```tsx
const conversations = useMonitoringConversations(filters);
const conversation = useMonitoringConversation(importedTimeline ? null : selectedThreadId);
const liveTimeline = useMonitoringRunTimeline(importedTimeline ? null : selectedRunId);
const timeline = importedTimeline ?? liveTimeline.timeline;
const selectedEvent = timeline?.events.find((event) => event.seq === selectedSeq) ?? null;
```

Top actions must include a search input, source/status select controls, refresh button, and import button with lucide icons. Layout:

```tsx
<main className="bg-background flex h-screen min-h-0 flex-col">
  <header className="flex items-center justify-between border-b px-5 py-3">...</header>
  <div className="grid min-h-0 flex-1 grid-cols-[360px_minmax(360px,1fr)_minmax(420px,1.2fr)]">
    <ConversationList ... />
    <ConversationDetail ... />
    <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_minmax(220px,34vh)]">
      <RunTimeline ... />
      <EventInspector event={selectedEvent} />
    </div>
  </div>
  <ImportRunDialog ... />
</main>
```

When `onImported` fires, clear live selection and set selected sequence:

```tsx
setImportedTimeline(timeline);
setSelectedThreadId(null);
setSelectedRunId(timeline.run.run_id);
setSelectedSeq(timeline.events[0]?.seq ?? null);
```

- [ ] **Step 9: Run route guard test and typecheck**

Run:

```bash
cd frontend
pnpm test -- tests/unit/app/admin-monitoring-page.test.ts
pnpm typecheck
```

Expected: selected route test passes and TypeScript reports no errors.

- [ ] **Step 10: Commit UI work**

Run:

```bash
git add frontend/src/app/admin/monitoring frontend/src/components/platform-admin/monitoring frontend/tests/unit/app/admin-monitoring-page.test.ts
git commit -m "新增监控页面"
```

## Task 5: Tool Start and Error Events

**Files:**
- Modify: `backend/packages/harness/deerflow/runtime/journal.py`
- Modify: `backend/tests/test_run_journal.py`

- [ ] **Step 1: Add failing journal tests**

In `backend/tests/test_run_journal.py`, replace `test_on_tool_error_no_crash` and add a tool-start test.

```python
    @pytest.mark.anyio
    async def test_on_tool_start_emits_trace_event(self, journal_setup):
        j, store = journal_setup
        j.on_tool_start(
            {"name": "text2cypher_answer_question"},
            "question=研发部门有多少人？",
            run_id=uuid4(),
            tags=["lead_agent"],
            metadata={"mcp_server_name": "text2cypher"},
        )
        await j.flush()
        events = await store.list_events("t1", "r1")
        tool_events = [e for e in events if e["event_type"] == "tool.start"]
        assert len(tool_events) == 1
        assert tool_events[0]["category"] == "trace"
        assert tool_events[0]["content"]["tool_name"] == "text2cypher_answer_question"
        assert tool_events[0]["metadata"]["caller"] == "lead_agent"

    @pytest.mark.anyio
    async def test_on_tool_error_emits_error_event(self, journal_setup):
        j, store = journal_setup
        j.on_tool_error(TimeoutError("timeout"), run_id=uuid4(), name="web_fetch")
        await j.flush()
        events = await store.list_events("t1", "r1")
        tool_events = [e for e in events if e["event_type"] == "tool.error"]
        assert len(tool_events) == 1
        assert tool_events[0]["category"] == "error"
        assert tool_events[0]["content"] == "timeout"
        assert tool_events[0]["metadata"]["error_type"] == "TimeoutError"
        assert tool_events[0]["metadata"]["tool_name"] == "web_fetch"
```

- [ ] **Step 2: Run journal tests and confirm failure**

Run:

```bash
cd backend
uv run pytest tests/test_run_journal.py -q
```

Expected: the new tool start/error assertions fail.

- [ ] **Step 3: Implement journal events**

In `backend/packages/harness/deerflow/runtime/journal.py`, update `on_tool_start` and `on_tool_error`.

```python
    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, tags=None, metadata=None, inputs=None, **kwargs):
        """Handle tool start event, cache tool call ID for later correlation."""
        tool_call_id = str(run_id)
        tool_name = (serialized or {}).get("name") or kwargs.get("name") or "unknown"
        caller = self._identify_caller(tags)
        logger.debug("Tool start for node %s, tool_call_id=%s, tags=%s", run_id, tool_call_id, tags)
        self._put(
            event_type="tool.start",
            category="trace",
            content={
                "tool_name": tool_name,
                "input": input_str,
                "input_keys": sorted(inputs.keys()) if isinstance(inputs, dict) else [],
            },
            metadata={"caller": caller, "tool_call_id": tool_call_id, **(metadata or {})},
        )

    def on_tool_error(self, error, *, run_id, parent_run_id=None, tags=None, metadata=None, name=None, **kwargs):
        """Handle tool error event without suppressing callback flow."""
        tool_call_id = str(run_id)
        caller = self._identify_caller(tags)
        self._put(
            event_type="tool.error",
            category="error",
            content=str(error),
            metadata={
                "caller": caller,
                "tool_call_id": tool_call_id,
                "tool_name": name or kwargs.get("tool_name") or "unknown",
                "error_type": type(error).__name__,
                **(metadata or {}),
            },
        )
```

Keep the existing `on_tool_end` message behavior unchanged so chat display remains stable.

- [ ] **Step 4: Run journal tests and confirm pass**

Run:

```bash
cd backend
uv run pytest tests/test_run_journal.py -q
```

Expected: all run journal tests pass.

- [ ] **Step 5: Commit journal work**

Run:

```bash
git add backend/packages/harness/deerflow/runtime/journal.py backend/tests/test_run_journal.py
git commit -m "补充工具事件"
```

## Task 6: Full Verification and Browser Check

**Files:**
- No planned source edits unless verification exposes a concrete bug.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd backend
uv run pytest tests/test_platform_persistence.py tests/test_platform_admin_api.py tests/test_run_journal.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run frontend unit tests**

Run:

```bash
cd frontend
pnpm test -- tests/unit/core/platform/api.test.ts tests/unit/core/platform/monitoring-import.test.ts tests/unit/app/admin-monitoring-page.test.ts
```

Expected: all selected frontend tests pass.

- [ ] **Step 3: Run frontend typecheck**

Run:

```bash
cd frontend
pnpm typecheck
```

Expected: TypeScript reports no errors.

- [ ] **Step 4: Start dev server for visual verification**

Run:

```bash
cd frontend
pnpm dev
```

Expected: Next dev server starts and prints a localhost URL. If port 3000 is busy, use the printed alternative.

- [ ] **Step 5: Open `/admin/monitoring` in Browser**

Use the in-app Browser to open the dev server URL plus `/admin/monitoring`.

Check:

- Normal user redirects away.
- Admin user can see the page.
- Default list requests `limit=50`.
- Selecting a conversation loads runs.
- Selecting a run loads the timeline.
- Beijing time is visible in list and timeline.
- IM identity shows channel raw fields only.
- Importing a valid run timeline JSON switches to the imported view.
- Importing invalid JSON shows a field-level error.
- Text does not overlap in desktop and narrow widths.

- [ ] **Step 6: Commit any verification fixes**

If Step 5 requires source fixes, commit only those fixes:

```bash
git add <changed-files>
git commit -m "修复监控验收"
```

If no fixes are required, do not create an empty commit.
