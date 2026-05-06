"""Add Google Identity fields to users.

Revision ID: 20260505_0033
Revises: 20260503_0032
Create Date: 2026-05-05 22:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260505_0033"
down_revision = "20260503_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_subject", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_users_google_subject", "users", ["google_subject"])


def downgrade() -> None:
    op.drop_constraint("uq_users_google_subject", "users", type_="unique")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "google_subject")
