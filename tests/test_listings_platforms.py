from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.listings_adapter import _build_standardized_compiled_listings
from cods_ok.quintoAndar import parse_run_dir as parse_quintoandar_run_dir
from cods_ok.vivaReal import parse_run_dir as parse_vivareal_run_dir
from core.listings_ops import scrape_zone_listings


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_standardized_compiled_listings_has_non_empty_items_for_three_platforms(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "run_123"

    _write_json(
        run_root / "vivareal" / "replay_vivareal_glue_listings_p1.json",
        {
            "search": {
                "result": {
                    "listings": [
                        {
                            "listing": {
                                "id": "vr-1",
                                "address": {"street": "Rua Teste", "city": "São Paulo", "state": "SP", "point": {"lat": -23.55, "lon": -46.63}},
                                "pricingInfos": [{"price": "2300"}],
                                "usableAreas": [55],
                                "bedrooms": 2,
                                "bathrooms": 1,
                                "parkingSpaces": 1,
                                "url": "https://www.vivareal.com.br/imovel/vr-1/",
                            }
                        }
                    ]
                }
            }
        },
    )

    _write_json(
        run_root / "quinto_andar" / "quintoandar_next_data_sample.json",
        {
            "props": {
                "pageProps": {
                    "initialState": {
                        "search": {"visibleHouses": {"pages": [["qa-1"]]}},
                        "houses": {
                            "qa-1": {
                                "totalCost": 2800,
                                "area": 48,
                                "bedrooms": 1,
                                "bathrooms": 1,
                                "parkingSpaces": 1,
                                "address": {
                                    "street": "Rua QA",
                                    "neighborhood": "Centro",
                                    "city": "São Paulo",
                                    "state": "SP",
                                    "point": {"lat": -23.56, "lon": -46.64},
                                },
                            }
                        },
                    }
                }
            }
        },
    )

    _write_json(
        run_root / "zapimoveis" / "replay_zapimoveis_glue_listings_p1.json",
        {
            "search": {
                "result": {
                    "listings": [
                        {
                            "listing": {
                                "id": "zap-1",
                                "address": {"street": "Rua ZAP", "city": "São Paulo", "state": "SP", "point": {"lat": -23.57, "lon": -46.65}},
                                "pricingInfos": [{"price": "3100"}],
                                "usableAreas": [62],
                                "bedrooms": 2,
                                "bathrooms": 2,
                                "parkingSpaces": 1,
                                "url": "https://www.zapimoveis.com.br/imovel/zap-1/",
                            }
                        }
                    ]
                }
            }
        },
    )

    out_file = _build_standardized_compiled_listings(run_root)
    payload = json.loads(out_file.read_text(encoding="utf-8"))

    counts = payload.get("platform_counts") or {}
    assert int(counts.get("vivareal") or 0) > 0
    assert int(counts.get("quinto_andar") or 0) > 0
    assert int(counts.get("zapimoveis") or 0) > 0


def test_scrape_zone_listings_fails_when_any_required_platform_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run_x"
    streets_path = run_dir / "zones" / "detail" / "zone-1" / "streets.json"
    _write_json(streets_path, {"streets": ["Rua Exemplo"]})

    monkeypatch.setattr("core.listings_ops.get_zone_feature", lambda *_args, **_kwargs: {"type": "Feature", "properties": {}})
    monkeypatch.setattr("core.listings_ops.zone_centroid_lonlat", lambda *_args, **_kwargs: (-46.63, -23.55))

    def fake_run_listings_all(*_args, **kwargs):
        out_dir = kwargs["out_dir"]
        run_root = out_dir / "runs" / "run_fake"
        _write_json(
            run_root / "compiled_listings_parsed.json",
            {
                "items": [
                    {"platform": "vivareal", "listing_id": "v1", "address": "Rua Exemplo, São Paulo, SP"},
                    {"platform": "quinto_andar", "listing_id": "q1", "address": "Rua Exemplo, São Paulo, SP"},
                ],
                "platform_counts": {"vivareal": 1, "quinto_andar": 1, "zapimoveis": 0},
            },
        )
        return run_root

    monkeypatch.setattr("core.listings_ops.run_listings_all", fake_run_listings_all)

    with pytest.raises(RuntimeError, match="plataformas sem resultados"):
        scrape_zone_listings(
            run_dir=run_dir,
            zone_uid="zone-1",
            params={"listing_mode": "rent", "require_all_listing_platforms": True},
        )


def test_vivareal_parser_accepts_recommendations_payload(tmp_path: Path) -> None:
    platform_dir = tmp_path / "vivareal"
    _write_json(
        platform_dir / "any_capture.json",
        {
            "recommendations": [
                {
                    "scores": [
                        {
                            "listing": {
                                "listing": {
                                    "id": "vr-rec-1",
                                    "address": {
                                        "street": "Rua Recomendada",
                                        "city": "São Paulo",
                                        "state": "SP",
                                        "point": {"lat": -23.5, "lon": -46.6},
                                    },
                                    "pricingInfos": [{"price": "4500"}],
                                    "usableAreas": [70],
                                    "bedrooms": [2],
                                    "bathrooms": [2],
                                    "parkingSpaces": [1],
                                    "url": "/imovel/vr-rec-1/",
                                }
                            }
                        }
                    ]
                }
            ]
        },
    )

    items = parse_vivareal_run_dir(platform_dir)
    assert len(items) == 1
    assert items[0]["platform"] == "vivareal"


def test_quintoandar_parser_accepts_pages_as_dict(tmp_path: Path) -> None:
    platform_dir = tmp_path / "quinto_andar"
    _write_json(
        platform_dir / "quintoandar_next_data_any.json",
        {
            "props": {
                "pageProps": {
                    "initialState": {
                        "search": {"visibleHouses": {"pages": {"0": ["qa-dict-1"]}}},
                        "houses": {
                            "qa-dict-1": {
                                "id": "qa-dict-1",
                                "totalCost": 3200,
                                "area": 52,
                                "bedrooms": 2,
                                "bathrooms": 1,
                                "parkingSpaces": 1,
                                "address": {"street": "Rua QA Dict", "city": "São Paulo", "state": "SP"},
                            }
                        },
                    }
                }
            }
        },
    )

    items = parse_quintoandar_run_dir(platform_dir)
    assert len(items) == 1
    assert items[0]["platform"] == "quinto_andar"
