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

from .auth import AuthGoogleLoginRequest, AuthLoginRequest, AuthRegisterRequest, AuthStatusRead, AuthUserRead
from .admin import (
    AdminRunNowResponse,
    AdminScrapingBatchRead,
    AdminScrapingBatchesRead,
    AdminScrapingOverviewRead,
    AdminScrapingQueueAddRequest,
    AdminScrapingQueueItemRead,
    AdminScrapingQueueMutationRead,
    AdminScrapingQueueRead,
    AdminUserRead,
    AdminUserRoleUpdateRequest,
    AdminUsersRead,
)
from .billing import (
    AccountCreditsRead,
    AccountPlanRead,
    PaymentStatusRead,
    PixCheckoutRequest,
    PixCheckoutResponse,
    PixConfirmRequest,
    PlanEntitlementsRead,
    PlanRead,
    ResolvedEntitlements,
)
from .dashboard import (
    DashboardDistributionBucketRead,
    DashboardPriceHistoryPointRead,
    DashboardRankingItemRead,
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
    FavoriteNoteUpdate,
    ListingAdRead,
    ListingCardRead,
    ListingPlatformVariantRead,
    ListingsRequestResult,
    ListingSnapshotRead,
    ManualFavoriteCreate,
    PriceRollupRead,
    PropertyRead,
    SearchAddressSuggestion,
    ZoneCacheStatusRead,
)
from .transport import TransportPointRead
from .zones import (
    FavoriteZoneCreate,
    FavoriteZoneMetricsSnapshot,
    FavoriteZoneNoteUpdate,
    FavoriteZonePayload,
    FavoriteZoneRead,
    FavoriteZoneTransportPoint,
    ZoneBadgeRead,
    ZoneJourneyRankRead,
    ZoneJourneyRankingsRead,
    ZoneListResponse,
    ZonePOIPointRead,
    ZonePriceSummaryRead,
    ZoneRead,
    ZoneSafetyIncidentCollectionRead,
    ZoneSafetyIncidentFeatureRead,
    ZoneSafetyIncidentGeometryRead,
    ZoneSafetyIncidentPropertiesRead,
)

__version__ = "0.1.0"

__all__ = [
    "AccountCreditsRead",
    "AccountPlanRead",
    "AdminRunNowResponse",
    "AdminScrapingBatchRead",
    "AdminScrapingBatchesRead",
    "AdminScrapingOverviewRead",
    "AdminScrapingQueueAddRequest",
    "AdminScrapingQueueItemRead",
    "AdminScrapingQueueMutationRead",
    "AdminScrapingQueueRead",
    "AdminUserRead",
    "AdminUserRoleUpdateRequest",
    "AdminUsersRead",
    "AuthLoginRequest",
    "AuthGoogleLoginRequest",
    "AuthRegisterRequest",
    "AuthStatusRead",
    "AuthUserRead",
    "PaymentStatusRead",
    "PixCheckoutRequest",
    "PixCheckoutResponse",
    "PixConfirmRequest",
    "PlanEntitlementsRead",
    "PlanRead",
    "ResolvedEntitlements",
    "FavoriteListingCreate",
    "FavoriteListingRead",
    "FavoriteNoteUpdate",
    "FavoriteZoneCreate",
    "FavoriteZoneNoteUpdate",
    "FavoriteZoneMetricsSnapshot",
    "FavoriteZonePayload",
    "FavoriteZoneRead",
    "FavoriteZoneTransportPoint",
    "DashboardDistributionBucketRead",
    "DashboardPriceHistoryPointRead",
    "DashboardRankingItemRead",
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
    "ManualFavoriteCreate",
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
    "ZoneJourneyRankRead",
    "ZoneJourneyRankingsRead",
    "ZonePOIPointRead",
    "ZonePriceSummaryRead",
    "ZoneRead",
    "ZoneListResponse",
    "ZoneSafetyIncidentCollectionRead",
    "ZoneSafetyIncidentFeatureRead",
    "ZoneSafetyIncidentGeometryRead",
    "ZoneSafetyIncidentPropertiesRead",
]
