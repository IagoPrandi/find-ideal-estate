"""zones: add is_circle_fallback flag to track when Valhalla was unavailable"""

from alembic import op

revision = "20260326_0009"
down_revision = "20260322_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE zones
        ADD COLUMN IF NOT EXISTS is_circle_fallback BOOLEAN NOT NULL DEFAULT FALSE
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE zones DROP COLUMN IF EXISTS is_circle_fallback")
