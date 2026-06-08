"""
Aggregate GEO content layer metrics from GeoSampa and public safety data.

Pré-requisito:
  Execute scripts/ingest_distritos_municipais.py antes desta pipeline para garantir
  que neighborhood_boundaries contenha os 96 distritos municipais oficiais de SP
  importados de geoportal_distrito_municipal_v2.gpkg (EPSG:31983 → EPSG:4326).
  Cada distrito = uma zona de análise (neighborhood_code = cd_distrito_municipal).

Pipeline (idempotent — safe to re-run):
  1. Populate slugs in neighborhood_boundaries
  2. Aggregate green area  → neighborhood_green_area_metrics
  3. Aggregate flood risk  → neighborhood_flood_risk_metrics
  4. Aggregate transport   → neighborhood_transport_metrics
  5. Aggregate POI access  → neighborhood_poi_metrics
  6. Normalize scores 0-100 → neighborhood_metric_scores
  7. Set coverage flags      → neighborhood_metric_coverage
  8. Refresh materialized view urban_metrics_by_district

Usage:
  python scripts/ingest_distritos_municipais.py --gpkg geoportal_distrito_municipal_v2.gpkg
  python scripts/aggregate_geo_metrics.py [--city-code SAO_PAULO] [--dry-run]

Requirements:
  DATABASE_URL env var must point to the PostGIS database.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from datetime import datetime, timezone

import sqlalchemy as sa

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

METRICS = ("transport", "green_area", "flood_risk", "safety", "poi_access")


def get_engine() -> sa.Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL not set")
        sys.exit(1)
    return sa.create_engine(url, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# 1. Slugs
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert neighborhood name to URL-safe slug."""
    import unicodedata
    normalized = unicodedata.normalize("NFD", name)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_str.lower().replace(" ", "-")
    # keep only alphanumeric and hyphens
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    # collapse multiple hyphens
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def populate_slugs(conn: sa.Connection, city_code: str, dry_run: bool) -> int:
    rows = conn.execute(
        sa.text(
            "SELECT neighborhood_code, neighborhood_name FROM neighborhood_boundaries "
            "WHERE city_code = :city_code AND slug IS NULL"
        ),
        {"city_code": city_code},
    ).fetchall()

    updated = 0
    for code, name in rows:
        slug = _slugify(name)
        if not dry_run:
            conn.execute(
                sa.text(
                    "UPDATE neighborhood_boundaries SET slug = :slug "
                    "WHERE neighborhood_code = :code"
                ),
                {"slug": slug, "code": code},
            )
        updated += 1
    log.info("Slugs: %d neighborhoods updated (dry_run=%s)", updated, dry_run)
    return updated


# ---------------------------------------------------------------------------
# 2. Green area
# ---------------------------------------------------------------------------

def aggregate_green_area(conn: sa.Connection, city_code: str, dry_run: bool) -> None:
    """
    Intersect geosampa_vegetacao_significativa polygons with neighborhood boundaries.
    Computes green_area_m2 and green_area_pct per neighborhood.
    """
    result = conn.execute(
        sa.text(
            """
            SELECT
                nb.neighborhood_code,
                nb.city_code,
                COALESCE(SUM(
                    ST_Area(ST_Transform(
                        ST_Intersection(nb.geometry, v.geometry), 3857
                    ))
                ), 0) AS green_area_m2,
                nb.area_km2
            FROM neighborhood_boundaries nb
            LEFT JOIN geosampa_vegetacao_significativa v
                ON ST_Intersects(nb.geometry, v.geometry)
            WHERE nb.city_code = :city_code
            GROUP BY nb.neighborhood_code, nb.city_code, nb.area_km2
            """
        ),
        {"city_code": city_code},
    ).fetchall()

    inputs_hash = hashlib.md5(city_code.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    for code, cc, area_m2, area_km2 in result:
        pct = (area_m2 / (area_km2 * 1_000_000) * 100) if area_km2 > 0 else 0
        if not dry_run:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO neighborhood_green_area_metrics
                        (neighborhood_code, city_code, green_area_m2, green_area_pct,
                         data_at, inputs_hash)
                    VALUES (:code, :cc, :area_m2, :pct, :now, :hash)
                    ON CONFLICT (neighborhood_code) DO UPDATE SET
                        green_area_m2 = EXCLUDED.green_area_m2,
                        green_area_pct = EXCLUDED.green_area_pct,
                        data_at = EXCLUDED.data_at,
                        inputs_hash = EXCLUDED.inputs_hash
                    """
                ),
                {"code": code, "cc": cc, "area_m2": area_m2,
                 "pct": round(pct, 4), "now": now, "hash": inputs_hash},
            )

    log.info("Green area: %d neighborhoods aggregated (dry_run=%s)", len(result), dry_run)


# ---------------------------------------------------------------------------
# 3. Flood risk
# ---------------------------------------------------------------------------

def aggregate_flood_risk(conn: sa.Connection, city_code: str, dry_run: bool) -> None:
    """
    Intersect geosampa_mancha_inundacao with neighborhood boundaries.
    """
    result = conn.execute(
        sa.text(
            """
            SELECT
                nb.neighborhood_code,
                nb.city_code,
                COALESCE(SUM(
                    ST_Area(ST_Transform(
                        ST_Intersection(nb.geometry, f.geometry), 3857
                    ))
                ), 0) AS flood_area_m2,
                nb.area_km2
            FROM neighborhood_boundaries nb
            LEFT JOIN geosampa_mancha_inundacao f
                ON ST_Intersects(nb.geometry, f.geometry)
            WHERE nb.city_code = :city_code
            GROUP BY nb.neighborhood_code, nb.city_code, nb.area_km2
            """
        ),
        {"city_code": city_code},
    ).fetchall()

    inputs_hash = hashlib.md5((city_code + "_flood").encode()).hexdigest()
    now = datetime.now(timezone.utc)

    for code, cc, area_m2, area_km2 in result:
        pct = (area_m2 / (area_km2 * 1_000_000) * 100) if area_km2 > 0 else 0
        if not dry_run:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO neighborhood_flood_risk_metrics
                        (neighborhood_code, city_code, flood_area_m2, flood_area_pct,
                         data_at, inputs_hash)
                    VALUES (:code, :cc, :area_m2, :pct, :now, :hash)
                    ON CONFLICT (neighborhood_code) DO UPDATE SET
                        flood_area_m2 = EXCLUDED.flood_area_m2,
                        flood_area_pct = EXCLUDED.flood_area_pct,
                        data_at = EXCLUDED.data_at,
                        inputs_hash = EXCLUDED.inputs_hash
                    """
                ),
                {"code": code, "cc": cc, "area_m2": area_m2,
                 "pct": round(pct, 4), "now": now, "hash": inputs_hash},
            )

    log.info("Flood risk: %d neighborhoods aggregated (dry_run=%s)", len(result), dry_run)


# ---------------------------------------------------------------------------
# 4. Transport
# ---------------------------------------------------------------------------

def aggregate_transport(conn: sa.Connection, city_code: str, dry_run: bool) -> None:
    """
    Count GeoSampa transit infrastructure (metro, trem, bus stops, terminals, corridors)
    per neighborhood boundary.
    """
    now = datetime.now(timezone.utc)

    # Run one query per infrastructure type, then combine
    result = conn.execute(
        sa.text(
            """
            SELECT
                nb.neighborhood_code,
                nb.city_code,
                nb.area_km2,
                COUNT(DISTINCT ms.geometry) AS metro_count,
                COUNT(DISTINCT ts.geometry) AS trem_count,
                COUNT(DISTINCT bs.geometry) AS bus_stop_count,
                COUNT(DISTINCT bt.geometry) AS bus_terminal_count,
                COUNT(DISTINCT bc.geometry) AS bus_corridor_count
            FROM neighborhood_boundaries nb
            LEFT JOIN geosampa_metro_stations ms
                ON ST_Contains(nb.geometry, ms.geometry)
            LEFT JOIN geosampa_trem_stations ts
                ON ST_Contains(nb.geometry, ts.geometry)
            LEFT JOIN geosampa_bus_stops bs
                ON ST_Contains(nb.geometry, bs.geometry)
            LEFT JOIN geosampa_bus_terminals bt
                ON ST_Contains(nb.geometry, bt.geometry)
            LEFT JOIN geosampa_bus_corridors bc
                ON ST_Intersects(nb.geometry, bc.geometry)
            WHERE nb.city_code = :city_code
            GROUP BY nb.neighborhood_code, nb.city_code, nb.area_km2
            """
        ),
        {"city_code": city_code},
    ).fetchall()

    for row in result:
        code, cc, area_km2, metro, trem, stops, terminals, corridors = row
        # Weighted transit density (metro/trem weighted 3x; terminals 2x; corridors 2x)
        weighted = metro * 3 + trem * 3 + terminals * 2 + corridors * 2 + stops
        density = weighted / area_km2 if area_km2 > 0 else 0
        if not dry_run:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO neighborhood_transport_metrics
                        (neighborhood_code, city_code, metro_station_count,
                         trem_station_count, bus_stop_count, bus_terminal_count,
                         bus_corridor_count, transit_density_per_km2, data_at)
                    VALUES (:code, :cc, :metro, :trem, :stops, :terminals,
                            :corridors, :density, :now)
                    ON CONFLICT (neighborhood_code) DO UPDATE SET
                        metro_station_count   = EXCLUDED.metro_station_count,
                        trem_station_count    = EXCLUDED.trem_station_count,
                        bus_stop_count        = EXCLUDED.bus_stop_count,
                        bus_terminal_count    = EXCLUDED.bus_terminal_count,
                        bus_corridor_count    = EXCLUDED.bus_corridor_count,
                        transit_density_per_km2 = EXCLUDED.transit_density_per_km2,
                        data_at               = EXCLUDED.data_at
                    """
                ),
                {"code": code, "cc": cc, "metro": metro, "trem": trem,
                 "stops": stops, "terminals": terminals, "corridors": corridors,
                 "density": round(density, 6), "now": now},
            )

    log.info("Transport: %d neighborhoods aggregated (dry_run=%s)", len(result), dry_run)


# ---------------------------------------------------------------------------
# 5. POI access (proxy from bus stop density)
# ---------------------------------------------------------------------------

def aggregate_poi_access(conn: sa.Connection, city_code: str, dry_run: bool) -> None:
    """
    POI access proxy: bus stop density per km² as first approximation.
    Will be replaced with OSM POI data in M5.
    """
    now = datetime.now(timezone.utc)
    result = conn.execute(
        sa.text(
            """
            SELECT
                neighborhood_code, city_code,
                bus_stop_count,
                transit_density_per_km2
            FROM neighborhood_transport_metrics
            WHERE city_code = :city_code
            """
        ),
        {"city_code": city_code},
    ).fetchall()

    for code, cc, stops, density in result:
        bus_density = stops / (
            conn.execute(
                sa.text("SELECT area_km2 FROM neighborhood_boundaries WHERE neighborhood_code = :c"),
                {"c": code},
            ).scalar() or 1
        )
        if not dry_run:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO neighborhood_poi_metrics
                        (neighborhood_code, city_code, bus_stop_density_per_km2,
                         poi_proxy_score, data_at)
                    VALUES (:code, :cc, :density, NULL, :now)
                    ON CONFLICT (neighborhood_code) DO UPDATE SET
                        bus_stop_density_per_km2 = EXCLUDED.bus_stop_density_per_km2,
                        data_at = EXCLUDED.data_at
                    """
                ),
                {"code": code, "cc": cc, "density": round(bus_density, 6), "now": now},
            )

    log.info("POI access: %d neighborhoods aggregated (dry_run=%s)", len(result), dry_run)


# ---------------------------------------------------------------------------
# 6. Normalize scores 0–100
# ---------------------------------------------------------------------------

def _normalize_scores(values: dict[str, float], invert: bool = False) -> dict[str, float]:
    """Min-max normalize to 0-100. If invert=True, 100 = smallest raw value."""
    if not values:
        return {}
    mn, mx = min(values.values()), max(values.values())
    span = mx - mn or 1
    result = {}
    for k, v in values.items():
        norm = (v - mn) / span * 100
        result[k] = round(100 - norm if invert else norm, 2)
    return result


def compute_scores(conn: sa.Connection, city_code: str, dry_run: bool) -> None:
    now = datetime.now(timezone.utc)

    # ---- Transport (higher density = better = higher score) ----
    rows = conn.execute(
        sa.text(
            "SELECT neighborhood_code, transit_density_per_km2 "
            "FROM neighborhood_transport_metrics WHERE city_code = :cc"
        ),
        {"cc": city_code},
    ).fetchall()
    raw = {r[0]: r[1] or 0 for r in rows}
    scores = _normalize_scores(raw, invert=False)
    _upsert_scores(conn, city_code, "transport", raw, scores, dry_run, now)

    # ---- Green area (higher pct = better) ----
    rows = conn.execute(
        sa.text(
            "SELECT neighborhood_code, green_area_pct "
            "FROM neighborhood_green_area_metrics WHERE city_code = :cc"
        ),
        {"cc": city_code},
    ).fetchall()
    raw = {r[0]: r[1] or 0 for r in rows}
    scores = _normalize_scores(raw, invert=False)
    _upsert_scores(conn, city_code, "green_area", raw, scores, dry_run, now)

    # ---- Flood risk (higher pct = MORE risk = lower score → invert) ----
    rows = conn.execute(
        sa.text(
            "SELECT neighborhood_code, flood_area_pct "
            "FROM neighborhood_flood_risk_metrics WHERE city_code = :cc"
        ),
        {"cc": city_code},
    ).fetchall()
    raw = {r[0]: r[1] or 0 for r in rows}
    scores = _normalize_scores(raw, invert=True)  # 100 = least flood risk
    _upsert_scores(conn, city_code, "flood_risk", raw, scores, dry_run, now)

    # ---- Safety (spatial join: SSP point-hull neighborhoods → PMSP districts) ----
    # SSP neighborhoods use their own neighborhood_code keys. We find SSP neighborhoods
    # whose geometry intersects each PMSP district purely by geospatial overlap
    # (no name or city_code string matching). Weighted average of robbery_density_per_km2
    # by intersection area. SSP neighborhoods from any city that spatially overlap with
    # a PMSP district boundary contribute to that district's score.
    rows = conn.execute(
        sa.text(
            """
            WITH pmsp AS (
                SELECT neighborhood_code, geometry
                FROM neighborhood_boundaries
                WHERE city_code = :cc
            ),
            sp_union AS (
                SELECT ST_Union(geometry) AS boundary
                FROM neighborhood_boundaries
                WHERE city_code = :cc
            ),
            ssp_in_sp AS (
                SELECT ssp.neighborhood_code,
                       ssp.geometry,
                       psm.robbery_density_per_km2
                FROM neighborhood_boundaries ssp
                JOIN public_safety_neighborhood_metrics psm
                    ON psm.neighborhood_code = ssp.neighborhood_code
                JOIN sp_union
                    ON ST_Intersects(ssp.geometry, sp_union.boundary)
            )
            SELECT
                pmsp.neighborhood_code,
                COALESCE(
                    SUM(
                        ssp.robbery_density_per_km2
                        * ST_Area(ST_Intersection(pmsp.geometry, ssp.geometry))
                    ) / NULLIF(
                        SUM(ST_Area(ST_Intersection(pmsp.geometry, ssp.geometry))), 0
                    ),
                    0
                ) AS weighted_robbery_density
            FROM pmsp
            LEFT JOIN ssp_in_sp ssp
                ON ST_Intersects(pmsp.geometry, ssp.geometry)
            GROUP BY pmsp.neighborhood_code
            """
        ),
        {"cc": city_code},
    ).fetchall()
    raw = {r[0]: float(r[1]) for r in rows}
    scores = _normalize_scores(raw, invert=True)  # 100 = safest
    _upsert_scores(conn, city_code, "safety", raw, scores, dry_run, now)

    # ---- POI access (higher bus density = better) ----
    rows = conn.execute(
        sa.text(
            "SELECT neighborhood_code, bus_stop_density_per_km2 "
            "FROM neighborhood_poi_metrics WHERE city_code = :cc"
        ),
        {"cc": city_code},
    ).fetchall()
    raw = {r[0]: r[1] or 0 for r in rows}
    scores = _normalize_scores(raw, invert=False)
    _upsert_scores(conn, city_code, "poi_access", raw, scores, dry_run, now)

    log.info("Scores computed for city_code=%s (dry_run=%s)", city_code, dry_run)


def _upsert_scores(
    conn: sa.Connection,
    city_code: str,
    metric: str,
    raw: dict[str, float],
    scores: dict[str, float],
    dry_run: bool,
    now: datetime,
) -> None:
    if dry_run:
        return
    sorted_codes = sorted(scores, key=lambda k: scores[k])
    ranks = {code: i + 1 for i, code in enumerate(sorted_codes)}
    n = len(sorted_codes) or 1
    for code, score in scores.items():
        conn.execute(
            sa.text(
                """
                INSERT INTO neighborhood_metric_scores
                    (neighborhood_code, city_code, metric_name, raw_value,
                     normalized_score, rank_asc, percentile, computed_at)
                VALUES (:code, :cc, :metric, :raw, :score, :rank, :pct, :now)
                ON CONFLICT (neighborhood_code, metric_name) DO UPDATE SET
                    raw_value        = EXCLUDED.raw_value,
                    normalized_score = EXCLUDED.normalized_score,
                    rank_asc         = EXCLUDED.rank_asc,
                    percentile       = EXCLUDED.percentile,
                    computed_at      = EXCLUDED.computed_at
                """
            ),
            {
                "code": code, "cc": city_code, "metric": metric,
                "raw": raw.get(code), "score": score,
                "rank": ranks[code],
                "pct": round(ranks[code] / n * 100, 2),
                "now": now,
            },
        )


# ---------------------------------------------------------------------------
# 7. Coverage flags
# ---------------------------------------------------------------------------

def compute_coverage(conn: sa.Connection, city_code: str, dry_run: bool) -> None:
    """
    Set coverage_level for each metric per neighborhood.
    - 'complete'     : data exists, area > 0 or count > 0
    - 'partial'      : data exists but limited (e.g., safety sub-register)
    - 'insufficient' : no data row or zero coverage
    """
    now = datetime.now(timezone.utc)

    codes = conn.execute(
        sa.text("SELECT neighborhood_code FROM neighborhood_boundaries WHERE city_code = :cc"),
        {"cc": city_code},
    ).scalars().all()

    transport_codes = set(
        conn.execute(
            sa.text(
                "SELECT neighborhood_code FROM neighborhood_transport_metrics "
                "WHERE city_code = :cc AND (metro_station_count + bus_stop_count) > 0"
            ),
            {"cc": city_code},
        ).scalars().all()
    )
    green_codes = set(
        conn.execute(
            sa.text(
                "SELECT neighborhood_code FROM neighborhood_green_area_metrics "
                "WHERE city_code = :cc AND green_area_m2 > 0"
            ),
            {"cc": city_code},
        ).scalars().all()
    )
    flood_codes = set(
        conn.execute(
            sa.text(
                "SELECT neighborhood_code FROM neighborhood_flood_risk_metrics "
                "WHERE city_code = :cc"  # flood 0 = valid (no flood area)
            ),
            {"cc": city_code},
        ).scalars().all()
    )
    # Safety coverage: use the already-computed score (raw_value > 0 means the spatial
    # join found SSP data overlapping this district). Always marked 'partial' due to
    # structural SSP sub-registro — never 'complete'.
    safety_codes = set(
        conn.execute(
            sa.text(
                "SELECT neighborhood_code FROM neighborhood_metric_scores "
                "WHERE city_code = :cc AND metric_name = 'safety' AND raw_value > 0"
            ),
            {"cc": city_code},
        ).scalars().all()
    )
    poi_codes = set(
        conn.execute(
            sa.text(
                "SELECT neighborhood_code FROM neighborhood_poi_metrics "
                "WHERE city_code = :cc"
            ),
            {"cc": city_code},
        ).scalars().all()
    )

    def _cov(code: str, data_set: set[str], partial: bool = False) -> tuple[str, bool]:
        if code in data_set:
            return ("partial" if partial else "complete", True)
        return ("insufficient", False)

    for code in codes:
        entries = [
            ("transport", *_cov(code, transport_codes)),
            ("green_area", *_cov(code, green_codes)),
            ("flood_risk", *_cov(code, flood_codes)),
            # Safety data has known sub-register → always partial
            ("safety", *_cov(code, safety_codes, partial=True)),
            ("poi_access", *_cov(code, poi_codes)),
        ]
        if not dry_run:
            for metric, level, has_data in entries:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO neighborhood_metric_coverage
                            (neighborhood_code, city_code, metric_name,
                             coverage_level, has_data, last_updated_at)
                        VALUES (:code, :cc, :metric, :level, :has_data, :now)
                        ON CONFLICT (neighborhood_code, metric_name) DO UPDATE SET
                            coverage_level   = EXCLUDED.coverage_level,
                            has_data         = EXCLUDED.has_data,
                            last_updated_at  = EXCLUDED.last_updated_at
                        """
                    ),
                    {"code": code, "cc": city_code, "metric": metric,
                     "level": level, "has_data": has_data, "now": now},
                )

    log.info("Coverage: %d neighborhoods × 5 metrics set (dry_run=%s)", len(codes), dry_run)


# ---------------------------------------------------------------------------
# 8. Refresh materialized view
# ---------------------------------------------------------------------------

def refresh_view(conn: sa.Connection, dry_run: bool) -> None:
    if dry_run:
        log.info("Refresh view: skipped (dry_run)")
        return
    conn.execute(sa.text("SELECT refresh_urban_metrics_by_district()"))
    log.info("urban_metrics_by_district refreshed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate GEO metrics pipeline")
    parser.add_argument("--city-code", default="SAO_PAULO", help="city_code to process")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to DB")
    args = parser.parse_args()

    engine = get_engine()
    with engine.begin() as conn:
        log.info("=== GEO metrics pipeline — city_code=%s ===", args.city_code)
        populate_slugs(conn, args.city_code, args.dry_run)
        aggregate_green_area(conn, args.city_code, args.dry_run)
        aggregate_flood_risk(conn, args.city_code, args.dry_run)
        aggregate_transport(conn, args.city_code, args.dry_run)
        aggregate_poi_access(conn, args.city_code, args.dry_run)
        compute_scores(conn, args.city_code, args.dry_run)
        compute_coverage(conn, args.city_code, args.dry_run)
        refresh_view(conn, args.dry_run)
        log.info("=== Pipeline complete ===")


if __name__ == "__main__":
    main()
