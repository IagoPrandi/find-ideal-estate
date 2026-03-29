"""persist detailed poi points per zone"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260329_0011"
down_revision = "20260328_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("zones", sa.Column("poi_points", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("zones", "poi_points")