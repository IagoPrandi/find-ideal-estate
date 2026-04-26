"""add note column to listing and zone favorites

Revision ID: 20260422_0026
Revises: 20260422_0025
Create Date: 2026-04-22 12:00:00.000000
"""

from alembic import op


revision = "20260422_0026"
down_revision = "20260422_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_listing_favorites ADD COLUMN IF NOT EXISTS note TEXT")
    op.execute("ALTER TABLE user_zone_favorites ADD COLUMN IF NOT EXISTS note TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE user_listing_favorites DROP COLUMN IF EXISTS note")
    op.execute("ALTER TABLE user_zone_favorites DROP COLUMN IF EXISTS note")
