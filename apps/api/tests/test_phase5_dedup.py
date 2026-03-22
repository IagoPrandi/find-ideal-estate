"""Unit tests for M5.5: property deduplication fingerprint and badge logic.

These tests cover:
  - compute_property_fingerprint determinism and collision-resistance.
  - Address normalisation (accents, case, extra whitespace).
  - lat/lon rounding to 4 decimal places.
  - area_m2 rounding to nearest int.
  - Identical inputs → identical fingerprint.
  - Different inputs → different fingerprint.

Integration tests (DB-backed) live in scripts/verify_m5_5_dedup.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from modules.listings.dedup import compute_property_fingerprint  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expected_fp(address: str, lat, lon, area, bedrooms) -> str:
    """Re-compute fingerprint using the same canonical logic as the module."""
    import re
    import unicodedata

    def norm_addr(addr):
        if not addr:
            return ""
        nfkd = unicodedata.normalize("NFKD", addr)
        ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
        lower = ascii_only.lower()
        return re.sub(r"\s+", " ", lower).strip()

    canonical = {
        "address": norm_addr(address),
        "area_m2": round(float(area)) if area is not None else None,
        "bedrooms": int(bedrooms) if bedrooms is not None else None,
        "lat": round(float(lat), 4) if lat is not None else None,
        "lon": round(float(lon), 4) if lon is not None else None,
    }
    payload = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# compute_property_fingerprint
# ---------------------------------------------------------------------------


class TestComputePropertyFingerprint:
    def test_deterministic_same_inputs(self) -> None:
        """Same inputs always produce the same 64-char hex fingerprint."""
        fp1 = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        fp2 = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        assert fp1 == fp2
        assert len(fp1) == 64
        assert all(c in "0123456789abcdef" for c in fp1)

    def test_matches_canonical_computation(self) -> None:
        """Fingerprint matches independent re-computation."""
        inputs = ("Rua Vergueiro 3185", -23.5951, -46.6388, 62.4, 2)
        assert compute_property_fingerprint(*inputs) == _expected_fp(*inputs)

    def test_address_normalisation_accent_insensitive(self) -> None:
        """'Rua São João' and 'Rua Sao Joao' must hash identically."""
        fp_accented = compute_property_fingerprint("Rua São João", -23.5, -46.6, 50.0, 1)
        fp_plain = compute_property_fingerprint("Rua Sao Joao", -23.5, -46.6, 50.0, 1)
        assert fp_accented == fp_plain

    def test_address_normalisation_case_insensitive(self) -> None:
        fp_upper = compute_property_fingerprint("RUA VERGUEIRO", -23.5, -46.6, 50.0, 1)
        fp_lower = compute_property_fingerprint("rua vergueiro", -23.5, -46.6, 50.0, 1)
        assert fp_upper == fp_lower

    def test_address_normalisation_collapses_whitespace(self) -> None:
        fp_multi = compute_property_fingerprint("Rua  Vergueiro   3185", -23.5, -46.6, 50.0, 1)
        fp_single = compute_property_fingerprint("Rua Vergueiro 3185", -23.5, -46.6, 50.0, 1)
        assert fp_multi == fp_single

    def test_lat_lon_rounded_to_4dp(self) -> None:
        """Points within ~10m of each other (same 4-dp bucket) → same fingerprint."""
        fp_a = compute_property_fingerprint("Rua A", -23.59512, -46.63878, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.59514, -46.63882, 62.0, 2)
        assert fp_a == fp_b

    def test_lat_lon_different_5th_dp_still_same(self) -> None:
        """5th decimal difference must collapse to same fingerprint."""
        # Both -23.59511 and -23.59513 round to -23.5951 at 4dp
        fp_a = compute_property_fingerprint("Rua A", -23.59511, -46.63881, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.59513, -46.63883, 62.0, 2)
        assert fp_a == fp_b

    def test_different_address_different_fingerprint(self) -> None:
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua B", -23.5951, -46.6388, 62.0, 2)
        assert fp_a != fp_b

    def test_different_bedrooms_different_fingerprint(self) -> None:
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.0, 3)
        assert fp_a != fp_b

    def test_area_rounded_to_nearest_int(self) -> None:
        """62.4 and 62.49 both round to 62 → same fingerprint."""
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.4, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.49, 2)
        assert fp_a == fp_b

    def test_area_that_rounds_differently(self) -> None:
        """62.4 rounds to 62; 63.5 rounds to 64 (Python banker's rounding: rounds to even)."""
        fp_a = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 62.4, 2)
        fp_b = compute_property_fingerprint("Rua A", -23.5951, -46.6388, 63.6, 2)
        assert fp_a != fp_b

    def test_none_fields_stable(self) -> None:
        """None inputs produce a deterministic fingerprint (no crash)."""
        fp1 = compute_property_fingerprint(None, None, None, None, None)
        fp2 = compute_property_fingerprint(None, None, None, None, None)
        assert fp1 == fp2
        assert len(fp1) == 64
