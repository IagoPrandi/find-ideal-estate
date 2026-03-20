from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .enums import JobState, JobType


class JobCreate(BaseModel):
    journey_id: UUID
    job_type: JobType
    current_stage: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID
    journey_id: UUID | None = None
    job_type: JobType
    state: JobState
    progress_percent: int
    current_stage: str | None = None
    cancel_requested_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    worker_id: str | None = None
    result_ref: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class JobCancelAccepted(BaseModel):
    job_id: UUID
    status: str
    cancel_requested_at: datetime


class JobEventRead(BaseModel):
    id: UUID
    job_id: UUID
    event_type: str
    stage: str | None = None
    message: str | None = None
    payload_json: dict[str, Any] | None = None
    created_at: datetime