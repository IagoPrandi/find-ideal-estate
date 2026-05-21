"""Add user permission for immediate listings scraping.

Revision ID: 20260521_0036
Revises: 20260521_0035
Create Date: 2026-05-21 00:36:00.000000
"""

from alembic import op


revision = "20260521_0036"
down_revision = "20260521_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS can_start_immediate_scraping BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        UPDATE users
        SET can_start_immediate_scraping = true,
            updated_at = now()
        WHERE is_superuser = true
           OR lower(email) = 'iago.oliveira2478@gmail.com'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS can_start_immediate_scraping")
