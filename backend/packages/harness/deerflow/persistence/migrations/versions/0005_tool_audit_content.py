"""Ensure structured tool audit content column exists."""

import sqlalchemy as sa
from alembic import op

revision = "0005_tool_audit_content"
down_revision = "0004_agent_platform_mvp"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "tool_audit_logs" not in _table_names():
        return
    if "content_json" not in _column_names("tool_audit_logs"):
        op.add_column("tool_audit_logs", sa.Column("content_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "tool_audit_logs" not in _table_names():
        return
    if "content_json" in _column_names("tool_audit_logs"):
        op.drop_column("tool_audit_logs", "content_json")
