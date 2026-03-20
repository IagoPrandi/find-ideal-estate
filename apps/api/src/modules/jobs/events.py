from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from contracts import JobEventRead
from core.db import get_engine
from core.redis import get_redis
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import RowMapping

_EVENTS_SELECT = """
SELECT
    id,
    job_id,
    event_type,
    stage,
    message,
    payload_json,
    created_at
FROM job_events
WHERE job_id = :job_id
ORDER BY created_at ASC, id ASC
"""


def job_channel(job_id: UUID) -> str:
    return f"job:{job_id}"


def _row_to_event(row: RowMapping) -> JobEventRead:
    return JobEventRead(
        id=row["id"],
        job_id=row["job_id"],
        event_type=row["event_type"],
        stage=row["stage"],
        message=row["message"],
        payload_json=row["payload_json"],
        created_at=row["created_at"],
    )


def _event_to_sse_payload(event: JobEventRead) -> str:
    return event.model_dump_json()


def _format_sse_message(payload: str) -> str:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return f"data: {payload}\n\n"

    event_id = parsed.get("id")
    event_type = parsed.get("event_type")
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    if event_type:
        lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(parsed, default=str)}")
    return "\n".join(lines) + "\n\n"


def _events_after_id(events: list[JobEventRead], last_event_id: str | None) -> list[JobEventRead]:
    if not last_event_id:
        return events
    for index, event in enumerate(events):
        if str(event.id) == last_event_id:
            return events[index + 1 :]
    return events


async def list_job_events(job_id: UUID) -> list[JobEventRead]:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text(_EVENTS_SELECT), {"job_id": job_id})
        rows = result.mappings().all()
    return [_row_to_event(row) for row in rows]


async def create_job_event(
    job_id: UUID,
    event_type: str,
    *,
    stage: str | None = None,
    message: str | None = None,
    payload_json: dict[str, Any] | None = None,
) -> JobEventRead:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO job_events (job_id, event_type, stage, message, payload_json)
                VALUES (:job_id, :event_type, :stage, :message, CAST(:payload_json AS JSONB))
                RETURNING id, job_id, event_type, stage, message, payload_json, created_at
                """
            ),
            {
                "job_id": job_id,
                "event_type": event_type,
                "stage": stage,
                "message": message,
                "payload_json": json.dumps(payload_json) if payload_json is not None else None,
            },
        )
        row = result.mappings().one()
    return _row_to_event(row)


async def publish_job_event(
    job_id: UUID,
    event_type: str,
    *,
    stage: str | None = None,
    message: str | None = None,
    payload_json: dict[str, Any] | None = None,
) -> JobEventRead:
    event = await create_job_event(
        job_id,
        event_type,
        stage=stage,
        message=message,
        payload_json=payload_json,
    )
    redis = get_redis()
    await redis.publish(job_channel(job_id), _event_to_sse_payload(event))
    return event


async def job_events_stream(
    job_id: UUID,
    request: Request,
    *,
    last_event_id: str | None = None,
) -> AsyncIterator[str]:
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(job_channel(job_id))
    try:
        replay_events = await list_job_events(job_id)
        for replay_event in _events_after_id(replay_events, last_event_id):
            yield _format_sse_message(_event_to_sse_payload(replay_event))

        while True:
            if await request.is_disconnected():
                break
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            data = message.get("data")
            if data is None:
                continue
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            yield _format_sse_message(str(data))
    finally:
        await pubsub.unsubscribe(job_channel(job_id))
        await pubsub.aclose()