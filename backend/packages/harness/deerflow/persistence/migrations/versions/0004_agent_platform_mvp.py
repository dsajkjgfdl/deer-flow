"""Create enterprise agent platform tables."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_agent_platform_mvp"
down_revision: str | Sequence[str] | None = "0003_scheduled_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "agent_assignments" not in existing_tables:
        op.create_table(
            "agent_assignments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("agent_name", sa.String(length=128), nullable=False),
            sa.Column("granted_by", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "agent_name", name="uq_agent_assignments_user_agent"),
        )
        op.create_index("ix_agent_assignments_user_id", "agent_assignments", ["user_id"])
        op.create_index("ix_agent_assignments_agent_name", "agent_assignments", ["agent_name"])

    if "admin_audit_logs" not in existing_tables:
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("actor_user_id", sa.String(length=64), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("target_user_id", sa.String(length=64), nullable=True),
            sa.Column("target_agent_name", sa.String(length=128), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_admin_audit_logs_actor_user_id", "admin_audit_logs", ["actor_user_id"])
        op.create_index("ix_admin_audit_logs_target_user_id", "admin_audit_logs", ["target_user_id"])
        op.create_index("ix_admin_audit_logs_target_agent_name", "admin_audit_logs", ["target_agent_name"])

    if "tool_audit_logs" not in existing_tables:
        op.create_table(
            "tool_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("thread_id", sa.String(length=64), nullable=True),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("agent_name", sa.String(length=128), nullable=True),
            sa.Column("tool_name", sa.String(length=256), nullable=False),
            sa.Column("mcp_server_name", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("content_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_tool_audit_logs_run_id", "tool_audit_logs", ["run_id"])
        op.create_index("ix_tool_audit_logs_thread_id", "tool_audit_logs", ["thread_id"])
        op.create_index("ix_tool_audit_logs_user_id", "tool_audit_logs", ["user_id"])
        op.create_index("ix_tool_audit_logs_agent_name", "tool_audit_logs", ["agent_name"])
        op.create_index("ix_tool_audit_logs_tool_name", "tool_audit_logs", ["tool_name"])
        op.create_index("ix_tool_audit_logs_mcp_server_name", "tool_audit_logs", ["mcp_server_name"])
        op.create_index("ix_tool_audit_logs_agent_server", "tool_audit_logs", ["agent_name", "mcp_server_name"])


def downgrade() -> None:
    op.drop_index("ix_tool_audit_logs_agent_server", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_mcp_server_name", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_tool_name", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_agent_name", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_user_id", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_thread_id", table_name="tool_audit_logs")
    op.drop_index("ix_tool_audit_logs_run_id", table_name="tool_audit_logs")
    op.drop_table("tool_audit_logs")

    op.drop_index("ix_admin_audit_logs_target_agent_name", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_target_user_id", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_actor_user_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")

    op.drop_index("ix_agent_assignments_agent_name", table_name="agent_assignments")
    op.drop_index("ix_agent_assignments_user_id", table_name="agent_assignments")
    op.drop_table("agent_assignments")
