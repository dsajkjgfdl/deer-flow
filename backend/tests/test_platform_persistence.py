import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _session_factory(tmp_path):
    import deerflow.persistence.models  # noqa: F401
    from deerflow.persistence.base import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _count_rows(sf, model):
    from sqlalchemy import func, select

    async with sf() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def _list_rows(sf, model):
    from sqlalchemy import select

    async with sf() as session:
        return list((await session.execute(select(model))).scalars())


@pytest.mark.anyio
async def test_agent_assignment_grant_revoke_and_admin_audit(tmp_path):
    from deerflow.persistence.platform.model import AdminAuditLogRow, AgentAssignmentRow
    from deerflow.persistence.platform.sql import PlatformRepository

    engine, sf = await _session_factory(tmp_path)
    try:
        repo = PlatformRepository(sf)

        await repo.grant_agent("user-1", "hr-boss-agent", actor_user_id="admin-1")
        await repo.grant_agent("user-1", "hr-boss-agent", actor_user_id="admin-1")

        assert await repo.user_has_agent("user-1", "hr-boss-agent")
        assert await repo.list_user_agents("user-1") == ["hr-boss-agent"]
        assert await _count_rows(sf, AgentAssignmentRow) == 1
        assert await _count_rows(sf, AdminAuditLogRow) == 1

        await repo.revoke_agent("user-1", "hr-boss-agent", actor_user_id="admin-1")

        assert not await repo.user_has_agent("user-1", "hr-boss-agent")
        assert await repo.list_user_agents("user-1") == []
        assert await _count_rows(sf, AgentAssignmentRow) == 0
        assert await _count_rows(sf, AdminAuditLogRow) == 2
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_tool_audit_log_can_be_written_and_listed(tmp_path):
    from deerflow.persistence.platform.model import ToolAuditLogRow
    from deerflow.persistence.platform.sql import PlatformRepository

    engine, sf = await _session_factory(tmp_path)
    try:
        repo = PlatformRepository(sf)

        await repo.write_tool_audit(
            run_id="run-1",
            thread_id="thread-1",
            user_id="user-1",
            agent_name="hr-boss-agent",
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="success",
            latency_ms=123,
            metadata={"argument_keys": ["question"]},
        )

        rows = await _list_rows(sf, ToolAuditLogRow)
        assert len(rows) == 1
        assert rows[0].run_id == "run-1"
        assert rows[0].agent_name == "hr-boss-agent"
        assert rows[0].mcp_server_name == "text2cypher"
        assert rows[0].metadata_json == {"argument_keys": ["question"]}
    finally:
        await engine.dispose()


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
        blank_query_page = await repo.list_recent_monitoring_conversations(limit=50, offset=0, q="   ")

        assert page["total"] == 2
        assert [item["thread_id"] for item in page["items"]] == ["thread-2", "thread-1"]
        assert page["items"][1]["latest_run_id"] == "run-new"
        assert page["items"][1]["last_message"] == "latest question"
        assert page["items"][1]["error_summary"] == "backend unavailable"
        assert blank_query_page["total"] == page["total"]
        assert [item["thread_id"] for item in blank_query_page["items"]] == ["thread-2", "thread-1"]
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_monitoring_run_detail_and_tool_audit_lookup(tmp_path):
    from datetime import UTC, datetime

    from deerflow.persistence.platform.model import ToolAuditLogRow
    from deerflow.persistence.platform.sql import PlatformRepository
    from deerflow.persistence.run.model import RunRow

    engine, sf = await _session_factory(tmp_path)
    try:
        async with sf() as session:
            audit_time = datetime(2026, 6, 8, 5, 2, tzinfo=UTC)
            session.add_all(
                [
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
                    ),
                    RunRow(
                        run_id="run-other-thread",
                        thread_id="thread-2",
                        assistant_id="hr-boss-agent",
                        user_id="user-2",
                        status="success",
                        first_human_message="Other thread",
                        message_count=1,
                        created_at=datetime(2026, 6, 8, 6, 0, tzinfo=UTC),
                        updated_at=datetime(2026, 6, 8, 6, 1, tzinfo=UTC),
                    ),
                    ToolAuditLogRow(
                        run_id="run-1",
                        thread_id="thread-1",
                        user_id="user-1",
                        agent_name="hr-boss-agent",
                        tool_name="text2cypher_prepare_schema",
                        mcp_server_name="text2cypher",
                        status="success",
                        latency_ms=100,
                        metadata_json={"argument_keys": ["schema"]},
                        created_at=audit_time,
                    ),
                    ToolAuditLogRow(
                        run_id="run-1",
                        thread_id="thread-1",
                        user_id="user-1",
                        agent_name="hr-boss-agent",
                        tool_name="text2cypher_answer_question",
                        mcp_server_name="text2cypher",
                        status="error",
                        latency_ms=842,
                        error="timeout",
                        metadata_json={"argument_keys": ["question"]},
                        created_at=audit_time,
                    ),
                    ToolAuditLogRow(
                        run_id="run-other",
                        thread_id="thread-1",
                        user_id="user-1",
                        agent_name="hr-boss-agent",
                        tool_name="other_run_tool",
                        mcp_server_name="text2cypher",
                        status="success",
                        latency_ms=10,
                        created_at=datetime(2026, 6, 8, 4, 0, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()

        repo = PlatformRepository(sf)

        run = await repo.get_run_for_admin("run-1")
        runs = await repo.list_runs_for_thread("thread-1")
        audits = await repo.list_tool_audits_for_run("run-1")

        assert run is not None
        assert run["run_id"] == "run-1"
        assert [item["run_id"] for item in runs] == ["run-1"]
        assert [item["tool_name"] for item in audits] == [
            "text2cypher_prepare_schema",
            "text2cypher_answer_question",
        ]
        assert audits[1]["metadata_json"] == {"argument_keys": ["question"]}
    finally:
        await engine.dispose()
