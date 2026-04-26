"""Add proprietario role to users

Revision ID: 20260426_0028
Revises: 20260426_0027
Create Date: 2026-04-26 13:00:00.000000
"""

from alembic import op


revision = "20260426_0028"
down_revision = "20260426_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user'
    """)
    op.execute("""
        UPDATE users SET role = 'proprietario' WHERE lower(email) = 'iago.oliveira2478@gmail.com'
    """)


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'user' WHERE role = 'proprietario'")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS role")
