"""Tests for zone badge computation (M4.5)."""

from __future__ import annotations

from modules.zones.badges import (
    ZoneBadgeValue,
    _compute_rank_percentile,
    _percentile_to_tier,
)


class TestBadgeTierMapping:
    """Test badge tier classification from percentile ranks."""

    def test_tier_excellent(self):
        """Percentile >= 75 => excellent."""
        assert _percentile_to_tier(75) == "excellent"
        assert _percentile_to_tier(100) == "excellent"
        assert _percentile_to_tier(90) == "excellent"

    def test_tier_good(self):
        """50 <= percentile < 75 => good."""
        assert _percentile_to_tier(50) == "good"
        assert _percentile_to_tier(74) == "good"
        assert _percentile_to_tier(60) == "good"

    def test_tier_fair(self):
        """25 <= percentile < 50 => fair."""
        assert _percentile_to_tier(25) == "fair"
        assert _percentile_to_tier(49) == "fair"
        assert _percentile_to_tier(30) == "fair"

    def test_tier_poor(self):
        """percentile < 25 => poor."""
        assert _percentile_to_tier(0) == "poor"
        assert _percentile_to_tier(24) == "poor"
        assert _percentile_to_tier(1) == "poor"


class TestPercentileComputation:
    """Test percentile rank computation."""

    def test_percentile_single_value(self):
        """Single value in peer set ranks at 100%."""
        percentile = _compute_rank_percentile(100, [100])
        assert percentile == 100.0

    def test_percentile_min_value(self):
        """Minimum value in peer set ranks near 0%."""
        percentile = _compute_rank_percentile(1, [1, 2, 3, 4, 5])
        assert percentile == 20.0  # 1/5

    def test_percentile_max_value(self):
        """Maximum value in peer set ranks at 100%."""
        percentile = _compute_rank_percentile(5, [1, 2, 3, 4, 5])
        assert percentile == 100.0  # 5/5

    def test_percentile_median_value(self):
        """Median value ranks at 40-60% depending on ties."""
        percentile = _compute_rank_percentile(3, [1, 2, 3, 4, 5])
        assert percentile == 60.0  # 3/5

    def test_percentile_empty_peer_set(self):
        """Empty peer set returns 50% (neutral)."""
        percentile = _compute_rank_percentile(10, [])
        assert percentile == 50.0

    def test_percentile_with_duplicates(self):
        """Duplicates are counted correctly."""
        percentile = _compute_rank_percentile(3, [1, 2, 3, 3, 3, 4, 5])
        # Values <= 3 are: [1, 2, 3, 3, 3] = 5 values
        # Percentile = 5/7 = 71.43%
        assert abs(percentile - 71.43) < 0.1


class TestZoneBadgeValue:
    """Test badge value representation."""

    def test_zone_badge_value_to_dict(self):
        """ZoneBadgeValue converts to dict."""
        badge = ZoneBadgeValue(
            metric_name="green_area_m2",
            value=5000,
            peer_median=4000,
            rank_percentile=75.0,
            tier="excellent",
        )

        data = badge.to_dict()

        assert data["metric_name"] == "green_area_m2"
        assert data["value"] == 5000
        assert data["peer_median"] == 4000
        assert data["rank_percentile"] == 75.0
        assert data["tier"] == "excellent"

    def test_badge_value_int_vs_float(self):
        """Badge value preserves int/float types."""
        badge_int = ZoneBadgeValue(
            metric_name="safety_incidents_count",
            value=10,
            peer_median=8,
            rank_percentile=60.0,
            tier="good",
        )

        badge_float = ZoneBadgeValue(
            metric_name="green_area_m2",
            value=5000.5,
            peer_median=4000.25,
            rank_percentile=75.5,
            tier="excellent",
        )

        assert isinstance(badge_int.to_dict()["value"], int)
        assert isinstance(badge_float.to_dict()["value"], float)


class TestBadgeInversion:
    """Test inverted metrics (where lower is better)."""

    def test_flood_area_percentile_inverted(self):
        """
        Flood area: lower is better.
        Zone with lowest flood area should be at highest percentile.
        """
        # Value is 100 (low), peers are [100, 500, 1000]
        # Raw percentile: 100 <= 100 is 1/3 = 33%
        # Inverted: 100 - 33 = 67% (good/better than expected)
        raw_percentile = _compute_rank_percentile(100, [100, 500, 1000])
        inverted_percentile = 100 - raw_percentile

        assert abs(raw_percentile - 33.33) < 0.1
        assert abs(inverted_percentile - 66.67) < 0.1
        assert _percentile_to_tier(inverted_percentile) in ("good", "excellent")

    def test_safety_incidents_percentile_inverted(self):
        """
        Safety incidents: lower is better.
        Zone with fewest incidents should be at highest percentile.
        """
        # Value is 5 (low), peers are [5, 10, 15]
        # Raw percentile: 5 <= 5 is 1/3 = 33%
        # Inverted: 100 - 33 = 67%
        raw_percentile = _compute_rank_percentile(5, [5, 10, 15])
        inverted_percentile = 100 - raw_percentile

        assert abs(inverted_percentile - 66.67) < 1.0
        assert _percentile_to_tier(inverted_percentile) in ("good", "excellent")
