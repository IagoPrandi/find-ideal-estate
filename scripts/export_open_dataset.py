"""
Export open dataset — BetterPlace Qualidade Urbana por Distrito (São Paulo).

Gera CSV, JSON e GeoJSON a partir da view materializada urban_metrics_by_district
e das geometrias em neighborhood_boundaries.

Saída: apps/content/public/dados/
  betterplace-qualidade-urbana-sp-v{VERSION}.csv
  betterplace-qualidade-urbana-sp-v{VERSION}.json
  betterplace-qualidade-urbana-sp-v{VERSION}.geojson
  dicionario-campos.json
  changelog.json

Usage:
  python scripts/export_open_dataset.py [--version 0.1] [--dry-run]

Requirements:
  DATABASE_URL env var must point to the PostGIS database.
  pip install sqlalchemy psycopg2-binary geoalchemy2
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATASET_VERSION = "0.1"
OUTPUT_DIR = Path(__file__).parent.parent / "apps" / "content" / "public" / "dados"
LICENSE = "CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/"
SOURCE_URL = "https://www.betterplace.com.br"
METODOLOGIA_URL = "https://www.betterplace.com.br/metodologia"

DICIONARIO = [
    {"campo": "dataset_version", "tipo": "string", "descricao": "Versão do dataset no formato semver simplificado.", "exemplo": "0.1"},
    {"campo": "data_atualizacao", "tipo": "string (YYYY-MM-DD)", "descricao": "Data de referência dos dados do pipeline.", "exemplo": "2026-06-06"},
    {"campo": "cidade", "tipo": "string", "descricao": "Município de referência.", "exemplo": "São Paulo"},
    {"campo": "slug", "tipo": "string", "descricao": "Identificador único do distrito em formato URL-friendly (kebab-case).", "exemplo": "vila-mariana"},
    {"campo": "nome", "tipo": "string", "descricao": "Nome do bairro ou referência popular.", "exemplo": "Vila Mariana"},
    {"campo": "distrito", "tipo": "string", "descricao": "Nome oficial do distrito municipal (IBGE/PMSP).", "exemplo": "Vila Mariana"},
    {
        "campo": "transport_score",
        "tipo": "number (0–100)",
        "descricao": "Score de acesso a transporte público. Densidade ponderada de metrô, CPTM, ônibus e terminais. Min-max normalizado. 100 = máxima cobertura relativa.",
        "fonte": "GTFS SPTrans, Metrô SP, CPTM — GeoSampa",
        "exemplo": 44.2,
    },
    {
        "campo": "green_score",
        "tipo": "number (0–100)",
        "descricao": "Score de áreas verdes. % vegetação significativa por área do distrito via ST_Intersection. Min-max normalizado. 100 = máxima cobertura vegetal relativa.",
        "fonte": "GeoSampa — vegetacao_significativa",
        "exemplo": 25.4,
    },
    {
        "campo": "flood_risk_score",
        "tipo": "number (0–100, invertido)",
        "descricao": "Score de risco de alagamento — invertido. 100 = menor exposição relativa. Calculado como % área coberta por mancha de inundação, invertido e normalizado.",
        "fonte": "GeoSampa — mancha_inundacao",
        "exemplo": 100.0,
    },
    {
        "campo": "safety_score",
        "tipo": "number (0–100, invertido)",
        "descricao": "Score de segurança pública — invertido. 100 = menor densidade de ocorrências SSP-SP. Sujeito a sub-registro estrutural.",
        "fonte": "SSP-SP — boletins de ocorrência, join espacial por distrito",
        "exemplo": 89.9,
    },
    {
        "campo": "safety_data_coverage",
        "tipo": "enum: completa | parcial | insuficiente",
        "descricao": "'parcial' indica sub-registro estrutural — interpretar com cautela. 'insuficiente' indica dado indisponível.",
        "exemplo": "parcial",
    },
    {
        "campo": "poi_score",
        "tipo": "number (0–100)",
        "descricao": "Score de acesso a POIs. Proxy via densidade de paradas de ônibus por km². Min-max normalizado.",
        "fonte": "GeoSampa — paradas de ônibus SPTrans",
        "exemplo": 45.1,
    },
]

NOTAS_GERAIS = [
    "Scores normalizados por min-max em relação ao conjunto de distritos analisados. Não comparáveis com outras cidades sem renormalização.",
    "flood_risk_score e safety_score são invertidos: valor maior = menor exposição/ocorrência relativa.",
    "Dados de preço imobiliário não incluídos nesta versão.",
    "Geometrias dos polígonos oficiais exportadas da tabela neighborhood_boundaries (GeoSampa / PMSP — EPSG:4326).",
]


def get_engine() -> sa.Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL não definida")
        sys.exit(1)
    return sa.create_engine(url, pool_pre_ping=True)


def fetch_districts(conn: sa.Connection) -> list[dict]:
    """Busca todos os distritos publicáveis da view materializada."""
    rows = conn.execute(
        text("""
            SELECT
                nb.slug,
                nb.neighborhood_name   AS nome,
                nb.neighborhood_name   AS distrito,
                'São Paulo'            AS cidade,
                ROUND(COALESCE(s_transport.normalized_score, 0)::numeric, 1)   AS transport_score,
                ROUND(COALESCE(s_green.normalized_score,    0)::numeric, 1)    AS green_score,
                ROUND(COALESCE(s_flood.normalized_score,    0)::numeric, 1)    AS flood_risk_score,
                ROUND(COALESCE(s_safety.normalized_score,   0)::numeric, 1)    AS safety_score,
                COALESCE(cov_safety.coverage_level, 'insuficiente')             AS safety_data_coverage,
                ROUND(COALESCE(s_poi.normalized_score,      0)::numeric, 1)    AS poi_score,
                CURRENT_DATE::text                                              AS data_atualizacao
            FROM neighborhood_boundaries nb
            LEFT JOIN neighborhood_metric_scores s_transport
                ON s_transport.neighborhood_code = nb.neighborhood_code
                AND s_transport.metric_name = 'transport'
            LEFT JOIN neighborhood_metric_scores s_green
                ON s_green.neighborhood_code = nb.neighborhood_code
                AND s_green.metric_name = 'green_area'
            LEFT JOIN neighborhood_metric_scores s_flood
                ON s_flood.neighborhood_code = nb.neighborhood_code
                AND s_flood.metric_name = 'flood_risk'
            LEFT JOIN neighborhood_metric_scores s_safety
                ON s_safety.neighborhood_code = nb.neighborhood_code
                AND s_safety.metric_name = 'safety'
            LEFT JOIN neighborhood_metric_scores s_poi
                ON s_poi.neighborhood_code = nb.neighborhood_code
                AND s_poi.metric_name = 'poi_access'
            LEFT JOIN neighborhood_metric_coverage cov_safety
                ON cov_safety.neighborhood_code = nb.neighborhood_code
                AND cov_safety.metric_name = 'safety'
            WHERE nb.is_publishable = TRUE
            ORDER BY nb.neighborhood_name
        """)
    ).mappings().all()
    return [dict(r) for r in rows]


def fetch_geometries(conn: sa.Connection) -> dict[str, str]:
    """Retorna geometrias GeoJSON por slug."""
    rows = conn.execute(
        text("""
            SELECT slug,
                   ST_AsGeoJSON(ST_Transform(geometry, 4326))::json AS geom
            FROM neighborhood_boundaries
            WHERE is_publishable = TRUE
        """)
    ).mappings().all()
    return {r["slug"]: r["geom"] for r in rows}


def write_csv(districts: list[dict], version: str, today: str) -> Path:
    path = OUTPUT_DIR / f"betterplace-qualidade-urbana-sp-v{version}.csv"
    fields = [
        "dataset_version", "data_atualizacao", "cidade", "slug", "nome", "distrito",
        "transport_score", "green_score", "flood_risk_score", "safety_score",
        "safety_data_coverage", "poi_score",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for d in districts:
            writer.writerow({
                "dataset_version": version,
                "data_atualizacao": d["data_atualizacao"],
                "cidade": d["cidade"],
                "slug": d["slug"],
                "nome": d["nome"],
                "distrito": d["distrito"],
                "transport_score": d["transport_score"],
                "green_score": d["green_score"],
                "flood_risk_score": d["flood_risk_score"],
                "safety_score": d["safety_score"],
                "safety_data_coverage": d["safety_data_coverage"],
                "poi_score": d["poi_score"],
            })
    log.info("CSV escrito: %s (%d linhas)", path, len(districts))
    return path


def write_json(districts: list[dict], version: str, today: str) -> Path:
    path = OUTPUT_DIR / f"betterplace-qualidade-urbana-sp-v{version}.json"
    payload = {
        "versao": version,
        "data_atualizacao": today,
        "cidade": "São Paulo",
        "unidade": "distrito_oficial",
        "total_distritos": len(districts),
        "licenca": LICENSE,
        "fonte": SOURCE_URL,
        "metodologia": METODOLOGIA_URL,
        "notas": NOTAS_GERAIS,
        "distritos": [
            {
                "slug": d["slug"],
                "nome": d["nome"],
                "distrito": d["distrito"],
                "cidade": d["cidade"],
                "transport_score": float(d["transport_score"]),
                "green_score": float(d["green_score"]),
                "flood_risk_score": float(d["flood_risk_score"]),
                "safety_score": float(d["safety_score"]),
                "safety_data_coverage": d["safety_data_coverage"],
                "poi_score": float(d["poi_score"]),
                "data_atualizacao": d["data_atualizacao"],
            }
            for d in districts
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("JSON escrito: %s (%d distritos)", path, len(districts))
    return path


def write_geojson(districts: list[dict], geometries: dict[str, str], version: str, today: str) -> Path:
    path = OUTPUT_DIR / f"betterplace-qualidade-urbana-sp-v{version}.geojson"
    features = []
    for d in districts:
        geom = geometries.get(d["slug"])
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "slug": d["slug"],
                "nome": d["nome"],
                "distrito": d["distrito"],
                "transport_score": float(d["transport_score"]),
                "green_score": float(d["green_score"]),
                "flood_risk_score": float(d["flood_risk_score"]),
                "safety_score": float(d["safety_score"]),
                "safety_data_coverage": d["safety_data_coverage"],
                "poi_score": float(d["poi_score"]),
                "data_atualizacao": d["data_atualizacao"],
            },
        })
    payload = {
        "type": "FeatureCollection",
        "metadata": {
            "versao": version,
            "data_atualizacao": today,
            "cidade": "São Paulo",
            "unidade": "distrito_oficial",
            "licenca": LICENSE,
            "fonte": SOURCE_URL,
            "metodologia": METODOLOGIA_URL,
            "crs": "EPSG:4326",
            "nota_geometria": "Polígonos oficiais: GeoSampa / PMSP — geoportal_distrito_municipal_v2.gpkg.",
        },
        "features": features,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("GeoJSON escrito: %s (%d features)", path, len(features))
    return path


def write_dicionario(today: str) -> Path:
    path = OUTPUT_DIR / "dicionario-campos.json"
    payload = {
        "versao": DATASET_VERSION,
        "data_atualizacao": today,
        "descricao": "Dicionário de campos do dataset BetterPlace de Qualidade Urbana — São Paulo",
        "campos": DICIONARIO,
        "notas_gerais": NOTAS_GERAIS,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Dicionário escrito: %s", path)
    return path


def write_changelog(version: str, today: str, total: int) -> Path:
    path = OUTPUT_DIR / "changelog.json"
    entry = {
        "versao": version,
        "data": today,
        "tipo": "atualização" if path.exists() else "lançamento",
        "total_distritos": total,
        "descricao": f"Exportação automática via export_open_dataset.py — pipeline GeoSampa + SSP-SP.",
    }
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing.setdefault("changelog", []).insert(0, entry)
        payload = existing
    else:
        payload = {
            "dataset": "BetterPlace — Qualidade Urbana por Distrito (São Paulo)",
            "changelog": [entry],
        }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Changelog atualizado: %s", path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta dataset aberto BetterPlace")
    parser.add_argument("--version", default=DATASET_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = date.today().isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    with engine.connect() as conn:
        log.info("Buscando distritos publicáveis...")
        districts = fetch_districts(conn)
        if not districts:
            log.error("Nenhum distrito publicável encontrado. Verifique is_publishable na tabela neighborhood_boundaries.")
            sys.exit(1)
        log.info("%d distritos encontrados", len(districts))

        log.info("Buscando geometrias...")
        geometries = fetch_geometries(conn)
        log.info("%d geometrias encontradas", len(geometries))

    if args.dry_run:
        log.info("Dry-run — nenhum arquivo escrito.")
        return

    write_csv(districts, args.version, today)
    write_json(districts, args.version, today)
    write_geojson(districts, geometries, args.version, today)
    write_dicionario(today)
    write_changelog(args.version, today, len(districts))

    log.info("Export concluído. Arquivos em: %s", OUTPUT_DIR)


if __name__ == "__main__":
    main()
