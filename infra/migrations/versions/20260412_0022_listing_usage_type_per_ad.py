"""Store listing usage classification per advertisement instead of per property."""

from alembic import op


revision = "20260412_0022"
down_revision = "20260409_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE listing_ads
        ADD COLUMN IF NOT EXISTS usage_type TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE listing_ads
        ADD COLUMN IF NOT EXISTS usage_type_inferred BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        UPDATE listing_ads la
        SET usage_type = CASE
                WHEN LOWER(COALESCE(la.url, '')) LIKE '%conjunto-comercial%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%sala-comercial%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%imovel-comercial%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%casa-comercial%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%ponto-comercial%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%predio-comercial%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%andar-corporativo%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%consultorio%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%galpao%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%loja%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%sobreloja%'
                THEN 'commercial'
                WHEN p.bedrooms IS NULL OR p.bedrooms <= 0
                THEN 'commercial'
                WHEN LOWER(COALESCE(la.url, '')) LIKE '%apartamento%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%casa%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%sobrado%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%studio%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%kitnet%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%kitinete%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%cobertura%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%duplex%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%triplex%'
                  OR LOWER(COALESCE(la.url, '')) LIKE '%loft%'
                THEN 'residential'
                ELSE COALESCE(la.usage_type, p.usage_type, 'residential')
            END,
            usage_type_inferred = true
        FROM properties p
        WHERE p.id = la.property_id
        """
    )
    op.execute(
        """
        UPDATE properties
        SET usage_type = NULL,
            usage_type_inferred = false
        WHERE usage_type_inferred = true
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_listing_ads_usage_type
        ON listing_ads (usage_type, is_active)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_listing_ads_usage_type")
    op.execute(
        """
        ALTER TABLE listing_ads
        DROP COLUMN IF EXISTS usage_type_inferred
        """
    )
    op.execute(
        """
        ALTER TABLE listing_ads
        DROP COLUMN IF EXISTS usage_type
        """
    )