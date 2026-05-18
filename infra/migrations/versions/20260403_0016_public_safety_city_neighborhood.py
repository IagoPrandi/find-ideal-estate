"""Add city and neighborhood columns to public_safety_incidents."""

from alembic import op

revision = "20260403_0016"
down_revision = "20260329_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public_safety_incidents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            occurred_at TIMESTAMPTZ,
            category TEXT,
            location geometry(Point, 4326),
            city_name TEXT,
            neighborhood_name TEXT,
            occurrence_hour_known BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute("ALTER TABLE public_safety_incidents ADD COLUMN IF NOT EXISTS city_name TEXT")
    op.execute("ALTER TABLE public_safety_incidents ADD COLUMN IF NOT EXISTS neighborhood_name TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_location "
        "ON public_safety_incidents USING GIST (location)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_city_neighborhood "
        "ON public_safety_incidents (city_name, neighborhood_name, occurred_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_public_safety_incidents_occurred_at "
        "ON public_safety_incidents (occurred_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_public_safety_incidents_occurred_at")
    op.execute("DROP INDEX IF EXISTS ix_public_safety_incidents_city_neighborhood")
    op.execute("DROP INDEX IF EXISTS ix_public_safety_incidents_location")
    op.execute("ALTER TABLE public_safety_incidents DROP COLUMN IF EXISTS neighborhood_name")
    op.execute("ALTER TABLE public_safety_incidents DROP COLUMN IF EXISTS city_name")
