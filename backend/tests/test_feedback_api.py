"""Tests for thread run feedback endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway.routers import feedback


def _make_app():
    app = make_authed_test_app()
    app.include_router(feedback.router)

    run_store = MagicMock()
    run_store.get = AsyncMock(return_value={"run_id": "run-1", "thread_id": "thread-1"})
    app.state.run_store = run_store

    feedback_repo = MagicMock()
    feedback_repo.upsert = AsyncMock(
        return_value={
            "feedback_id": "fb-1",
            "thread_id": "thread-1",
            "run_id": "run-1",
            "user_id": None,
            "rating": -1,
            "comment": "wrong",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    feedback_repo.delete_by_run = AsyncMock(return_value=True)
    app.state.feedback_repo = feedback_repo
    return app, feedback_repo


def test_upsert_feedback_is_run_scoped():
    app, feedback_repo = _make_app()

    with TestClient(app) as client:
        response = client.put(
            "/api/threads/thread-1/runs/run-1/feedback",
            json={"rating": -1, "comment": "wrong", "message_id": "ai-1"},
    )

    assert response.status_code == 200
    assert "message_id" not in response.json()
    feedback_repo.upsert.assert_awaited_once_with(
        run_id="run-1",
        thread_id="thread-1",
        rating=-1,
        user_id=None,
        comment="wrong",
    )


def test_delete_feedback_is_run_scoped():
    app, feedback_repo = _make_app()

    with TestClient(app) as client:
        response = client.delete(
            "/api/threads/thread-1/runs/run-1/feedback?message_id=ai-1"
        )

    assert response.status_code == 200
    feedback_repo.delete_by_run.assert_awaited_once_with(
        thread_id="thread-1",
        run_id="run-1",
        user_id=None,
    )
