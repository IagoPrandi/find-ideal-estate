from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.modules.transport.points_service import (  # noqa: E402
    _build_transport_search_sql,
    _source_filter_tokens,
    run_transport_search_for_job,
)


def test_source_filter_tokens_follow_public_transport_mode() -> None:
    assert _source_filter_tokens({"transport_mode": "transit", "public_transport_mode": "bus"}) == {"bus"}
    assert _source_filter_tokens({"transport_mode": "transit", "public_transport_mode": "rail"}) == {"metro", "trem"}
    assert _source_filter_tokens({"transport_mode": "transit", "public_transport_mode": "mixed"}) == {"bus", "metro", "trem"}


def test_bus_only_transport_search_sql_keeps_bus_sources_visible() -> None:
    sql = _build_transport_search_sql({"bus"})

    assert "SET LOCAL jit = off" not in sql
    assert "nearby_gtfs_stops AS" in sql
    assert "JOIN nearby_gtfs_stops nearby ON nearby.stop_id = st.stop_id" in sql
    assert "s.location && ST_Expand(ref.ref_point, ref.radius_deg)" in sql
    assert "gtfs_stops" in sql
    assert "geosampa_bus_stops" in sql
    assert "geosampa_bus_terminals" in sql


def test_rail_only_transport_search_sql_skips_gtfs_bus_aggregation() -> None:
    sql = _build_transport_search_sql({"metro", "trem"})

    assert "nearby_gtfs_stops AS" not in sql
    assert "nearby_gtfs_route_agg AS" not in sql
    assert "geosampa_metro_stations" in sql
    assert "geosampa_trem_stations" in sql


def test_run_transport_search_clears_selected_transport_point_before_replacing_rows(monkeypatch) -> None:
    execution_order: list[str] = []
    result_ref_payloads: list[dict[str, object]] = []

    class _FakeMappings:
        def __init__(self, *, first_row=None, all_rows=None):
            self._first_row = first_row
            self._all_rows = list(all_rows or [])

        def first(self):
            return self._first_row

        def all(self):
            return list(self._all_rows)

    class _FakeResult:
        def __init__(self, *, first_row=None, all_rows=None):
            self._mappings = _FakeMappings(first_row=first_row, all_rows=all_rows)

        def mappings(self):
            return self._mappings

    class _FakeConn:
        async def execute(self, statement, params=None):
            sql = str(statement)
            if "SET LOCAL jit = off" in sql:
                return _FakeResult()
            if "FROM jobs jb" in sql:
                return _FakeResult(
                    first_row={
                        "journey_id": uuid4(),
                        "input_snapshot": {"reference_point": {"lat": -23.55, "lon": -46.63}, "transport_mode": "transit", "public_transport_mode": "bus"},
                        "secondary_reference_lat": None,
                        "secondary_reference_lon": None,
                    }
                )
            if "ORDER BY walk_distance_m ASC, route_count DESC" in sql:
                return _FakeResult(
                    all_rows=[
                        {
                            "source": "gtfs_stop",
                            "external_id": "stop-1",
                            "name": "Parada Teste",
                            "lat": -23.55,
                            "lon": -46.63,
                            "walk_distance_m": 120.0,
                            "route_ids": ["875A-10"],
                            "modal_types": ["bus"],
                        }
                    ]
                )
            if "UPDATE journeys" in sql and "selected_transport_point_id = NULL" in sql:
                execution_order.append("clear_selected")
                return _FakeResult()
            if "UPDATE journey_zones" in sql and "SET transport_point_id = NULL" in sql:
                execution_order.append("clear_journey_zone_refs")
                return _FakeResult()
            if "UPDATE zones" in sql and "SET transport_point_id = NULL" in sql:
                execution_order.append("clear_zone_refs")
                return _FakeResult()
            if "DELETE FROM transport_points" in sql:
                execution_order.append("delete_points")
                return _FakeResult()
            if "INSERT INTO transport_points" in sql:
                execution_order.append("insert_points")
                return _FakeResult()
            raise AssertionError(f"Unexpected SQL executed: {sql}")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeEngine:
        def begin(self):
            return _FakeConn()

    monkeypatch.setattr("src.modules.transport.points_service.get_engine", lambda: _FakeEngine())

    async def _fake_update_job_execution_state(job_id, **kwargs):
        result_ref_payloads.append(kwargs["result_ref"])

    monkeypatch.setattr("src.modules.transport.points_service.update_job_execution_state", _fake_update_job_execution_state)

    inserted_count = asyncio.run(run_transport_search_for_job(uuid4()))

    assert inserted_count == 1
    assert execution_order[:5] == [
        "clear_selected",
        "clear_journey_zone_refs",
        "clear_zone_refs",
        "delete_points",
        "insert_points",
    ]
    assert result_ref_payloads == [
        {
            "transport_points_count": 1,
            "source_filter": ["bus"],
            "radius_m": 300,
            "used_relaxed_radius": False,
        }
    ]