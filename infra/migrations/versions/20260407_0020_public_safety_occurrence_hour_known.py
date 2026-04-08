"""Track whether SSP incidents have a reliable occurrence hour."""

from alembic import op

revision = "20260407_0020"
down_revision = "20260406_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public_safety_incidents "
        "ADD COLUMN IF NOT EXISTS occurrence_hour_known BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public_safety_incidents DROP COLUMN IF EXISTS occurrence_hour_known")