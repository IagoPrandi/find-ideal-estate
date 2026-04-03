"""Unit tests for M5.6: listing_search_requests recording and aggregation.

These tests use monkeypatching to avoid DB connectivity. DB-backed acceptance
is verified separately via scripts/verify_m5_6_search_requests.py.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from modules.listings.search_requests import (  # noqa: E402
    get_prewarm_targets,
    record_search_request,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_ROW_ID = uuid4()

_SAMPLE_TARGETS = [
    {
        "search_location_normalized": "rua vergueiro 3185 sao paulo",
        "search_location_label": "Rua Vergueiro 3185",
        "search_location_type": "street",
        "search_type": "rent",
        "usage_type": "residential",
        "platforms_hash": "abc123",
        "demand_count": 3,
        "last_requested_at": datetime(2026, 3, 22, tzinfo=timezone.utc),
    },
    {
        "search_location_normalized": "av paulista 1000 sao paulo",
        "search_location_label": "Av. Paulista 1000",
        "search_location_type": "street",
        "search_type": "rent",
        "usage_type": "residential",
        "platforms_hash": "abc123",
        "demand_count": 1,
        "last_requested_at": datetime(2026, 3, 22, tzinfo=timezone.utc),
    },
]


def _mock_engine(scalar_return: Any = _SAMPLE_ROW_ID, mappings_return: list | None = None):
    """Return a mock engine whose begin()/connect() context managers work."""
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.execute.return_value.scalar_one = MagicMock(return_value=scalar_return)
    if mappings_return is not None:
        conn.execute.return_value.mappings = MagicMock(return_value=iter(mappings_return))

    ctx_begin = AsyncMock()
    ctx_begin.__aenter__ = AsyncMock(return_value=conn)
    ctx_begin.__aexit__ = AsyncMock(return_value=False)

    ctx_connect = AsyncMock()
    ctx_connect.__aenter__ = AsyncMock(return_value=conn)
    ctx_connect.__aexit__ = AsyncMock(return_value=False)

    engine = MagicMock()
    engine.begin = MagicMock(return_value=ctx_begin)
    engine.connect = MagicMock(return_value=ctx_connect)
    return engine


# ---------------------------------------------------------------------------
# record_search_request
# ---------------------------------------------------------------------------


class TestRecordSearchRequest:
    @pytest.mark.anyio
    async def test_returns_uuid(self) -> None:
        """record_search_request must return the inserted row id as a UUID."""
        engine = _mock_engine(scalar_return=_SAMPLE_ROW_ID)
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            result = await record_search_request(
                zone_fingerprint="fp-abc",
                search_location_normalized="rua a sao paulo",
                search_location_label="Rua A",
                search_location_type="street",
                search_type="rent",
                usage_type="residential",
                platforms_hash="hash1",
                result_source="cache_hit",
            )
        assert result == _SAMPLE_ROW_ID

    @pytest.mark.anyio
    async def test_persists_once_per_call(self) -> None:
        """Each call to record_search_request executes exactly one INSERT."""
        engine = _mock_engine(scalar_return=uuid4())
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            await record_search_request(
                zone_fingerprint="fp-abc",
                search_location_normalized="rua a sao paulo",
                search_location_label="Rua A",
                search_location_type="street",
                search_type="rent",
                usage_type="residential",
                platforms_hash="hash1",
                result_source="cache_miss",
            )
        ctx = engine.begin.return_value
        conn = ctx.__aenter__.return_value
        assert conn.execute.call_count == 1

    @pytest.mark.anyio
    async def test_cache_miss_also_recorded(self) -> None:
        """PRD requires cache_miss searches to be recorded (drives prewarm)."""
        engine = _mock_engine(scalar_return=uuid4())
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            row_id = await record_search_request(
                zone_fingerprint="fp-xyz",
                search_location_normalized="rua b sao paulo",
                search_location_label="Rua B",
                search_location_type="street",
                search_type="rent",
                usage_type="residential",
                platforms_hash="hash2",
                result_source="cache_miss",
            )
        assert isinstance(row_id, UUID)

    @pytest.mark.anyio
    async def test_optional_journey_and_session(self) -> None:
        """journey_id and session_id are optional (may be None)."""
        engine = _mock_engine(scalar_return=uuid4())
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            # Should not raise
            await record_search_request(
                zone_fingerprint="fp-abc",
                search_location_normalized="rua a",
                search_location_label="Rua A",
                search_location_type="street",
                search_type="sale",
                usage_type="commercial",
                platforms_hash="hash3",
                result_source="cache_hit",
                journey_id=None,
                session_id=None,
            )

    @pytest.mark.anyio
    async def test_normalizes_search_location_before_insert(self) -> None:
        """Equivalent addresses must persist under a single canonical key."""
        engine = _mock_engine(scalar_return=uuid4())
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            await record_search_request(
                zone_fingerprint="fp-abc",
                search_location_normalized="  Avenida Brigadeiro Luís Antônio,   Jardim Paulista, São Paulo, SP  ",
                search_location_label="Avenida Brigadeiro Luís Antônio, Jardim Paulista, São Paulo, SP",
                search_location_type="street",
                search_type="rent",
                usage_type="residential",
                platforms_hash="hash4",
                result_source="cache_hit",
            )

        ctx = engine.begin.return_value
        conn = ctx.__aenter__.return_value
        execute_args = conn.execute.call_args.args[1]
        assert execute_args["search_location_normalized"] == (
            "avenida brigadeiro luis antonio, jardim paulista, sao paulo, sp"
        )


# ---------------------------------------------------------------------------
# get_prewarm_targets
# ---------------------------------------------------------------------------


class TestGetPrewarmTargets:
    @pytest.mark.anyio
    async def test_returns_list_of_dicts(self) -> None:
        engine = _mock_engine(mappings_return=_SAMPLE_TARGETS)
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            targets = await get_prewarm_targets(lookback_hours=24, limit=50)
        assert isinstance(targets, list)
        assert len(targets) == 2

    @pytest.mark.anyio
    async def test_demand_count_present(self) -> None:
        engine = _mock_engine(mappings_return=_SAMPLE_TARGETS)
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            targets = await get_prewarm_targets(lookback_hours=24)
        for t in targets:
            assert "demand_count" in t, "demand_count key must be present in each target"

    @pytest.mark.anyio
    async def test_top_entry_has_highest_demand(self) -> None:
        """PRD criterion: first result should have highest demand_count."""
        engine = _mock_engine(mappings_return=_SAMPLE_TARGETS)
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            targets = await get_prewarm_targets(lookback_hours=24)
        assert targets[0]["demand_count"] >= targets[-1]["demand_count"]

    @pytest.mark.anyio
    async def test_empty_when_no_requests(self) -> None:
        engine = _mock_engine(mappings_return=[])
        with patch(
            "modules.listings.search_requests.get_engine", return_value=engine
        ):
            targets = await get_prewarm_targets(lookback_hours=24)
        assert targets == []
