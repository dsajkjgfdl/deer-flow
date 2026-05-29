from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest


async def _session_factory(tmp_path):
    from deerflow.persistence.base import Base
    import deerflow.persistence.models  # noqa: F401

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
