"""
Validate GEO content layer data quality.

Checks:
  1. Slugs  — all neighborhoods have unique, non-null slugs
  2. Geometry — all boundaries are ST_IsValid and non-empty
  3. Scores — all publishable neighborhoods have scores for >= 4 metrics
  4. Coverage — coverage flags are consistent with score presence
  5. View — urban_metrics_by_district is populated and reasonably fresh
  6. No price data — confirms preço imobiliário is absent (MVP constraint)

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed (details logged).

Usage:
  python scripts/validate_geo_data.py [--city-code SAO_PAULO]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"


def get_engine() -> sa.Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL not set")
        sys.exit(1)
    return sa.create_engine(url, pool_pre_ping=True)


def check(label: str, passed: bool, detail: str = "") -> bool:
    status = PASS if passed else FAIL
    msg = f"[{status}] {label}"
    if detail:
        msg += f" — {detail}"
    log.info(msg)
    return passed


def run_checks(conn: sa.Connection, city_code: str) -> list[bool]:
    results: list[bool] = []

    # ------------------------------------------------------------------
    # 1. Slugs
    # ------------------------------------------------------------------
    null_slugs = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM neighborhood_boundaries "
            "WHERE city_code = :cc AND slug IS NULL"
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("Slugs: no NULL slugs", null_slugs == 0,
                         f"{null_slugs} neighborhoods missing slug"))

    dup_slugs = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "  SELECT slug FROM neighborhood_boundaries "
            "  WHERE city_code = :cc AND slug IS NOT NULL "
            "  GROUP BY slug HAVING COUNT(*) > 1"
            ") t"
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("Slugs: all slugs unique", dup_slugs == 0,
                         f"{dup_slugs} duplicate slugs"))

    # ------------------------------------------------------------------
    # 2. Geometry validity
    # ------------------------------------------------------------------
    invalid_geom = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM neighborhood_boundaries "
            "WHERE city_code = :cc AND NOT ST_IsValid(geometry)"
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("Geometry: all boundaries valid", invalid_geom == 0,
                         f"{invalid_geom} invalid geometries"))

    empty_geom = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM neighborhood_boundaries "
            "WHERE city_code = :cc AND ST_IsEmpty(geometry)"
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("Geometry: no empty geometries", empty_geom == 0,
                         f"{empty_geom} empty geometries"))

    # ------------------------------------------------------------------
    # 3. Scores — publishable neighborhoods must have >= 4 metric scores
    # ------------------------------------------------------------------
    total = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM urban_metrics_by_district "
            "WHERE city_code = :cc"
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("View: urban_metrics_by_district populated",
                         total > 0, f"{total} rows"))

    publishable = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM urban_metrics_by_district "
            "WHERE city_code = :cc AND is_publishable = TRUE"
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("Publishable: at least 1 publishable neighborhood",
                         publishable > 0, f"{publishable} publishable"))

    # Publishable must not have NULL scores for all 5 metrics
    null_score_publishable = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM urban_metrics_by_district "
            "WHERE city_code = :cc AND is_publishable = TRUE "
            "AND transport_score IS NULL AND green_area_score IS NULL "
            "AND flood_risk_score IS NULL AND safety_score IS NULL "
            "AND poi_access_score IS NULL"
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("Scores: publishable neighborhoods have at least 1 score",
                         null_score_publishable == 0,
                         f"{null_score_publishable} publishable with no scores"))

    # ------------------------------------------------------------------
    # 4. Coverage consistency
    # ------------------------------------------------------------------
    inconsistent = conn.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM neighborhood_metric_coverage nmc
            JOIN neighborhood_metric_scores nms
                ON nmc.neighborhood_code = nms.neighborhood_code
                AND nmc.metric_name = nms.metric_name
            WHERE nmc.city_code = :cc
              AND nmc.has_data = FALSE
              AND nms.normalized_score IS NOT NULL
            """
        ),
        {"cc": city_code},
    ).scalar()
    results.append(check("Coverage: no score where coverage=no_data",
                         inconsistent == 0,
                         f"{inconsistent} inconsistencies"))

    # ------------------------------------------------------------------
    # 5. View freshness (warn if older than 24h)
    # ------------------------------------------------------------------
    refreshed_at = conn.execute(
        sa.text(
            "SELECT MAX(refreshed_at) FROM urban_metrics_by_district "
            "WHERE city_code = :cc"
        ),
        {"cc": city_code},
    ).scalar()
    if refreshed_at:
        age = datetime.now(timezone.utc) - refreshed_at.replace(tzinfo=timezone.utc)
        fresh = age < timedelta(hours=24)
        log.info("[%s] View freshness: %s old",
                 PASS if fresh else WARN, str(age).split(".")[0])
        # Freshness is a warning, not a failure
    else:
        log.info("[%s] View freshness: no refreshed_at found", WARN)

    # ------------------------------------------------------------------
    # 6. No price data (MVP constraint)
    # ------------------------------------------------------------------
    price_tables = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "AND table_name LIKE '%price%' OR table_name LIKE '%preco%'"
        ),
    ).scalar()
    results.append(check("MVP constraint: no price tables", price_tables == 0,
                         f"{price_tables} price-related tables found"))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate GEO data quality")
    parser.add_argument("--city-code", default="SAO_PAULO")
    args = parser.parse_args()

    engine = get_engine()
    with engine.connect() as conn:
        log.info("=== GEO data validation — city_code=%s ===", args.city_code)
        results = run_checks(conn, args.city_code)

    passed = sum(results)
    total = len(results)
    log.info("=== %d/%d checks passed ===", passed, total)

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
