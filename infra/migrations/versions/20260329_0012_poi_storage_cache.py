"""persist canonical POI cache and snapshots"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260329_0012"
down_revision = "20260329_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE poi_places (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            provider TEXT NOT NULL,
            provider_poi_id TEXT,
            name TEXT,
            address TEXT,
            location GEOMETRY(Point, 4326),
            category TEXT NOT NULL,
            fingerprint TEXT NOT NULL UNIQUE,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_active BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute("CREATE INDEX ix_poi_places_location ON poi_places USING GIST (location)")
    op.execute("CREATE INDEX ix_poi_places_provider ON poi_places (provider, category, is_active)")

    op.execute(
        """
        CREATE TABLE poi_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            poi_place_id UUID NOT NULL REFERENCES poi_places(id) ON DELETE CASCADE,
            observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            raw_payload JSONB
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_poi_snapshots_place_id ON poi_snapshots (poi_place_id, observed_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE zone_poi_caches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            zone_fingerprint TEXT NOT NULL,
            config_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            poi_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
            point_count INT NOT NULL DEFAULT 0,
            scraped_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (zone_fingerprint, config_hash)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_zone_poi_caches_fingerprint ON zone_poi_caches (zone_fingerprint, config_hash)"
    )
    op.execute("CREATE INDEX ix_zone_poi_caches_expires_at ON zone_poi_caches (expires_at)")

    op.execute(
        """
        CREATE TABLE zone_poi_cache_items (
            zone_poi_cache_id UUID NOT NULL REFERENCES zone_poi_caches(id) ON DELETE CASCADE,
            poi_place_id UUID NOT NULL REFERENCES poi_places(id) ON DELETE CASCADE,
            position INT NOT NULL,
            PRIMARY KEY (zone_poi_cache_id, position)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_zone_poi_cache_items_place_id ON zone_poi_cache_items (poi_place_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_zone_poi_cache_items_place_id")
    op.execute("DROP TABLE IF EXISTS zone_poi_cache_items")
    op.execute("DROP INDEX IF EXISTS ix_zone_poi_caches_expires_at")
    op.execute("DROP INDEX IF EXISTS ix_zone_poi_caches_fingerprint")
    op.execute("DROP TABLE IF EXISTS zone_poi_caches")
    op.execute("DROP INDEX IF EXISTS ix_poi_snapshots_place_id")
    op.execute("DROP TABLE IF EXISTS poi_snapshots")
    op.execute("DROP INDEX IF EXISTS ix_poi_places_provider")
    op.execute("DROP INDEX IF EXISTS ix_poi_places_location")
    op.execute("DROP TABLE IF EXISTS poi_places")