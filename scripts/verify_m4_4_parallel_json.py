from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from core.db import close_db, get_engine, init_db  # noqa: E402
from core.redis import close_redis, init_redis  # noqa: E402
from modules.zones.enrichment import (  # noqa: E402
    enrich_zone_flood,
    enrich_zone_green,
    enrich_zone_pois,
    enrich_zone_safety,
)
from sqlalchemy import text  # noqa: E402


@dataclass
class ExplainResult:
    label: str
    execution_ms: float


def _extract_execution_ms(payload: object) -> float:
    data = payload
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, list) and data:
        root = data[0]
    else:
        root = data
    if isinstance(root, dict):
        if "Execution Time" in root:
            return float(root["Execution Time"])
        if "Plan" in root and isinstance(root["Plan"], dict):
            total = root["Plan"].get("Actual Total Time")
            if total is not None:
                return float(total)
    raise RuntimeError(f"Could not parse EXPLAIN JSON payload: {type(payload)!r}")


async def _check_required_tables() -> list[str]:
    required = {
        "zones",
        "geosampa_vegetacao_significativa",
        "geosampa_mancha_inundacao",
        "public_safety_incidents",
    }
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(CAST(:tables AS text[]))
                """
            ),
            {"tables": sorted(required)},
        )
        present = {row[0] for row in result.fetchall()}
    return sorted(required - present)


async def _get_or_create_zone_id() -> UUID:
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(text("SELECT id FROM zones ORDER BY created_at DESC LIMIT 1"))
        ).first()
        if row is not None:
            return row[0]

        journey_id = (
            await conn.execute(
                text(
                    """
                    INSERT INTO journeys (state, input_snapshot, created_at, updated_at)
                    VALUES ('draft', '{}'::jsonb, now(), now())
                    RETURNING id
                    """
                )
            )
        ).scalar_one()

        transport_point_id = (
            await conn.execute(
                text(
                    """
                    INSERT INTO transport_points (
                        journey_id, source, external_id, name, location,
                        walk_time_sec, walk_distance_m, route_ids, modal_types, created_at
                    ) VALUES (
                        :journey_id, 'bootstrap', 'bootstrap-point', 'Bootstrap Point',
                        ST_SetSRID(ST_MakePoint(-46.6333, -23.5505), 4326),
                        60, 80, ARRAY[]::text[], ARRAY['walk']::text[], now()
                    )
                    RETURNING id
                    """
                ),
                {"journey_id": journey_id},
            )
        ).scalar_one()

        polygon = (
            "POLYGON((-46.64 -23.56,-46.62 -23.56,-46.62 -23.54,"
            "-46.64 -23.54,-46.64 -23.56))"
        )
        zone_id = (
            await conn.execute(
                text(
                    """
                    INSERT INTO zones (
                        journey_id, transport_point_id, modal, max_time_minutes,
                        radius_meters, fingerprint, isochrone_geom, state, updated_at
                    ) VALUES (
                        :journey_id, :transport_point_id, 'walking', 20,
                        800, md5(random()::text), ST_GeomFromText(:poly, 4326),
                        'enriching', now()
                    )
                    RETURNING id
                    """
                ),
                {
                    "journey_id": journey_id,
                    "transport_point_id": transport_point_id,
                    "poly": polygon,
                },
            )
        ).scalar_one()
        return zone_id


async def _run_explain_query(zone_id: UUID, label: str, sql_body: str) -> ExplainResult:
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql_body}"),
            {"zone_id": zone_id},
        )
        payload = result.scalar_one()
    return ExplainResult(label=label, execution_ms=_extract_execution_ms(payload))


async def _run_sequential(zone_id: UUID) -> float:
    start = time.perf_counter()
    await enrich_zone_green(zone_id)
    await enrich_zone_flood(zone_id)
    await enrich_zone_safety(zone_id)
    await enrich_zone_pois(zone_id)
    return (time.perf_counter() - start) * 1000.0


async def _run_parallel(zone_id: UUID) -> tuple[float, dict[str, float]]:
    start = time.perf_counter()
    await asyncio.gather(
        enrich_zone_green(zone_id),
        enrich_zone_flood(zone_id),
        enrich_zone_safety(zone_id),
        enrich_zone_pois(zone_id),
    )
    wall_ms = (time.perf_counter() - start) * 1000.0

    engine = get_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT green_area_m2, flood_area_m2, safety_incidents_count, poi_counts
                FROM zones
                WHERE id = :zone_id
                """
            ),
            {"zone_id": zone_id},
        )
        row = res.mappings().first()
        if row is None:
            raise RuntimeError("Zone not found after enrichment")

    metrics = {
        "green_area_m2": float(row["green_area_m2"] or 0.0),
        "flood_area_m2": float(row["flood_area_m2"] or 0.0),
        "safety_incidents_count": float(row["safety_incidents_count"] or 0),
        "poi_counts_present": 1.0 if row["poi_counts"] is not None else 0.0,
    }
    return wall_ms, metrics


async def main() -> int:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/find_ideal_estate",
    )
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Ensure get_settings() has required vars when POI enrichment executes in script mode.
    os.environ.setdefault("DATABASE_URL", database_url)
    os.environ.setdefault("REDIS_URL", redis_url)
    os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "m4_4_verifier_dummy_token")
    os.environ.setdefault("MAPTILER_API_KEY", "m4_4_verifier_dummy_key")
    os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
    os.environ.setdefault("OTP_URL", "http://localhost:8080")

    init_db(database_url)
    redis_ready = False
    try:
        init_redis(redis_url)
        redis_ready = True

        missing = await _check_required_tables()
        if missing:
            print("[FAIL] Missing tables:")
            for t in missing:
                print(f"  - {t}")
            return 2

        zone_id = await _get_or_create_zone_id()
        print(f"zone_id={zone_id}")

        # Prime POI cache so timed parallel run measures orchestrator parallelism,
        # not first-time external API latency.
        await enrich_zone_pois(zone_id)

        queries = [
            (
                "green",
                """
                SELECT COALESCE(
                    SUM(ST_Area(ST_Intersection(z.isochrone_geom, gv.geometry)::geography)),
                    0
                )
                FROM zones z
                LEFT JOIN geosampa_vegetacao_significativa gv
                    ON z.isochrone_geom IS NOT NULL
                    AND ST_Intersects(z.isochrone_geom, gv.geometry)
                WHERE z.id = :zone_id
                GROUP BY z.id
                """,
            ),
            (
                "flood",
                """
                SELECT COALESCE(
                    SUM(ST_Area(ST_Intersection(z.isochrone_geom, gf.geometry)::geography)),
                    0
                )
                FROM zones z
                LEFT JOIN geosampa_mancha_inundacao gf
                    ON z.isochrone_geom IS NOT NULL
                    AND ST_Intersects(z.isochrone_geom, gf.geometry)
                WHERE z.id = :zone_id
                GROUP BY z.id
                """,
            ),
            (
                "safety",
                """
                SELECT COALESCE(COUNT(psi.id)::INT, 0)
                FROM zones z
                LEFT JOIN public_safety_incidents psi
                    ON z.isochrone_geom IS NOT NULL
                    AND ST_Within(psi.location, z.isochrone_geom)
                WHERE z.id = :zone_id
                GROUP BY z.id
                """,
            ),
            (
                "pois-base",
                """
                SELECT z.fingerprint,
                       ST_X(ST_Centroid(z.isochrone_geom)) AS lon,
                       ST_Y(ST_Centroid(z.isochrone_geom)) AS lat,
                       ST_XMin(z.isochrone_geom)::DOUBLE PRECISION AS xmin,
                       ST_YMin(z.isochrone_geom)::DOUBLE PRECISION AS ymin,
                       ST_XMax(z.isochrone_geom)::DOUBLE PRECISION AS xmax,
                       ST_YMax(z.isochrone_geom)::DOUBLE PRECISION AS ymax
                FROM zones z
                WHERE z.id = :zone_id
                """,
            ),
        ]

        explain_items: list[ExplainResult] = []
        for label, sql in queries:
            explain_items.append(await _run_explain_query(zone_id, label, sql))

        explain_sum = sum(item.execution_ms for item in explain_items)
        for item in explain_items:
            print(f"explain_{item.label}_ms={item.execution_ms:.3f}")
        print(f"explain_sum_ms={explain_sum:.3f}")

        sequential_wall_ms = await _run_sequential(zone_id)
        print(f"sequential_wall_ms={sequential_wall_ms:.3f}")

        wall_ms, metrics = await _run_parallel(zone_id)
        print(f"parallel_wall_ms={wall_ms:.3f}")
        print(f"metric_green_area_m2={metrics['green_area_m2']:.3f}")
        print(f"metric_flood_area_m2={metrics['flood_area_m2']:.3f}")
        print(f"metric_safety_incidents_count={int(metrics['safety_incidents_count'])}")
        print(f"metric_poi_counts_present={int(metrics['poi_counts_present'])}")

        speedup = sequential_wall_ms / wall_ms if wall_ms > 0 else 0.0
        print(f"speedup_ratio={speedup:.2f}x")

        if wall_ms < sequential_wall_ms:
            print("[OK] M4.4 verification passed: parallel run faster than sequential")
            return 0

        print("[FAIL] M4.4 verification failed: parallel_wall_ms >= sequential_wall_ms")
        return 1
    finally:
        if redis_ready:
            await close_redis()
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
