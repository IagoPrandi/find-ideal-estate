"""Add user toggle for usage restrictions.

Revision ID: 20260523_0037
Revises: 20260521_0036
Create Date: 2026-05-23 00:37:00.000000
"""

from alembic import op


revision = "20260523_0037"
down_revision = "20260521_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS usage_restrictions_disabled BOOLEAN NOT NULL DEFAULT false
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS usage_restrictions_disabled")
