from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class AgentAssignmentRow(Base):
    __tablename__ = "agent_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    granted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("user_id", "agent_name", name="uq_agent_assignments_user_agent"),)


class AdminAuditLogRow(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ToolAuditLogRow(Base):
    __tablename__ = "tool_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    mcp_server_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (Index("ix_tool_audit_logs_agent_server", "agent_name", "mcp_server_name"),)
