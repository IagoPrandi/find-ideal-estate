"""transport tile performance indexes"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260328_0010"
down_revision = "20260326_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_gtfs_shapes_location ON gtfs_shapes USING GIST (location)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_gtfs_shapes_location")