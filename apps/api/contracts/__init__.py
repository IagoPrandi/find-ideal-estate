"""Local import shim for monorepo contracts during bootstrap.

This keeps `import contracts` working from `apps/api` while re-exporting the
real shared DTOs from `packages/contracts/contracts`.
"""

# ruff: noqa: E402

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

# __file__ = apps/api/contracts/__init__.py -> repo root is parents[3].
_SHARED_CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "contracts"
if str(_SHARED_CONTRACTS_DIR) not in __path__:
    __path__.append(str(_SHARED_CONTRACTS_DIR))

from .auth import AuthLoginRequest, AuthRegisterRequest, AuthStatusRead, AuthUserRead
from .dashboard import (
    DashboardDistributionBucketRead,
    DashboardPriceHistoryPointRead,
    DashboardRankRead,
    DashboardSafetyHourBucketRead,
    ZoneFavoriteAnalyticsRead,
    ZoneFavoriteMetricsRead,
    ZoneDashboardAnalyticsRead,
    ZoneDashboardContextRead,
    ZoneDashboardEnvironmentRead,
    ZoneDashboardPriceRead,
    ZoneDashboardSafetyRead,
)
from .enums import JobState, JobType, JourneyState
from .jobs import JobCancelAccepted, JobCreate, JobEventRead, JobRead
from .journeys import JourneyCreate, JourneyRead, JourneyReferencePoint, JourneyUpdate
from .listings import (
    FavoriteListingCreate,
    FavoriteListingRead,
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
from .zones import (
    ZoneBadgeRead,
    ZoneListResponse,
    ZonePOIPointRead,
    ZoneRead,
    ZoneSafetyIncidentCollectionRead,
    ZoneSafetyIncidentFeatureRead,
    ZoneSafetyIncidentGeometryRead,
    ZoneSafetyIncidentPropertiesRead,
)

__version__ = "0.1.0"

__all__ = [
    "AuthLoginRequest",
    "AuthRegisterRequest",
    "AuthStatusRead",
    "AuthUserRead",
    "FavoriteListingCreate",
    "FavoriteListingRead",
    "DashboardDistributionBucketRead",
    "DashboardPriceHistoryPointRead",
    "DashboardRankRead",
    "DashboardSafetyHourBucketRead",
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
    "ZoneDashboardAnalyticsRead",
    "ZoneDashboardContextRead",
    "ZoneDashboardEnvironmentRead",
    "ZoneDashboardPriceRead",
    "ZoneDashboardSafetyRead",
    "ZoneFavoriteAnalyticsRead",
    "ZoneFavoriteMetricsRead",
    "ZoneBadgeRead",
    "ZoneCacheStatusRead",
    "ZonePOIPointRead",
    "ZoneRead",
    "ZoneListResponse",
    "ZoneSafetyIncidentCollectionRead",
    "ZoneSafetyIncidentFeatureRead",
    "ZoneSafetyIncidentGeometryRead",
    "ZoneSafetyIncidentPropertiesRead",
]
