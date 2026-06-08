"""
Generate BetterPlace quarterly report — CSV and JSON.

Puxa dados do banco (urban_metrics_by_district), calcula rankings,
gera os arquivos de exportação em apps/content/public/relatorios/.
O relatório HTML é gerado pelo build Astro SSG — não há export de PDF.

Usage:
  python scripts/generate_report.py --periodo 2026-06 [--dry-run]

Requirements:
  DATABASE_URL env var deve apontar para o banco PostGIS.
  pip install sqlalchemy psycopg2-binary
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

OUTPUT_DIR = Path(__file__).parent.parent / "apps" / "content" / "public" / "relatorios"
SITE_URL = "https://www.betterplace.com.br"
LICENSE = "CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/"
METRICS = [
    ("transport", "transport_score", "Acesso a transporte público"),
    ("green_area", "green_score", "Áreas verdes"),
    ("flood_risk", "flood_risk_score", "Menor exposição a alagamento"),
    ("safety", "safety_score", "Menor densidade de ocorrências SSP-SP"),
    ("poi_access", "poi_score", "Acesso a pontos de interesse"),
]
TOP_N = 5


def get_engine() -> sa.Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL não definida")
        sys.exit(1)
    return sa.create_engine(url, pool_pre_ping=True)


def fetch_scores(conn: sa.Connection) -> list[dict]:
    """Retorna todos os scores publicáveis da view materializada."""
    rows = conn.execute(
        text("""
            SELECT
                nb.slug,
                nb.neighborhood_name AS nome,
                ROUND(COALESCE(s_transport.normalized_score, 0)::numeric, 1) AS transport_score,
                ROUND(COALESCE(s_green.normalized_score,    0)::numeric, 1) AS green_score,
                ROUND(COALESCE(s_flood.normalized_score,    0)::numeric, 1) AS flood_risk_score,
                ROUND(COALESCE(s_safety.normalized_score,   0)::numeric, 1) AS safety_score,
                ROUND(COALESCE(s_poi.normalized_score,      0)::numeric, 1) AS poi_score
            FROM neighborhood_boundaries nb
            LEFT JOIN neighborhood_metric_scores s_transport
                ON s_transport.neighborhood_code = nb.neighborhood_code AND s_transport.metric_name = 'transport'
            LEFT JOIN neighborhood_metric_scores s_green
                ON s_green.neighborhood_code = nb.neighborhood_code AND s_green.metric_name = 'green_area'
            LEFT JOIN neighborhood_metric_scores s_flood
                ON s_flood.neighborhood_code = nb.neighborhood_code AND s_flood.metric_name = 'flood_risk'
            LEFT JOIN neighborhood_metric_scores s_safety
                ON s_safety.neighborhood_code = nb.neighborhood_code AND s_safety.metric_name = 'safety'
            LEFT JOIN neighborhood_metric_scores s_poi
                ON s_poi.neighborhood_code = nb.neighborhood_code AND s_poi.metric_name = 'poi_access'
            WHERE nb.is_publishable = TRUE
            ORDER BY nb.neighborhood_name
        """)
    ).mappings().all()
    return [dict(r) for r in rows]


def build_rankings(districts: list[dict]) -> dict:
    rankings = {}
    for metric_name, score_field, label in METRICS:
        sorted_d = sorted(districts, key=lambda d: d[score_field], reverse=True)
        top = [
            {"posicao": i + 1, "slug": d["slug"], "nome": d["nome"], "score": float(d[score_field])}
            for i, d in enumerate(sorted_d[:TOP_N])
        ]
        rankings[score_field] = {"label": label, "top": top}
    return rankings


def write_csv(periodo: str, rankings: dict, today: str) -> Path:
    path = OUTPUT_DIR / f"betterplace-qualidade-urbana-sp-{periodo}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["relatorio_slug", "relatorio_periodo", "metrica", "posicao", "slug", "nome", "score"]
        )
        writer.writeheader()
        for metrica, data in rankings.items():
            for item in data["top"]:
                writer.writerow(
                    {
                        "relatorio_slug": periodo,
                        "relatorio_periodo": periodo,
                        "metrica": metrica,
                        "posicao": item["posicao"],
                        "slug": item["slug"],
                        "nome": item["nome"],
                        "score": item["score"],
                    }
                )
    log.info("CSV escrito: %s", path)
    return path


def write_json(periodo: str, rankings: dict, districts: list[dict], today: str) -> Path:
    path = OUTPUT_DIR / f"betterplace-qualidade-urbana-sp-{periodo}.json"
    payload = {
        "relatorio": {
            "slug": periodo,
            "data_publicacao": today,
            "total_distritos_analisados": len(districts),
            "licenca": LICENSE,
            "fonte": SITE_URL,
            "metodologia": f"{SITE_URL}/metodologia",
            "dataset": f"{SITE_URL}/dados",
        },
        "rankings": rankings,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("JSON escrito: %s", path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera relatório trimestral BetterPlace — CSV e JSON")
    parser.add_argument("--periodo", required=True, help="Slug do período, ex.: 2026-06")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = date.today().isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    with engine.connect() as conn:
        log.info("Buscando scores dos distritos publicáveis...")
        districts = fetch_scores(conn)
        if not districts:
            log.error("Nenhum distrito publicável. Verifique is_publishable em neighborhood_boundaries.")
            sys.exit(1)
        log.info("%d distritos encontrados", len(districts))

    rankings = build_rankings(districts)

    if args.dry_run:
        log.info("Dry-run — nenhum arquivo escrito.")
        return

    write_csv(args.periodo, rankings, today)
    write_json(args.periodo, rankings, districts, today)

    log.info("Relatório %s concluído. Arquivos em: %s", args.periodo, OUTPUT_DIR)


if __name__ == "__main__":
    main()
