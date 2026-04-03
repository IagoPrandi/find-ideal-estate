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
