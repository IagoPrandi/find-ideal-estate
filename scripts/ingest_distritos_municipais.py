"""
Ingest official São Paulo municipal districts into neighborhood_boundaries.

Source: geoportal_distrito_municipal_v2.gpkg (PMSP / GeoSampa)
  Layer : distrito_municipal_v2
  CRS   : EPSG:31983 — SIRGAS 2000 / UTM zone 23S (projected, meters)

Each of the 96 municipal districts becomes one analysis zone (neighborhood_code).

Column mapping  GeoPackage → neighborhood_boundaries:
  cd_distrito_municipal  → neighborhood_code, district_code
  nm_distrito_municipal  → district_name, neighborhood_name
  sg_distrito_municipal  → neighborhood_abbreviation
  qt_area_quilometro     → area_km2
  cd_identificador_distrito → gpkg_identifier
  cd_regiao_05           → region_5_code
  nm_regiao_05           → region_5_name
  geometry (EPSG:31983)  → geometry (EPSG:4326)

Slugs are generated from nm_distrito_municipal and stored in the slug column.

Usage:
  python scripts/ingest_distritos_municipais.py \
      --gpkg geoportal_distrito_municipal_v2.gpkg \
      [--layer distrito_municipal_v2] \
      [--city-code SAO_PAULO] \
      [--dry-run]

Requirements:
  pip install geopandas sqlalchemy psycopg2-binary
  DATABASE_URL env var must point to the PostGIS database.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import unicodedata

import geopandas as gpd
import sqlalchemy as sa
from shapely import wkt as shapely_wkt

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

CITY_CODE = "SAO_PAULO"
CITY_NAME = "São Paulo"
TARGET_EPSG = 4326
SOURCE_LAYER = "distrito_municipal_v2"


def get_engine() -> sa.Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL não definida")
        sys.exit(1)
    return sa.create_engine(url, pool_pre_ping=True)


def _slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFD", name)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_str.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def load_gpkg(gpkg_path: str, layer: str) -> gpd.GeoDataFrame:
    log.info("Lendo GeoPackage: %s (layer=%s)", gpkg_path, layer)
    gdf = gpd.read_file(gpkg_path, layer=layer)
    log.info("  %d distritos carregados, CRS=%s", len(gdf), gdf.crs)
    if gdf.crs is None:
        log.warning("CRS ausente — atribuindo EPSG:31983")
        gdf = gdf.set_crs(epsg=31983)
    if gdf.crs.to_epsg() != TARGET_EPSG:
        log.info("  Reprojetando EPSG:%d → EPSG:%d", gdf.crs.to_epsg(), TARGET_EPSG)
        gdf = gdf.to_crs(epsg=TARGET_EPSG)
    return gdf


def build_rows(gdf: gpd.GeoDataFrame, city_code: str) -> list[dict]:
    rows = []
    for _, r in gdf.iterrows():
        geom = r.geometry
        if geom is None or geom.is_empty:
            log.warning("Geometria vazia para distrito %s — ignorado", r.get("nm_distrito_municipal"))
            continue

        nm = str(r["nm_distrito_municipal"]).strip()
        cd = str(int(r["cd_distrito_municipal"])).strip()
        sg = str(r.get("sg_distrito_municipal", "") or "").strip()

        region_code_raw = r.get("cd_regiao_05")
        region_name_raw = r.get("nm_regiao_05")
        region_code = int(region_code_raw) if region_code_raw is not None else None
        region_name = str(region_name_raw).strip() if region_name_raw else None

        gpkg_id_raw = r.get("cd_identificador_distrito")
        gpkg_id = int(gpkg_id_raw) if gpkg_id_raw is not None else None

        area_km2_raw = r.get("qt_area_quilometro")
        area_km2 = float(area_km2_raw) if area_km2_raw is not None else None

        rows.append(
            {
                "neighborhood_code": cd,
                "city_code": city_code,
                "city_name": CITY_NAME,
                "district_code": cd,
                "district_name": nm,
                "neighborhood_name": nm,
                "neighborhood_abbreviation": sg or None,
                "area_km2": area_km2,
                "slug": _slugify(nm),
                "region_5_code": region_code,
                "region_5_name": region_name,
                "gpkg_identifier": gpkg_id,
                "geometry_wkt": shapely_wkt.dumps(geom, rounding_precision=8),
            }
        )
    return rows


_UPSERT_SQL = sa.text(
    """
    INSERT INTO neighborhood_boundaries (
        neighborhood_code,
        city_code,
        city_name,
        district_code,
        district_name,
        neighborhood_name,
        neighborhood_abbreviation,
        area_km2,
        slug,
        region_5_code,
        region_5_name,
        gpkg_identifier,
        geometry
    ) VALUES (
        :neighborhood_code,
        :city_code,
        :city_name,
        :district_code,
        :district_name,
        :neighborhood_name,
        :neighborhood_abbreviation,
        :area_km2,
        :slug,
        :region_5_code,
        :region_5_name,
        :gpkg_identifier,
        ST_GeomFromText(:geometry_wkt, 4326)
    )
    ON CONFLICT (neighborhood_code) DO UPDATE SET
        city_code                 = EXCLUDED.city_code,
        city_name                 = EXCLUDED.city_name,
        district_code             = EXCLUDED.district_code,
        district_name             = EXCLUDED.district_name,
        neighborhood_name         = EXCLUDED.neighborhood_name,
        neighborhood_abbreviation = EXCLUDED.neighborhood_abbreviation,
        area_km2                  = EXCLUDED.area_km2,
        slug                      = EXCLUDED.slug,
        region_5_code             = EXCLUDED.region_5_code,
        region_5_name             = EXCLUDED.region_5_name,
        gpkg_identifier           = EXCLUDED.gpkg_identifier,
        geometry                  = EXCLUDED.geometry
    """
)


def ingest(conn: sa.Connection, rows: list[dict], dry_run: bool) -> None:
    if dry_run:
        log.info("[dry-run] %d distritos seriam inseridos/atualizados", len(rows))
        for r in rows[:5]:
            log.info(
                "  [dry-run] %s | %s | slug=%s | %.3f km²",
                r["neighborhood_code"],
                r["neighborhood_name"],
                r["slug"],
                r["area_km2"] or 0,
            )
        if len(rows) > 5:
            log.info("  [dry-run] ... e mais %d distritos", len(rows) - 5)
        return

    inserted = 0
    for row in rows:
        conn.execute(_UPSERT_SQL, row)
        inserted += 1

    log.info(
        "Ingestão concluída: %d distritos upsertados em neighborhood_boundaries", inserted
    )


def verify(conn: sa.Connection, city_code: str) -> None:
    total = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM neighborhood_boundaries WHERE city_code = :cc"
        ),
        {"cc": city_code},
    ).scalar()
    null_slugs = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM neighborhood_boundaries "
            "WHERE city_code = :cc AND slug IS NULL"
        ),
        {"cc": city_code},
    ).scalar()
    invalid_geom = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM neighborhood_boundaries "
            "WHERE city_code = :cc AND NOT ST_IsValid(geometry)"
        ),
        {"cc": city_code},
    ).scalar()
    log.info("Verificação pós-ingestão:")
    log.info("  Total de distritos: %d", total)
    log.info("  Slugs nulos: %d", null_slugs)
    log.info("  Geometrias inválidas: %d", invalid_geom)

    if null_slugs > 0 or invalid_geom > 0:
        log.error("Falha na verificação — corrija antes de rodar o pipeline de agregação")
        sys.exit(1)
    log.info("OK — neighborhood_boundaries pronto para agregação")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingere distritos municipais de SP no neighborhood_boundaries"
    )
    parser.add_argument(
        "--gpkg",
        default="data/geo/raw/geoportal_distrito_municipal_v2.gpkg",
        help="Caminho para o GeoPackage (default: data/geo/raw/geoportal_distrito_municipal_v2.gpkg)",
    )
    parser.add_argument(
        "--layer",
        default=SOURCE_LAYER,
        help=f"Nome da layer no GeoPackage (default: {SOURCE_LAYER})",
    )
    parser.add_argument(
        "--city-code",
        default=CITY_CODE,
        help=f"city_code a ser registrado (default: {CITY_CODE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula sem escrever no banco",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.gpkg):
        log.error("GeoPackage não encontrado: %s", args.gpkg)
        sys.exit(1)

    gdf = load_gpkg(args.gpkg, args.layer)
    rows = build_rows(gdf, args.city_code)

    if not rows:
        log.error("Nenhum distrito válido encontrado no GeoPackage")
        sys.exit(1)

    log.info("%d distritos prontos para ingestão", len(rows))

    engine = get_engine()
    with engine.begin() as conn:
        ingest(conn, rows, args.dry_run)
        if not args.dry_run:
            verify(conn, args.city_code)


if __name__ == "__main__":
    main()
