"""Shared contracts package for inter-module DTOs."""

from .enums import JobState, JobType, JourneyState
from .jobs import JobCancelAccepted, JobCreate, JobEventRead, JobRead
from .journeys import JourneyCreate, JourneyRead, JourneyReferencePoint, JourneyUpdate
from .listings import (
    ListingAdRead,
    ListingCardRead,
    ListingPlatformVariantRead,
    ListingsRequestResult,
    ListingSnapshotRead,
    PriceRollupRead,
    PropertyRead,
    SearchAddressSuggestion,
    ZoneCacheStatusRead,
)
from .transport import TransportPointRead
from .zones import ZoneBadgeRead, ZoneListResponse, ZonePOIPointRead, ZoneRead

__version__ = "0.1.0"

__all__ = [
    "JobCancelAccepted",
    "JobCreate",
    "JobEventRead",
    "JobRead",
    "JobState",
    "JobType",
    "JourneyCreate",
    "JourneyRead",
    "JourneyReferencePoint",
    "JourneyState",
    "JourneyUpdate",
    "ListingAdRead",
    "ListingCardRead",
    "ListingPlatformVariantRead",
    "ListingsRequestResult",
    "ListingSnapshotRead",
    "PriceRollupRead",
    "PropertyRead",
    "SearchAddressSuggestion",
    "TransportPointRead",
    "ZoneBadgeRead",
    "ZoneCacheStatusRead",
    "ZonePOIPointRead",
    "ZoneRead",
    "ZoneListResponse",
]
