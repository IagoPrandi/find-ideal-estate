from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ZoneBadgeRead(BaseModel):
    """Single badge value with percentile and tier."""
    value: float
    percentile: float
    tier: str  # "excellent", "good", "fair", "poor"


class ZoneJourneyRankRead(BaseModel):
    """Compact ranking summary for a zone inside the current journey scope."""

    position: int | None = None
    total: int = 0
    percentile: float | None = None


class ZoneJourneyRankingsRead(BaseModel):
    """Per-metric journey rankings aligned with the dashboard cards."""

    safety: ZoneJourneyRankRead | None = None
    green: ZoneJourneyRankRead | None = None
    flood: ZoneJourneyRankRead | None = None
    price: ZoneJourneyRankRead | None = None


class ZonePriceSummaryRead(BaseModel):
    """Price summary used by the zone list before the listings step."""

    p50_price: float | None = None
    active_listing_count: int = 0


class ZonePOIPointRead(BaseModel):
    """Single POI item persisted for a zone."""
    kind: str = "poi"
    id: str | None = None
    name: str | None = None
    category: str | None = None
    address: str | None = None
    lat: float
    lon: float


class ZoneRead(BaseModel):
    """Full zone with enrichment data and badges."""
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    journey_id: UUID
    transport_point_id: UUID | None = None
    fingerprint: str
    state: str  # "pending", "generating", "enriching", "complete", "failed"
    is_circle_fallback: bool = False
    travel_time_minutes: int | None = None
    walk_distance_meters: int | None = None
    isochrone_geom: dict[str, Any] | None = None  # GeoJSON
    green_area_m2: float | None = None
    green_vegetation_level: str | None = None
    green_vegetation_label: str | None = None
    flood_area_m2: float | None = None
    safety_incidents_count: int | None = None
    poi_counts: dict[str, int] | None = None  # {"supermarket": 5, "pharmacy": 3, ...}
    poi_points: list[ZonePOIPointRead] | None = None
    badges: dict[str, ZoneBadgeRead] | None = None  # {"green_badge", "flood_badge", ...}
    journey_rankings: ZoneJourneyRankingsRead | None = None
    price_summary: ZonePriceSummaryRead | None = None
    badges_provisional: bool = True
    created_at: datetime
    updated_at: datetime


class ZoneListResponse(BaseModel):
    """Response for listing zones for a journey."""
    zones: list[ZoneRead]
    total_count: int
    completed_count: int


class ZoneSafetyIncidentPropertiesRead(BaseModel):
    """Properties for a single safety incident feature rendered on the map."""

    id: UUID
    zone_fingerprint: str
    crime_group: str
    crime_group_label: str
    crime_type: str | None = None
    occurred_at: datetime | None = None


class ZoneSafetyIncidentGeometryRead(BaseModel):
    """Point geometry for a safety incident."""

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class ZoneSafetyIncidentFeatureRead(BaseModel):
    """GeoJSON feature representing a single safety incident."""

    type: Literal["Feature"] = "Feature"
    geometry: ZoneSafetyIncidentGeometryRead
    properties: ZoneSafetyIncidentPropertiesRead


class ZoneSafetyIncidentCollectionRead(BaseModel):
    """GeoJSON FeatureCollection for journey zone safety incidents."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ZoneSafetyIncidentFeatureRead]


class FavoriteZoneMetricsSnapshot(BaseModel):
    """Snapshot of zone metrics captured when the user saves the zone."""

    zone_area_m2: float | None = None
    green_area_m2: float | None = None
    green_percentage: float | None = None
    flood_area_m2: float | None = None
    flood_percentage: float | None = None
    flood_risk_label: str | None = None
    safety_incidents_count: int | None = None
    homicide_density_per_km2: float | None = None
    robbery_density_per_km2: float | None = None
    theft_density_per_km2: float | None = None
    crime_density_per_km2: float | None = None
    zone_average_price: float | None = None
    zone_average_unit_price: float | None = None
    travel_time_minutes: int | None = None


class FavoriteZoneTransportPoint(BaseModel):
    """Transport seed (stop/station) used to generate a zone."""

    id: UUID | None = None
    name: str | None = None
    source: str | None = None
    external_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    walk_distance_m: int | None = None
    walk_time_sec: int | None = None
    modal_types: list[str] = []


class FavoriteZonePayload(BaseModel):
    """Full snapshot of a zone + related listings when saved by the user."""

    fingerprint: str
    journey_id: UUID
    transport_point_id: UUID | None = None
    transport_point: FavoriteZoneTransportPoint | None = None
    neighborhood_name: str | None = None
    city_name: str | None = None
    state_code: str | None = None
    isochrone_geom: dict[str, Any] | None = None
    poi_counts: dict[str, int] | None = None
    poi_points: list[ZonePOIPointRead] = []
    metrics: FavoriteZoneMetricsSnapshot
    listings: list[dict[str, Any]] = []


class FavoriteZoneCreate(BaseModel):
    journey_id: UUID
    zone_fingerprint: str
    search_type: str
    usage_type: str
    payload: FavoriteZonePayload | None = None


class FavoriteZoneRead(BaseModel):
    zone_key: str
    journey_id: UUID
    zone_fingerprint: str
    search_type: str
    usage_type: str
    saved_at: datetime
    payload: FavoriteZonePayload
    note: str | None = None


class FavoriteZoneNoteUpdate(BaseModel):
    note: str | None = None
