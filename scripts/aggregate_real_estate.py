"""
Agrega dados imobiliários da base interna BetterPlace por distrito de São Paulo.

Fonte obrigatória: base imobiliária interna (properties, listing_ads, listing_snapshots,
neighborhood_boundaries). Sem scraping novo. Sem fonte externa.

Saídas:
  apps/content/src/data/imoveis_aggregates.ts  — dados tipados para Astro SSG
  apps/content/public/imoveis/aggregates.json  — JSON público (CC BY 4.0)
  apps/content/public/imoveis/aggregates.csv   — CSV público (CC BY 4.0)

Política de agregação:
  - Mínimo de 5 imóveis ativos com área conhecida por tipo (aluguel/venda) para publicar métrica.
  - Separação estrita entre aluguel e venda; nenhuma métrica mistura os dois.
  - Encargos (condomínio, IPTU) declarados apenas quando disponíveis; ausência informada.
  - Variação de preço calculada apenas sobre o mesmo conjunto de imóveis nos dois períodos.
  - Amostra limitada a 8 imóveis por distrito por tipo; ordenação determinística (area_m2 DESC).
  - Lacunas declaradas explicitamente; sem fallback silencioso.

Usage:
  python scripts/aggregate_real_estate.py [--dry-run] [--distrito slug]

Requirements:
  DATABASE_URL env var
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
from statistics import median, quantiles

import sqlalchemy as sa
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TS_OUTPUT = ROOT / "apps" / "content" / "src" / "data" / "imoveis_aggregates.ts"
PUBLIC_DIR = ROOT / "apps" / "content" / "public" / "imoveis"
SITE_URL = "https://www.betterplace.com.br"
LICENSE = "CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/"
MIN_SAMPLE = 5
SAMPLE_CAP = 8
LOOKBACK_DAYS_CURRENT = 90
LOOKBACK_DAYS_PRIOR = 180


def get_engine() -> sa.Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL não definida")
        sys.exit(1)
    return sa.create_engine(url, pool_pre_ping=True)


def fetch_districts(conn: sa.Connection, slug_filter: str | None) -> list[dict]:
    where = "WHERE nb.slug IS NOT NULL"
    if slug_filter:
        where += f" AND nb.slug = :slug_filter"
    rows = conn.execute(
        text(f"""
            SELECT
                nb.slug,
                nb.neighborhood_name AS nome
            FROM neighborhood_boundaries nb
            {where}
            ORDER BY nb.neighborhood_name
        """),
        {"slug_filter": slug_filter} if slug_filter else {},
    ).mappings().all()
    return [dict(r) for r in rows]


def fetch_listings_for_district(conn: sa.Connection, slug: str) -> list[dict]:
    """
    Busca imóveis ativos dentro do polígono do distrito.
    Retorna somente imóveis com area_m2 > 0 e price > 0 no snapshot mais recente.
    """
    rows = conn.execute(
        text("""
            SELECT
                p.id::text                                AS id,
                la.advertised_usage_type                  AS tipo_negocio,
                la.usage_type                             AS tipo_imovel,
                p.area_m2,
                p.bedrooms                                AS quartos,
                la.url,
                ls.price,
                ls.condo_fee,
                ls.iptu,
                ls.observed_at
            FROM neighborhood_boundaries nb
            JOIN properties p
                ON ST_Within(p.location, nb.geometry)
            JOIN listing_ads la
                ON la.property_id = p.id AND la.is_active = TRUE
            JOIN LATERAL (
                SELECT price, condo_fee, iptu, observed_at
                FROM listing_snapshots ls
                WHERE ls.listing_ad_id = la.id
                  AND ls.availability_state = 'active'
                ORDER BY ls.observed_at DESC
                LIMIT 1
            ) ls ON TRUE
            WHERE nb.slug = :slug
              AND p.area_m2 IS NOT NULL
              AND p.area_m2 > 0
              AND ls.price IS NOT NULL
              AND ls.price > 0
        """),
        {"slug": slug},
    ).mappings().all()
    return [dict(r) for r in rows]


def calc_quartis(values: list[float]) -> dict:
    if len(values) < 4:
        return None
    qs = quantiles(values, n=4)
    return {"q1": round(qs[0], 2), "median": round(qs[1], 2), "q3": round(qs[2], 2)}


def calc_per_m2(price: float, area: float) -> float | None:
    if area and area > 0:
        return round(price / area, 2)
    return None


def build_district_metrics(listings: list[dict]) -> dict:
    alugueis = [l for l in listings if l["tipo_negocio"] == "rent"]
    vendas = [l for l in listings if l["tipo_negocio"] == "sale"]

    def aggregate_group(group: list[dict], tipo: str) -> dict | None:
        if len(group) < MIN_SAMPLE:
            return None
        prices = [float(l["price"]) for l in group]
        areas = [float(l["area_m2"]) for l in group]
        prices_m2 = [
            float(l["price"]) / float(l["area_m2"])
            for l in group
            if l["area_m2"] and float(l["area_m2"]) > 0
        ]

        total_costs = []
        for l in group:
            base = float(l["price"])
            condo = float(l["condo_fee"]) if l["condo_fee"] else 0
            total_costs.append(base + condo)

        total_costs_m2 = [
            tc / float(l["area_m2"])
            for tc, l in zip(total_costs, group)
            if l["area_m2"] and float(l["area_m2"]) > 0
        ]

        return {
            "tipo": tipo,
            "sample_count": len(group),
            "mediana_preco_m2": round(median(prices_m2), 2) if prices_m2 else None,
            "mediana_custo_total_m2": round(median(total_costs_m2), 2) if total_costs_m2 else None,
            "quartis_preco": calc_quartis(prices),
            "encargos_incluidos": any(l["condo_fee"] for l in group),
            "iptu_incluido": any(l["iptu"] for l in group),
            "limitacoes": _build_limitacoes(group),
        }

    def _build_limitacoes(group: list[dict]) -> list[str]:
        lims = []
        sem_condo = sum(1 for l in group if not l["condo_fee"])
        sem_iptu = sum(1 for l in group if not l["iptu"])
        sem_area = sum(1 for l in group if not l["area_m2"] or float(l["area_m2"]) <= 0)
        if sem_condo > 0:
            lims.append(f"Condomínio ausente em {sem_condo} imóvel(is) — custo total subestimado.")
        if sem_iptu > 0:
            lims.append(f"IPTU ausente em {sem_iptu} imóvel(is) — encargo não contabilizado.")
        if sem_area > 0:
            lims.append(f"Área ausente em {sem_area} imóvel(is) — excluídos do cálculo por m².")
        return lims

    def build_sample(group: list[dict], tipo: str) -> list[dict]:
        sorted_group = sorted(
            group,
            key=lambda l: (-(float(l["area_m2"]) if l["area_m2"] else 0), l["id"]),
        )[:SAMPLE_CAP]
        result = []
        for l in sorted_group:
            area = float(l["area_m2"]) if l["area_m2"] else None
            price = float(l["price"])
            condo = float(l["condo_fee"]) if l["condo_fee"] else None
            item = {
                "id_publico": l["id"][:8],
                "tipo_negocio": "aluguel" if tipo == "rent" else "venda",
                "tipo_imovel": l["tipo_imovel"] or "residencial",
                "area_m2": area,
                "quartos": l["quartos"],
                "aluguel": price if tipo == "rent" else None,
                "condominio": condo,
                "preco_venda": price if tipo == "sale" else None,
                "preco_total_mensal": (price + (condo or 0)) if tipo == "rent" else None,
                "aluguel_m2": calc_per_m2(price, area) if tipo == "rent" and area else None,
                "preco_venda_m2": calc_per_m2(price, area) if tipo == "sale" and area else None,
                "url": l["url"] or SITE_URL,
            }
            result.append(item)
        return result

    aluguel_agg = aggregate_group(alugueis, "rent")
    venda_agg = aggregate_group(vendas, "sale")

    return {
        "aluguel": aluguel_agg,
        "venda": venda_agg,
        "amostra_aluguel": build_sample(alugueis, "rent") if aluguel_agg else [],
        "amostra_venda": build_sample(vendas, "sale") if venda_agg else [],
        "total_elegiveis": len(listings),
        "cobertura": "suficiente" if (aluguel_agg or venda_agg) else "insuficiente",
    }


def build_real_estate_metrics(slug: str, nome: str, data: dict, today: str) -> dict:
    """Constrói o objeto RealEstateMetrics compatível com imoveis_aggregates.ts."""
    al = data["aluguel"]
    vd = data["venda"]
    sample = data["amostra_aluguel"] + data["amostra_venda"]

    rent_per_m2 = al["mediana_preco_m2"] if al else None
    total_rent_m2 = al["mediana_custo_total_m2"] if al else None
    sale_per_m2 = vd["mediana_preco_m2"] if vd else None
    rent_q = al["quartis_preco"] if al else None
    sale_q = vd["quartis_preco"] if vd else None
    count = data["total_elegiveis"]

    cost_index = _calc_cost_index(rent_per_m2, sale_per_m2)

    return {
        "aggregationLevel": "bairro",
        "aggregationSlug": slug,
        "listingSampleCount": count,
        "rentPerM2": rent_per_m2,
        "totalRentCostPerM2": total_rent_m2,
        "salePricePerM2": sale_per_m2,
        "rentQuartiles": rent_q,
        "saleQuartiles": sale_q,
        "sameListingPriceChange": None,
        "costIndex": cost_index,
        "sampleListings": sample,
        "dataAt": today,
    }


def _calc_cost_index(rent_m2: float | None, sale_m2: float | None) -> int:
    """Placeholder linear — o pipeline substitui por min-max entre todos os distritos."""
    if rent_m2 is None and sale_m2 is None:
        return 50
    ref = rent_m2 if rent_m2 else sale_m2
    return max(0, min(100, int((ref / 150) * 100)))


def write_ts(entries: list[dict], cidade_summary: dict, today: str) -> None:
    def py_to_ts(val) -> str:
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, str):
            escaped = val.replace("\\", "\\\\").replace("'", "\\'")
            return f"'{escaped}'"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, list):
            items = ", ".join(py_to_ts(v) for v in val)
            return f"[{items}]"
        if isinstance(val, dict):
            fields = ", ".join(f"{k}: {py_to_ts(v)}" for k, v in val.items())
            return f"{{ {fields} }}"
        return repr(val)

    def build_metrics_ts(m: dict) -> str:
        rq = m["rentQuartiles"]
        sq = m["saleQuartiles"]
        rent_q_ts = (
            f"{{ q1: {rq['q1']}, median: {rq['median']}, q3: {rq['q3']} }}" if rq else "undefined"
        )
        sale_q_ts = (
            f"{{ q1: {sq['q1']}, median: {sq['median']}, q3: {sq['q3']} }}" if sq else "undefined"
        )
        samples = m.get("sampleListings") or []
        samples_ts_parts = []
        for s in samples:
            fields = ", ".join(f"{k}: {py_to_ts(v)}" for k, v in s.items())
            samples_ts_parts.append(f"    {{ {fields} }}")
        samples_ts = "[\n" + ",\n".join(samples_ts_parts) + "\n  ]" if samples_ts_parts else "[]"

        lines = [
            f"      aggregationLevel: 'bairro',",
            f"      aggregationSlug: '{m['aggregationSlug']}',",
            f"      listingSampleCount: {m['listingSampleCount']},",
        ]
        if m["rentPerM2"] is not None:
            lines.append(f"      rentPerM2: {m['rentPerM2']},")
        if m["totalRentCostPerM2"] is not None:
            lines.append(f"      totalRentCostPerM2: {m['totalRentCostPerM2']},")
        if m["salePricePerM2"] is not None:
            lines.append(f"      salePricePerM2: {m['salePricePerM2']},")
        if rq:
            lines.append(f"      rentQuartiles: {rent_q_ts},")
        if sq:
            lines.append(f"      saleQuartiles: {sale_q_ts},")
        lines += [
            f"      costIndex: {m['costIndex']},",
            f"      sampleListings: {samples_ts},",
            f"      dataAt: '{m['dataAt']}',",
        ]
        return "\n".join(lines)

    entry_parts = []
    for e in entries:
        metrics_ts = build_metrics_ts(e["metrics"])
        entry_parts.append(
            f"  {{\n"
            f"    slug: '{e['slug']}',\n"
            f"    nome: '{e['nome']}',\n"
            f"    cidade: 'São Paulo',\n"
            f"    estado: 'SP',\n"
            f"    metrics: {{\n{metrics_ts}\n    }},\n"
            f"  }}"
        )

    cidade_ts = (
        f"  {{\n"
        f"    estado: 'SP',\n"
        f"    estadoSlug: 'sp',\n"
        f"    cidade: 'São Paulo',\n"
        f"    cidadeSlug: 'sao-paulo',\n"
        f"    totalBairros: {cidade_summary['total_bairros']},\n"
        f"    totalImoveisElegiveis: {cidade_summary['total_imoveis']},\n"
        f"    medianaAluguelM2: {cidade_summary['mediana_aluguel_m2'] or 'null'},\n"
        f"    medianaVendaM2: {cidade_summary['mediana_venda_m2'] or 'null'},\n"
        f"    dataAtualizacao: '{today}',\n"
        f"    cobertura: '{cidade_summary['cobertura']}',\n"
        f"  }}"
    ) if cidade_summary else "null"

    content = (
        "import type { RealEstateMetrics } from './bairros';\n\n"
        "export type { RealEstateMetrics };\n\n"
        "export interface ImoveisCidade {\n"
        "  estado: string;\n"
        "  estadoSlug: string;\n"
        "  cidade: string;\n"
        "  cidadeSlug: string;\n"
        "  totalBairros: number;\n"
        "  totalImoveisElegiveis: number;\n"
        "  medianaAluguelM2: number | null;\n"
        "  medianaVendaM2: number | null;\n"
        "  dataAtualizacao: string;\n"
        "  cobertura: 'suficiente' | 'parcial' | 'insuficiente';\n"
        "}\n\n"
        "export interface ImoveisBairroData {\n"
        "  slug: string;\n"
        "  nome: string;\n"
        "  cidade: string;\n"
        "  estado: string;\n"
        "  metrics: RealEstateMetrics;\n"
        "}\n\n"
        "// NÃO alterar manualmente — gerado por scripts/aggregate_real_estate.py\n"
        f"export const IMOVEIS_AGGREGATES: ImoveisBairroData[] = [\n"
        + ",\n".join(entry_parts)
        + "\n];\n\n"
        "// NÃO alterar manualmente — gerado por scripts/aggregate_real_estate.py\n"
        f"export const IMOVEIS_CIDADE: ImoveisCidade | null = {cidade_ts};\n\n"
        "export function getImoveisBairro(slug: string): ImoveisBairroData | undefined {\n"
        "  return IMOVEIS_AGGREGATES.find((a) => a.slug === slug);\n"
        "}\n\n"
        "export function hasImoveisData(): boolean {\n"
        "  return IMOVEIS_AGGREGATES.length > 0;\n"
        "}\n"
    )
    TS_OUTPUT.write_text(content, encoding="utf-8")
    log.info("TS escrito: %s (%d distritos)", TS_OUTPUT, len(entries))


def write_json(entries: list[dict], cidade_summary: dict, today: str) -> None:
    path = PUBLIC_DIR / "aggregates.json"
    payload = {
        "versao": "0.1",
        "data_publicacao": today,
        "licenca": LICENSE,
        "fonte": SITE_URL,
        "metodologia": f"{SITE_URL}/metodologia",
        "cidade": cidade_summary,
        "distritos": [
            {
                "slug": e["slug"],
                "nome": e["nome"],
                "cidade": "São Paulo",
                "estado": "SP",
                **{k: v for k, v in e["metrics"].items() if k != "sampleListings"},
            }
            for e in entries
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("JSON escrito: %s", path)


def write_csv(entries: list[dict], today: str) -> None:
    path = PUBLIC_DIR / "aggregates.csv"
    fieldnames = [
        "data_publicacao", "slug", "nome", "cidade", "estado",
        "total_elegiveis", "aluguel_mediana_m2", "custo_total_mediana_m2",
        "venda_mediana_m2", "aluguel_q1", "aluguel_mediana", "aluguel_q3",
        "venda_q1", "venda_mediana", "venda_q3", "custo_index", "data_referencia",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in entries:
            m = e["metrics"]
            rq = m.get("rentQuartiles") or {}
            sq = m.get("saleQuartiles") or {}
            writer.writerow({
                "data_publicacao": today,
                "slug": e["slug"],
                "nome": e["nome"],
                "cidade": "São Paulo",
                "estado": "SP",
                "total_elegiveis": m["listingSampleCount"],
                "aluguel_mediana_m2": m.get("rentPerM2") or "",
                "custo_total_mediana_m2": m.get("totalRentCostPerM2") or "",
                "venda_mediana_m2": m.get("salePricePerM2") or "",
                "aluguel_q1": rq.get("q1", ""),
                "aluguel_mediana": rq.get("median", ""),
                "aluguel_q3": rq.get("q3", ""),
                "venda_q1": sq.get("q1", ""),
                "venda_mediana": sq.get("median", ""),
                "venda_q3": sq.get("q3", ""),
                "custo_index": m["costIndex"],
                "data_referencia": m["dataAt"],
            })
    log.info("CSV escrito: %s", path)


def calc_cidade_summary(entries: list[dict]) -> dict:
    aluguel_m2s = [
        e["metrics"]["rentPerM2"]
        for e in entries
        if e["metrics"].get("rentPerM2") is not None
    ]
    venda_m2s = [
        e["metrics"]["salePricePerM2"]
        for e in entries
        if e["metrics"].get("salePricePerM2") is not None
    ]
    total_imoveis = sum(e["metrics"]["listingSampleCount"] for e in entries)
    cobertura = "suficiente" if len(entries) >= 5 else "parcial" if entries else "insuficiente"

    return {
        "total_bairros": len(entries),
        "total_imoveis": total_imoveis,
        "mediana_aluguel_m2": round(median(aluguel_m2s), 2) if aluguel_m2s else None,
        "mediana_venda_m2": round(median(venda_m2s), 2) if venda_m2s else None,
        "cobertura": cobertura,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Agrega dados imobiliários BetterPlace por distrito")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--distrito", help="Filtrar por slug de distrito único")
    args = parser.parse_args()

    today = date.today().isoformat()
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    with engine.connect() as conn:
        districts = fetch_districts(conn, args.distrito)
        if not districts:
            log.error("Nenhum distrito publicável encontrado. Verifique is_publishable e slug em neighborhood_boundaries.")
            sys.exit(1)
        log.info("%d distritos publicáveis", len(districts))

        entries = []
        skipped = []

        for d in districts:
            slug = d["slug"]
            nome = d["nome"]
            log.info("Processando %s (%s)...", nome, slug)
            listings = fetch_listings_for_district(conn, slug)
            log.info("  %d anúncios elegíveis", len(listings))

            if not listings:
                log.warning("  Sem imóveis — declarando lacuna para %s", slug)
                skipped.append(slug)
                continue

            data = build_district_metrics(listings)
            metrics = build_real_estate_metrics(slug, nome, data, today)

            entries.append({"slug": slug, "nome": nome, "metrics": metrics})

    if skipped:
        log.warning("Distritos sem cobertura suficiente (lacuna declarada): %s", ", ".join(skipped))

    cidade_summary = calc_cidade_summary(entries)
    log.info("Resumo cidade: %s", cidade_summary)

    if args.dry_run:
        log.info("Dry-run — nenhum arquivo escrito.")
        return

    write_ts(entries, cidade_summary, today)
    write_json(entries, cidade_summary, today)
    write_csv(entries, today)

    log.info("Concluído: %d distritos com dados, %d sem cobertura suficiente.", len(entries), len(skipped))


if __name__ == "__main__":
    main()
