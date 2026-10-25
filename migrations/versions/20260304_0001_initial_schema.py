"""initial schema for ai sales assistant

Revision ID: 20260304_0001
Revises:
Create Date: 2026-03-04 15:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260304_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("manager_message", sa.Text(), nullable=False),
        sa.Column("suggested_reply", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("lead_stage", sa.Text(), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_ai_suggestions_confidence_range"),
    )
    op.create_index("idx_ai_suggestions_created_at", "ai_suggestions", ["created_at"], unique=False)
    op.create_index("idx_ai_suggestions_intent", "ai_suggestions", ["intent"], unique=False)
    op.create_index("idx_ai_suggestions_lead_stage", "ai_suggestions", ["lead_stage"], unique=False)

    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("suggestion_id", sa.BigInteger(), nullable=False),
        sa.Column("manager_action", sa.Text(), nullable=False),
        sa.Column("edited_reply", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "manager_action IN ('accepted', 'edited', 'rejected')",
            name="ck_ai_feedback_manager_action",
        ),
        sa.ForeignKeyConstraint(["suggestion_id"], ["ai_suggestions.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_ai_feedback_suggestion_id", "ai_feedback", ["suggestion_id"], unique=False)
    op.create_index("idx_ai_feedback_created_at", "ai_feedback", ["created_at"], unique=False)

    op.create_table(
        "bot_pending_edits",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("suggestion_id", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["suggestion_id"], ["ai_suggestions.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_bot_pending_edits_updated_at", "bot_pending_edits", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_bot_pending_edits_updated_at", table_name="bot_pending_edits")
    op.drop_table("bot_pending_edits")

    op.drop_index("idx_ai_feedback_created_at", table_name="ai_feedback")
    op.drop_index("idx_ai_feedback_suggestion_id", table_name="ai_feedback")
    op.drop_table("ai_feedback")

    op.drop_index("idx_ai_suggestions_lead_stage", table_name="ai_suggestions")
    op.drop_index("idx_ai_suggestions_intent", table_name="ai_suggestions")
    op.drop_index("idx_ai_suggestions_created_at", table_name="ai_suggestions")
    op.drop_table("ai_suggestions")
