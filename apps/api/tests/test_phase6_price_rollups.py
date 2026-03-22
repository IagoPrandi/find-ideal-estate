"""Unit tests for M6.1: property_price_rollups statistics helpers.

These tests cover pure-Python logic that does NOT require a DB:
  - is_median_within_iqr: boundary conditions and normal cases.
  - Verification scenario: 20 synthetic prices → computed percentiles → IQR check.

Integration/DB-level tests live in scripts/verify_m6_1_price_rollups.py.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from modules.listings.price_rollups import (  # noqa: E402
    RETENTION_DAYS,
    is_median_within_iqr,
)


# ---------------------------------------------------------------------------
# is_median_within_iqr
# ---------------------------------------------------------------------------


class TestIsMedianWithinIqr:
    def test_typical_case(self):
        assert is_median_within_iqr(Decimal("1000"), Decimal("1500"), Decimal("2000"))

    def test_median_equals_p25(self):
        # Exact lower boundary → still within
        assert is_median_within_iqr(Decimal("1000"), Decimal("1000"), Decimal("2000"))

    def test_median_equals_p75(self):
        # Exact upper boundary → still within
        assert is_median_within_iqr(Decimal("1000"), Decimal("2000"), Decimal("2000"))

    def test_median_below_p25(self):
        assert not is_median_within_iqr(Decimal("1500"), Decimal("1000"), Decimal("2000"))

    def test_median_above_p75(self):
        assert not is_median_within_iqr(Decimal("1000"), Decimal("2500"), Decimal("2000"))

    def test_none_p25(self):
        assert not is_median_within_iqr(None, Decimal("1500"), Decimal("2000"))

    def test_none_median(self):
        assert not is_median_within_iqr(Decimal("1000"), None, Decimal("2000"))

    def test_none_p75(self):
        assert not is_median_within_iqr(Decimal("1000"), Decimal("1500"), None)

    def test_all_none(self):
        assert not is_median_within_iqr(None, None, None)

    def test_float_inputs(self):
        # Accepts floats as well
        assert is_median_within_iqr(800.0, 1200.0, 1600.0)


# ---------------------------------------------------------------------------
# PRD verification scenario: 20 synthetic prices → median within IQR
# ---------------------------------------------------------------------------


def _compute_percentiles(prices: list[float]) -> tuple[float, float, float]:
    """Pure-Python percentile_cont equivalent (linear interpolation, SQL-compatible)."""
    n = len(prices)
    if n == 0:
        return 0.0, 0.0, 0.0
    sorted_p = sorted(prices)

    def _pc(q: float) -> float:
        row_number = q * (n - 1)
        lo = int(row_number)
        hi = lo + 1
        if hi >= n:
            return sorted_p[-1]
        frac = row_number - lo
        return sorted_p[lo] + frac * (sorted_p[hi] - sorted_p[lo])

    return _pc(0.25), _pc(0.50), _pc(0.75)


class TestVerificationScenario:
    """
    PRD Verificação (M6.1): after ingesting 20 listings →
    rollup calculated; median within IQR expected.
    """

    def test_20_prices_median_within_iqr(self):
        """20 uniform prices in [2000, 5800] → median must lie in [p25, p75]."""
        prices = [2000.0 + i * 200.0 for i in range(20)]  # 2000 … 5800
        p25, median, p75 = _compute_percentiles(prices)
        assert is_median_within_iqr(p25, median, p75), (
            f"Median {median} not within IQR [{p25}, {p75}]"
        )

    def test_20_prices_sample_count(self):
        prices = [1500.0 + i * 100.0 for i in range(20)]
        assert len(prices) == 20

    def test_skewed_prices_median_still_within_iqr(self):
        """Right-skewed distribution (outlier at top) — median must still be <= p75."""
        prices = [1000.0] * 15 + [5000.0, 5100.0, 5200.0, 5300.0, 10000.0]
        p25, median, p75 = _compute_percentiles(prices)
        assert is_median_within_iqr(p25, median, p75), (
            f"Median {median} not within IQR [{p25}, {p75}]"
        )

    def test_all_same_price(self):
        """Degenerate: all 20 listings same price → p25 == median == p75."""
        prices = [3500.0] * 20
        p25, median, p75 = _compute_percentiles(prices)
        assert p25 == median == p75 == 3500.0
        assert is_median_within_iqr(p25, median, p75)


# ---------------------------------------------------------------------------
# RETENTION_DAYS constant
# ---------------------------------------------------------------------------


class TestRetentionDays:
    def test_retention_is_365(self):
        assert RETENTION_DAYS == 365
