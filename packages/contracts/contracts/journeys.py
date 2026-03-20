from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .enums import JourneyState


class JourneyReferencePoint(BaseModel):
    lat: float
    lon: float


class JourneyCreate(BaseModel):
    input_snapshot: dict[str, Any] | None = None
    secondary_reference_label: str | None = None
    secondary_reference_point: JourneyReferencePoint | None = None


class JourneyUpdate(BaseModel):
    state: JourneyState | None = None
    input_snapshot: dict[str, Any] | None = None
    selected_transport_point_id: UUID | None = None
    selected_zone_id: UUID | None = None
    selected_property_id: UUID | None = None
    last_completed_step: int | None = None
    secondary_reference_label: str | None = None
    secondary_reference_point: JourneyReferencePoint | None = None


class JourneyRead(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    user_id: UUID | None = None
    anonymous_session_id: str | None = None
    state: JourneyState
    input_snapshot: dict[str, Any] | None = None
    selected_transport_point_id: UUID | None = None
    selected_zone_id: UUID | None = None
    selected_property_id: UUID | None = None
    last_completed_step: int | None = None
    secondary_reference_label: str | None = None
    secondary_reference_point: JourneyReferencePoint | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None