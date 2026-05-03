"""Enable zone radius customization for every plan with 50-500m range.

Revision ID: 20260503_0032
Revises: 20260427_0031
Create Date: 2026-05-03 16:20:00.000000
"""

from alembic import op


revision = "20260503_0032"
down_revision = "20260427_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE plan_entitlements pe
        SET can_customize_radius = true
        FROM plans p
        WHERE p.id = pe.plan_id
          AND p.slug IN ('anonymous', 'free', 'basico', 'pro', 'pro_max')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE plan_entitlements pe
        SET can_customize_radius = false
        FROM plans p
        WHERE p.id = pe.plan_id
          AND p.slug IN ('anonymous', 'free')
    """)
