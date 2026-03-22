from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from contracts import JobType  # noqa: E402
from core.db import close_db, get_engine, init_db  # noqa: E402
from modules.zones.service import ZoneService, compute_zone_fingerprint  # noqa: E402
from sqlalchemy import text  # noqa: E402


class _FakeValhallaAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def isochrone(self, origin, costing, contours_minutes):
        self.calls += 1
        lat = float(origin.lat)
        lon = float(origin.lon)
        delta = 0.005
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [lon - delta, lat - delta],
                                [lon + delta, lat - delta],
                                [lon + delta, lat + delta],
                                [lon - delta, lat + delta],
                                [lon - delta, lat - delta],
                            ]
                        ],
                    },
                    "properties": {
                        "costing": costing,
                        "contours_minutes": contours_minutes,
                    },
                }
            ],
        }


async def _insert_journey_bundle(
    *,
    journey_id: UUID,
    transport_point_id: UUID,
    job_id: UUID,
    lat: float,
    lon: float,
    input_snapshot: dict,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO journeys (
                    id,
                    state,
                    input_snapshot,
                    created_at,
                    updated_at
                )
                VALUES (
                    :journey_id,
                    'draft',
                    CAST(:input_snapshot AS JSONB),
                    now(),
                    now()
                )
                """
            ),
            {
                "journey_id": journey_id,
                "input_snapshot": __import__("json").dumps(input_snapshot),
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO transport_points (
                    id,
                    journey_id,
                    source,
                    external_id,
                    name,
                    location,
                    walk_time_sec,
                    walk_distance_m,
                    route_ids,
                    modal_types,
                    created_at
                ) VALUES (
                    :transport_point_id,
                    :journey_id,
                    'gtfs_stop',
                    :external_id,
                    'M4.2 verification point',
                    ST_SetSRID(
                        ST_MakePoint(
                            CAST(:lon AS DOUBLE PRECISION),
                            CAST(:lat AS DOUBLE PRECISION)
                        ),
                        4326
                    ),
                    120,
                    150,
                    ARRAY['m4_2_test_route']::text[],
                    ARRAY['bus']::text[],
                    now()
                )
                """
            ),
            {
                "transport_point_id": transport_point_id,
                "journey_id": journey_id,
                "external_id": f"m4_2_{transport_point_id}",
                "lat": lat,
                "lon": lon,
            },
        )
        await conn.execute(
            text(
                """
                UPDATE journeys
                SET selected_transport_point_id = :transport_point_id,
                    updated_at = now()
                WHERE id = :journey_id
                """
            ),
            {
                "journey_id": journey_id,
                "transport_point_id": transport_point_id,
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO jobs (
                    id,
                    journey_id,
                    job_type,
                    state,
                    current_stage,
                    result_ref,
                    created_at
                )
                VALUES (
                    :job_id,
                    :journey_id,
                    :job_type,
                    'pending',
                    'zone_generation',
                    '{}'::jsonb,
                    now()
                )
                """
            ),
            {
                "job_id": job_id,
                "journey_id": journey_id,
                "job_type": JobType.ZONE_GENERATION.value,
            },
        )


async def _cleanup_entities(
    *,
    journey_ids: list[UUID],
    transport_point_ids: list[UUID],
    job_ids: list[UUID],
    fingerprint: str,
) -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM zones WHERE fingerprint = :fingerprint"),
            {"fingerprint": fingerprint},
        )
        await conn.execute(
            text(
                """
                UPDATE journeys
                SET selected_transport_point_id = NULL,
                    selected_zone_id = NULL,
                    updated_at = now()
                WHERE id = ANY(CAST(:journey_ids AS UUID[]))
                """
            ),
            {"journey_ids": [str(item) for item in journey_ids]},
        )
        await conn.execute(
            text("DELETE FROM jobs WHERE id = ANY(CAST(:job_ids AS UUID[]))"),
            {"job_ids": [str(item) for item in job_ids]},
        )
        await conn.execute(
            text(
                "DELETE FROM transport_points WHERE id = ANY(CAST(:transport_point_ids AS UUID[]))"
            ),
            {"transport_point_ids": [str(item) for item in transport_point_ids]},
        )
        await conn.execute(
            text("DELETE FROM journeys WHERE id = ANY(CAST(:journey_ids AS UUID[]))"),
            {"journey_ids": [str(item) for item in journey_ids]},
        )


async def _count_zones_by_fingerprint(fingerprint: str) -> int:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT count(*) FROM zones WHERE fingerprint = :fingerprint"),
            {"fingerprint": fingerprint},
        )
        return int(result.scalar_one())


async def main() -> int:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    init_db(database_url)

    lat = -23.54123
    lon = -46.61234
    input_snapshot = {
        "travel_mode": "walking",
        "max_travel_time_min": 37,
        "zone_radius_meters": 1234,
        "dataset_version_id": None,
    }
    fingerprint = compute_zone_fingerprint(lat, lon, "walking", 37, 1234, None)

    journey_ids = [uuid4(), uuid4()]
    transport_point_ids = [uuid4(), uuid4()]
    job_ids = [uuid4(), uuid4()]

    fake_valhalla = _FakeValhallaAdapter()
    zone_service = ZoneService(valhalla_adapter=fake_valhalla, otp_adapter=object())

    await _cleanup_entities(
        journey_ids=journey_ids,
        transport_point_ids=transport_point_ids,
        job_ids=job_ids,
        fingerprint=fingerprint,
    )

    try:
        for journey_id, transport_point_id, job_id in zip(
            journey_ids,
            transport_point_ids,
            job_ids,
            strict=False,
        ):
            await _insert_journey_bundle(
                journey_id=journey_id,
                transport_point_id=transport_point_id,
                job_id=job_id,
                lat=lat,
                lon=lon,
                input_snapshot=input_snapshot,
            )

        first = await zone_service.ensure_zone_for_job(job_ids[0])
        second = await zone_service.ensure_zone_for_job(job_ids[1])
        zone_count = await _count_zones_by_fingerprint(fingerprint)

        print(f"fingerprint={fingerprint}")
        print(f"first_zone_id={first.zone_id}; reused={first.reused}")
        print(f"second_zone_id={second.zone_id}; reused={second.reused}")
        print(f"zones_with_fingerprint={zone_count}")
        print(f"valhalla_calls={fake_valhalla.calls}")

        if zone_count != 1:
            raise RuntimeError(
                f"PRD M4.2 verification failed: expected 1 zone for fingerprint, got {zone_count}"
            )
        if first.reused:
            raise RuntimeError(
                "PRD M4.2 verification failed: "
                "first generation unexpectedly reused an existing zone"
            )
        if not second.reused:
            raise RuntimeError(
                "PRD M4.2 verification failed: second generation did not reuse existing zone"
            )
        if fake_valhalla.calls != 1:
            raise RuntimeError(
                "PRD M4.2 verification failed: expected exactly 1 Valhalla call, "
                f"got {fake_valhalla.calls}"
            )

        print("[OK] M4.2 verification passed")
        return 0
    finally:
        await _cleanup_entities(
            journey_ids=journey_ids,
            transport_point_ids=transport_point_ids,
            job_ids=job_ids,
            fingerprint=fingerprint,
        )
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
