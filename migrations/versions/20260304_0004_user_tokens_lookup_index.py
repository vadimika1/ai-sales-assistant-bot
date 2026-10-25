"""optimize user token usage lookup index

Revision ID: 20260304_0004
Revises: 20260304_0003
Create Date: 2026-03-04 19:05:00
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260304_0004"
down_revision = "20260304_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_ai_suggestions_user_created_at",
        "ai_suggestions",
        ["request_user_id", "created_at"],
        unique=False,
    )
    op.drop_index("idx_ai_suggestions_request_user_id", table_name="ai_suggestions")


def downgrade() -> None:
    op.create_index(
        "idx_ai_suggestions_request_user_id",
        "ai_suggestions",
        ["request_user_id"],
        unique=False,
    )
    op.drop_index("idx_ai_suggestions_user_created_at", table_name="ai_suggestions")
