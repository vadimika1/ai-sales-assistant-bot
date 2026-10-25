"""add token usage fields to ai_suggestions

Revision ID: 20260304_0003
Revises: 20260304_0002
Create Date: 2026-03-04 18:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260304_0003"
down_revision = "20260304_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_suggestions", sa.Column("request_user_id", sa.String(length=128), nullable=True))
    op.add_column(
        "ai_suggestions",
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "ai_suggestions",
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "ai_suggestions",
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index(
        "idx_ai_suggestions_request_user_id",
        "ai_suggestions",
        ["request_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_ai_suggestions_request_user_id", table_name="ai_suggestions")
    op.drop_column("ai_suggestions", "total_tokens")
    op.drop_column("ai_suggestions", "completion_tokens")
    op.drop_column("ai_suggestions", "prompt_tokens")
    op.drop_column("ai_suggestions", "request_user_id")
