import math
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from src.api.routes.transport import (  # noqa: E402
    _TRANSPORT_LINES_TILE_ROWS_SQL,
    _TRANSPORT_STOPS_TILE_ROWS_SQL,
    get_transport_stop_details,
)
from core.db import close_db, get_engine, init_db  # noqa: E402


SAMPLE_STOP_ID = "S_TILE_META"
SAMPLE_SHAPE_ID = "SH_TILE_META"
SAMPLE_ROUTE_IDS = ("R_TILE_META_1", "R_TILE_META_2")
SAMPLE_TRIP_IDS = ("T_TILE_META_1", "T_TILE_META_2")
SAMPLE_LAT = 0.01
SAMPLE_LON = 0.01
SAMPLE_GEOSAMPA_STOP_NAME = "GeoSampa Tile Stop"


def _lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    scale = 2**zoom
    x = int((lon + 180.0) / 360.0 * scale)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale)
    return x, y


async def _ensure_gtfs_schema() -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
      exists = await conn.execute(text("SELECT to_regclass('public.gtfs_stops') IS NOT NULL"))
      return bool(exists.scalar())


async def _ensure_geosampa_schema() -> bool:
    engine = get_engine()
    async with engine.connect() as conn:
        exists = await conn.execute(text("SELECT to_regclass('public.geosampa_bus_stops') IS NOT NULL"))
        return bool(exists.scalar())


async def _cleanup_sample_rows() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM geosampa_bus_stops WHERE nm_ponto_onibus = :stop_name"), {"stop_name": SAMPLE_GEOSAMPA_STOP_NAME})
        await conn.execute(text("DELETE FROM gtfs_stop_times WHERE trip_id = ANY(:trip_ids)"), {"trip_ids": list(SAMPLE_TRIP_IDS)})
        await conn.execute(text("DELETE FROM gtfs_trips WHERE trip_id = ANY(:trip_ids)"), {"trip_ids": list(SAMPLE_TRIP_IDS)})
        await conn.execute(text("DELETE FROM gtfs_routes WHERE route_id = ANY(:route_ids)"), {"route_ids": list(SAMPLE_ROUTE_IDS)})
        await conn.execute(text("DELETE FROM gtfs_shapes WHERE shape_id = :shape_id"), {"shape_id": SAMPLE_SHAPE_ID})
        await conn.execute(text("DELETE FROM gtfs_stops WHERE stop_id = :stop_id"), {"stop_id": SAMPLE_STOP_ID})


async def _insert_sample_gtfs_rows() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO geosampa_bus_stops (nm_ponto_onibus, geometry)
                VALUES (:stop_name, ST_SetSRID(ST_MakePoint(:stop_lon, :stop_lat), 4326))
                """
            ),
            {
                "stop_name": SAMPLE_GEOSAMPA_STOP_NAME,
                "stop_lon": SAMPLE_LON,
                "stop_lat": SAMPLE_LAT,
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO gtfs_stops (stop_id, stop_name, stop_lat, stop_lon, location)
                VALUES (:stop_id, :stop_name, :stop_lat, :stop_lon, ST_SetSRID(ST_MakePoint(:stop_lon, :stop_lat), 4326))
                """
            ),
            {
                "stop_id": SAMPLE_STOP_ID,
                "stop_name": "Tile Stop",
                "stop_lat": SAMPLE_LAT,
                "stop_lon": SAMPLE_LON,
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO gtfs_routes (route_id, route_short_name, route_long_name, route_type)
                VALUES
                    (:route_id_1, '175T-10', 'Linha 175T-10', 3),
                    (:route_id_2, '875A-10', 'Linha 875A-10', 3)
                """
            ),
            {
                "route_id_1": SAMPLE_ROUTE_IDS[0],
                "route_id_2": SAMPLE_ROUTE_IDS[1],
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO gtfs_trips (trip_id, route_id, shape_id)
                VALUES
                    (:trip_id_1, :route_id_1, :shape_id),
                    (:trip_id_2, :route_id_2, :shape_id)
                """
            ),
            {
                "trip_id_1": SAMPLE_TRIP_IDS[0],
                "trip_id_2": SAMPLE_TRIP_IDS[1],
                "route_id_1": SAMPLE_ROUTE_IDS[0],
                "route_id_2": SAMPLE_ROUTE_IDS[1],
                "shape_id": SAMPLE_SHAPE_ID,
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO gtfs_stop_times (trip_id, stop_id, arrival_time, departure_time, stop_sequence)
                VALUES
                    (:trip_id_1, :stop_id, '08:00:00', '08:00:00', 1),
                    (:trip_id_2, :stop_id, '08:05:00', '08:05:00', 1)
                """
            ),
            {
                "trip_id_1": SAMPLE_TRIP_IDS[0],
                "trip_id_2": SAMPLE_TRIP_IDS[1],
                "stop_id": SAMPLE_STOP_ID,
            },
        )
        await conn.execute(
            text(
                """
                INSERT INTO gtfs_shapes (shape_id, shape_pt_sequence, location)
                VALUES
                    (:shape_id, 1, ST_SetSRID(ST_MakePoint(:lon_1, :lat_1), 4326)),
                    (:shape_id, 2, ST_SetSRID(ST_MakePoint(:lon_2, :lat_2), 4326))
                """
            ),
            {
                "shape_id": SAMPLE_SHAPE_ID,
                "lon_1": SAMPLE_LON,
                "lat_1": SAMPLE_LAT,
                "lon_2": SAMPLE_LON + 0.005,
                "lat_2": SAMPLE_LAT + 0.005,
            },
        )


@pytest.mark.anyio
async def test_transport_tile_rows_keep_stop_plotting_lightweight() -> None:
    init_db(os.environ["DATABASE_URL"])
    try:
        if not await _ensure_gtfs_schema() or not await _ensure_geosampa_schema():
            pytest.skip("Phase 3 transport schemas not migrated. Run alembic upgrade head.")

        await _cleanup_sample_rows()
        await _insert_sample_gtfs_rows()

        zoom = 14
        x, y = _lonlat_to_tile(SAMPLE_LON, SAMPLE_LAT, zoom)
        params = {"z": zoom, "x": x, "y": y}

        engine = get_engine()
        async with engine.connect() as conn:
            stop_rows = (await conn.execute(text(_TRANSPORT_STOPS_TILE_ROWS_SQL), params)).mappings().all()
            line_rows = (await conn.execute(text(_TRANSPORT_LINES_TILE_ROWS_SQL), params)).mappings().all()

        stop_row = next(row for row in stop_rows if row["id"] == SAMPLE_STOP_ID)
        geosampa_stop_row = next(
            row for row in stop_rows if row["source_kind"] == "geosampa_bus_stop" and row["name"] == SAMPLE_GEOSAMPA_STOP_NAME
        )
        line_row = next(row for row in line_rows if row["id"] == SAMPLE_SHAPE_ID)

        expected_list = "175T-10||875A-10"
        assert stop_row["bus_count"] == 0
        assert stop_row["bus_list"] == ""

        assert geosampa_stop_row["bus_count"] == 0
        assert geosampa_stop_row["bus_list"] == ""

        assert line_row["bus_count"] == 2
        assert line_row["bus_list"] == expected_list
        assert line_row["mode"] == "bus"
    finally:
        await _cleanup_sample_rows()
        await close_db()


@pytest.mark.anyio
async def test_transport_stop_details_return_lines_on_demand() -> None:
    init_db(os.environ["DATABASE_URL"])
    try:
        if not await _ensure_gtfs_schema() or not await _ensure_geosampa_schema():
            pytest.skip("Phase 3 transport schemas not migrated. Run alembic upgrade head.")

        await _cleanup_sample_rows()
        await _insert_sample_gtfs_rows()

        zoom = 14
        x, y = _lonlat_to_tile(SAMPLE_LON, SAMPLE_LAT, zoom)
        params = {"z": zoom, "x": x, "y": y}

        engine = get_engine()
        async with engine.connect() as conn:
            stop_rows = (await conn.execute(text(_TRANSPORT_STOPS_TILE_ROWS_SQL), params)).mappings().all()

        geosampa_stop_row = next(
            row for row in stop_rows if row["source_kind"] == "geosampa_bus_stop" and row["name"] == SAMPLE_GEOSAMPA_STOP_NAME
        )

        gtfs_result = await get_transport_stop_details(SAMPLE_STOP_ID, "gtfs_stop")
        geosampa_result = await get_transport_stop_details(str(geosampa_stop_row["id"]), "geosampa_bus_stop")

        assert gtfs_result["count"] == 2
        assert gtfs_result["buses"] == ["175T-10", "875A-10"]
        assert geosampa_result["count"] == 2
        assert geosampa_result["buses"] == ["175T-10", "875A-10"]
    finally:
        await _cleanup_sample_rows()
        await close_db()