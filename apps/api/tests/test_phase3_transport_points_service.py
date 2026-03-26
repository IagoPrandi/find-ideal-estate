from __future__ import annotations

import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from src.modules.transport.points_service import (  # noqa: E402
    _build_transport_search_sql,
    _source_filter_tokens,
)


def test_source_filter_tokens_follow_public_transport_mode() -> None:
    assert _source_filter_tokens({"transport_mode": "transit", "public_transport_mode": "bus"}) == {"bus"}
    assert _source_filter_tokens({"transport_mode": "transit", "public_transport_mode": "rail"}) == {"metro", "trem"}
    assert _source_filter_tokens({"transport_mode": "transit", "public_transport_mode": "mixed"}) == {"bus", "metro", "trem"}


def test_bus_only_transport_search_sql_keeps_bus_sources_visible() -> None:
    sql = _build_transport_search_sql({"bus"})

    assert "gtfs_stops" in sql
    assert "geosampa_bus_stops" in sql
    assert "geosampa_bus_terminals" in sql