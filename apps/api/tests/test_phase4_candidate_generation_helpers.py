from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.modules.zones.candidate_generation import (  # noqa: E402
    _BUS_DOWNSTREAM_SQL,
    _METRO_LINES_SQL,
    _RAIL_STATIONS_SQL,
    _TREM_LINES_SQL,
    _bucketize_candidates,
    _buffer_candidate,
    _dedupe_point_candidates,
    CandidateZoneGenerationError,
    generate_candidate_zones_for_seed,
    PointCandidate,
)


def test_bucketize_candidates_keeps_fastest_per_bucket() -> None:
    candidates = [
        PointCandidate("bus:a", "bus", "a", 4.1, -46.63, -23.55),
        PointCandidate("bus:b", "bus", "b", 4.8, -46.631, -23.551),
        PointCandidate("bus:c", "bus", "c", 6.2, -46.632, -23.552),
    ]

    bucketed = _bucketize_candidates(candidates, 2)

    assert [candidate.source_point_id for candidate in bucketed] == ["a", "c"]


def test_dedupe_candidates_and_buffer_generation_are_spatially_stable() -> None:
    candidates = [
        PointCandidate("rail:a", "rail", "a", 8.0, -46.6300, -23.5500),
        PointCandidate("rail:b", "rail", "b", 9.0, -46.6301, -23.5501),
        PointCandidate("rail:c", "rail", "c", 12.0, -46.6400, -23.5600),
    ]

    deduped = _dedupe_point_candidates(candidates, 50.0)

    assert [candidate.source_point_id for candidate in deduped] == ["a", "c"]

    zone = _buffer_candidate(deduped[0], 600)

    assert zone.mode == "rail"
    assert zone.geometry["type"] == "Polygon"
    assert abs(zone.centroid_lon - deduped[0].lon) < 0.01
    assert abs(zone.centroid_lat - deduped[0].lat) < 0.01


def test_rail_sql_templates_match_materialized_geosampa_schema() -> None:
    bus_sql = _BUS_DOWNSTREAM_SQL.text
    station_sql = _RAIL_STATIONS_SQL.text
    metro_line_sql = _METRO_LINES_SQL.text
    trem_line_sql = _TREM_LINES_SQL.text

    assert "nearby_origins" in bus_sql
    assert "ST_DWithin(s.location::geography, reference.geom::geography" in bus_sql
    assert "DISTINCT ON (origin_stop_id, trip_id)" in bus_sql
    assert "seed_area.stop_id = candidate.stop_id" in bus_sql
    assert "CAST(:prefix AS text) || md5(ST_AsEWKB(ST_PointOnSurface(geometry))::text)" in station_sql
    assert "CAST(:mode AS text) AS mode" in station_sql
    assert "id::text" not in station_sql
    assert "nr_nome_linha" not in station_sql
    assert "nr_nome_linha" in metro_line_sql
    assert "CAST(:mode AS text) AS mode" in metro_line_sql
    assert "CAST(:mode AS text) AS mode" in trem_line_sql
    assert "nr_nome_linha" not in trem_line_sql


def test_generate_candidate_zones_respects_public_transport_mode(monkeypatch) -> None:
    helper_calls: list[str] = []

    async def _fake_load_bus_candidates(*args, **kwargs):
        helper_calls.append("bus")
        return [PointCandidate("bus:a", "bus", "a", 5.0, -46.63, -23.55)]

    async def _fake_load_rail_candidates(*args, **kwargs):
        helper_calls.append("rail")
        return [PointCandidate("rail:a", "rail", "a", 7.0, -46.64, -23.56)]

    monkeypatch.setattr(
        "src.modules.zones.candidate_generation._load_bus_candidates",
        _fake_load_bus_candidates,
    )
    monkeypatch.setattr(
        "src.modules.zones.candidate_generation._load_rail_candidates",
        _fake_load_rail_candidates,
    )

    zones = asyncio.run(
        generate_candidate_zones_for_seed(
            seed_lat=-23.55,
            seed_lon=-46.63,
            max_time_minutes=20,
            radius_meters=600,
            public_transport_mode="rail",
        )
    )

    assert helper_calls == ["rail"]
    assert [zone.mode for zone in zones] == ["rail"]


def test_generate_candidate_zones_raises_when_bus_candidates_are_unavailable(monkeypatch) -> None:
    async def _fake_load_bus_candidates(*args, **kwargs):
        return []

    async def _unexpected_load_rail_candidates(*args, **kwargs):
        raise AssertionError("rail candidates should not be loaded for bus-only mode")

    monkeypatch.setattr(
        "src.modules.zones.candidate_generation._load_bus_candidates",
        _fake_load_bus_candidates,
    )
    monkeypatch.setattr(
        "src.modules.zones.candidate_generation._load_rail_candidates",
        _unexpected_load_rail_candidates,
    )

    try:
        asyncio.run(
            generate_candidate_zones_for_seed(
                seed_lat=-23.55,
                seed_lon=-46.63,
                max_time_minutes=30,
                radius_meters=600,
                public_transport_mode="bus",
            )
        )
    except CandidateZoneGenerationError as exc:
        assert "bus candidate zones" in str(exc)
    else:
        raise AssertionError("Expected bus-only generation to fail without downstream GTFS candidates")