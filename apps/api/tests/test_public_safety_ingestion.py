from __future__ import annotations

import os
import sys
from datetime import time as datetime_time
from pathlib import Path

import pandas as pd

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from modules.public_safety.ingestion import (  # noqa: E402
    _prepare_incidents_dataframe,
    normalize_location_context_name,
)
from modules.public_safety.standardization import normalized_location_name_sql  # noqa: E402


def test_prepare_incidents_dataframe_keeps_city_and_neighborhood_when_present():
    dataframe = pd.DataFrame(
        {
            "DATA_DIA": ["2025-05-10"],
            "NATUREZA_APURADA": ["FURTO"],
            "LONGITUDE": [-46.63],
            "LATITUDE": [-23.55],
            "MUNICIPIO_FATO": ["São Paulo"],
            "BAIRRO": ["Bela Vista"],
        }
    )

    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=2025)

    assert dropped_rows == 0
    assert len(prepared) == 1
    assert prepared.iloc[0]["city_name"] == "SAO PAULO"
    assert prepared.iloc[0]["neighborhood_name"] == "BELA VISTA"


def test_prepare_incidents_dataframe_uses_occurrence_date_and_hour_when_available():
    dataframe = pd.DataFrame(
        {
            "DATA_DIA": ["2025-05-11"],
            "DATA_OCORRENCIA_BO": ["2025-05-10"],
            "HORA_OCORRENCIA_BO": [datetime_time(18, 30)],
            "NATUREZA_APURADA": ["ROUBO"],
            "LONGITUDE": [-46.63],
            "LATITUDE": [-23.55],
            "MUNICIPIO_FATO": ["São Paulo"],
            "BAIRRO": ["Bela Vista"],
        }
    )

    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=2025)

    assert dropped_rows == 0
    assert len(prepared) == 1
    occurred_at = prepared.iloc[0]["occurred_at"].tz_convert("America/Sao_Paulo")
    assert occurred_at.strftime("%Y-%m-%d %H:%M:%S") == "2025-05-10 18:30:00"
    assert bool(prepared.iloc[0]["occurrence_hour_known"]) is True


def test_prepare_incidents_dataframe_marks_unknown_hour_without_dropping_incident():
    dataframe = pd.DataFrame(
        {
            "DATA_OCORRENCIA_BO": ["2025-05-10"],
            "HORA_OCORRENCIA_BO": ["NULL"],
            "NATUREZA_APURADA": ["ROUBO"],
            "LONGITUDE": [-46.63],
            "LATITUDE": [-23.55],
            "MUNICIPIO_FATO": ["São Paulo"],
            "BAIRRO": ["Bela Vista"],
        }
    )

    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=2025)

    assert dropped_rows == 0
    assert len(prepared) == 1
    assert bool(prepared.iloc[0]["occurrence_hour_known"]) is False


def test_prepare_incidents_dataframe_preserves_midnight_when_it_is_explicit():
    dataframe = pd.DataFrame(
        {
            "DATA_OCORRENCIA_BO": ["2025-05-10"],
            "HORA_OCORRENCIA_BO": [datetime_time(0, 0)],
            "NATUREZA_APURADA": ["ROUBO"],
            "LONGITUDE": [-46.63],
            "LATITUDE": [-23.55],
            "MUNICIPIO_FATO": ["São Paulo"],
            "BAIRRO": ["Bela Vista"],
        }
    )

    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=2025)

    assert dropped_rows == 0
    assert len(prepared) == 1
    occurred_at = prepared.iloc[0]["occurred_at"].tz_convert("America/Sao_Paulo")
    assert occurred_at.strftime("%H:%M:%S") == "00:00:00"
    assert bool(prepared.iloc[0]["occurrence_hour_known"]) is True


def test_prepare_incidents_dataframe_falls_back_to_null_location_context_columns():
    dataframe = pd.DataFrame(
        {
            "DATA_DIA": ["2025-05-10"],
            "NATUREZA_APURADA": ["FURTO"],
            "LONGITUDE": [-46.63],
            "LATITUDE": [-23.55],
        }
    )

    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=2025)

    assert dropped_rows == 0
    assert len(prepared) == 1
    assert pd.isna(prepared.iloc[0]["city_name"])
    assert pd.isna(prepared.iloc[0]["neighborhood_name"])


def test_prepare_incidents_dataframe_drops_zero_and_out_of_state_coordinates():
    dataframe = pd.DataFrame(
        {
            "DATA_DIA": ["2025-05-10", "2025-05-10", "2025-05-10"],
            "NATUREZA_APURADA": ["FURTO", "FURTO", "FURTO"],
            "LONGITUDE": [-46.63, 0.0, -47.45],
            "LATITUDE": [-23.55, 0.0, 23.52],
            "MUNICIPIO_FATO": ["São Paulo", "Sorocaba", "Sorocaba"],
            "BAIRRO": ["Bela Vista", "Campolim", "Campolim"],
        }
    )

    prepared, dropped_rows = _prepare_incidents_dataframe(dataframe, source_year=2025)

    assert dropped_rows == 2
    assert len(prepared) == 1
    assert prepared.iloc[0]["city_name"] == "SAO PAULO"
    assert prepared.iloc[0]["neighborhood_name"] == "BELA VISTA"


def test_normalize_location_context_name_canonicalizes_case_accents_and_spacing():
    assert normalize_location_context_name("  Centro  ") == "CENTRO"
    assert normalize_location_context_name("Sé") == "SE"
    assert normalize_location_context_name("Jardim   São   Luís") == "JARDIM SAO LUIS"
    assert normalize_location_context_name(" Bela-Vista ") == "BELA VISTA"


def test_normalized_location_name_sql_uses_same_cleanup_steps_as_python_normalizer():
    expression = normalized_location_name_sql("psi.neighborhood_name")

    assert "TRANSLATE" in expression
    assert "regexp_replace" in expression
    assert "psi.neighborhood_name" in expression