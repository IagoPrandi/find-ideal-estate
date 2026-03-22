from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TransportPointRead(BaseModel):
    id: UUID
    journey_id: UUID
    source: str
    external_id: str | None = None
    name: str | None = None
    lat: float
    lon: float
    walk_time_sec: int
    walk_distance_m: int
    route_ids: list[str]
    modal_types: list[str]
    route_count: int
    created_at: datetime
