from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReferencePoint(BaseModel):
    name: Optional[str] = None
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class RunCreateRequest(BaseModel):
    reference_points: List[ReferencePoint] = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


class RunStatus(BaseModel):
    state: str
    stage: str
    stages: List[Dict[str, Any]]
    created_at: str
    updated_at: str


class RunCreateResponse(BaseModel):
    run_id: str
    status: RunStatus


class RunStatusResponse(BaseModel):
    run_id: str
    status: RunStatus


class ZoneSelectionRequest(BaseModel):
    zone_uids: List[str] = Field(..., min_length=1)


class SimpleMessageResponse(BaseModel):
    message: str


class ZonePoint(BaseModel):
    kind: str
    id: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    lat: float
    lon: float


class ZoneDetailResponse(BaseModel):
    zone_uid: str
    zone_name: str
    green_area_ratio: float
    flood_area_ratio: float
    poi_count_by_category: Dict[str, int]
    bus_lines_count: int
    train_lines_count: int
    bus_stop_count: int
    train_station_count: int
    lines_used_for_generation: List[Dict[str, Any]]
    reference_transport_point: Optional[Dict[str, Any]] = None
    seed_transport_point: Optional[ZonePoint] = None
    downstream_transport_point: Optional[ZonePoint] = None
    transport_points: List[ZonePoint] = Field(default_factory=list)
    poi_points: List[ZonePoint] = Field(default_factory=list)
    streets_count: int
    has_street_data: bool
    has_poi_data: bool
    has_transport_data: bool


class ListingsScrapeRequest(BaseModel):
    street_filter: Optional[str] = None


class ListingsScrapeResponse(BaseModel):
    zone_uid: str
    listings_count: int


class FinalizeResponse(BaseModel):
    listings_final_json: str
    listings_final_csv: str
    listings_final_geojson: str
    zones_final_geojson: str
