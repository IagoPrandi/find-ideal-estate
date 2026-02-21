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


class ZoneDetailResponse(BaseModel):
    zone_uid: str
    streets_path: str
    pois_path: str
    transport_path: str


class ListingsScrapeResponse(BaseModel):
    zone_uid: str
    listing_files: List[str]


class FinalizeResponse(BaseModel):
    listings_final_json: str
    listings_final_csv: str
    listings_final_geojson: str
    zones_final_geojson: str
