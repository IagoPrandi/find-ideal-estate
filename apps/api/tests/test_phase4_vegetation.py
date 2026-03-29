"""Tests for vegetation grouping and cumulative green selection semantics."""

from __future__ import annotations

from modules.zones.vegetation import (
    extract_green_preferences,
    get_green_vegetation_label,
    get_included_green_vegetation_levels,
    green_vegetation_case_sql,
    green_vegetation_inclusion_sql,
    normalize_green_vegetation_level,
)


def test_normalize_green_vegetation_level_accepts_portuguese_aliases():
    assert normalize_green_vegetation_level("pouca") == "low"
    assert normalize_green_vegetation_level("média") == "medium"
    assert normalize_green_vegetation_level("muita") == "high"


def test_extract_green_preferences_reads_nested_enrichment_payload():
    enabled, level = extract_green_preferences(
        {
            "enrichments": {
                "green": True,
                "green_vegetation_level": "medium",
            }
        }
    )

    assert enabled is True
    assert level == "medium"


def test_get_green_vegetation_label_returns_human_label():
    assert get_green_vegetation_label("low") == "Pouca vegetação"
    assert get_green_vegetation_label("medium") == "Média vegetação"
    assert get_green_vegetation_label("high") == "Muita vegetação"


def test_cumulative_green_levels_match_requested_behavior():
    assert get_included_green_vegetation_levels("low") == ("low",)
    assert get_included_green_vegetation_levels("medium") == ("low", "medium")
    assert get_included_green_vegetation_levels("high") == ("low", "medium", "high")


def test_green_vegetation_case_sql_contains_expected_levels():
    sql = green_vegetation_case_sql("gv.ves_categ")

    assert "THEN 'low'" in sql
    assert "THEN 'medium'" in sql
    assert "THEN 'high'" in sql


def test_green_vegetation_inclusion_sql_matches_cumulative_levels():
    sql = green_vegetation_inclusion_sql("vegetation_level", "medium")

    assert sql == "vegetation_level IN ('low', 'medium')"