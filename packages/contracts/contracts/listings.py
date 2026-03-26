from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PropertyRead(BaseModel):
    id: UUID
    address_normalized: str | None = None
    location: dict[str, Any] | None = None  # GeoJSON Point
    area_m2: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking: int | None = None
    usage_type: str | None = None
    usage_type_inferred: bool = False
    fingerprint: str
    created_at: datetime


class ListingAdRead(BaseModel):
    id: UUID
    property_id: UUID
    platform: str
    platform_listing_id: str
    url: str | None = None
    advertised_usage_type: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool = True


class ListingSnapshotRead(BaseModel):
    id: UUID
    listing_ad_id: UUID
    observed_at: datetime
    price: Decimal | None = None
    condo_fee: Decimal | None = None
    iptu: Decimal | None = None
    availability_state: str | None = None


class ListingCardRead(BaseModel):
    """Flattened view for UI listing cards — property + best active ad price."""
    property_id: UUID
    address_normalized: str | None = None
    area_m2: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    parking: int | None = None
    usage_type: str | None = None

    # best price across active listing_ads
    current_best_price: Decimal | None = None
    second_best_price: Decimal | None = None
    duplication_badge: str | None = None  # e.g. "Disponível em 2 plataformas · menor: R$ X"

    # platform details
    platform: str
    platform_listing_id: str
    url: str | None = None
    observed_at: datetime | None = None


class ZoneCacheStatusRead(BaseModel):
    """Current state of a zone's listing cache."""
    id: UUID
    zone_fingerprint: str
    config_hash: str
    status: str
    platforms_completed: list[str]
    platforms_failed: list[str]
    coverage_ratio: float | None = None
    preliminary_count: int | None = None
    scraped_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class ListingsRequestResult(BaseModel):
    """Result of a listings search request — what the API returns to the client."""
    source: str  # 'cache' | 'scraping' | 'none'
    job_id: UUID | None = None
    freshness_status: str | None = None  # 'fresh' | 'stale' | 'queued_for_next_prewarm'
    upgrade_reason: str | None = None  # why fresh scraping is unavailable for FREE plan
    next_refresh_window: str | None = None  # human-readable, e.g. "03:00–05:30"
    listings: list[ListingCardRead] = []
    total_count: int = 0
    cache_age_hours: float | None = None


class SearchAddressSuggestion(BaseModel):
    """Address suggestion for Step 5 combobox."""
    label: str
    normalized: str
    location_type: str  # 'neighborhood' | 'street' | 'address' | 'landmark'
    lat: float
    lon: float


class PriceRollupRead(BaseModel):
    """One daily price-percentile snapshot for a zone (M6.1)."""
    id: UUID
    date: str            # ISO date string: YYYY-MM-DD
    zone_fingerprint: str
    search_type: str     # 'rent' | 'sale'
    median_price: Decimal | None = None
    p25_price: Decimal | None = None
    p75_price: Decimal | None = None
    sample_count: int = 0
    computed_at: datetime
    lat: float
    lon: float
