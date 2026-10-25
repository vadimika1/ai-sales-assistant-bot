"""add bot user locales table

Revision ID: 20260304_0005
Revises: 20260304_0004
Create Date: 2026-03-04 20:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260304_0005"
down_revision = "20260304_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_user_locales",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("locale IN ('ru', 'en')", name="ck_bot_user_locales_locale"),
    )
    op.create_index("idx_bot_user_locales_updated_at", "bot_user_locales", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_bot_user_locales_updated_at", table_name="bot_user_locales")
    op.drop_table("bot_user_locales")
