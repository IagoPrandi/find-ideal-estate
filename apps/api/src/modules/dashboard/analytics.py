from __future__ import annotations

import asyncio
import csv
from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import UUID

from core.db import get_engine
from modules.listings.cache import cache_is_usable, get_cache_record
from modules.listings.search_requests import get_latest_search_request_for_zone
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

_PRICE_ZONE_NEIGHBORHOOD_SCOPE_NOTE = (
    "O ranking abaixo usa o valor medio do m² considerando apenas os anuncios ativos visiveis no recorte atual. "
    "O bairro destacado e a posicao no ranking refletem esse mesmo subconjunto filtrado."
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


def _build_price_dashboard_filter_sql(
    *,
    spatial_scope: str,
    usage_type: str,
    min_price: float | None,
    max_price: float | None,
    min_size: float | None,
    max_size: float | None,
    price_alias: str,
    usage_alias: str | None,
    area_alias: str,
    inside_zone_alias: str,
) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if spatial_scope == "inside_zone":
        clauses.append(f"{inside_zone_alias} = TRUE")
    if usage_type != "all" and usage_alias:
        clauses.append(f"({usage_alias} IS NULL OR {usage_alias} = :price_filter_usage_type)")
        params["price_filter_usage_type"] = usage_type
    if min_price is not None:
        clauses.append(f"{price_alias} >= :price_filter_min_price")
        params["price_filter_min_price"] = min_price
    if max_price is not None:
        clauses.append(f"{price_alias} <= :price_filter_max_price")
        params["price_filter_max_price"] = max_price
    if min_size is not None:
        clauses.append(f"{area_alias} IS NOT NULL AND {area_alias} >= :price_filter_min_size")
        params["price_filter_min_size"] = min_size
    if max_size is not None:
        clauses.append(f"{area_alias} IS NOT NULL AND {area_alias} <= :price_filter_max_size")
        params["price_filter_max_size"] = max_size

    if not clauses:
        return "", params
    return "\n                  AND " + "\n                  AND ".join(clauses), params


def _price_dashboard_scope_phrase(spatial_scope: str) -> str:
    return "dentro da zona" if spatial_scope == "inside_zone" else "no recorte atual"


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
    sortable_rows: list[dict[str, Any]] = []
    for row in rows:
        neighborhood_name = row.get("neighborhood_name")
        value = _safe_float(row.get(value_key))
        if not neighborhood_name or value is None:
            continue
        sortable_rows.append(
            {
                "city_name": str(row["city_name"]) if row.get("city_name") else None,
                "neighborhood_name": str(neighborhood_name),
                "value": value,
                "yearly_change_pct": _safe_float(row.get("yearly_change_pct")),
                "listing_count": int(row.get("listing_count") or 0) if row.get("listing_count") is not None else None,
                "is_selected": bool(row.get("is_selected")),
            }
        )

    sortable_rows.sort(
        key=lambda item: (
            -float(item["value"]) if higher_is_better else float(item["value"]),
            _normalize_location_context_name(str(item.get("city_name") or "")) or str(item.get("city_name") or ""),
            _normalize_location_context_name(str(item.get("neighborhood_name") or "")) or str(item.get("neighborhood_name") or ""),
        )
    )

    ranked_rows: list[dict[str, Any]] = []
    previous_value: float | None = None
    current_position = 0
    for index, item in enumerate(sortable_rows, start=1):
        current_value = float(item["value"])
        if previous_value is None or current_value != previous_value:
            current_position = index
            previous_value = current_value
        ranked_rows.append(
            {
                "position": current_position,
                **item,
            }
        )

    return ranked_rows


async def fetch_zone_dashboard_analytics(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    property_id: UUID | None,
    neighborhood_name: str | None,
    city_name: str | None,
    page: str | None,
    search_type: str,
    usage_type: str,
    spatial_scope: str,
    address_scope: str,
    min_price: float | None,
    max_price: float | None,
    min_size: float | None,
    max_size: float | None,
) -> dict[str, Any]:
    requested_page = page or "all"
    latest_search = await get_latest_search_request_for_zone(journey_id, zone_fingerprint)
    latest_search_location = (
        str(latest_search["search_location_normalized"])
        if latest_search and latest_search.get("search_location_normalized")
        else None
    )
    latest_cache = await get_cache_record(latest_search_location)
    usable_latest_cache = latest_cache if latest_cache and cache_is_usable(latest_cache) else None
    loaded_search_observed_since = usable_latest_cache.get("created_at") if usable_latest_cache else None
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

        zone_area_m2 = _safe_float(zone_row.get("zone_area_m2"))
        requested_city: str | None = city_name.strip() if isinstance(city_name, str) and city_name.strip() else None
        selected_neighborhood: str | None = neighborhood_name.strip() if isinstance(neighborhood_name, str) and neighborhood_name.strip() else None
        selected_state: str | None = None

        if requested_page == "ambiente":
            journey_metrics_result = await conn.execute(
                text(
                    """
                    WITH journey_zone_base AS (
                        SELECT
                            z.fingerprint,
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

            return {
                "context": {
                    "zone_fingerprint": zone_fingerprint,
                    "neighborhood_name": selected_neighborhood,
                    "city_name": requested_city,
                    "state_code": selected_state,
                    "zone_area_m2": zone_area_m2,
                },
                "price": {},
                "safety": {},
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

        if requested_page == "seguranca":
            safety_group_sql = public_safety_group_case_sql("psi.category")
            normalized_category_sql = _public_safety_normalized_sql("psi.category")

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
                      AND psi.occurrence_hour_known IS TRUE
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

            safety_city_name = _resolve_location_context_match(requested_city, city_options)

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

            selected_city_options = city_options or ([safety_city_name] if safety_city_name else [])
            selected_neighborhood = selected_neighborhood or selected_safety_neighborhood_name

            return {
                "context": {
                    "zone_fingerprint": zone_fingerprint,
                    "neighborhood_name": selected_neighborhood,
                    "city_name": requested_city,
                    "state_code": selected_state,
                    "zone_area_m2": zone_area_m2,
                },
                "price": {},
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
                "environment": {},
            }

        current_price_filters_sql, current_price_filter_params = _build_price_dashboard_filter_sql(
            spatial_scope=spatial_scope,
            usage_type=usage_type,
            min_price=min_price,
            max_price=max_price,
            min_size=min_size,
            max_size=max_size,
            price_alias="lap.current_total_price",
            usage_alias=None,
            area_alias="zp.area_m2",
            inside_zone_alias="zp.inside_zone",
        )

        current_zone_prices_result = await conn.execute(
            text(
                _PARSED_ADDRESS_CTE
                + f"""
                , latest_active_prices AS (
                    SELECT
                        la.property_id,
                                                MIN(COALESCE(snapshot.price, 0) + COALESCE(snapshot.condo_fee, 0) + COALESCE(snapshot.iptu, 0))::DOUBLE PRECISION AS current_total_price
                    FROM listing_ads la
                    JOIN LATERAL (
                                                SELECT ls.price, ls.condo_fee, ls.iptu
                        FROM listing_snapshots ls
                        WHERE ls.listing_ad_id = la.id
                          AND ls.price IS NOT NULL
                          AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                        ORDER BY ls.observed_at DESC
                        LIMIT 1
                    ) snapshot ON TRUE
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                                            AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                    GROUP BY la.property_id
                ),
                recent_search_properties AS (
                    SELECT DISTINCT la.property_id
                    FROM listing_ads la
                    JOIN listing_snapshots ls ON ls.listing_ad_id = la.id
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                      AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                      AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                      AND (
                            (
                                :address_scope = 'selected_address'
                                AND (
                                    (
                                        :has_search_location = TRUE
                                        AND ls.raw_payload->>'search_location_normalized' = :search_location_normalized
                                    )
                                    OR (
                                        CAST(:observed_since AS TIMESTAMPTZ) IS NOT NULL
                                        AND COALESCE(ls.raw_payload->>'search_location_normalized', '') = ''
                                        AND ls.observed_at >= CAST(:observed_since AS TIMESTAMPTZ)
                                    )
                                )
                            )
                            OR (
                                :address_scope = 'all_addresses'
                            )
                        )
                ),
                zone_props AS (
                    SELECT
                        p.id AS property_id,
                        pa.city_name,
                        pa.neighborhood_name,
                        p.area_m2,
                        p.location,
                        CASE
                            WHEN p.location IS NULL THEN FALSE
                            ELSE ST_Within(p.location, z.isochrone_geom)
                        END AS inside_zone
                    FROM properties p
                    JOIN parsed_addresses pa ON pa.property_id = p.id
                    JOIN zones z ON z.fingerprint = :zone_fingerprint
                )
                SELECT
                    zp.property_id,
                    zp.city_name,
                    zp.neighborhood_name,
                    zp.inside_zone,
                    CASE
                        WHEN :address_scope = 'selected_address' THEN COALESCE(rsp.property_id IS NOT NULL, FALSE)
                        ELSE TRUE
                    END AS in_loaded_scope,
                    lap.current_total_price,
                    CASE
                        WHEN zp.area_m2 IS NOT NULL AND zp.area_m2 > 0
                        THEN lap.current_total_price / zp.area_m2::DOUBLE PRECISION
                        ELSE NULL
                    END AS unit_price
                FROM zone_props zp
                LEFT JOIN recent_search_properties rsp ON rsp.property_id = zp.property_id
                JOIN latest_active_prices lap ON lap.property_id = zp.property_id
                                WHERE (zp.inside_zone = TRUE OR rsp.property_id IS NOT NULL)
                  AND zp.city_name IS NOT NULL
                  AND zp.neighborhood_name IS NOT NULL
                                    {current_price_filters_sql}
                """
            ),
                        {
                            "usage_type": usage_type,
                                "search_type": search_type,
                                "address_scope": address_scope,
                                "zone_fingerprint": zone_fingerprint,
                                "has_search_location": bool(latest_search_location),
                                "search_location_normalized": latest_search_location,
                                "observed_since": loaded_search_observed_since,
                                **current_price_filter_params,
                        },
        )
        current_zone_price_rows = [dict(row) for row in current_zone_prices_result.mappings().all()]

        citywide_filters_sql, citywide_filter_params = _build_price_dashboard_filter_sql(
            spatial_scope="all",
            usage_type=usage_type,
            min_price=min_price,
            max_price=max_price,
            min_size=min_size,
            max_size=max_size,
            price_alias="lap.current_total_price",
            usage_alias=None,
            area_alias="p.area_m2",
            inside_zone_alias="FALSE",
        )

        citywide_prices_result = await conn.execute(
            text(
                _PARSED_ADDRESS_CTE
                + f"""
                , latest_active_prices AS (
                    SELECT
                        la.property_id,
                        MIN(COALESCE(snapshot.price, 0) + COALESCE(snapshot.condo_fee, 0) + COALESCE(snapshot.iptu, 0))::DOUBLE PRECISION AS current_total_price
                    FROM listing_ads la
                    JOIN LATERAL (
                        SELECT ls.price, ls.condo_fee, ls.iptu
                        FROM listing_snapshots ls
                        WHERE ls.listing_ad_id = la.id
                          AND ls.price IS NOT NULL
                          AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                        ORDER BY ls.observed_at DESC
                        LIMIT 1
                    ) snapshot ON TRUE
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                      AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                    GROUP BY la.property_id
                )
                SELECT
                    pa.city_name,
                    pa.neighborhood_name,
                    COUNT(*)::INT AS listing_count,
                    AVG(lap.current_total_price)::DOUBLE PRECISION AS avg_price,
                    AVG(
                        CASE
                            WHEN p.area_m2 IS NOT NULL AND p.area_m2 > 0
                            THEN lap.current_total_price / p.area_m2::DOUBLE PRECISION
                            ELSE NULL
                        END
                    )::DOUBLE PRECISION AS avg_unit_price
                FROM parsed_addresses pa
                JOIN properties p ON p.id = pa.property_id
                JOIN latest_active_prices lap ON lap.property_id = pa.property_id
                WHERE pa.city_name IS NOT NULL
                  AND pa.neighborhood_name IS NOT NULL
                  {citywide_filters_sql}
                GROUP BY pa.city_name, pa.neighborhood_name
                """
            ),
            {
                "usage_type": usage_type,
                "search_type": search_type,
                **citywide_filter_params,
            },
        )
        citywide_price_rows = [dict(row) for row in citywide_prices_result.mappings().all()]

        neighborhood_history: dict[str, float | None] = {}
        zone_history: dict[str, float | None] = {}
        yearly_change_rank = None
        neighborhood_average_unit_price = None
        neighborhood_rank = None
        neighborhood_unit_price_ranking: list[dict[str, Any]] = []
        yearly_change_pct = None
        selected_city: str | None = None
        requested_city = city_name.strip() if isinstance(city_name, str) and city_name.strip() else None
        selected_neighborhood = None
        selected_state = None
        zone_average_price = None
        zone_average_unit_price = None
        zone_yearly_change_pct = None
        loaded_current_zone_price_rows = [
            row for row in current_zone_price_rows if bool(row.get("in_loaded_scope", True))
        ]
        zone_active_listing_count = len(loaded_current_zone_price_rows)
        price_city_options: list[str] = []
        selected_neighborhood_prices: list[float] = []
        price_group_map: dict[tuple[str, str], dict[str, Any]] = {}
        zone_current_prices: list[float] = []
        zone_unit_prices: list[float] = []
        for row in loaded_current_zone_price_rows:
            current_city_name = str(row.get("city_name") or "")
            current_neighborhood_name = str(row.get("neighborhood_name") or "")
            if not current_city_name or not current_neighborhood_name:
                continue
            current_price = _safe_float(row.get("current_total_price"))
            unit_price = _safe_float(row.get("unit_price"))
            price_city_options.append(current_city_name)
            if current_price is not None:
                zone_current_prices.append(current_price)
            if unit_price is not None:
                zone_unit_prices.append(unit_price)

            group_key = (current_city_name, current_neighborhood_name)
            group_entry = price_group_map.setdefault(
                group_key,
                {
                    "city_name": current_city_name,
                    "neighborhood_name": current_neighborhood_name,
                    "listing_count": 0,
                    "current_prices": [],
                    "unit_prices": [],
                },
            )
            group_entry["listing_count"] += 1
            if current_price is not None:
                group_entry["current_prices"].append(current_price)
            if unit_price is not None:
                group_entry["unit_prices"].append(unit_price)

        zone_average_price = sum(zone_current_prices) / len(zone_current_prices) if zone_current_prices else None
        zone_average_unit_price = sum(zone_unit_prices) / len(zone_unit_prices) if zone_unit_prices else None
        for citywide_row in citywide_price_rows:
            citywide_city = str(citywide_row.get("city_name") or "")
            if citywide_city:
                price_city_options.append(citywide_city)
        price_city_options = sorted(set(price_city_options))
        selected_city = _resolve_location_context_match(requested_city, price_city_options)
        if selected_city is None and requested_city is not None:
            selected_city = requested_city

        zone_dominant_group_map: dict[tuple[str, str], dict[str, Any]] = {}
        for row in current_zone_price_rows:
            if not row.get("inside_zone"):
                continue
            current_city_name = str(row.get("city_name") or "")
            current_neighborhood_name = str(row.get("neighborhood_name") or "")
            if not current_city_name or not current_neighborhood_name:
                continue

            group_key = (current_city_name, current_neighborhood_name)
            group_entry = zone_dominant_group_map.setdefault(
                group_key,
                {
                    "city_name": current_city_name,
                    "neighborhood_name": current_neighborhood_name,
                    "listing_count": 0,
                },
            )
            group_entry["listing_count"] += 1

        grouped_price_rows: list[dict[str, Any]] = []
        for group_entry in price_group_map.values():
            current_prices = list(group_entry.pop("current_prices"))
            unit_prices = list(group_entry.pop("unit_prices"))
            grouped_price_rows.append(
                {
                    **group_entry,
                    "avg_price": sum(current_prices) / len(current_prices) if current_prices else None,
                    "avg_unit_price": sum(unit_prices) / len(unit_prices) if unit_prices else None,
                }
            )

        def _dominant_price_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
            if not rows:
                return None
            return sorted(
                rows,
                key=lambda item: (
                    -int(item.get("listing_count") or 0),
                    str(item.get("city_name") or ""),
                    _normalize_location_context_name(str(item.get("neighborhood_name") or ""))
                    or str(item.get("neighborhood_name") or ""),
                ),
            )[0]

        dominant_zone_price_row = _dominant_price_row(list(zone_dominant_group_map.values()))
        dominant_price_row = _dominant_price_row(grouped_price_rows)
        ranking_price_rows = [
            {
                "city_name": str(citywide_row.get("city_name") or "") or None,
                "neighborhood_name": str(citywide_row.get("neighborhood_name") or "") or None,
                "avg_price": _safe_float(citywide_row.get("avg_price")),
                "avg_unit_price": _safe_float(citywide_row.get("avg_unit_price")),
                "listing_count": int(citywide_row.get("listing_count") or 0),
            }
            for citywide_row in citywide_price_rows
            if citywide_row.get("neighborhood_name")
            and (selected_city is None or str(citywide_row.get("city_name") or "") == selected_city)
        ]
        dominant_filtered_price_row = _dominant_price_row(ranking_price_rows)

        if dominant_zone_price_row is not None:
            selected_neighborhood = str(dominant_zone_price_row.get("neighborhood_name") or "") or None
            selected_state = None
        elif dominant_price_row is not None:
            selected_neighborhood = str(dominant_price_row.get("neighborhood_name") or "") or None
            if selected_city is None:
                selected_city = str(dominant_price_row.get("city_name") or "") or None

        history_result = await conn.execute(
            text(
                _PARSED_ADDRESS_CTE
                + f"""
                , latest_active_prices AS (
                    SELECT
                        la.property_id,
                                                MIN(COALESCE(snapshot.price, 0) + COALESCE(snapshot.condo_fee, 0) + COALESCE(snapshot.iptu, 0))::DOUBLE PRECISION AS current_total_price
                    FROM listing_ads la
                    JOIN LATERAL (
                                                SELECT ls.price, ls.condo_fee, ls.iptu
                        FROM listing_snapshots ls
                        WHERE ls.listing_ad_id = la.id
                          AND ls.price IS NOT NULL
                          AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                        ORDER BY ls.observed_at DESC
                        LIMIT 1
                    ) snapshot ON TRUE
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                                            AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                    GROUP BY la.property_id
                )
                , recent_search_properties AS (
                    SELECT DISTINCT la.property_id
                    FROM listing_ads la
                    JOIN listing_snapshots ls ON ls.listing_ad_id = la.id
                    WHERE la.is_active = TRUE
                      AND la.advertised_usage_type = :search_type
                      AND (:usage_type = 'all' OR la.usage_type IS NULL OR la.usage_type = :usage_type)
                      AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                      AND (
                            (
                                :address_scope = 'selected_address'
                                AND (
                                    (
                                        :has_search_location = TRUE
                                        AND ls.raw_payload->>'search_location_normalized' = :search_location_normalized
                                    )
                                    OR (
                                        CAST(:observed_since AS TIMESTAMPTZ) IS NOT NULL
                                        AND COALESCE(ls.raw_payload->>'search_location_normalized', '') = ''
                                        AND ls.observed_at >= CAST(:observed_since AS TIMESTAMPTZ)
                                    )
                                )
                            )
                            OR (
                                :address_scope = 'all_addresses'
                            )
                        )
                )
                , zone_props AS (
                    SELECT
                        p.id AS property_id,
                        pa.city_name,
                        pa.neighborhood_name,
                        p.area_m2,
                        CASE
                            WHEN p.location IS NULL THEN FALSE
                            ELSE ST_Within(p.location, z.isochrone_geom)
                        END AS inside_zone
                    FROM properties p
                    JOIN parsed_addresses pa ON pa.property_id = p.id
                    JOIN zones z ON z.fingerprint = :zone_fingerprint
                )
                , filtered_props AS (
                    SELECT
                        zp.property_id,
                        zp.city_name,
                        zp.neighborhood_name,
                        CASE
                            WHEN :address_scope = 'selected_address' THEN COALESCE(rsp.property_id IS NOT NULL, FALSE)
                            ELSE TRUE
                        END AS in_loaded_scope
                    FROM zone_props zp
                                        LEFT JOIN recent_search_properties rsp ON rsp.property_id = zp.property_id
                    JOIN latest_active_prices lap ON lap.property_id = zp.property_id
                                        WHERE (zp.inside_zone = TRUE OR rsp.property_id IS NOT NULL)
                                            AND zp.city_name IS NOT NULL
                      AND zp.neighborhood_name IS NOT NULL
                      {current_price_filters_sql}
                )
                SELECT
                    fp.city_name,
                    fp.neighborhood_name,
                    fp.in_loaded_scope,
                    DATE(ls.observed_at) AS day,
                    AVG(COALESCE(ls.price, 0) + COALESCE(ls.condo_fee, 0) + COALESCE(ls.iptu, 0))::DOUBLE PRECISION AS average_price,
                    COUNT(*)::INT AS sample_count
                FROM filtered_props fp
                JOIN listing_ads la ON la.property_id = fp.property_id
                JOIN listing_snapshots ls ON ls.listing_ad_id = la.id
                WHERE la.is_active = TRUE
                  AND la.advertised_usage_type = :search_type
                  AND ls.price IS NOT NULL
                  AND (ls.availability_state = 'active' OR ls.availability_state IS NULL)
                  AND ls.observed_at >= CURRENT_DATE - INTERVAL '365 days'
                GROUP BY fp.city_name, fp.neighborhood_name, fp.in_loaded_scope, DATE(ls.observed_at)
                ORDER BY DATE(ls.observed_at) ASC, fp.city_name ASC, fp.neighborhood_name ASC
                """
            ),
            {
                "zone_fingerprint": zone_fingerprint,
                "search_type": search_type,
                "usage_type": usage_type,
                "address_scope": address_scope,
                "has_search_location": bool(latest_search_location),
                "search_location_normalized": latest_search_location,
                "observed_since": loaded_search_observed_since,
                **current_price_filter_params,
            },
        )
        history_rows = [dict(row) for row in history_result.mappings().all()]

        neighborhood_history_series: dict[tuple[str, str], list[tuple[str, float, int]]] = defaultdict(list)
        zone_history_weighted: dict[str, dict[str, float]] = {}
        for row in history_rows:
            current_city_name = str(row.get("city_name") or "")
            current_neighborhood_name = str(row.get("neighborhood_name") or "")
            raw_day = row.get("day")
            average_price = _safe_float(row.get("average_price"))
            sample_count = int(row.get("sample_count") or 0)
            in_loaded_scope = bool(row.get("in_loaded_scope", True))
            if not current_city_name or not current_neighborhood_name or raw_day is None or average_price is None or sample_count <= 0:
                continue

            day = raw_day.isoformat() if hasattr(raw_day, "isoformat") else str(raw_day)
            neighborhood_history_series[(current_city_name, current_neighborhood_name)].append((day, average_price, sample_count))
            if in_loaded_scope:
                weighted_day = zone_history_weighted.setdefault(day, {"weighted_sum": 0.0, "sample_count": 0.0})
                weighted_day["weighted_sum"] += average_price * sample_count
                weighted_day["sample_count"] += sample_count

        yearly_changes: dict[tuple[str, str], float | None] = {}
        for history_key, series in neighborhood_history_series.items():
            if not series:
                continue
            first_price = series[0][1]
            last_price = series[-1][1]
            if first_price > 0:
                yearly_changes[history_key] = round(((last_price - first_price) / first_price) * 100.0, 2)

        zone_history = {
            day: values["weighted_sum"] / values["sample_count"]
            for day, values in zone_history_weighted.items()
            if values.get("sample_count")
        }
        if zone_history:
            sorted_zone_days = sorted(zone_history.keys())
            first_zone_price = zone_history.get(sorted_zone_days[0])
            last_zone_price = zone_history.get(sorted_zone_days[-1])
            if first_zone_price is not None and last_zone_price is not None and first_zone_price > 0:
                zone_yearly_change_pct = round(((last_zone_price - first_zone_price) / first_zone_price) * 100.0, 2)

        selected_neighborhood_key: tuple[str, str] | None = None
        if dominant_zone_price_row is not None:
            selected_neighborhood_key = (
                str(dominant_zone_price_row.get("city_name") or ""),
                str(dominant_zone_price_row.get("neighborhood_name") or ""),
            )
        elif dominant_filtered_price_row is not None:
            selected_neighborhood_key = (
                str(dominant_filtered_price_row.get("city_name") or ""),
                str(dominant_filtered_price_row.get("neighborhood_name") or ""),
            )
        elif dominant_price_row is not None:
            selected_neighborhood_key = (
                str(dominant_price_row.get("city_name") or ""),
                str(dominant_price_row.get("neighborhood_name") or ""),
            )

        if selected_neighborhood_key is not None:
            neighborhood_history = {
                day: average_price
                for day, average_price, _sample_count in neighborhood_history_series.get(selected_neighborhood_key, [])
            }
            yearly_change_pct = yearly_changes.get(selected_neighborhood_key)

        selected_neighborhood_prices = [
            current_price
            for row in current_zone_price_rows
            for current_price in [_safe_float(row.get("current_total_price"))]
            if current_price is not None
            and selected_neighborhood_key is not None
            and str(row.get("city_name") or "") == selected_neighborhood_key[0]
            and str(row.get("neighborhood_name") or "") == selected_neighborhood_key[1]
        ]

        scope_phrase = _price_dashboard_scope_phrase(spatial_scope)
        ranking_scope_label = f"Bairros com anuncios ativos na base carregada {scope_phrase}"
        neighborhood_unit_price_ranking = _build_dashboard_ranking_items(
            [
                {
                    "city_name": str(row.get("city_name") or "") or None,
                    "neighborhood_name": str(row.get("neighborhood_name") or ""),
                    "avg_unit_price": _safe_float(row.get("avg_unit_price")),
                    "yearly_change_pct": yearly_changes.get(
                        (str(row.get("city_name") or ""), str(row.get("neighborhood_name") or ""))
                    ),
                    "listing_count": int(row.get("listing_count") or 0),
                    "is_selected": selected_neighborhood_key is not None
                    and str(row.get("city_name") or "") == selected_neighborhood_key[0]
                    and str(row.get("neighborhood_name") or "") == selected_neighborhood_key[1],
                }
                for row in ranking_price_rows
                if row.get("neighborhood_name")
            ],
            value_key="avg_unit_price",
            higher_is_better=False,
        )

        selected_neighborhood_row = next(
            (
                row
                for row in ranking_price_rows
                if selected_neighborhood_key is not None
                and str(row.get("city_name") or "") == selected_neighborhood_key[0]
                and str(row.get("neighborhood_name") or "") == selected_neighborhood_key[1]
            ),
            None,
        )
        if selected_neighborhood_row is not None:
            neighborhood_average_unit_price = _safe_float(selected_neighborhood_row.get("avg_unit_price"))
            neighborhood_rank = build_rank_summary(
                neighborhood_average_unit_price,
                [_safe_float(row.get("avg_unit_price")) for row in ranking_price_rows],
                higher_is_better=False,
                scope_label=ranking_scope_label,
                note=_PRICE_ZONE_NEIGHBORHOOD_SCOPE_NOTE,
            )
            if yearly_change_pct is not None:
                yearly_change_rank = build_rank_summary(
                    yearly_change_pct,
                    [
                        yearly_changes.get((str(row.get("city_name") or ""), str(row.get("neighborhood_name") or "")))
                        for row in ranking_price_rows
                    ],
                    higher_is_better=False,
                    scope_label=ranking_scope_label,
                    note=_PRICE_ZONE_NEIGHBORHOOD_SCOPE_NOTE,
                )

        price_history = [
            {
                "date": day,
                "zone_average_price": zone_history.get(day),
                "neighborhood_average_price": neighborhood_history.get(day),
            }
            for day in sorted(set(zone_history.keys()) | set(neighborhood_history.keys()))
        ]

        zone_area_m2 = _safe_float(zone_row.get("zone_area_m2"))
        scope_phrase = _price_dashboard_scope_phrase(spatial_scope)
        price_note = None
        if zone_active_listing_count == 0:
            price_note = f"Sem anuncios ativos {scope_phrase} para montar o dashboard de preco."
        elif selected_city and not ranking_price_rows:
            price_note = f"Sem anuncios ativos na cidade filtrada {scope_phrase}."
        elif not neighborhood_unit_price_ranking:
            price_note = f"Sem bairros suficientes com anuncios ativos {scope_phrase} para montar o ranking de preco."

        if requested_page == "preco":
            return {
                "context": {
                    "zone_fingerprint": zone_fingerprint,
                    "neighborhood_name": selected_neighborhood,
                    "city_name": selected_city,
                    "state_code": selected_state,
                    "zone_area_m2": zone_area_m2,
                },
                "price": {
                    "city_options": price_city_options,
                    "selected_city": selected_city,
                    "ranking_scope_label": "Valor medio do m² por bairro",
                    "ranking_scope_note": _PRICE_ZONE_NEIGHBORHOOD_SCOPE_NOTE,
                    "selected_neighborhood_name": selected_neighborhood,
                    "zone_average_price": zone_average_price,
                    "zone_average_unit_price": zone_average_unit_price,
                    "zone_yearly_change_pct": zone_yearly_change_pct,
                    "zone_active_listing_count": zone_active_listing_count,
                    "neighborhood_average_unit_price": neighborhood_average_unit_price,
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
                "safety": {},
                "environment": {},
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
                                    AND psi.occurrence_hour_known IS TRUE
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

    return {
        "context": {
            "zone_fingerprint": zone_fingerprint,
            "neighborhood_name": selected_neighborhood,
            "city_name": selected_city,
            "state_code": selected_state,
            "zone_area_m2": zone_area_m2,
        },
        "price": {
            "city_options": price_city_options,
            "selected_city": selected_city,
            "ranking_scope_label": "Valor medio do m² por bairro",
            "ranking_scope_note": _PRICE_ZONE_NEIGHBORHOOD_SCOPE_NOTE,
            "selected_neighborhood_name": selected_neighborhood,
            "zone_average_price": zone_average_price,
            "zone_average_unit_price": zone_average_unit_price,
            "zone_yearly_change_pct": zone_yearly_change_pct,
            "zone_active_listing_count": zone_active_listing_count,
            "neighborhood_average_unit_price": neighborhood_average_unit_price,
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


async def fetch_zone_favorite_analytics(
    *,
    journey_id: UUID,
    zone_fingerprint: str,
    search_type: str,
    usage_type: str,
) -> dict[str, Any]:
    async def _fetch_dashboard_page(page: str) -> dict[str, Any]:
        return await fetch_zone_dashboard_analytics(
            journey_id=journey_id,
            zone_fingerprint=zone_fingerprint,
            property_id=None,
            neighborhood_name=None,
            city_name=None,
            page=page,
            search_type=search_type,
            usage_type=usage_type,
            spatial_scope="inside_zone",
            address_scope="all_addresses",
            min_price=None,
            max_price=None,
            min_size=None,
            max_size=None,
        )

    price_payload, safety_payload, environment_payload = await asyncio.gather(
        _fetch_dashboard_page("preco"),
        _fetch_dashboard_page("seguranca"),
        _fetch_dashboard_page("ambiente"),
    )

    context = price_payload.get("context") or safety_payload.get("context") or environment_payload.get("context") or {}
    zone_area_m2 = _safe_float(context.get("zone_area_m2"))
    zone_area_km2 = _safe_ratio(zone_area_m2, _SQUARE_METERS_PER_KM2)
    safety = safety_payload.get("safety") or {}
    environment = environment_payload.get("environment") or {}
    homicide_density_per_km2 = _safe_float(safety.get("homicide_density_per_km2"))
    robbery_density_per_km2 = _safe_float(safety.get("robbery_density_per_km2"))
    theft_density_per_km2 = _safe_ratio(float(int(safety.get("theft_count_365d") or 0)), zone_area_km2)
    crime_density_components = [
        value
        for value in [homicide_density_per_km2, robbery_density_per_km2, theft_density_per_km2]
        if value is not None
    ]

    return {
        "context": {
            "zone_fingerprint": zone_fingerprint,
            "neighborhood_name": context.get("neighborhood_name"),
            "city_name": context.get("city_name"),
            "state_code": context.get("state_code"),
            "zone_area_m2": zone_area_m2,
        },
        "metrics": {
            "zone_average_price": _safe_float((price_payload.get("price") or {}).get("zone_average_price")),
            "zone_average_unit_price": _safe_float((price_payload.get("price") or {}).get("zone_average_unit_price")),
            "homicide_density_per_km2": homicide_density_per_km2,
            "robbery_density_per_km2": robbery_density_per_km2,
            "theft_density_per_km2": theft_density_per_km2,
            "crime_density_per_km2": sum(crime_density_components) if crime_density_components else None,
            "green_percentage": _safe_float(environment.get("green_percentage")),
            "flood_percentage": _safe_float(environment.get("flood_percentage")),
            "flood_risk_label": environment.get("flood_risk_label"),
        },
    }
