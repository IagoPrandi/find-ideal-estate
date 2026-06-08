"""Add metadata columns to neighborhood_boundaries for GeoPackage import.

Adds:
  - neighborhood_abbreviation: sg_distrito_municipal (e.g. "LIB", "PIN")
  - region_5_code: cd_regiao_05 (1=Centro, 2=Leste, 3=Norte, 4=Oeste, 5=Sul)
  - region_5_name: nm_regiao_05 (e.g. "Centro", "Norte", "Sul", "Leste", "Oeste")
  - gpkg_identifier: cd_identificador_distrito (numeric id from the PMSP GeoPackage)

Revision ID: 20260606_0043
Revises: 20260606_0042
Create Date: 2026-06-06
"""

from alembic import op

revision = "20260606_0043"
down_revision = "20260606_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE neighborhood_boundaries
        ADD COLUMN IF NOT EXISTS neighborhood_abbreviation TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE neighborhood_boundaries
        ADD COLUMN IF NOT EXISTS region_5_code INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE neighborhood_boundaries
        ADD COLUMN IF NOT EXISTS region_5_name TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE neighborhood_boundaries
        ADD COLUMN IF NOT EXISTS gpkg_identifier INTEGER
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_neighborhood_boundaries_region_5
        ON neighborhood_boundaries (city_code, region_5_code)
        WHERE region_5_code IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_neighborhood_boundaries_gpkg_id
        ON neighborhood_boundaries (gpkg_identifier)
        WHERE gpkg_identifier IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_neighborhood_boundaries_gpkg_id")
    op.execute("DROP INDEX IF EXISTS ix_neighborhood_boundaries_region_5")
    op.execute("ALTER TABLE neighborhood_boundaries DROP COLUMN IF EXISTS gpkg_identifier")
    op.execute("ALTER TABLE neighborhood_boundaries DROP COLUMN IF EXISTS region_5_name")
    op.execute("ALTER TABLE neighborhood_boundaries DROP COLUMN IF EXISTS region_5_code")
    op.execute(
        "ALTER TABLE neighborhood_boundaries DROP COLUMN IF EXISTS neighborhood_abbreviation"
    )
