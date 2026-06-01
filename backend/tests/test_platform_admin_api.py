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
