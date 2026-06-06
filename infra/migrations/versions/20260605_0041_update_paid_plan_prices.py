"""Update paid plan prices

Revision ID: 20260605_0041
Revises: 20260525_0040
Create Date: 2026-06-05 21:00:00.000000
"""

from alembic import op

revision = "20260605_0041"
down_revision = "20260525_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE plans
        SET price_brl = CASE slug
            WHEN 'basico' THEN 12.99
            WHEN 'pro' THEN 30.99
            WHEN 'pro_max' THEN 149.90
            ELSE price_brl
        END
        WHERE slug IN ('basico', 'pro', 'pro_max')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE plans
        SET price_brl = CASE slug
            WHEN 'basico' THEN 21.99
            WHEN 'pro' THEN 90.99
            WHEN 'pro_max' THEN 312.99
            ELSE price_brl
        END
        WHERE slug IN ('basico', 'pro', 'pro_max')
    """)
