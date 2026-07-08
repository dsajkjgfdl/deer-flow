from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from deerflow.persistence.platform import PlatformRepository
from deerflow.persistence.platform.model import ToolAuditLogRow


async def _make_repo(tmp_path) -> PlatformRepository:
    from deerflow.persistence.engine import get_session_factory, init_engine

    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    await init_engine("sqlite", url=url, sqlite_dir=str(tmp_path))
    return PlatformRepository(get_session_factory())


async def _cleanup() -> None:
    from deerflow.persistence.engine import close_engine

    await close_engine()


@pytest.mark.anyio
async def test_agent_assignment_lifecycle_records_admin_audit(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    try:
        assert await repo.list_user_agents("u-1") == []

        assert await repo.grant_agent("u-1", "hr-boss-agent", actor_user_id="admin-1") is True
        assert await repo.grant_agent("u-1", "hr-boss-agent", actor_user_id="admin-1") is False
        assert await repo.user_has_agent("u-1", "hr-boss-agent") is True
        assert await repo.list_user_agents("u-1") == ["hr-boss-agent"]

        assert await repo.revoke_agent("u-1", "hr-boss-agent", actor_user_id="admin-1") is True
        assert await repo.revoke_agent("u-1", "hr-boss-agent", actor_user_id="admin-1") is False
        assert await repo.user_has_agent("u-1", "hr-boss-agent") is False

        audit_actions = [item["action"] for item in await repo.list_admin_audit()]
        assert audit_actions == ["agent.revoke", "agent.grant"]
    finally:
        await _cleanup()


@pytest.mark.anyio
async def test_tool_audit_summary_groups_by_agent_and_tool(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    try:
        await repo.write_tool_audit(
            run_id="run-1",
            thread_id="thread-1",
            user_id="u-1",
            agent_name="hr-boss-agent",
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="success",
            latency_ms=40,
            metadata={"source": "test"},
            content={"answer": "ok"},
        )
        await repo.write_tool_audit(
            run_id="run-2",
            thread_id="thread-2",
            user_id="u-1",
            agent_name="hr-boss-agent",
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="error",
            latency_ms=60,
            error="boom",
        )

        [summary] = await repo.summarize_tools_by_agent()
        assert summary["agent_name"] == "hr-boss-agent"
        assert summary["mcp_server_name"] == "text2cypher"
        assert summary["tool_name"] == "text2cypher_answer_question"
        assert summary["call_count"] == 2
        assert summary["error_count"] == 1
        assert summary["avg_latency_ms"] == 50

        [failure] = await repo.recent_tool_failures()
        assert failure["run_id"] == "run-2"
        assert failure["content_json"] == {}
    finally:
        await _cleanup()


@pytest.mark.anyio
async def test_list_tool_audits_for_run_includes_unattributed_rows_in_run_window(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    try:
        inside = await repo.write_tool_audit(
            thread_id="thread-1",
            agent_name="hr-boss-agent",
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="success",
        )
        outside_time = await repo.write_tool_audit(
            thread_id="thread-1",
            agent_name="hr-boss-agent",
            tool_name="text2cypher_query_employees",
            mcp_server_name="text2cypher",
            status="success",
        )
        outside_thread = await repo.write_tool_audit(
            thread_id="thread-2",
            agent_name="hr-boss-agent",
            tool_name="hr-graphrag-qa_query_global",
            mcp_server_name="hr-graphrag-qa",
            status="success",
        )
        attributed = await repo.write_tool_audit(
            run_id="run-1",
            thread_id="thread-1",
            agent_name="hr-boss-agent",
            tool_name="text2cypher_query_employees",
            mcp_server_name="text2cypher",
            status="success",
        )

        start = datetime(2026, 7, 8, 3, 6, 25, tzinfo=UTC)
        end = datetime(2026, 7, 8, 3, 6, 30, tzinfo=UTC)
        from deerflow.persistence.engine import get_session_factory

        sf = get_session_factory()
        async with sf() as session:
            await session.execute(
                update(ToolAuditLogRow)
                .where(ToolAuditLogRow.id == inside["id"])
                .values(created_at=start + timedelta(seconds=2))
            )
            await session.execute(
                update(ToolAuditLogRow)
                .where(ToolAuditLogRow.id == outside_time["id"])
                .values(created_at=start - timedelta(seconds=1))
            )
            await session.execute(
                update(ToolAuditLogRow)
                .where(ToolAuditLogRow.id == outside_thread["id"])
                .values(created_at=start + timedelta(seconds=2))
            )
            await session.execute(
                update(ToolAuditLogRow)
                .where(ToolAuditLogRow.id == attributed["id"])
                .values(created_at=start + timedelta(seconds=1))
            )
            await session.commit()

        audits = await repo.list_tool_audits_for_run(
            "run-1",
            thread_id="thread-1",
            started_at=start,
            ended_at=end,
        )

        assert [audit["id"] for audit in audits] == [attributed["id"], inside["id"]]
    finally:
        await _cleanup()
