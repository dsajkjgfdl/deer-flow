from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.platform.model import AdminAuditLogRow, AgentAssignmentRow, ToolAuditLogRow
from deerflow.persistence.run.model import RunRow


class PlatformRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return row.to_dict()

    def _run_row_to_monitoring_dict(self, row: RunRow) -> dict[str, Any]:
        data = self._row_to_dict(row)
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        data["agent_name"] = str(metadata.get("agent_name") or row.assistant_id or "default")
        data["latest_run_id"] = row.run_id
        data["last_message"] = row.last_ai_message or row.first_human_message
        data["error_summary"] = row.error
        return data

    async def write_admin_audit(
        self,
        *,
        actor_user_id: str,
        action: str,
        target_user_id: str | None = None,
        target_agent_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = AdminAuditLogRow(
            actor_user_id=actor_user_id,
            action=action,
            target_user_id=target_user_id,
            target_agent_name=target_agent_name,
            metadata_json=metadata or {},
            created_at=datetime.now(UTC),
        )
        async with self._sf() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def grant_agent(self, user_id: str, agent_name: str, *, actor_user_id: str) -> bool:
        async with self._sf() as session:
            existing = (
                await session.execute(
                    select(AgentAssignmentRow).where(
                        AgentAssignmentRow.user_id == user_id,
                        AgentAssignmentRow.agent_name == agent_name,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return False

            session.add(
                AgentAssignmentRow(
                    user_id=user_id,
                    agent_name=agent_name,
                    granted_by=actor_user_id,
                    created_at=datetime.now(UTC),
                )
            )
            session.add(
                AdminAuditLogRow(
                    actor_user_id=actor_user_id,
                    action="agent.grant",
                    target_user_id=user_id,
                    target_agent_name=agent_name,
                    metadata_json={},
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return True

    async def revoke_agent(self, user_id: str, agent_name: str, *, actor_user_id: str) -> bool:
        async with self._sf() as session:
            existing = (
                await session.execute(
                    select(AgentAssignmentRow).where(
                        AgentAssignmentRow.user_id == user_id,
                        AgentAssignmentRow.agent_name == agent_name,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                return False

            await session.delete(existing)
            session.add(
                AdminAuditLogRow(
                    actor_user_id=actor_user_id,
                    action="agent.revoke",
                    target_user_id=user_id,
                    target_agent_name=agent_name,
                    metadata_json={},
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return True

    async def list_user_agents(self, user_id: str) -> list[str]:
        stmt = select(AgentAssignmentRow.agent_name).where(AgentAssignmentRow.user_id == user_id).order_by(AgentAssignmentRow.agent_name.asc())
        async with self._sf() as session:
            return list((await session.execute(stmt)).scalars())

    async def user_has_agent(self, user_id: str, agent_name: str) -> bool:
        stmt = select(AgentAssignmentRow.id).where(AgentAssignmentRow.user_id == user_id, AgentAssignmentRow.agent_name == agent_name).limit(1)
        async with self._sf() as session:
            return (await session.execute(stmt)).scalar_one_or_none() is not None

    async def clear_user_assignments(self, user_id: str, *, actor_user_id: str) -> int:
        current = await self.list_user_agents(user_id)
        if not current:
            return 0
        async with self._sf() as session:
            result = await session.execute(delete(AgentAssignmentRow).where(AgentAssignmentRow.user_id == user_id))
            session.add(
                AdminAuditLogRow(
                    actor_user_id=actor_user_id,
                    action="agent.clear_user_assignments",
                    target_user_id=user_id,
                    target_agent_name=None,
                    metadata_json={"agent_names": current},
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
            return int(result.rowcount or 0)

    async def list_admin_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        stmt = select(AdminAuditLogRow).order_by(desc(AdminAuditLogRow.created_at), desc(AdminAuditLogRow.id)).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars()
            return [self._row_to_dict(row) for row in rows]

    async def write_tool_audit(
        self,
        *,
        tool_name: str,
        status: str,
        run_id: str | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_name: str | None = None,
        mcp_server_name: str | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = ToolAuditLogRow(
            run_id=run_id,
            thread_id=thread_id,
            user_id=user_id,
            agent_name=agent_name,
            tool_name=tool_name,
            mcp_server_name=mcp_server_name,
            status=status,
            latency_ms=latency_ms,
            error=error,
            metadata_json=metadata or {},
            created_at=datetime.now(UTC),
        )
        async with self._sf() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def summarize_runs_by_agent(self) -> list[dict[str, Any]]:
        stmt = select(RunRow)
        summaries: dict[str, dict[str, Any]] = {}
        async with self._sf() as session:
            rows = list((await session.execute(stmt)).scalars())

        for row in rows:
            metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            agent_name = metadata.get("agent_name") or row.assistant_id or "default"
            item = summaries.setdefault(
                str(agent_name),
                {
                    "agent_name": str(agent_name),
                    "run_count": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "total_tokens": 0,
                    "llm_call_count": 0,
                },
            )
            item["run_count"] += 1
            if row.status == "success":
                item["success_count"] += 1
            elif row.status == "error":
                item["error_count"] += 1
            item["total_tokens"] += row.total_tokens or 0
            item["llm_call_count"] += row.llm_call_count or 0

        return [summaries[key] for key in sorted(summaries)]

    async def summarize_tools_by_agent(self) -> list[dict[str, Any]]:
        stmt = select(ToolAuditLogRow)
        summaries: dict[tuple[str, str | None, str], dict[str, Any]] = {}
        latency_values: dict[tuple[str, str | None, str], list[int]] = {}
        async with self._sf() as session:
            rows = list((await session.execute(stmt)).scalars())

        for row in rows:
            agent_name = row.agent_name or "default"
            key = (agent_name, row.mcp_server_name, row.tool_name)
            item = summaries.setdefault(
                key,
                {
                    "agent_name": agent_name,
                    "mcp_server_name": row.mcp_server_name,
                    "tool_name": row.tool_name,
                    "call_count": 0,
                    "error_count": 0,
                    "avg_latency_ms": None,
                },
            )
            item["call_count"] += 1
            if row.status == "error":
                item["error_count"] += 1
            if row.latency_ms is not None:
                latency_values.setdefault(key, []).append(row.latency_ms)

        for key, values in latency_values.items():
            summaries[key]["avg_latency_ms"] = int(sum(values) / len(values))

        return [summaries[key] for key in sorted(summaries)]

    async def recent_tool_failures(self, *, limit: int = 20) -> list[dict[str, Any]]:
        stmt = (
            select(ToolAuditLogRow)
            .where(ToolAuditLogRow.status == "error")
            .order_by(desc(ToolAuditLogRow.created_at), desc(ToolAuditLogRow.id))
            .limit(limit)
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars()
            return [self._row_to_dict(row) for row in rows]

    async def list_recent_monitoring_conversations(self, *, limit: int = 50, offset: int = 0, q: str | None = None) -> dict[str, Any]:
        safe_limit = max(0, min(limit, 200))
        safe_offset = max(0, offset)
        q = q.strip() if q is not None else ""
        filters = []
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    RunRow.run_id.ilike(pattern),
                    RunRow.thread_id.ilike(pattern),
                    RunRow.user_id.ilike(pattern),
                    RunRow.assistant_id.ilike(pattern),
                    RunRow.status.ilike(pattern),
                    RunRow.first_human_message.ilike(pattern),
                    RunRow.last_ai_message.ilike(pattern),
                    RunRow.error.ilike(pattern),
                )
            )

        latest_runs = (
            select(
                RunRow.run_id.label("run_id"),
                func.row_number()
                .over(
                    partition_by=RunRow.thread_id,
                    order_by=(
                        desc(RunRow.updated_at),
                        desc(RunRow.created_at),
                        desc(RunRow.run_id),
                    ),
                )
                .label("row_number"),
            )
            .where(*filters)
            .subquery()
        )
        total_stmt = select(func.count(func.distinct(RunRow.thread_id))).where(*filters)
        items_stmt = (
            select(RunRow)
            .join(latest_runs, RunRow.run_id == latest_runs.c.run_id)
            .where(latest_runs.c.row_number == 1)
            .order_by(desc(RunRow.updated_at), desc(RunRow.created_at), desc(RunRow.run_id))
            .limit(safe_limit)
            .offset(safe_offset)
        )

        async with self._sf() as session:
            total = (await session.execute(total_stmt)).scalar_one()
            rows = list((await session.execute(items_stmt)).scalars())

        return {
            "items": [self._run_row_to_monitoring_dict(row) for row in rows],
            "total": int(total or 0),
            "limit": safe_limit,
            "offset": safe_offset,
        }

    async def get_run_for_admin(self, run_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(RunRow, run_id)
        if row is None:
            return None
        return self._run_row_to_monitoring_dict(row)

    async def list_runs_for_thread(self, thread_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        stmt = select(RunRow).where(RunRow.thread_id == thread_id).order_by(desc(RunRow.created_at), desc(RunRow.updated_at), desc(RunRow.run_id)).limit(max(0, min(limit, 200)))
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars()
            return [self._run_row_to_monitoring_dict(row) for row in rows]

    async def list_tool_audits_for_run(self, run_id: str) -> list[dict[str, Any]]:
        stmt = select(ToolAuditLogRow).where(ToolAuditLogRow.run_id == run_id).order_by(ToolAuditLogRow.created_at.asc(), ToolAuditLogRow.id.asc())
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars()
            return [self._row_to_dict(row) for row in rows]

    async def list_monitoring_tool_thread_ids(
        self,
        *,
        tool_name: str | None = None,
        mcp_server_name: str | None = None,
        q: str | None = None,
        limit: int = 5000,
    ) -> list[str]:
        filters = [ToolAuditLogRow.thread_id.is_not(None)]
        if tool_name and tool_name.strip():
            filters.append(ToolAuditLogRow.tool_name.ilike(f"%{tool_name.strip()}%"))
        if mcp_server_name and mcp_server_name.strip():
            filters.append(ToolAuditLogRow.mcp_server_name.ilike(f"%{mcp_server_name.strip()}%"))
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            filters.append(
                or_(
                    ToolAuditLogRow.tool_name.ilike(pattern),
                    ToolAuditLogRow.mcp_server_name.ilike(pattern),
                    ToolAuditLogRow.error.ilike(pattern),
                )
            )

        stmt = (
            select(ToolAuditLogRow.thread_id)
            .where(*filters)
            .distinct()
            .order_by(ToolAuditLogRow.thread_id)
            .limit(max(0, min(limit, 10_000)))
        )
        async with self._sf() as session:
            thread_ids = (await session.execute(stmt)).scalars()
            return [str(thread_id) for thread_id in thread_ids if thread_id]
