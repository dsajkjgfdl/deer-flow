"""SQLAlchemy-backed feedback storage.

Each method acquires its own short-lived session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.feedback.model import FeedbackRow
from deerflow.persistence.run.model import RunRow
from deerflow.runtime.user_context import AUTO, _AutoSentinel, resolve_user_id
from deerflow.utils.time import coerce_iso


class FeedbackRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _row_to_dict(row: FeedbackRow) -> dict:
        d = row.to_dict()
        val = d.get("created_at")
        if isinstance(val, datetime):
            # SQLite drops tzinfo on read; normalize via ``coerce_iso`` so output is always tz-aware.
            d["created_at"] = coerce_iso(val)
        return d

    async def create(
        self,
        *,
        run_id: str,
        thread_id: str,
        rating: int,
        user_id: str | None | _AutoSentinel = AUTO,
        message_id: str | None = None,
        comment: str | None = None,
    ) -> dict:
        """Create a feedback record. rating must be +1 or -1."""
        if rating not in (1, -1):
            raise ValueError(f"rating must be +1 or -1, got {rating}")
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.create")
        row = FeedbackRow(
            feedback_id=str(uuid.uuid4()),
            run_id=run_id,
            thread_id=thread_id,
            user_id=resolved_user_id,
            message_id=message_id,
            rating=rating,
            comment=comment,
            created_at=datetime.now(UTC),
        )
        async with self._sf() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def get(
        self,
        feedback_id: str,
        *,
        user_id: str | None | _AutoSentinel = AUTO,
    ) -> dict | None:
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.get")
        async with self._sf() as session:
            row = await session.get(FeedbackRow, feedback_id)
            if row is None:
                return None
            if resolved_user_id is not None and row.user_id != resolved_user_id:
                return None
            return self._row_to_dict(row)

    async def list_by_run(
        self,
        thread_id: str,
        run_id: str,
        *,
        limit: int = 100,
        user_id: str | None | _AutoSentinel = AUTO,
    ) -> list[dict]:
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.list_by_run")
        stmt = select(FeedbackRow).where(FeedbackRow.thread_id == thread_id, FeedbackRow.run_id == run_id)
        if resolved_user_id is not None:
            stmt = stmt.where(FeedbackRow.user_id == resolved_user_id)
        stmt = stmt.order_by(FeedbackRow.created_at.asc()).limit(limit)
        async with self._sf() as session:
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars()]

    async def list_by_thread(
        self,
        thread_id: str,
        *,
        limit: int = 100,
        user_id: str | None | _AutoSentinel = AUTO,
    ) -> list[dict]:
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.list_by_thread")
        stmt = select(FeedbackRow).where(FeedbackRow.thread_id == thread_id)
        if resolved_user_id is not None:
            stmt = stmt.where(FeedbackRow.user_id == resolved_user_id)
        stmt = stmt.order_by(FeedbackRow.created_at.asc()).limit(limit)
        async with self._sf() as session:
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars()]

    async def delete(
        self,
        feedback_id: str,
        *,
        user_id: str | None | _AutoSentinel = AUTO,
    ) -> bool:
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.delete")
        async with self._sf() as session:
            row = await session.get(FeedbackRow, feedback_id)
            if row is None:
                return False
            if resolved_user_id is not None and row.user_id != resolved_user_id:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def upsert(
        self,
        *,
        run_id: str,
        thread_id: str,
        rating: int,
        user_id: str | None | _AutoSentinel = AUTO,
        comment: str | None = None,
    ) -> dict:
        """Create or update feedback for (thread_id, run_id, user_id). rating must be +1 or -1."""
        if rating not in (1, -1):
            raise ValueError(f"rating must be +1 or -1, got {rating}")
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.upsert")
        async with self._sf() as session:
            stmt = select(FeedbackRow).where(
                FeedbackRow.thread_id == thread_id,
                FeedbackRow.run_id == run_id,
                FeedbackRow.user_id == resolved_user_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is not None:
                row.rating = rating
                row.comment = comment
                row.created_at = datetime.now(UTC)
            else:
                row = FeedbackRow(
                    feedback_id=str(uuid.uuid4()),
                    run_id=run_id,
                    thread_id=thread_id,
                    user_id=resolved_user_id,
                    rating=rating,
                    comment=comment,
                    created_at=datetime.now(UTC),
                )
                session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._row_to_dict(row)

    async def delete_by_run(
        self,
        *,
        thread_id: str,
        run_id: str,
        user_id: str | None | _AutoSentinel = AUTO,
    ) -> bool:
        """Delete the current user's feedback for a run. Returns True if a record was deleted."""
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.delete_by_run")
        async with self._sf() as session:
            stmt = select(FeedbackRow).where(
                FeedbackRow.thread_id == thread_id,
                FeedbackRow.run_id == run_id,
                FeedbackRow.user_id == resolved_user_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_by_thread_grouped(
        self,
        thread_id: str,
        *,
        user_id: str | None | _AutoSentinel = AUTO,
    ) -> dict[str, dict]:
        """Return feedback grouped by run_id for a thread: {run_id: feedback_dict}."""
        resolved_user_id = resolve_user_id(user_id, method_name="FeedbackRepository.list_by_thread_grouped")
        stmt = select(FeedbackRow).where(FeedbackRow.thread_id == thread_id)
        if resolved_user_id is not None:
            stmt = stmt.where(FeedbackRow.user_id == resolved_user_id)
        async with self._sf() as session:
            result = await session.execute(stmt)
            return {row.run_id: self._row_to_dict(row) for row in result.scalars()}

    async def aggregate_by_run(self, thread_id: str, run_id: str) -> dict:
        """Aggregate feedback stats for a run using database-side counting."""
        stmt = select(
            func.count().label("total"),
            func.coalesce(func.sum(case((FeedbackRow.rating == 1, 1), else_=0)), 0).label("positive"),
            func.coalesce(func.sum(case((FeedbackRow.rating == -1, 1), else_=0)), 0).label("negative"),
        ).where(FeedbackRow.thread_id == thread_id, FeedbackRow.run_id == run_id)
        async with self._sf() as session:
            row = (await session.execute(stmt)).one()
            return {
                "run_id": run_id,
                "total": row.total,
                "positive": row.positive,
                "negative": row.negative,
            }

    async def summarize_for_admin(self) -> dict[str, Any]:
        """Return global and per-agent feedback summary for admin monitoring."""
        feedback_stmt = select(FeedbackRow).where(FeedbackRow.message_id.is_(None))
        run_stmt = select(RunRow)
        async with self._sf() as session:
            feedback_rows = list((await session.execute(feedback_stmt)).scalars())
            run_rows = list((await session.execute(run_stmt)).scalars())

        run_by_id = {row.run_id: row for row in run_rows}
        summary: dict[str, Any] = {
            "total": 0,
            "positive": 0,
            "negative": 0,
            "positive_rate": 0,
            "by_agent": [],
        }
        by_agent: dict[str, dict[str, Any]] = {}
        for feedback in feedback_rows:
            agent_name = self._agent_name_for_run(run_by_id.get(feedback.run_id))
            item = by_agent.setdefault(
                agent_name,
                {
                    "agent_name": agent_name,
                    "total": 0,
                    "positive": 0,
                    "negative": 0,
                    "positive_rate": 0,
                },
            )
            summary["total"] += 1
            item["total"] += 1
            if feedback.rating == 1:
                summary["positive"] += 1
                item["positive"] += 1
            elif feedback.rating == -1:
                summary["negative"] += 1
                item["negative"] += 1

        summary["positive_rate"] = summary["positive"] / summary["total"] if summary["total"] else 0
        for item in by_agent.values():
            item["positive_rate"] = item["positive"] / item["total"] if item["total"] else 0
        summary["by_agent"] = [by_agent[key] for key in sorted(by_agent)]
        return summary

    async def recent_for_admin(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent run-level feedback rows with agent names for admin monitoring."""
        feedback_stmt = select(FeedbackRow).where(FeedbackRow.message_id.is_(None)).order_by(desc(FeedbackRow.created_at)).limit(limit)
        async with self._sf() as session:
            feedback_rows = list((await session.execute(feedback_stmt)).scalars())
            run_ids = [feedback.run_id for feedback in feedback_rows]
            if not run_ids:
                return []
            run_rows = list((await session.execute(select(RunRow).where(RunRow.run_id.in_(run_ids)))).scalars())

        run_by_id = {row.run_id: row for row in run_rows}
        items: list[dict[str, Any]] = []
        for feedback in feedback_rows:
            data = self._row_to_dict(feedback)
            data.pop("message_id", None)
            self._attach_run_context(data, run_by_id.get(feedback.run_id))
            self._attach_web_feedback_context(data)
            items.append(data)
        return items

    async def get_for_admin(self, feedback_id: str) -> dict[str, Any] | None:
        """Return a feedback row with run context, bypassing user ownership checks for admins."""
        async with self._sf() as session:
            feedback = await session.get(FeedbackRow, feedback_id)
            if feedback is None or feedback.message_id is not None:
                return None
            run = await session.get(RunRow, feedback.run_id)

        data = self._row_to_dict(feedback)
        data.pop("message_id", None)
        self._attach_run_context(data, run)
        self._attach_web_feedback_context(data)
        return data

    def _attach_run_context(self, data: dict[str, Any], run: RunRow | None) -> None:
        data["agent_name"] = self._agent_name_for_run(run)
        data["run_user_id"] = run.user_id if run is not None else None
        data["first_human_message"] = run.first_human_message if run is not None else None
        data["last_ai_message"] = run.last_ai_message if run is not None else None
        data["message_count"] = run.message_count if run is not None else 0

    @staticmethod
    def _attach_web_feedback_context(data: dict[str, Any]) -> None:
        data["source_channel"] = "web"
        data["platform_user_id"] = None
        data["platform_chat_id"] = None
        data["platform_message_id"] = None
        data["platform_feedback_id"] = None

    @staticmethod
    def _agent_name_for_run(run: RunRow | None) -> str:
        if run is None:
            return "default"
        metadata = run.metadata_json if isinstance(run.metadata_json, dict) else {}
        return str(metadata.get("agent_name") or run.assistant_id or "default")
