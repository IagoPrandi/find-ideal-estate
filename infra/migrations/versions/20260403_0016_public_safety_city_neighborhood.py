"""Add city and neighborhood columns to public_safety_incidents."""

from alembic import op

revision = "20260403_0016"
down_revision = "20260329_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE public_safety_incidents ADD COLUMN IF NOT EXISTS city_name TEXT")
    op.execute("ALTER TABLE public_safety_incidents ADD COLUMN IF NOT EXISTS neighborhood_name TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_city_neighborhood "
        "ON public_safety_incidents (city_name, neighborhood_name, occurred_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_public_safety_incidents_city_neighborhood")
    op.execute("ALTER TABLE public_safety_incidents DROP COLUMN IF EXISTS neighborhood_name")
    op.execute("ALTER TABLE public_safety_incidents DROP COLUMN IF EXISTS city_name")