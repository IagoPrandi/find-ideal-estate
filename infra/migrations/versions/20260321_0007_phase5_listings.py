"""Phase 5 – listings tables: properties, listing_ads, listing_snapshots,
zone_listing_caches, listing_search_requests, scraping_degradation_events"""

from alembic import op

revision = "20260321_0007"
down_revision = "20260321_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # properties — canonical physical unit, one per real-world property
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE properties (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            address_normalized   TEXT,
            location             GEOMETRY(Point, 4326),
            area_m2              FLOAT,
            bedrooms             INT,
            bathrooms            INT,
            parking              INT,
            usage_type           TEXT,
            usage_type_inferred  BOOLEAN NOT NULL DEFAULT false,
            geo_hash             TEXT,
            fingerprint          TEXT NOT NULL UNIQUE,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_properties_location ON properties USING GIST (location)")
    op.execute("CREATE INDEX ix_properties_geo_hash ON properties (geo_hash)")

    # ------------------------------------------------------------------
    # listing_ads — one advertisement per platform per property
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE listing_ads (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            property_id           UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
            platform              TEXT NOT NULL,
            platform_listing_id   TEXT NOT NULL,
            url                   TEXT,
            advertised_usage_type TEXT,
            first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_active             BOOLEAN NOT NULL DEFAULT true,
            UNIQUE (platform, platform_listing_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_listing_ads_property_id ON listing_ads (property_id)")
    op.execute("CREATE INDEX ix_listing_ads_platform ON listing_ads (platform, is_active)")

    # ------------------------------------------------------------------
    # listing_snapshots — price/availability captured at a point in time
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE listing_snapshots (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            listing_ad_id      UUID NOT NULL REFERENCES listing_ads(id) ON DELETE CASCADE,
            observed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            price              NUMERIC(12,2),
            condo_fee          NUMERIC(10,2),
            iptu               NUMERIC(10,2),
            availability_state TEXT,
            raw_payload        JSONB
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_listing_snapshots_listing_ad_id ON listing_snapshots (listing_ad_id, observed_at DESC)"
    )

    # ------------------------------------------------------------------
    # zone_listing_caches — per-zone cache state
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE zone_listing_caches (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            zone_fingerprint     TEXT NOT NULL,
            config_hash          TEXT NOT NULL,
            status               TEXT NOT NULL DEFAULT 'pending',
            platforms_completed  TEXT[] NOT NULL DEFAULT '{}',
            platforms_failed     TEXT[] NOT NULL DEFAULT '{}',
            coverage_ratio       FLOAT,
            preliminary_count    INT,
            scraped_at           TIMESTAMPTZ,
            expires_at           TIMESTAMPTZ,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (zone_fingerprint, config_hash)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_zone_listing_caches_fingerprint ON zone_listing_caches (zone_fingerprint, config_hash)"
    )
    op.execute(
        "CREATE INDEX ix_zone_listing_caches_expires_at ON zone_listing_caches (expires_at)"
    )

    # ------------------------------------------------------------------
    # listing_search_requests — demand ledger for prewarm scheduler
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE listing_search_requests (
            id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            journey_id                 UUID,
            user_id                    UUID,
            session_id                 TEXT,
            zone_fingerprint           TEXT NOT NULL,
            search_location_normalized TEXT NOT NULL,
            search_location_label      TEXT NOT NULL,
            search_location_type       TEXT NOT NULL,
            search_type                TEXT NOT NULL,
            usage_type                 TEXT NOT NULL,
            platforms_hash             TEXT NOT NULL,
            result_source              TEXT NOT NULL,
            requested_at               TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_listing_search_requests_requested_at "
        "ON listing_search_requests (requested_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_listing_search_requests_location_norm "
        "ON listing_search_requests (search_location_normalized, requested_at DESC)"
    )

    # ------------------------------------------------------------------
    # scraping_degradation_events — audit trail for scraper health
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE scraping_degradation_events (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            platform            TEXT NOT NULL,
            event_type          TEXT NOT NULL,
            trigger_metric      TEXT,
            metric_value        FLOAT,
            bright_data_enabled BOOLEAN NOT NULL DEFAULT false,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_scraping_degradation_events_platform "
        "ON scraping_degradation_events (platform, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scraping_degradation_events")
    op.execute("DROP TABLE IF EXISTS listing_search_requests")
    op.execute("DROP TABLE IF EXISTS zone_listing_caches")
    op.execute("DROP TABLE IF EXISTS listing_snapshots")
    op.execute("DROP TABLE IF EXISTS listing_ads")
    op.execute("DROP TABLE IF EXISTS properties")
