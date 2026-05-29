from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _session_factory(tmp_path):
    from deerflow.persistence.base import Base
    import deerflow.persistence.models  # noqa: F401

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'monitoring.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_run_monitoring_summarizes_runs_by_agent(tmp_path):
    from deerflow.persistence.platform.sql import PlatformRepository
    from deerflow.persistence.run.model import RunRow

    engine, sf = await _session_factory(tmp_path)
    try:
        async with sf() as session:
            session.add_all(
                [
                    RunRow(
                        run_id="run-1",
                        thread_id="thread-1",
                        assistant_id="hr-boss-agent",
                        user_id="user-1",
                        status="success",
                        metadata_json={"agent_name": "hr-boss-agent"},
                        total_tokens=100,
                        llm_call_count=2,
                    ),
                    RunRow(
                        run_id="run-2",
                        thread_id="thread-2",
                        assistant_id="hr-boss-agent",
                        user_id="user-1",
                        status="error",
                        metadata_json={"agent_name": "hr-boss-agent"},
                        total_tokens=30,
                        llm_call_count=1,
                    ),
                ]
            )
            await session.commit()

        items = await PlatformRepository(sf).summarize_runs_by_agent()

        assert items == [
            {
                "agent_name": "hr-boss-agent",
                "run_count": 2,
                "success_count": 1,
                "error_count": 1,
                "total_tokens": 130,
                "llm_call_count": 3,
            }
        ]
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_tool_monitoring_summarizes_calls_and_recent_failures(tmp_path):
    from deerflow.persistence.platform.sql import PlatformRepository

    engine, sf = await _session_factory(tmp_path)
    try:
        repo = PlatformRepository(sf)
        await repo.write_tool_audit(
            agent_name="hr-boss-agent",
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="success",
            latency_ms=100,
        )
        await repo.write_tool_audit(
            agent_name="hr-boss-agent",
            tool_name="text2cypher_answer_question",
            mcp_server_name="text2cypher",
            status="error",
            latency_ms=300,
            error="backend unavailable",
        )

        summary = await repo.summarize_tools_by_agent()
        failures = await repo.recent_tool_failures(limit=5)

        assert summary == [
            {
                "agent_name": "hr-boss-agent",
                "mcp_server_name": "text2cypher",
                "tool_name": "text2cypher_answer_question",
                "call_count": 2,
                "error_count": 1,
                "avg_latency_ms": 200,
            }
        ]
        assert len(failures) == 1
        assert failures[0]["status"] == "error"
        assert failures[0]["error"] == "backend unavailable"
    finally:
        await engine.dispose()
