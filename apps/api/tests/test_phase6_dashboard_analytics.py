from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/find_ideal_estate")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MAPBOX_ACCESS_TOKEN", "test")
os.environ.setdefault("MAPTILER_API_KEY", "test")
os.environ.setdefault("VALHALLA_URL", "http://localhost:8002")
os.environ.setdefault("OTP_URL", "http://localhost:8080")

from contracts import JourneyRead, JourneyState  # noqa: E402
from modules.dashboard.analytics import (  # noqa: E402
    build_rank_summary,
    classify_flood_risk,
    parse_address_components,
)
from src.main import app  # noqa: E402


def _sample_journey() -> JourneyRead:
    return JourneyRead(
        id=uuid4(),
        user_id=None,
        anonymous_session_id="session-123",
        state=JourneyState.DRAFT,
        input_snapshot={"radius": 500},
        selected_transport_point_id=None,
        selected_zone_id=None,
        selected_property_id=None,
        last_completed_step=6,
        secondary_reference_label=None,
        secondary_reference_point=None,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        expires_at=None,
    )


def test_parse_address_components_handles_street_neighborhood_city_state():
    parsed = parse_address_components("Rua Itacema, Itaim Bibi, São Paulo, SP")

    assert parsed["neighborhood_name"] == "Itaim Bibi"
    assert parsed["city_name"] == "São Paulo"
    assert parsed["state_code"] == "SP"


def test_parse_address_components_handles_neighborhood_city_state_without_street():
    parsed = parse_address_components("Gonzaga, Santos, SP")

    assert parsed["neighborhood_name"] == "Gonzaga"
    assert parsed["city_name"] == "Santos"
    assert parsed["state_code"] == "SP"


def test_build_rank_summary_inverts_lower_better_metrics():
    summary = build_rank_summary(
        1.2,
        [1.2, 2.4, 3.6],
        higher_is_better=False,
        scope_label="Zonas da jornada atual",
    )

    assert summary is not None
    assert summary["position"] == 1
    assert summary["total"] == 3
    assert summary["direction"] == "lower_better"


def test_classify_flood_risk_uses_percentage_thresholds():
    assert classify_flood_risk(0) == "Muito baixo"
    assert classify_flood_risk(0.6) == "Baixo"
    assert classify_flood_risk(2.5) == "Moderado"
    assert classify_flood_risk(5.0) == "Alto"
    assert classify_flood_risk(12.0) == "Muito alto"


def test_get_zone_dashboard_analytics_route_returns_contract(monkeypatch):
    sample = _sample_journey()

    async def _get_journey(journey_id):
        assert journey_id == sample.id
        return sample

    async def _fetch_zone_dashboard_analytics(**kwargs):
        assert kwargs["journey_id"] == sample.id
        assert kwargs["zone_fingerprint"] == "zone-fp-1"
        return {
            "context": {
                "zone_fingerprint": "zone-fp-1",
                "property_id": str(uuid4()),
                "property_address": "Rua Itacema, Itaim Bibi, São Paulo, SP",
                "neighborhood_name": "Itaim Bibi",
                "city_name": "São Paulo",
                "state_code": "SP",
                "selected_price": 11000.0,
                "selected_unit_price": 104.76,
                "zone_area_m2": 120000.0,
            },
            "price": {
                "neighborhood_median_unit_price": 99.5,
                "selected_vs_neighborhood_pct": 5.29,
                "neighborhood_unit_price_rank": {
                    "position": 4,
                    "total": 18,
                    "percentile": 77.78,
                    "scope_label": "Bairros com anuncios ativos em São Paulo",
                    "direction": "lower_better",
                    "note": None,
                },
                "neighborhood_unit_price_ranking": [
                    {"position": 1, "neighborhood_name": "Aclimação", "value": 87.4, "is_selected": False},
                    {"position": 4, "neighborhood_name": "Itaim Bibi", "value": 99.5, "is_selected": True},
                ],
                "yearly_change_pct": -2.5,
                "yearly_change_rank": None,
                "history": [
                    {
                        "date": "2026-03-01",
                        "property_price": 11200.0,
                        "neighborhood_median_price": 10900.0,
                    }
                ],
                "price_distribution": [{"label": "ate 3 mil", "count": 0}],
                "note": None,
            },
            "safety": {
                "city_options": ["Barueri", "São Paulo"],
                "selected_city": None,
                "ranking_scope_label": "Bairros na zona analisada",
                "ranking_scope_note": "O ranking abaixo soma todas as ocorrencias registradas por bairro dentro da zona analisada. Sem filtro de cidade, a lista considera todas as cidades disponiveis; quando preenchido, restringe apenas os bairros exibidos.",
                "rate_scale_base": None,
                "selected_neighborhood_name": "Itaim Bibi",
                "homicide_count_365d": 6,
                "homicide_density_per_km2": 0.06,
                "homicide_rank": None,
                "robbery_count_365d": 996,
                "robbery_density_per_km2": 9.96,
                "robbery_rate_rank": None,
                "robbery_rate_ranking": [
                    {"position": 1, "city_name": "São Paulo", "neighborhood_name": "Sé", "value": 1280, "is_selected": False},
                    {"position": 6, "city_name": "São Paulo", "neighborhood_name": "Itaim Bibi", "value": 841, "is_selected": True},
                ],
                "theft_count_365d": 3519,
                "robbery_to_theft_ratio": 0.28,
                "robbery_to_theft_rank": None,
                "peak_hours": [{"hour": 18, "total_count": 4, "homicide_count": 0, "robbery_count": 1, "theft_count": 1}],
            },
            "environment": {
                "ranking_scope_label": "Zonas da jornada atual",
                "ranking_scope_note": "nota",
                "green_area_m2": 32000.0,
                "green_percentage": 26.6,
                "green_rank": None,
                "flood_area_m2": 1200.0,
                "flood_percentage": 1.0,
                "flood_risk_label": "Moderado",
                "flood_rank": None,
            },
        }

    monkeypatch.setattr("api.routes.journeys.get_journey", _get_journey)
    monkeypatch.setattr("api.routes.journeys.fetch_zone_dashboard_analytics", _fetch_zone_dashboard_analytics)

    with TestClient(app) as client:
        response = client.get(f"/journeys/{sample.id}/zones/zone-fp-1/dashboard-analytics?search_type=rent")

    assert response.status_code == 200
    body = response.json()
    assert body["context"]["city_name"] == "São Paulo"
    assert body["price"]["neighborhood_median_unit_price"] == 99.5
    assert body["price"]["neighborhood_unit_price_ranking"][1]["neighborhood_name"] == "Itaim Bibi"
    assert body["safety"]["rate_scale_base"] is None
    assert body["safety"]["robbery_density_per_km2"] == 9.96
    assert body["safety"]["robbery_rate_ranking"][1]["city_name"] == "São Paulo"
    assert body["environment"]["flood_risk_label"] == "Moderado"