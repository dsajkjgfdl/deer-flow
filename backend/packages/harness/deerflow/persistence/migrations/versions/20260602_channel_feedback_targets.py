"""Create channel feedback target mappings."""

import sqlalchemy as sa
from alembic import op

revision = "20260602_channel_feedback_targets"
down_revision = "20260529_agent_platform_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_feedback_targets",
        sa.Column("native_feedback_id", sa.String(length=256), primary_key=True),
        sa.Column("channel_name", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.String(length=128), nullable=True),
        sa.Column("platform_user_id", sa.String(length=128), nullable=True),
        sa.Column("platform_message_id", sa.String(length=128), nullable=True),
        sa.Column("thread_id", sa.String(length=64), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("feedback_row_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_channel_feedback_targets_channel_name", "channel_feedback_targets", ["channel_name"])
    op.create_index("ix_channel_feedback_targets_chat_id", "channel_feedback_targets", ["chat_id"])
    op.create_index("ix_channel_feedback_targets_platform_user_id", "channel_feedback_targets", ["platform_user_id"])
    op.create_index("ix_channel_feedback_targets_platform_message_id", "channel_feedback_targets", ["platform_message_id"])
    op.create_index("ix_channel_feedback_targets_thread_id", "channel_feedback_targets", ["thread_id"])
    op.create_index("ix_channel_feedback_targets_run_id", "channel_feedback_targets", ["run_id"])
    op.create_index("ix_channel_feedback_targets_feedback_row_id", "channel_feedback_targets", ["feedback_row_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_feedback_targets_feedback_row_id", table_name="channel_feedback_targets")
    op.drop_index("ix_channel_feedback_targets_run_id", table_name="channel_feedback_targets")
    op.drop_index("ix_channel_feedback_targets_thread_id", table_name="channel_feedback_targets")
    op.drop_index("ix_channel_feedback_targets_platform_message_id", table_name="channel_feedback_targets")
    op.drop_index("ix_channel_feedback_targets_platform_user_id", table_name="channel_feedback_targets")
    op.drop_index("ix_channel_feedback_targets_chat_id", table_name="channel_feedback_targets")
    op.drop_index("ix_channel_feedback_targets_channel_name", table_name="channel_feedback_targets")
    op.drop_table("channel_feedback_targets")
