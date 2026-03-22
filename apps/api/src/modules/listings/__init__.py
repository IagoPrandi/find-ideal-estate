"""Listings domain module."""

from .cache import (
    cache_age_hours,
    cache_is_usable,
    compute_config_hash,
    create_cache_record,
    find_partial_hit_from_overlapping_zone,
    get_cache_record,
    transition_cache_status,
)
from .dedup import (
    compute_property_fingerprint,
    fetch_listing_cards_for_zone,
    upsert_property_and_ad,
)
from .models import (
    ALL_PLATFORMS,
    FREE_PLATFORMS,
    PRO_PLATFORMS,
    InvalidStateTransition,
    PreliminaryResultThresholds,
    ZoneCacheStatus,
)
from .scraping_lock import scraping_lock

__all__ = [
    "ALL_PLATFORMS",
    "FREE_PLATFORMS",
    "PRO_PLATFORMS",
    "InvalidStateTransition",
    "PreliminaryResultThresholds",
    "ZoneCacheStatus",
    "cache_age_hours",
    "cache_is_usable",
    "compute_config_hash",
    "compute_property_fingerprint",
    "create_cache_record",
    "fetch_listing_cards_for_zone",
    "find_partial_hit_from_overlapping_zone",
    "get_cache_record",
    "scraping_lock",
    "transition_cache_status",
    "upsert_property_and_ad",
]
