"""Add global usage restrictions setting.

Revision ID: 20260523_0038
Revises: 20260523_0037
Create Date: 2026-05-23 00:38:00.000000
"""

from alembic import op


revision = "20260523_0038"
down_revision = "20260523_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('usage_restrictions_disabled_globally', 'false'::jsonb, now())
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM app_settings WHERE key = 'usage_restrictions_disabled_globally'")
