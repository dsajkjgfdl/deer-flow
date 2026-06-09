from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway.auth.models import User

ADMIN_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")


def _user(role: str) -> User:
    user_id = ADMIN_ID if role == "admin" else USER_ID
    return User(id=user_id, email=f"{role}@example.com", password_hash="x", system_role=role)


def _catalog_entry(name: str = "hr-boss-agent", *, status: str = "valid"):
    from deerflow.agents.catalog import AgentCatalogEntry

    return AgentCatalogEntry(
        name=name,
        display_name="HR Boss Agent",
        description="HR leadership demo agent",
        model="qwen3.5-plus",
        tool_groups=["file:read"],
        skills=["hr-boss"],
        mcp_servers=["text2cypher"],
        config_path=f"/agents/{name}/config.yaml",
        soul_path=f"/agents/{name}/SOUL.md",
        config_hash="config-hash",
        soul_hash="soul-hash",
        status=status,
        validation_errors=[] if status != "invalid" else ["bad config"],
        validation_warnings=[],
    )


class FakePlatformRepo:
    def __init__(self) -> None:
        self.assignments: dict[str, list[str]] = {}
        self.audit: list[dict] = []

    async def list_user_agents(self, user_id: str) -> list[str]:
        return self.assignments.get(user_id, [])

    async def user_has_agent(self, user_id: str, agent_name: str) -> bool:
        return agent_name in self.assignments.get(user_id, [])

    async def grant_agent(self, user_id: str, agent_name: str, *, actor_user_id: str) -> bool:
        agents = self.assignments.setdefault(user_id, [])
        if agent_name in agents:
            return False
        agents.append(agent_name)
        self.audit.append({"actor_user_id": actor_user_id, "action": "agent.grant", "target_user_id": user_id, "target_agent_name": agent_name})
        return True

    async def revoke_agent(self, user_id: str, agent_name: str, *, actor_user_id: str) -> bool:
        agents = self.assignments.setdefault(user_id, [])
        if agent_name not in agents:
            return False
        agents.remove(agent_name)
        self.audit.append({"actor_user_id": actor_user_id, "action": "agent.revoke", "target_user_id": user_id, "target_agent_name": agent_name})
        return True

    async def list_admin_audit(self, *, limit: int = 100) -> list[dict]:
        return self.audit[:limit]

    async def summarize_runs_by_agent(self) -> list[dict]:
        return []

    async def summarize_tools_by_agent(self) -> list[dict]:
        return []

    async def recent_tool_failures(self, *, limit: int = 20) -> list[dict]:
        return []


class FakeMonitoringRepo(FakePlatformRepo):
    def __init__(self) -> None:
        super().__init__()
        self.recent_calls: list[dict] = []
        self.tool_thread_calls: list[dict] = []

    def _run(self) -> dict:
        return {
            "thread_id": "thread-im",
            "run_id": "run-im",
            "user_id": "internal",
            "agent_name": "hr-boss-agent",
            "model": "qwen3.5-plus",
            "model_name": "qwen3.5-plus",
            "status": "error",
            "message_count": 2,
            "first_human_message": "查询研发工程师人数",
            "last_ai_message": "查询失败",
            "error": "timeout",
            "total_input_tokens": 12,
            "total_output_tokens": 8,
            "total_tokens": 20,
            "llm_call_count": 1,
            "created_at": "2026-06-08T05:39:20+00:00",
            "updated_at": "2026-06-08T05:39:22+00:00",
        }

    async def list_recent_monitoring_conversations(self, **kwargs) -> list[dict]:
        self.recent_calls.append(kwargs)
        run = self._run()
        return [
            {
                "thread_id": run["thread_id"],
                "run_id": run["run_id"],
                "user_id": run["user_id"],
                "agent_name": run["agent_name"],
                "status": run["status"],
                "updated_at": run["updated_at"],
                "message_count": run["message_count"],
                "first_human_message": run["first_human_message"],
                "error": run["error"],
            }
        ]

    async def list_runs_for_thread(self, thread_id: str, limit: int = 100) -> list[dict]:
        if thread_id != "thread-im":
            return []
        return [self._run()][:limit]

    async def get_run_for_admin(self, run_id: str) -> dict | None:
        if run_id != "run-im":
            return None
        return self._run()

    async def list_tool_audits_for_run(self, run_id: str) -> list[dict]:
        if run_id != "run-im":
            return []
        return [
            {
                "run_id": "run-im",
                "thread_id": "thread-im",
                "tool_name": "text2cypher_answer_question",
                "mcp_server_name": "text2cypher",
                "status": "error",
                "latency_ms": 842,
                "error": "timeout",
                "created_at": "2026-06-08T05:39:24+00:00",
                "metadata_json": {"argument_keys": ["question"]},
            }
        ]

    async def list_monitoring_tool_thread_ids(
        self,
        *,
        tool_name: str | None = None,
        mcp_server_name: str | None = None,
        q: str | None = None,
    ) -> list[str]:
        self.tool_thread_calls.append(
            {
                "tool_name": tool_name,
                "mcp_server_name": mcp_server_name,
                "q": q,
            }
        )
        values = "text2cypher_answer_question text2cypher timeout"
        filters = [value.strip().lower() for value in (tool_name, mcp_server_name, q) if value and value.strip()]
        return ["thread-im"] if all(value in values for value in filters) else []


class FakeChannelStore:
    async def list_entries(self) -> list[dict]:
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


class FakeMultiChannelStore:
    async def list_entries(self) -> list[dict]:
        return [
            {
                "channel_name": "feishu",
                "chat_id": "oc_xxx",
                "topic_id": "msg_xxx",
                "thread_id": "thread-im",
                "user_id": "ou_xxx",
                "created_at": 1780897160.0,
                "updated_at": 1780897162.0,
            },
            {
                "channel_name": "slack",
                "chat_id": "C_xxx",
                "thread_id": "thread-slack",
                "user_id": "U_xxx",
                "created_at": 1780897160.0,
                "updated_at": 1780897162.0,
            },
        ]


def _monitoring_conversation_row(
    thread_id: str,
    *,
    run_id: str | None = None,
    user_id: str = "user-web",
    agent_name: str = "hr-boss-agent",
    status: str = "success",
    updated_at: str = "2026-06-08T05:39:22+00:00",
) -> dict:
    return {
        "thread_id": thread_id,
        "run_id": run_id or f"run-{thread_id}",
        "user_id": user_id,
        "agent_name": agent_name,
        "status": status,
        "updated_at": updated_at,
        "message_count": 1,
        "first_human_message": f"message {thread_id}",
        "error": "timeout" if status == "error" else None,
    }


class FakePushdownMonitoringRepo(FakeMonitoringRepo):
    def __init__(self) -> None:
        super().__init__()
        self.rows = [
            _monitoring_conversation_row(f"thread-web-{idx:03d}", agent_name="other-agent", status="success")
            for idx in range(240)
        ]
        self.rows.append(
            _monitoring_conversation_row(
                "thread-im",
                run_id="run-im",
                user_id="internal",
                agent_name="hr-boss-agent",
                status="error",
            )
        )
        self.rows.append(
            _monitoring_conversation_row(
                "thread-slack",
                run_id="run-slack",
                user_id="internal",
                agent_name="hr-boss-agent",
                status="error",
            )
        )

    async def list_recent_monitoring_conversations(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
        agent_name: str | None = None,
        status: str | None = None,
        source_thread_ids: list[str] | None = None,
    ) -> dict:
        call = {
            "limit": limit,
            "offset": offset,
            "q": q,
            "agent_name": agent_name,
            "status": status,
            "source_thread_ids": source_thread_ids,
        }
        self.recent_calls.append(call)
        rows = list(self.rows)
        if agent_name:
            rows = [row for row in rows if row["agent_name"] == agent_name]
        if status:
            rows = [row for row in rows if row["status"] == status]
        if source_thread_ids is not None:
            allowed = set(source_thread_ids)
            rows = [row for row in rows if row["thread_id"] in allowed]
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }


class FakeIgnoringThreadFilterMonitoringRepo(FakePushdownMonitoringRepo):
    async def list_recent_monitoring_conversations(self, **kwargs) -> dict:
        self.recent_calls.append(kwargs)
        limit = int(kwargs.get("limit", 50))
        offset = int(kwargs.get("offset", 0))
        rows = list(self.rows)
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }


class FakeWebPagingMonitoringRepo(FakeMonitoringRepo):
    def __init__(self) -> None:
        super().__init__()
        self.rows = [_monitoring_conversation_row("thread-im", user_id="internal")]
        self.rows.extend(_monitoring_conversation_row(f"thread-web-{idx:03d}") for idx in range(205))

    async def list_recent_monitoring_conversations(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
        agent_name: str | None = None,
        status: str | None = None,
        source_thread_ids: list[str] | None = None,
    ) -> dict:
        self.recent_calls.append(
            {
                "limit": limit,
                "offset": offset,
                "q": q,
                "agent_name": agent_name,
                "status": status,
                "source_thread_ids": source_thread_ids,
            }
        )
        rows = list(self.rows)
        if source_thread_ids is not None:
            allowed = set(source_thread_ids)
            rows = [row for row in rows if row["thread_id"] in allowed]
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
        }


class FakeFeedbackRepo:
    async def summarize_for_admin(self) -> dict:
        return {
            "total": 3,
            "positive": 2,
            "negative": 1,
            "positive_rate": 2 / 3,
            "by_agent": [
                {
                    "agent_name": "hr-boss-agent",
                    "total": 3,
                    "positive": 2,
                    "negative": 1,
                    "positive_rate": 2 / 3,
                }
            ],
        }

    async def recent_for_admin(self, *, limit: int = 20) -> list[dict]:
        return [
            {
                "feedback_id": "fb-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
                "user_id": "user-1",
                "agent_name": "hr-boss-agent",
                "rating": -1,
                "comment": "wrong data",
                "run_user_id": "user-1",
                "first_human_message": "How many people are in R&D?",
                "last_ai_message": "There are 42 people in R&D.",
                "message_count": 2,
                "created_at": "2026-05-29T00:00:00+00:00",
            }
        ][:limit]

    async def get_for_admin(self, feedback_id: str) -> dict | None:
        if feedback_id != "fb-1":
            return None
        return (await self.recent_for_admin(limit=1))[0]


class FakeRunEventStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def list_messages_by_run(self, thread_id: str, run_id: str, *, limit: int = 50, user_id=None):
        self.calls.append(
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "limit": limit,
                "user_id": user_id,
            }
        )
        return [
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "event_type": "human_message",
                "category": "message",
                "content": {"type": "human", "content": "How many people are in R&D?"},
                "seq": 1,
            },
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "event_type": "ai_message",
                "category": "message",
                "content": {"type": "ai", "content": "There are 42 people in R&D."},
                "seq": 2,
            },
        ]


class FakeTimelineRunEventStore(FakeRunEventStore):
    async def list_events(self, thread_id, run_id, *, event_types=None, limit=500, user_id=None):
        self.calls.append(
            {
                "thread_id": thread_id,
                "run_id": run_id,
                "event_types": event_types,
                "limit": limit,
                "user_id": user_id,
            }
        )
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


class FakeSameTimestampMonitoringRepo(FakeMonitoringRepo):
    async def list_tool_audits_for_run(self, run_id: str) -> list[dict]:
        if run_id != "run-im":
            return []
        return [
            {
                "run_id": "run-im",
                "thread_id": "thread-im",
                "tool_name": "text2cypher_answer_question",
                "mcp_server_name": "text2cypher",
                "status": "error",
                "latency_ms": 842,
                "error": "timeout",
                "created_at": "2026-06-08T05:39:20+00:00",
                "metadata_json": {"argument_keys": ["question"]},
            }
        ]


class FakeEmptyRunEventStore:
    async def list_messages_by_run(self, thread_id: str, run_id: str, *, limit: int = 50, user_id=None):
        return []


class FakeLocalProvider:
    def __init__(self) -> None:
        self.users = [
            User(
                id=UUID("00000000-0000-0000-0000-000000000011"),
                email="alice@example.com",
                password_hash="x",
                system_role="user",
            ),
            User(
                id=UUID("00000000-0000-0000-0000-000000000012"),
                email="admin2@example.com",
                password_hash="x",
                system_role="admin",
            ),
            User(
                id=UUID("00000000-0000-0000-0000-000000000013"),
                email="bob@example.com",
                password_hash="x",
                system_role="user",
                needs_setup=True,
            ),
        ]
        self.users_by_id = {
            "user-1": SimpleNamespace(id="user-1", email="reviewer@example.com"),
        }

    async def list_users(self, *, limit: int = 50, offset: int = 0):
        return self.users[offset : offset + limit], len(self.users)

    async def get_user(self, user_id: str):
        return self.users_by_id.get(user_id)


def test_admin_users_route_returns_paginated_users(monkeypatch):
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakePlatformRepo()
    app.include_router(platform_admin.router)
    monkeypatch.setattr(platform_admin, "get_local_provider", lambda: FakeLocalProvider())

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/users?limit=2&offset=1")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert [item["email"] for item in data["items"]] == [
        "admin2@example.com",
        "bob@example.com",
    ]
    assert data["items"][0]["system_role"] == "admin"
    assert data["items"][1]["needs_setup"] is True


def test_admin_catalog_and_assignment_routes(monkeypatch):
    from app.gateway.routers import platform_admin

    repo = FakePlatformRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.include_router(platform_admin.router)

    monkeypatch.setattr(platform_admin, "scan_agent_catalog", lambda app_config=None: [_catalog_entry()])

    with TestClient(app) as client:
        catalog = client.get("/api/platform/admin/agents/catalog")
        assert catalog.status_code == 200
        assert catalog.json()["agents"][0]["name"] == "hr-boss-agent"

        granted = client.put("/api/platform/admin/users/user-1/agents/hr-boss-agent")
        assert granted.status_code == 200
        assert granted.json() == {"user_id": "user-1", "agent_name": "hr-boss-agent", "granted": True}

        listed = client.get("/api/platform/admin/users/user-1/agents")
        assert listed.status_code == 200
        assert listed.json() == {"user_id": "user-1", "agent_names": ["hr-boss-agent"]}

        revoked = client.delete("/api/platform/admin/users/user-1/agents/hr-boss-agent")
        assert revoked.status_code == 200
        assert revoked.json() == {"user_id": "user-1", "agent_name": "hr-boss-agent", "revoked": True}

        audit = client.get("/api/platform/admin/audit")
        assert audit.status_code == 200
        assert [item["action"] for item in audit.json()["items"]] == ["agent.grant", "agent.revoke"]


def test_admin_assignment_rejects_invalid_agent(monkeypatch):
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakePlatformRepo()
    app.include_router(platform_admin.router)
    monkeypatch.setattr(platform_admin, "scan_agent_catalog", lambda app_config=None: [_catalog_entry(status="invalid")])

    with TestClient(app) as client:
        response = client.put("/api/platform/admin/users/user-1/agents/hr-boss-agent")

    assert response.status_code == 400
    assert "invalid" in response.json()["detail"]


def test_admin_feedback_routes_return_summary_and_recent(monkeypatch):
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakePlatformRepo()
    app.state.feedback_repo = FakeFeedbackRepo()
    app.include_router(platform_admin.router)
    monkeypatch.setattr(platform_admin, "get_local_provider", lambda: FakeLocalProvider())

    with TestClient(app) as client:
        summary = client.get("/api/platform/admin/feedback/summary")
        recent = client.get("/api/platform/admin/feedback/recent?limit=1")

    assert summary.status_code == 200
    assert summary.json()["total"] == 3
    assert summary.json()["positive"] == 2
    assert summary.json()["negative"] == 1
    assert summary.json()["by_agent"][0]["agent_name"] == "hr-boss-agent"

    assert recent.status_code == 200
    assert recent.json()["items"] == [
        {
            "feedback_id": "fb-1",
            "thread_id": "thread-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_name": "hr-boss-agent",
            "rating": -1,
            "comment": "wrong data",
            "user_email": "reviewer@example.com",
            "run_user_id": "user-1",
            "first_human_message": "How many people are in R&D?",
            "last_ai_message": "There are 42 people in R&D.",
            "message_count": 2,
            "created_at": "2026-05-29T00:00:00+00:00",
        }
    ]


def test_admin_feedback_conversation_returns_voter_and_messages(monkeypatch):
    from app.gateway.routers import platform_admin

    event_store = FakeRunEventStore()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakePlatformRepo()
    app.state.feedback_repo = FakeFeedbackRepo()
    app.state.run_event_store = event_store
    app.include_router(platform_admin.router)
    monkeypatch.setattr(platform_admin, "get_local_provider", lambda: FakeLocalProvider())

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/feedback/fb-1/conversation?limit=50")

    assert response.status_code == 200
    data = response.json()
    assert data["feedback"]["feedback_id"] == "fb-1"
    assert data["feedback"]["user_email"] == "reviewer@example.com"
    assert data["feedback"]["first_human_message"] == "How many people are in R&D?"
    assert [message["event_type"] for message in data["messages"]] == [
        "human_message",
        "ai_message",
    ]
    assert event_store.calls == [
        {
            "thread_id": "thread-1",
            "run_id": "run-1",
            "limit": 50,
            "user_id": None,
        }
    ]


def test_admin_feedback_conversation_falls_back_to_run_summary(monkeypatch):
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakePlatformRepo()
    app.state.feedback_repo = FakeFeedbackRepo()
    app.state.run_event_store = FakeEmptyRunEventStore()
    app.include_router(platform_admin.router)
    monkeypatch.setattr(platform_admin, "get_local_provider", lambda: FakeLocalProvider())

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/feedback/fb-1/conversation?limit=50")

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == [
        {
            "thread_id": "thread-1",
            "run_id": "run-1",
            "event_type": "human_message",
            "category": "message",
            "content": {"type": "human", "content": "How many people are in R&D?"},
            "metadata": {"source": "run_summary"},
            "seq": 1,
        },
        {
            "thread_id": "thread-1",
            "run_id": "run-1",
            "event_type": "ai_message",
            "category": "message",
            "content": {"type": "ai", "content": "There are 42 people in R&D."},
            "metadata": {"source": "run_summary"},
            "seq": 2,
        },
    ]


def test_feedback_admin_routes_reject_normal_user():
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.state.platform_repo = FakePlatformRepo()
    app.state.feedback_repo = FakeFeedbackRepo()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/feedback/summary")

    assert response.status_code == 403


def test_admin_monitoring_recent_conversations_includes_im_raw_identity():
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
    item = data["items"][0]
    assert item["identity"]["identity_type"] == "channel"
    assert item["identity"]["identity_source"] == "feishu"
    assert item["identity"]["raw_identity"] == {
        "channel_user_id": "ou_xxx",
        "chat_id": "oc_xxx",
        "topic_id": "msg_xxx",
    }
    assert item["updated_at_bj"] == "2026-06-08 13:39:22"


def test_admin_monitoring_recent_conversations_searches_im_raw_identity():
    from app.gateway.routers import platform_admin

    repo = FakeMonitoringRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.state.channel_store = FakeChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        for query in ["ou_xxx", "OC_XXX", "msg_xxx"]:
            repo.recent_calls.clear()
            response = client.get(f"/api/platform/admin/monitoring/conversations/recent?q={query}")

            assert response.status_code == 200
            data = response.json()
            assert [item["thread_id"] for item in data["items"]] == ["thread-im"]
            assert repo.recent_calls[-1].get("q") is None


def test_admin_monitoring_recent_conversations_pushes_agent_status_to_repo():
    from app.gateway.routers import platform_admin

    repo = FakePushdownMonitoringRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.state.channel_store = FakeMultiChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get(
            "/api/platform/admin/monitoring/conversations/recent"
            "?agent_name=hr-boss-agent&status=error&limit=10"
        )

    assert response.status_code == 200
    assert repo.recent_calls[-1]["agent_name"] == "hr-boss-agent"
    assert repo.recent_calls[-1]["status"] == "error"
    assert {item["thread_id"] for item in response.json()["items"]} == {
        "thread-im",
        "thread-slack",
    }


def test_admin_monitoring_recent_conversations_pushes_channel_source_thread_ids():
    from app.gateway.routers import platform_admin

    repo = FakePushdownMonitoringRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.state.channel_store = FakeMultiChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/conversations/recent?source=feishu&limit=1")

    assert response.status_code == 200
    assert repo.recent_calls[-1]["source_thread_ids"] == ["thread-im"]
    data = response.json()
    assert data["total"] == 1
    assert [item["thread_id"] for item in data["items"]] == ["thread-im"]


def test_admin_monitoring_recent_conversations_filters_by_tool_and_mcp():
    from app.gateway.routers import platform_admin

    repo = FakeIgnoringThreadFilterMonitoringRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.state.channel_store = FakeMultiChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        tool_response = client.get(
            "/api/platform/admin/monitoring/conversations/recent",
            params={"tool_name": "answer_question"},
        )
        mcp_response = client.get(
            "/api/platform/admin/monitoring/conversations/recent",
            params={"mcp_server_name": "text2cypher"},
        )
        combined_response = client.get(
            "/api/platform/admin/monitoring/conversations/recent",
            params={"source": "feishu", "tool_name": "text2cypher"},
        )

    assert tool_response.status_code == 200
    assert [item["thread_id"] for item in tool_response.json()["items"]] == ["thread-im"]
    assert mcp_response.status_code == 200
    assert [item["thread_id"] for item in mcp_response.json()["items"]] == ["thread-im"]
    assert combined_response.status_code == 200
    assert [item["thread_id"] for item in combined_response.json()["items"]] == ["thread-im"]
    assert repo.recent_calls[-1]["source_thread_ids"] == ["thread-im"]


def test_admin_monitoring_recent_conversations_q_matches_tool_audit():
    from app.gateway.routers import platform_admin

    repo = FakePushdownMonitoringRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.state.channel_store = FakeMultiChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get(
            "/api/platform/admin/monitoring/conversations/recent",
            params={"q": "answer_question"},
        )

    assert response.status_code == 200
    assert [item["thread_id"] for item in response.json()["items"]] == ["thread-im"]
    assert all(call.get("q") is None for call in repo.recent_calls)


def test_admin_monitoring_recent_conversations_filters_beijing_time_range():
    from app.gateway.routers import platform_admin

    repo = FakeMonitoringRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.state.channel_store = FakeChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        included = client.get(
            "/api/platform/admin/monitoring/conversations/recent",
            params={"from": "2026-06-08T13:39:21", "to": "2026-06-08T13:39:23"},
        )
        excluded = client.get(
            "/api/platform/admin/monitoring/conversations/recent",
            params={"to": "2026-06-08T13:39:21"},
        )
        invalid = client.get(
            "/api/platform/admin/monitoring/conversations/recent",
            params={"from": "2026-06-08T14:00", "to": "2026-06-08T13:00"},
        )

    assert included.status_code == 200
    assert [item["thread_id"] for item in included.json()["items"]] == ["thread-im"]
    assert excluded.status_code == 200
    assert excluded.json()["items"] == []
    assert invalid.status_code == 422


def test_admin_monitoring_recent_conversations_web_source_scans_pages():
    from app.gateway.routers import platform_admin

    repo = FakeWebPagingMonitoringRepo()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = repo
    app.state.channel_store = FakeChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/conversations/recent?source=web&limit=2&offset=203")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 205
    assert data["offset"] == 203
    assert [item["thread_id"] for item in data["items"]] == [
        "thread-web-203",
        "thread-web-204",
    ]
    assert [call["offset"] for call in repo.recent_calls] == [0, 200]


def test_admin_monitoring_conversation_detail_returns_runs_and_identity():
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakeMonitoringRepo()
    app.state.channel_store = FakeChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/conversations/thread-im")

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "thread-im"
    assert data["identity"]["identity_display"] == "feishu: ou_xxx"
    assert data["message_preview"] == "查询研发工程师人数"
    assert data["runs"][0]["run_id"] == "run-im"
    assert data["runs"][0]["updated_at_bj"] == "2026-06-08 13:39:22"


def test_admin_monitoring_run_timeline_merges_events_and_tool_audit():
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


def test_admin_monitoring_run_timeline_limit_applies_after_merge():
    from app.gateway.routers import platform_admin

    event_store = FakeTimelineRunEventStore()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakeMonitoringRepo()
    app.state.channel_store = FakeChannelStore()
    app.state.run_event_store = event_store
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/runs/run-im/timeline?limit=1")

    assert response.status_code == 200
    assert [event["kind"] for event in response.json()["events"]] == ["run.start"]


def test_admin_monitoring_run_timeline_sorts_missing_seq_after_same_time_run_event():
    from app.gateway.routers import platform_admin

    event_store = FakeTimelineRunEventStore()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakeSameTimestampMonitoringRepo()
    app.state.channel_store = FakeChannelStore()
    app.state.run_event_store = event_store
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/runs/run-im/timeline")

    assert response.status_code == 200
    assert [event["kind"] for event in response.json()["events"]] == ["run.start", "tool.error"]


def test_admin_monitoring_run_messages_returns_admin_messages():
    from app.gateway.routers import platform_admin

    event_store = FakeRunEventStore()
    app = make_authed_test_app(user_factory=lambda: _user("admin"))
    app.state.platform_repo = FakeMonitoringRepo()
    app.state.channel_store = FakeChannelStore()
    app.state.run_event_store = event_store
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/runs/run-im/messages?limit=50")

    assert response.status_code == 200
    data = response.json()
    assert data["run"]["run_id"] == "run-im"
    assert [message["event_type"] for message in data["messages"]] == [
        "human_message",
        "ai_message",
    ]
    assert event_store.calls[-1]["user_id"] is None


def test_admin_monitoring_rejects_normal_user():
    from app.gateway.routers import platform_admin

    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.state.platform_repo = FakeMonitoringRepo()
    app.state.channel_store = FakeChannelStore()
    app.include_router(platform_admin.router)

    with TestClient(app) as client:
        response = client.get("/api/platform/admin/monitoring/conversations/recent")

    assert response.status_code == 403


def test_user_platform_agents_routes_only_return_assigned_agents(monkeypatch):
    from app.gateway.routers import platform_agents

    repo = FakePlatformRepo()
    repo.assignments[str(USER_ID)] = ["hr-boss-agent"]
    app = make_authed_test_app(user_factory=lambda: _user("user"))
    app.state.platform_repo = repo
    app.include_router(platform_agents.router)

    monkeypatch.setattr(
        platform_agents,
        "scan_agent_catalog",
        lambda app_config=None: [_catalog_entry("hr-boss-agent"), _catalog_entry("finance-agent")],
    )

    with TestClient(app) as client:
        listed = client.get("/api/platform/agents")
        assert listed.status_code == 200
        assert [agent["name"] for agent in listed.json()["agents"]] == ["hr-boss-agent"]

        detail = client.get("/api/platform/agents/hr-boss-agent")
        assert detail.status_code == 200
        assert detail.json()["name"] == "hr-boss-agent"

        denied = client.get("/api/platform/agents/finance-agent")
        assert denied.status_code == 403
