"""Helpers for vegetation classification and journey green preferences."""

from __future__ import annotations

from typing import Any

GREEN_VEGETATION_LEVELS = ("low", "medium", "high")

GREEN_VEGETATION_LABELS = {
    "low": "Pouca vegetação",
    "medium": "Média vegetação",
    "high": "Muita vegetação",
}

BASE_VEGETATION_CATEGORIES_BY_LEVEL = {
    "low": (
        "Baixa cobertura arbórea, arbóreo-arbustiva e ou arborescente",
        "Vegetação herbáceo-arbustiva",
        "Agricultura",
        "Vegetação aquática flutuante",
    ),
    "medium": (
        "Vegetação herbáceo-arbustiva de várzea ou de brejo",
        "Floresta ombrófila densa secundária em estágio inicial",
        "Mista",
    ),
    "high": (
        "Média a alta cobertura arbórea, arbóreo-arbustiva e ou arborescente",
        "Floresta ombrófila densa secundária em estágio médio",
        "Maciços florestais heterogêneos e bosques urbanos",
        "Floresta paludosa e ou de várzea",
        "Maciços florestais homogêneos",
    ),
}

INCLUDED_LEVELS_BY_SELECTION = {
    "low": ("low",),
    "medium": ("low", "medium"),
    "high": ("low", "medium", "high"),
}


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def normalize_green_vegetation_level(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    alias_map = {
        "low": "low",
        "pouca": "low",
        "baixo": "low",
        "medium": "medium",
        "media": "medium",
        "média": "medium",
        "medio": "medium",
        "médio": "medium",
        "high": "high",
        "muita": "high",
        "alto": "high",
    }
    return alias_map.get(normalized)


def get_green_vegetation_label(level: str | None) -> str | None:
    if level is None:
        return None
    return GREEN_VEGETATION_LABELS.get(level)


def get_included_green_vegetation_levels(level: str | None) -> tuple[str, ...]:
    if level is None:
        return ()
    return INCLUDED_LEVELS_BY_SELECTION.get(level, ())


def extract_green_preferences(input_snapshot: Any) -> tuple[bool, str | None]:
    green_enabled = True
    green_level = None

    if isinstance(input_snapshot, dict):
        enrichments = input_snapshot.get("enrichments")
        if isinstance(enrichments, dict):
            green_enabled = _parse_bool(enrichments.get("green"), True)
            green_level = normalize_green_vegetation_level(enrichments.get("green_vegetation_level"))

        if green_level is None:
            green_level = normalize_green_vegetation_level(input_snapshot.get("green_vegetation_level"))

        green_enabled = _parse_bool(input_snapshot.get("zone_detail_include_green"), green_enabled)

    if green_enabled and green_level is None:
        green_level = "medium"

    return green_enabled, green_level


def green_vegetation_case_sql(column_sql: str) -> str:
    def quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    parts: list[str] = ["CASE"]
    for level in GREEN_VEGETATION_LEVELS:
        categories = ", ".join(quote(item) for item in BASE_VEGETATION_CATEGORIES_BY_LEVEL[level])
        parts.append(
            f"WHEN NULLIF(BTRIM(COALESCE({column_sql}, '')), '') IN ({categories}) THEN '{level}'"
        )
    parts.append("ELSE NULL END")
    return " ".join(parts)


def green_vegetation_inclusion_sql(classification_sql: str, selected_level: str | None) -> str:
    included_levels = get_included_green_vegetation_levels(selected_level)
    if not included_levels:
        return "FALSE"
    quoted_levels = ", ".join(f"'{level}'" for level in included_levels)
    return f"{classification_sql} IN ({quoted_levels})"