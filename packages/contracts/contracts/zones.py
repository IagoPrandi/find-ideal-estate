from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ZoneBadgeRead(BaseModel):
    """Single badge value with percentile and tier."""
    value: float
    percentile: float
    tier: str  # "excellent", "good", "fair", "poor"


class ZoneRead(BaseModel):
    """Full zone with enrichment data and badges."""
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    journey_id: UUID
    transport_point_id: UUID
    fingerprint: str
    state: str  # "pending", "generating", "enriching", "complete", "failed"
    is_circle_fallback: bool = False
    travel_time_minutes: int | None = None
    walk_distance_meters: int | None = None
    isochrone_geom: dict[str, Any] | None = None  # GeoJSON
    green_area_m2: float | None = None
    flood_area_m2: float | None = None
    safety_incidents_count: int | None = None
    poi_counts: dict[str, int] | None = None  # {"supermarket": 5, "pharmacy": 3, ...}
    badges: dict[str, ZoneBadgeRead] | None = None  # {"green_badge", "flood_badge", ...}
    badges_provisional: bool = True
    created_at: datetime
    updated_at: datetime


class ZoneListResponse(BaseModel):
    """Response for listing zones for a journey."""
    zones: list[ZoneRead]
    total_count: int
    completed_count: int
