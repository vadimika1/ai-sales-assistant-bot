"""add crm sync log table

Revision ID: 20260304_0002
Revises: 20260304_0001
Create Date: 2026-03-04 16:55:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260304_0002"
down_revision = "20260304_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_sync_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("suggestion_id", sa.BigInteger(), nullable=False),
        sa.Column("sync_status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("sync_status IN ('success', 'failed')", name="ck_crm_sync_log_status"),
        sa.CheckConstraint("attempts >= 1", name="ck_crm_sync_log_attempts_positive"),
        sa.ForeignKeyConstraint(["suggestion_id"], ["ai_suggestions.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_crm_sync_log_suggestion_id", "crm_sync_log", ["suggestion_id"], unique=False)
    op.create_index("idx_crm_sync_log_created_at", "crm_sync_log", ["created_at"], unique=False)
    op.create_index("idx_crm_sync_log_status", "crm_sync_log", ["sync_status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_crm_sync_log_status", table_name="crm_sync_log")
    op.drop_index("idx_crm_sync_log_created_at", table_name="crm_sync_log")
    op.drop_index("idx_crm_sync_log_suggestion_id", table_name="crm_sync_log")
    op.drop_table("crm_sync_log")
