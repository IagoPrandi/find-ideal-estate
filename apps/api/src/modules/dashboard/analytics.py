from __future__ import annotations

import csv
from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import UUID

from core.db import get_engine
from modules.public_safety.classification import public_safety_group_case_sql
from modules.public_safety.standardization import (
    normalize_location_display_name,
    normalized_location_name_sql,
)
from sqlalchemy import text

_JOURNEY_SCOPE_NOTE = (
    "A base atual nao inclui malha oficial de bairros para seguranca e ambiente; "
    "os rankings desta pagina usam as zonas geradas e persistidas nesta jornada."
)

_SQUARE_METERS_PER_KM2 = 1_000_000.0

_SAFETY_SCOPE_NOTE = (
    "As taxas e o ranking desta tela usam densidade de ocorrencias por km² nas zonas geradas nesta jornada."
)

_SAFETY_ZONE_NEIGHBORHOOD_SCOPE_NOTE = (
    "O ranking abaixo usa densidade de roubos por km² calculada sobre o poligono convexo formado pelos pontos SSP de cada bairro com pelo menos 3 pontos georreferenciados. "
    "Os nomes de cidade e bairro sao normalizados para evitar duplicidade por grafia e formatacao; sem filtro de cidade, a lista considera todas as cidades disponiveis."
)

_OBSERVASAMPA_INDICATORS_PATH = Path(__file__).resolve().parents[5] / "data_cache" / "observasampa" / "ObservaSampaDadosAbertosIndicadoresCSV.csv"
_OBSERVASAMPA_TOTAL_POPULATION_LABEL = "População total"

_ADDRESS_STREET_PREFIXES = (
    "rua",
    "r.",
    "avenida",
    "av.",
    "alameda",
    "travessa",
    "tv.",
    "praca",
    "praça",
    "rodovia",
    "estrada",
    "largo",
    "viaduto",
    "acesso",
)
_PARSED_ADDRESS_CTE = """
WITH address_parts AS (
    SELECT
        p.id AS property_id,
        p.address_normalized,
        regexp_split_to_array(
            regexp_replace(COALESCE(p.address_normalized, ''), '\\s*,\\s*', ',', 'g'),
            ','
        ) AS parts
    FROM properties p
),
parsed_addresses AS (
    SELECT
        property_id,
        address_normalized,
        CASE
            WHEN COALESCE(array_length(parts, 1), 0) >= 2
            THEN NULLIF(BTRIM(parts[array_length(parts, 1) - 1]), '')
            ELSE NULL
        END AS city_name,
        CASE
            WHEN COALESCE(array_length(parts, 1), 0) >= 2
              AND NULLIF(BTRIM(parts[array_length(parts, 1)]), '') ~ '^[A-Z]{2}$'
            THEN NULLIF(BTRIM(parts[array_length(parts, 1)]), '')
            ELSE NULL
        END AS state_code,
        CASE
            WHEN COALESCE(array_length(parts, 1), 0) >= 4
            THEN NULLIF(BTRIM(parts[array_length(parts, 1) - 2]), '')
            WHEN COALESCE(array_length(parts, 1), 0) = 3
              AND NULLIF(BTRIM(parts[3]), '') ~ '^[A-Z]{2}$'
              AND NULLIF(BTRIM(parts[1]), '') !~* '^(Rua|R\\.?|Avenida|Av\\.?|Alameda|Travessa|Tv\\.?|Pra[cç]a|Rodovia|Estrada|Largo|Viaduto|Acesso)$'
            THEN NULLIF(BTRIM(parts[1]), '')
            ELSE NULL
        END AS neighborhood_name
    FROM address_parts
)
"""


def parse_address_components(address: str | None) -> dict[str, str | None]:
    if not address:
        return {"neighborhood_name": None, "city_name": None, "state_code": None}

    parts = [part.strip() for part in address.split(",") if part.strip()]
    if len(parts) < 2:
        return {"neighborhood_name": None, "city_name": None, "state_code": None}

    last_part = parts[-1]
    has_state = len(last_part) == 2 and last_part.isalpha() and last_part.upper() == last_part
    state_code = last_part if has_state else None
    city_name = parts[-2] if len(parts) >= 2 else None
    neighborhood_name: str | None = None

    if len(parts) >= 4:
        neighborhood_name = parts[-3]
    elif len(parts) == 3 and has_state:
        first_part = parts[0].lower()
        if not any(first_part.startswith(prefix) for prefix in _ADDRESS_STREET_PREFIXES):
            neighborhood_name = parts[0]

    return {
        "neighborhood_name": neighborhood_name,
        "city_name": city_name,
        "state_code": state_code,
    }


def classify_flood_risk(flood_percentage: float | None) -> str:
    if flood_percentage is None or flood_percentage <= 0:
        return "Muito baixo"
    if flood_percentage < 1:
        return "Baixo"
    if flood_percentage < 3:
        return "Moderado"
    if flood_percentage < 8:
        return "Alto"
    return "Muito alto"


def build_rank_summary(
    value: float | None,
    peer_values: list[float],
    *,
    higher_is_better: bool,
    scope_label: str,
    note: str | None = None,
) -> dict[str, Any] | None:
    try:
        numeric_value = float(value) if value is not None else None
    except (TypeError, ValueError):
        numeric_value = None

    if numeric_value is None or not isfinite(numeric_value):
        return None

    filtered_peers: list[float] = []
    for peer in peer_values:
        try:
            numeric_peer = float(peer) if peer is not None else None
        except (TypeError, ValueError):
            numeric_peer = None
        if numeric_peer is not None and isfinite(numeric_peer):
            filtered_peers.append(numeric_peer)
    total = len(filtered_peers)
    if total == 0:
        return {
            "position": None,
            "total": 0,
            "percentile": None,
            "scope_label": scope_label,
            "direction": "higher_better" if higher_is_better else "lower_better",
            "note": note,
        }

    better_count = sum(1 for peer in filtered_peers if peer > numeric_value) if higher_is_better else sum(1 for peer in filtered_peers if peer < numeric_value)
    position = better_count + 1
    percentile = round(((total - better_count) / total) * 100, 2)
    return {
        "position": position,
        "total": total,
        "percentile": percentile,
        "scope_label": scope_label,
        "direction": "higher_better" if higher_is_better else "lower_better",
        "note": note,
    }


def bucket_prices(prices: list[float], search_type: str) -> list[dict[str, Any]]:
    if not prices:
        return []

    if search_type == "sale":
        buckets = [
            ("ate 500 mil", 0, 500000),
            ("500-750 mil", 500000, 750000),
            ("750 mil-1 mi", 750000, 1000000),
            ("1-1,5 mi", 1000000, 1500000),
            ("1,5 mi+", 1500000, float("inf")),
        ]
    else:
        buckets = [
            ("ate 3 mil", 0, 3000),
            ("3-5 mil", 3000, 5000),
            ("5-8 mil", 5000, 8000),
            ("8-12 mil", 8000, 12000),
            ("12 mil+", 12000, float("inf")),
        ]

    histogram: list[dict[str, Any]] = []
    for label, minimum, maximum in buckets:
        count = sum(1 for price in prices if price >= minimum and price < maximum)
        histogram.append({"label": label, "count": count})
    return histogram


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(numeric):
        return None
    return numeric


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _parse_observasampa_numeric(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "":
        return None
    normalized = normalized.replace(".", "").replace(",", ".")
    try:
        numeric = float(normalized)
    except ValueError:
        return None
    if not isfinite(numeric):
        return None
    return numeric


def _public_safety_normalized_sql(column_name: str) -> str:
    return normalized_location_name_sql(column_name)


def _normalize_location_context_name(value: str | None) -> str | None:
    return normalize_location_display_name(value)


def _resolve_location_context_match(target: str | None, candidates: list[str]) -> str | None:
    normalized_target = _normalize_location_context_name(target)
    if normalized_target is None:
        return None

    normalized_candidates = [
        (candidate, _normalize_location_context_name(candidate))
        for candidate in candidates
        if candidate
    ]
    for candidate, normalized_candidate in normalized_candidates:
        if normalized_candidate == normalized_target:
            return candidate

    best_candidate = None
    best_score = 0.0
    for candidate, normalized_candidate in normalized_candidates:
        if normalized_candidate is None:
            continue
        score = SequenceMatcher(a=normalized_target, b=normalized_candidate).ratio()
        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate if best_score >= 0.72 else None


@lru_cache(maxsize=1)
def _load_observasampa_district_population_index() -> dict[str, dict[str, Any]]:
    if not _OBSERVASAMPA_INDICATORS_PATH.exists():
        return {}

    district_index: dict[str, dict[str, Any]] = {}
    with _OBSERVASAMPA_INDICATORS_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        for row in reader:
            if len(row) < 4:
                continue
            indicator_name, territory_name, year_raw, value_raw = row[:4]
            if indicator_name != _OBSERVASAMPA_TOTAL_POPULATION_LABEL:
                continue
            if not territory_name.endswith("(Distrito)"):
                continue

            try:
                year = int(year_raw)
            except ValueError:
                continue

            population_total = _parse_observasampa_numeric(value_raw)
            if population_total is None or population_total <= 0:
                continue

            district_name = territory_name.replace("(Distrito)", "").strip()
            district_key = _normalize_location_context_name(district_name)
            if district_key is None:
                continue

            current_entry = district_index.get(district_key)
            if current_entry is None or year > int(current_entry["year"]):
                district_index[district_key] = {
                    "district_name": district_name,
                    "population_total": int(round(population_total)),
                    "year": year,
                }

    return district_index


def _build_dashboard_ranking_items(
    rows: list[dict[str, Any]],
    *,
    value_key: str,
    higher_is_better: bool,
) -> list[dict[str, Any]]:
    ranked_rows: list[dict[str, Any]] = []
    peer_values = [
        _safe_float(row.get(value_key))
        for row in rows
        if row.get("neighborhood_name")
    ]
    filtered_peer_values = [value for value in peer_values if value is not None]

    for row in rows:
        neighborhood_name = row.get("neighborhood_name")
        value = _safe_float(row.get(value_key))
        if not neighborhood_name or value is None:
            continue

        summary = build_rank_summary(
            value,
            filtered_peer_values,
            higher_is_better=higher_is_better,
            scope_label="",
        )
        ranked_rows.append(
            {
                "position": summary["position"] if summary and summary.get("position") else len(ranked_rows) + 1,
                "neighborhood_name": str(neighborhood_name),
                "city_name": str(row["city_name"]) if row.get("city_name") else None,
                "value": value,
                "yearly_change_pct": _safe_float(row.get("yearly_change_pct")),
                "is_selected": bool(row.get("is_selected")),
            }
        )

    ranked_rows.sort(
        key=lambda item: (
            int(item.get("position") or 0),
            _normalize_location_context_name(str(item.get("neighborhood_name") or "")) or str(item.get("neighborhood_name") or ""),
        )
    )
    return ranked_rows


async def fetch_zone_dashboard_analytics(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    property_id: UUID | None,
    neighborhood_name: str | None,
    city_name: str | None,
    search_type: str,
) -> dict[str, Any]:
    engine = get_engine()
    async with engine.connect() as conn:
        zone_result = await conn.execute(
            text(
                """
                SELECT
                    z.fingerprint,
                    COALESCE(ST_Area(z.isochrone_geom::geography), 0)::DOUBLE PRECISION AS zone_area_m2,
                    z.green_area_m2,
                    z.flood_area_m2
                FROM journey_zones jz
                JOIN zones z ON z.id = jz.zone_id
                WHERE jz.journey_id = :journey_id
                  AND z.fingerprint = :zone_fingerprint
                LIMIT 1
                """
            ),
            {"journey_id": journey_id, "zone_fingerprint": zone_fingerprint},
        )
        zone_row = zone_result.mappings().first()
        if zone_row is None:
            raise ValueError("Zone not found for dashboard analytics")

        selected_property_row: dict[str, Any] | None = None
        if property_id is not None:
            selected_property_result = await conn.execute(
                text(
                    """
                    WITH latest_active_prices AS (
                        SELECT
                            la.property_id,
                            MIN(snapshot.price)::DOUBLE PRECISION AS current_best_price
                        FROM listing_ads la
                        JOIN LATERAL (
                            SELECT ls.price
                            FROM listing_snapshots ls
                            WHERE ls.listing_ad_id = la.id
                              AND ls.price IS NOT NULL
                              AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                            ORDER BY ls.observed_at DESC
                            LIMIT 1
                        ) snapshot ON TRUE
                        WHERE la.is_active = TRUE
                          AND la.advertised_usage_type = :search_type
                        GROUP BY la.property_id
                    )
                    SELECT
                        p.id,
                        p.address_normalized,
                        p.area_m2,
                        lap.current_best_price
                    FROM properties p
                    LEFT JOIN latest_active_prices lap ON lap.property_id = p.id
                    WHERE p.id = :property_id
                    LIMIT 1
                    """
                ),
                {"property_id": property_id, "search_type": search_type},
            )
            row = selected_property_result.mappings().first()
            selected_property_row = dict(row) if row is not None else None

        active_prices_result = await conn.execute(
            text(
                """
                WITH latest_active_prices AS (
                    SELECT
                        la.property_id,
                        MIN(snapshot.price)::DOUBLE PRECISION AS current_best_price
                    FROM listing_ads la
                    JOIN LATERAL (
                        SELECT ls.price
                        FROM listing_snapshots ls
                        WHERE ls.listing_ad_id = la.id
                          AND ls.price IS NOT NULL
                          AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                        ORDER BY ls.observed_at DESC
                        LIMIT 1
                    ) snapshot ON TRUE
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                    GROUP BY la.property_id
                )
                SELECT
                    p.id,
                    p.address_normalized,
                    p.area_m2,
                    lap.current_best_price
                FROM properties p
                JOIN latest_active_prices lap ON lap.property_id = p.id
                WHERE p.address_normalized IS NOT NULL
                  AND p.area_m2 IS NOT NULL
                  AND p.area_m2 > 0
                """
            ),
            {"search_type": search_type},
        )
        active_price_rows = [dict(row) for row in active_prices_result.mappings().all()]

        neighborhood_history: dict[str, float | None] = {}
        yearly_change_rank = None
        neighborhood_median_unit_price = None
        selected_vs_neighborhood_pct = None
        neighborhood_rank = None
        neighborhood_unit_price_ranking: list[dict[str, Any]] = []
        yearly_change_pct = None
        selected_city: str | None = city_name.strip() if isinstance(city_name, str) and city_name.strip() else None
        selected_neighborhood: str | None = neighborhood_name.strip() if isinstance(neighborhood_name, str) and neighborhood_name.strip() else None
        selected_state: str | None = None
        selected_price = _safe_float(selected_property_row.get("current_best_price")) if selected_property_row else None
        selected_area = _safe_float(selected_property_row.get("area_m2")) if selected_property_row else None
        selected_unit_price = _safe_ratio(selected_price, selected_area)
        property_address = selected_property_row.get("address_normalized") if selected_property_row else None
        if isinstance(property_address, str):
            address_parts = parse_address_components(property_address)
            if selected_city is None:
                selected_city = address_parts["city_name"]
            if selected_neighborhood is None:
                selected_neighborhood = address_parts["neighborhood_name"]
            selected_state = address_parts["state_code"]

        selected_neighborhood_prices: list[float] = []

        if selected_city:
            neighborhoods_in_city: dict[str, list[float]] = defaultdict(list)
            for row in active_price_rows:
                address_parts = parse_address_components(row.get("address_normalized"))
                city_name = address_parts["city_name"]
                neighborhood_name = address_parts["neighborhood_name"]
                if city_name != selected_city or not neighborhood_name:
                    continue
                current_price = _safe_float(row.get("current_best_price"))
                area_m2 = _safe_float(row.get("area_m2"))
                unit_price = _safe_ratio(current_price, area_m2)
                if unit_price is None:
                    continue
                neighborhoods_in_city[neighborhood_name].append(unit_price)

            neighborhood_medians = {
                neighborhood_name: sorted(values)[len(values) // 2]
                for neighborhood_name, values in neighborhoods_in_city.items()
                if values
            }

            yearly_changes: dict[str, float | None] = {}
            yearly_change_result = await conn.execute(
                text(
                    _PARSED_ADDRESS_CTE
                    + """
                    , neighborhood_daily_prices AS (
                        SELECT
                            pa.neighborhood_name,
                            DATE(ls.observed_at) AS day,
                            percentile_cont(0.5) WITHIN GROUP (ORDER BY ls.price)::DOUBLE PRECISION AS median_price
                        FROM listing_snapshots ls
                        JOIN listing_ads la ON la.id = ls.listing_ad_id
                        JOIN parsed_addresses pa ON pa.property_id = la.property_id
                        WHERE la.advertised_usage_type = :search_type
                          AND ls.price IS NOT NULL
                          AND ls.observed_at >= CURRENT_DATE - INTERVAL '365 days'
                          AND pa.city_name = :city_name
                          AND pa.neighborhood_name IS NOT NULL
                        GROUP BY pa.neighborhood_name, DATE(ls.observed_at)
                    ),
                    neighborhood_swings AS (
                        SELECT
                            neighborhood_name,
                            (ARRAY_AGG(median_price ORDER BY day ASC))[1] AS first_price,
                            (ARRAY_AGG(median_price ORDER BY day DESC))[1] AS last_price
                        FROM neighborhood_daily_prices
                        GROUP BY neighborhood_name
                    )
                    SELECT
                        neighborhood_name,
                        ((last_price - first_price) / NULLIF(first_price, 0)) * 100.0 AS yearly_change_pct
                    FROM neighborhood_swings
                    WHERE first_price IS NOT NULL
                      AND last_price IS NOT NULL
                    """
                ),
                {"search_type": search_type, "city_name": selected_city},
            )
            yearly_changes = {
                row["neighborhood_name"]: _safe_float(row["yearly_change_pct"])
                for row in yearly_change_result.mappings().all()
                if row["neighborhood_name"]
            }

            resolved_price_neighborhood_name = _resolve_location_context_match(
                selected_neighborhood,
                list(neighborhood_medians.keys()),
            )
            provisional_ranking_items = _build_dashboard_ranking_items(
                [
                    {
                        "neighborhood_name": current_neighborhood_name,
                        "unit_price": median_value,
                        "yearly_change_pct": yearly_changes.get(current_neighborhood_name),
                        "is_selected": False,
                    }
                    for current_neighborhood_name, median_value in neighborhood_medians.items()
                ],
                value_key="unit_price",
                higher_is_better=False,
            )
            if resolved_price_neighborhood_name:
                selected_neighborhood = resolved_price_neighborhood_name
            elif provisional_ranking_items:
                selected_neighborhood = str(provisional_ranking_items[0]["neighborhood_name"])

            neighborhood_unit_price_ranking = _build_dashboard_ranking_items(
                [
                    {
                        "neighborhood_name": current_neighborhood_name,
                        "unit_price": median_value,
                        "yearly_change_pct": yearly_changes.get(current_neighborhood_name),
                        "is_selected": current_neighborhood_name == selected_neighborhood,
                    }
                    for current_neighborhood_name, median_value in neighborhood_medians.items()
                ],
                value_key="unit_price",
                higher_is_better=False,
            )

            if selected_neighborhood and selected_neighborhood in neighborhood_medians:
                neighborhood_median_unit_price = neighborhood_medians[selected_neighborhood]
                if selected_unit_price is not None and neighborhood_median_unit_price:
                    selected_vs_neighborhood_pct = round(
                        ((selected_unit_price - neighborhood_median_unit_price) / neighborhood_median_unit_price) * 100,
                        2,
                    )
                neighborhood_rank = build_rank_summary(
                    neighborhood_median_unit_price,
                    list(neighborhood_medians.values()),
                    higher_is_better=False,
                    scope_label=f"Bairros com anuncios ativos em {selected_city}",
                )
                yearly_change_pct = yearly_changes.get(selected_neighborhood)
                if yearly_change_pct is not None:
                    yearly_change_rank = build_rank_summary(
                        yearly_change_pct,
                        [value for value in yearly_changes.values() if value is not None],
                        higher_is_better=False,
                        scope_label=f"Oscilacao de preco dos bairros em {selected_city}",
                    )
                selected_neighborhood_prices = neighborhoods_in_city.get(selected_neighborhood, [])

            if selected_neighborhood:
                neighborhood_history_result = await conn.execute(
                    text(
                        _PARSED_ADDRESS_CTE
                        + """
                        SELECT
                            DATE(ls.observed_at) AS day,
                            percentile_cont(0.5) WITHIN GROUP (ORDER BY ls.price)::DOUBLE PRECISION AS neighborhood_median_price
                        FROM listing_snapshots ls
                        JOIN listing_ads la ON la.id = ls.listing_ad_id
                        JOIN parsed_addresses pa ON pa.property_id = la.property_id
                        WHERE la.advertised_usage_type = :search_type
                          AND ls.price IS NOT NULL
                          AND ls.observed_at >= CURRENT_DATE - INTERVAL '365 days'
                          AND pa.city_name = :city_name
                          AND pa.neighborhood_name = :neighborhood_name
                        GROUP BY DATE(ls.observed_at)
                        ORDER BY DATE(ls.observed_at)
                        """
                    ),
                    {
                        "search_type": search_type,
                        "city_name": selected_city,
                        "neighborhood_name": selected_neighborhood,
                    },
                )
                neighborhood_history = {
                    row["day"].isoformat(): _safe_float(row["neighborhood_median_price"])
                    for row in neighborhood_history_result.mappings().all()
                }

        safety_group_sql = public_safety_group_case_sql("psi.category")
        normalized_category_sql = _public_safety_normalized_sql("psi.category")
        journey_metrics_result = await conn.execute(
            text(
                f"""
                WITH journey_zone_base AS (
                    SELECT
                        z.fingerprint,
                        z.isochrone_geom,
                        COALESCE(ST_Area(z.isochrone_geom::geography), 0)::DOUBLE PRECISION AS zone_area_m2,
                        COALESCE(z.green_area_m2, 0)::DOUBLE PRECISION AS green_area_m2,
                        COALESCE(z.flood_area_m2, 0)::DOUBLE PRECISION AS flood_area_m2
                    FROM journey_zones jz
                    JOIN zones z ON z.id = jz.zone_id
                    WHERE jz.journey_id = :journey_id
                )
                SELECT
                    jzb.fingerprint,
                    jzb.zone_area_m2,
                    jzb.green_area_m2,
                    jzb.flood_area_m2
                FROM journey_zone_base jzb
                """
            ),
            {"journey_id": journey_id},
        )
        journey_metrics = [dict(row) for row in journey_metrics_result.mappings().all()]

        peak_hours_result = await conn.execute(
            text(
                f"""
                SELECT
                    EXTRACT(HOUR FROM psi.occurred_at AT TIME ZONE 'America/Sao_Paulo')::INT AS hour,
                    COUNT(*)::INT AS total_count,
                    COALESCE(COUNT(*) FILTER (WHERE {normalized_category_sql} LIKE '%HOMIC%'), 0)::INT AS homicide_count,
                    COALESCE(COUNT(*) FILTER (WHERE ({safety_group_sql}) = 'robbery'), 0)::INT AS robbery_count,
                    COALESCE(COUNT(*) FILTER (WHERE ({safety_group_sql}) = 'theft'), 0)::INT AS theft_count
                FROM public_safety_incidents psi
                JOIN zones z ON z.fingerprint = :zone_fingerprint
                WHERE psi.location IS NOT NULL
                  AND z.isochrone_geom IS NOT NULL
                  AND ST_Within(psi.location, z.isochrone_geom)
                  AND psi.occurred_at >= NOW() - INTERVAL '365 days'
                GROUP BY EXTRACT(HOUR FROM psi.occurred_at AT TIME ZONE 'America/Sao_Paulo')
                ORDER BY hour ASC
                """
            ),
            {"zone_fingerprint": zone_fingerprint},
        )
        peak_hours = [dict(row) for row in peak_hours_result.mappings().all()]

        city_options_result = await conn.execute(
            text(
                """
                SELECT DISTINCT city_name
                FROM public_safety_neighborhood_metrics
                WHERE NULLIF(BTRIM(city_name), '') IS NOT NULL
                ORDER BY city_name ASC
                """
            )
        )
        city_options = [str(row[0]) for row in city_options_result.all() if row[0]]

        dominant_safety_context_result = await conn.execute(
            text(
                f"""
                SELECT
                    {normalized_location_name_sql("psi.city_name")} AS city_name,
                    {normalized_location_name_sql("psi.neighborhood_name")} AS neighborhood_name,
                    COUNT(*)::INT AS incidents_count
                FROM public_safety_incidents psi
                JOIN zones z ON z.fingerprint = :zone_fingerprint
                WHERE psi.location IS NOT NULL
                  AND z.isochrone_geom IS NOT NULL
                  AND ST_Within(psi.location, z.isochrone_geom)
                  AND psi.occurred_at >= NOW() - INTERVAL '365 days'
                GROUP BY {normalized_location_name_sql("psi.city_name")}, {normalized_location_name_sql("psi.neighborhood_name")}
                ORDER BY incidents_count DESC, city_name ASC NULLS LAST, neighborhood_name ASC NULLS LAST
                LIMIT 1
                """
            ),
            {"zone_fingerprint": zone_fingerprint},
        )
        dominant_safety_context = dominant_safety_context_result.mappings().first()

        dominant_safety_city_name = str(dominant_safety_context.get("city_name")) if dominant_safety_context and dominant_safety_context.get("city_name") else None
        dominant_safety_neighborhood_name = str(dominant_safety_context.get("neighborhood_name")) if dominant_safety_context and dominant_safety_context.get("neighborhood_name") else None

        resolved_safety_city_name = _resolve_location_context_match(selected_city, city_options)

        safety_city_name = resolved_safety_city_name

        selected_safety_neighborhood_name = dominant_safety_neighborhood_name
        neighborhood_homicide_rank = None
        homicide_density_per_km2 = None
        selected_homicide_count_365d = 0
        robbery_density_per_km2 = None
        robbery_rate_rank = None
        robbery_rate_ranking: list[dict[str, Any]] = []
        selected_robbery_count_365d = 0
        selected_theft_count_365d = 0
        robbery_to_theft_ratio = None
        neighborhood_safety_ratio_rank = None

        journey_safety_result = await conn.execute(
            text(
                f"""
                WITH journey_zone_base AS (
                    SELECT
                        z.fingerprint,
                        z.isochrone_geom,
                        COALESCE(ST_Area(z.isochrone_geom::geography), 0)::DOUBLE PRECISION AS zone_area_m2
                    FROM journey_zones jz
                    JOIN zones z ON z.id = jz.zone_id
                    WHERE jz.journey_id = :journey_id
                ),
                zone_incidents AS (
                    SELECT
                        jzb.fingerprint,
                        COUNT(*) FILTER (
                            WHERE psi.occurred_at >= NOW() - INTERVAL '365 days'
                              AND {normalized_category_sql} LIKE '%HOMIC%'
                        )::INT AS homicide_count_365d,
                        COUNT(*) FILTER (
                            WHERE psi.occurred_at >= NOW() - INTERVAL '365 days'
                              AND ({safety_group_sql}) = 'robbery'
                        )::INT AS robbery_count_365d,
                        COUNT(*) FILTER (
                            WHERE psi.occurred_at >= NOW() - INTERVAL '365 days'
                              AND ({safety_group_sql}) = 'theft'
                        )::INT AS theft_count_365d
                    FROM journey_zone_base jzb
                    LEFT JOIN public_safety_incidents psi
                      ON psi.location IS NOT NULL
                     AND jzb.isochrone_geom IS NOT NULL
                     AND ST_Within(psi.location, jzb.isochrone_geom)
                    GROUP BY jzb.fingerprint
                ),
                zone_context AS (
                    SELECT
                        jzb.fingerprint,
                        NULLIF(BTRIM(psi.neighborhood_name), '') AS neighborhood_name,
                        COUNT(*)::INT AS incidents_count,
                        ROW_NUMBER() OVER (
                            PARTITION BY jzb.fingerprint
                            ORDER BY COUNT(*) DESC, NULLIF(BTRIM(psi.neighborhood_name), '') ASC NULLS LAST
                        ) AS row_num
                    FROM journey_zone_base jzb
                    LEFT JOIN public_safety_incidents psi
                      ON psi.location IS NOT NULL
                     AND jzb.isochrone_geom IS NOT NULL
                     AND ST_Within(psi.location, jzb.isochrone_geom)
                     AND psi.occurred_at >= NOW() - INTERVAL '365 days'
                    GROUP BY jzb.fingerprint, NULLIF(BTRIM(psi.neighborhood_name), '')
                )
                SELECT
                    jzb.fingerprint,
                    jzb.zone_area_m2,
                    COALESCE(zi.homicide_count_365d, 0)::INT AS homicide_count_365d,
                    COALESCE(zi.robbery_count_365d, 0)::INT AS robbery_count_365d,
                    COALESCE(zi.theft_count_365d, 0)::INT AS theft_count_365d,
                    zc.neighborhood_name AS zone_label
                FROM journey_zone_base jzb
                LEFT JOIN zone_incidents zi ON zi.fingerprint = jzb.fingerprint
                LEFT JOIN zone_context zc ON zc.fingerprint = jzb.fingerprint AND zc.row_num = 1
                ORDER BY jzb.fingerprint ASC
                """
            ),
            {"journey_id": journey_id},
        )
        raw_journey_safety_rows = [dict(row) for row in journey_safety_result.mappings().all()]

        journey_safety_rows: list[dict[str, Any]] = []
        for index, row in enumerate(raw_journey_safety_rows, start=1):
            zone_area_m2_value = _safe_float(row.get("zone_area_m2"))
            zone_area_km2 = _safe_ratio(zone_area_m2_value, _SQUARE_METERS_PER_KM2)
            homicide_count_value = int(row.get("homicide_count_365d") or 0)
            robbery_count_value = int(row.get("robbery_count_365d") or 0)
            theft_count_value = int(row.get("theft_count_365d") or 0)
            zone_label = str(row.get("zone_label") or f"Zona {index}")
            journey_safety_rows.append(
                {
                    "fingerprint": str(row.get("fingerprint") or ""),
                    "neighborhood_name": zone_label,
                    "homicide_count_365d": homicide_count_value,
                    "robbery_count_365d": robbery_count_value,
                    "theft_count_365d": theft_count_value,
                    "homicide_density_per_km2": _safe_ratio(float(homicide_count_value), zone_area_km2),
                    "robbery_density_per_km2": _safe_ratio(float(robbery_count_value), zone_area_km2),
                    "robbery_to_theft_ratio": _safe_ratio(float(robbery_count_value), float(theft_count_value)),
                }
            )

        selected_zone_safety_metrics = next(
            (row for row in journey_safety_rows if row.get("fingerprint") == zone_fingerprint),
            None,
        )

        zone_neighborhood_safety_sql = """
            SELECT
                city_name,
                neighborhood_name,
                area_km2,
                incident_count_365d,
                homicide_count_365d,
                robbery_count_365d,
                theft_count_365d,
                homicide_density_per_km2,
                robbery_density_per_km2,
                theft_density_per_km2,
                robbery_to_theft_ratio
            FROM public_safety_neighborhood_metrics
            WHERE area_km2 > 0
        """
        zone_neighborhood_safety_params: dict[str, Any] = {}
        if safety_city_name is not None:
            zone_neighborhood_safety_sql += """
              AND city_name = :city_name_exact
            """
            zone_neighborhood_safety_params["city_name_exact"] = safety_city_name
        zone_neighborhood_safety_sql += """
            ORDER BY robbery_density_per_km2 DESC NULLS LAST, city_name ASC, neighborhood_name ASC
        """
        zone_neighborhood_safety_result = await conn.execute(
            text(zone_neighborhood_safety_sql),
            zone_neighborhood_safety_params,
        )
        raw_zone_neighborhood_safety_rows = [dict(row) for row in zone_neighborhood_safety_result.mappings().all()]
        city_neighborhood_names = [
            str(row["neighborhood_name"])
            for row in raw_zone_neighborhood_safety_rows
            if row.get("neighborhood_name")
        ]
        selected_safety_neighborhood_name = (
            _resolve_location_context_match(dominant_safety_neighborhood_name, city_neighborhood_names)
            or _resolve_location_context_match(selected_neighborhood, city_neighborhood_names)
            or next(
                (
                    str(row["neighborhood_name"])
                    for row in raw_zone_neighborhood_safety_rows
                    if row.get("neighborhood_name")
                ),
                dominant_safety_neighborhood_name,
            )
        )
        robbery_rate_ranking = _build_dashboard_ranking_items(
            [
                {
                    "city_name": str(row["city_name"]) if row.get("city_name") else None,
                    "neighborhood_name": str(row["neighborhood_name"]),
                    "robbery_density_per_km2": _safe_float(row.get("robbery_density_per_km2")),
                    "is_selected": str(row["neighborhood_name"]) == selected_safety_neighborhood_name,
                }
                for row in raw_zone_neighborhood_safety_rows
                if row.get("neighborhood_name")
            ],
            value_key="robbery_density_per_km2",
            higher_is_better=True,
        )

        if selected_zone_safety_metrics is not None:
            selected_homicide_count_365d = int(selected_zone_safety_metrics.get("homicide_count_365d") or 0)
            selected_robbery_count_365d = int(selected_zone_safety_metrics.get("robbery_count_365d") or 0)
            selected_theft_count_365d = int(selected_zone_safety_metrics.get("theft_count_365d") or 0)
            homicide_density_per_km2 = _safe_float(selected_zone_safety_metrics.get("homicide_density_per_km2"))
            robbery_density_per_km2 = _safe_float(selected_zone_safety_metrics.get("robbery_density_per_km2"))
            robbery_to_theft_ratio = _safe_float(selected_zone_safety_metrics.get("robbery_to_theft_ratio"))

            neighborhood_homicide_rank = build_rank_summary(
                homicide_density_per_km2,
                [_safe_float(row.get("homicide_density_per_km2")) for row in journey_safety_rows],
                higher_is_better=False,
                scope_label="Zonas da jornada atual",
                note=_SAFETY_SCOPE_NOTE,
            )
            robbery_rate_rank = build_rank_summary(
                robbery_density_per_km2,
                [_safe_float(row.get("robbery_density_per_km2")) for row in journey_safety_rows],
                higher_is_better=False,
                scope_label="Zonas da jornada atual",
                note=_SAFETY_SCOPE_NOTE,
            )
            neighborhood_safety_ratio_rank = build_rank_summary(
                robbery_to_theft_ratio,
                [_safe_float(row.get("robbery_to_theft_ratio")) for row in journey_safety_rows],
                higher_is_better=False,
                scope_label="Zonas da jornada atual",
                note=_SAFETY_SCOPE_NOTE,
            )

    history_dates = sorted(neighborhood_history.keys())
    price_history = [
        {
            "date": day,
            "property_price": None,
            "neighborhood_median_price": neighborhood_history.get(day),
        }
        for day in history_dates
    ]

    zone_area_m2 = _safe_float(zone_row.get("zone_area_m2"))
    green_area_m2 = _safe_float(zone_row.get("green_area_m2")) or 0.0
    flood_area_m2 = _safe_float(zone_row.get("flood_area_m2")) or 0.0
    green_percentage = _safe_ratio(green_area_m2 * 100.0, zone_area_m2)
    flood_percentage = _safe_ratio(flood_area_m2 * 100.0, zone_area_m2)

    green_peer_values = [
        _safe_ratio((_safe_float(row.get("green_area_m2")) or 0.0) * 100.0, _safe_float(row.get("zone_area_m2")))
        for row in journey_metrics
    ]
    flood_peer_values = [
        _safe_ratio((_safe_float(row.get("flood_area_m2")) or 0.0) * 100.0, _safe_float(row.get("zone_area_m2")))
        for row in journey_metrics
    ]

    selected_city_options = city_options or ([safety_city_name] if safety_city_name else [])
    price_note = None
    if not selected_city:
        price_note = "Selecione um imóvel com cidade e bairro identificados para liberar o filtro do dashboard de preço."
    elif not selected_neighborhood:
        price_note = "Não foi possível identificar um bairro com base suficiente para aplicar o filtro do dashboard de preço."

    return {
        "context": {
            "zone_fingerprint": zone_fingerprint,
            "property_id": str(property_id) if property_id is not None else None,
            "property_address": property_address,
            "neighborhood_name": selected_neighborhood,
            "city_name": selected_city,
            "state_code": selected_state,
            "selected_price": selected_price,
            "selected_unit_price": selected_unit_price,
            "zone_area_m2": zone_area_m2,
        },
        "price": {
            "neighborhood_median_unit_price": neighborhood_median_unit_price,
            "selected_vs_neighborhood_pct": selected_vs_neighborhood_pct,
            "neighborhood_unit_price_rank": neighborhood_rank,
            "neighborhood_unit_price_ranking": neighborhood_unit_price_ranking,
            "yearly_change_pct": yearly_change_pct,
            "yearly_change_rank": yearly_change_rank,
            "history": price_history,
            "price_distribution": bucket_prices(
                [price for price in selected_neighborhood_prices if price is not None],
                search_type,
            ),
            "note": price_note,
        },
        "safety": {
            "city_options": selected_city_options,
            "selected_city": safety_city_name,
            "ranking_scope_label": "Densidade de roubos por km² por bairro",
            "ranking_scope_note": _SAFETY_ZONE_NEIGHBORHOOD_SCOPE_NOTE,
            "rate_scale_base": None,
            "selected_neighborhood_name": selected_safety_neighborhood_name,
            "homicide_count_365d": selected_homicide_count_365d,
            "homicide_density_per_km2": homicide_density_per_km2,
            "homicide_rank": neighborhood_homicide_rank,
            "robbery_count_365d": selected_robbery_count_365d,
            "robbery_density_per_km2": robbery_density_per_km2,
            "robbery_rate_rank": robbery_rate_rank,
            "robbery_rate_ranking": robbery_rate_ranking,
            "theft_count_365d": selected_theft_count_365d,
            "robbery_to_theft_ratio": robbery_to_theft_ratio,
            "robbery_to_theft_rank": neighborhood_safety_ratio_rank,
            "peak_hours": peak_hours,
        },
        "environment": {
            "ranking_scope_label": "Zonas da jornada atual",
            "ranking_scope_note": _JOURNEY_SCOPE_NOTE,
            "green_area_m2": green_area_m2,
            "green_percentage": green_percentage,
            "green_rank": build_rank_summary(
                green_percentage,
                [value for value in green_peer_values if value is not None],
                higher_is_better=True,
                scope_label="Zonas da jornada atual",
                note=_JOURNEY_SCOPE_NOTE,
            ),
            "flood_area_m2": flood_area_m2,
            "flood_percentage": flood_percentage,
            "flood_risk_label": classify_flood_risk(flood_percentage),
            "flood_rank": build_rank_summary(
                flood_percentage,
                [value for value in flood_peer_values if value is not None],
                higher_is_better=False,
                scope_label="Zonas da jornada atual",
                note=_JOURNEY_SCOPE_NOTE,
            ),
        },
    }