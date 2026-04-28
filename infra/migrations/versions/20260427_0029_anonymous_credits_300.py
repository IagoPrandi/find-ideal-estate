"""Fix anonymous plan monthly_credits to 300

Revision ID: 20260427_0029
Revises: 20260426_0028
Create Date: 2026-04-27 00:00:00.000000
"""

from alembic import op


revision = "20260427_0029"
down_revision = "20260426_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE plans
        SET monthly_credits = 300
        WHERE slug = 'anonymous'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE plans
        SET monthly_credits = 350
        WHERE slug = 'anonymous'
    """)
