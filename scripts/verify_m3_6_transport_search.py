from __future__ import annotations

# pyright: reportMissingImports=false

import asyncio
import math
import os
import sys
from pathlib import Path
from time import monotonic
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from contracts import JobType, JourneyCreate  # noqa: E402
from core.db import close_db, get_engine, init_db  # noqa: E402
from core.redis import close_redis, init_redis  # noqa: E402
from modules.jobs.service import get_job  # noqa: E402
from modules.journeys.service import create_journey  # noqa: E402
from modules.transport.points_service import list_transport_points_for_journey  # noqa: E402
from workers.handlers.transport import _transport_search_step  # noqa: E402
from workers.runtime import run_job_with_retry  # noqa: E402
from sqlalchemy import text  # noqa: E402

REF_LAT = -23.55
REF_LON = -46.63
RADIUS_METERS = 300


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


async def wait_for_job_completion(job_id, timeout_seconds: float = 30.0):
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        job = await get_job(job_id)
        if job is None:
            raise RuntimeError(f"Job {job_id} disappeared")
        if job.state in {"completed", "failed", "cancelled_partial"}:
            return job
        await asyncio.sleep(0.25)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_seconds}s")


async def create_transport_job_record(journey_id: UUID) -> UUID:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO jobs (journey_id, job_type, current_stage, result_ref)
                VALUES (:journey_id, :job_type, :current_stage, '{}'::jsonb)
                RETURNING id
                """
            ),
            {
                "journey_id": journey_id,
                "job_type": JobType.TRANSPORT_SEARCH.value,
                "current_stage": "transport_search",
            },
        )
        return result.scalar_one()


async def main() -> None:
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    init_db(database_url)
    init_redis(redis_url)

    try:
        journey = await create_journey(
            JourneyCreate(
                input_snapshot={
                    "reference_point": {
                        "lat": REF_LAT,
                        "lon": REF_LON,
                        "label": "Verificacao M3.6",
                    },
                    "travel_mode": "transit",
                    "zone_radius_meters": RADIUS_METERS,
                }
            )
        )

        job_id = await create_transport_job_record(journey.id)

        await run_job_with_retry(
            job_id,
            JobType.TRANSPORT_SEARCH,
            stage="transport_search",
            execute_step=lambda: _transport_search_step(job_id),
        )

        final_job = await wait_for_job_completion(job_id)
        if str(final_job.state) != "completed":
            raise RuntimeError(f"Transport job finished with state={final_job.state}")

        points = await list_transport_points_for_journey(journey.id)
        print(f"journey_id={journey.id}")
        print(f"job_id={job_id}")
        print(f"job_state={final_job.state}")
        print(f"radius_m={RADIUS_METERS}")
        print(f"transport_points={len(points)}")

        if not points:
            raise RuntimeError("No transport points returned")

        sample = points[:5]
        within_tolerance = 0
        for index, point in enumerate(sample, start=1):
            geometric_distance = haversine_m(REF_LAT, REF_LON, point.lat, point.lon)
            recorded_distance = float(point.walk_distance_m)
            delta_ratio = abs(recorded_distance - geometric_distance) / max(1.0, geometric_distance)
            if delta_ratio <= 0.10:
                within_tolerance += 1
            print(
                f"point_{index}: source={point.source}; walk_distance_m={point.walk_distance_m}; "
                f"haversine_m={geometric_distance:.1f}; delta_ratio={delta_ratio:.3f}; route_count={point.route_count}"
            )

        print(f"sample_within_10pct={within_tolerance}/{len(sample)}")
    finally:
        await close_db()
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
