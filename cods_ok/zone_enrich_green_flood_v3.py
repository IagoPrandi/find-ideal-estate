#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zone_enrich_green_flood_v2.py

Enriquece os outputs do candidate_zones (zones.geojson + ranking.csv) com:
- área alagável (geoportal_mancha_inundacao_25.gpkg) dentro de um raio (default 800m)
- área verde significativa (SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg) dentro de um raio (default 700m)

IMPORTANTE: NÃO calcula centróide; usa centroid_lon/centroid_lat já presentes nos outputs.

Saídas:
- zones_enriched.geojson  (mesma geometria, properties acrescidas)
- ranking_enriched.csv    (ranking.csv + colunas acrescidas, join por zone_id)

Requisitos (pip):
- shapely
- fiona
- pyproj
- numpy
- pandas (opcional; se não tiver, faz merge via csv)

Exemplo (Windows / PowerShell) — note o uso de aspas e crase para quebra de linha:
  python .\\zone_enrich_green_flood_v2.py `
    --runs-dir ".\\runs\\auto\\outputs" `
    --geodir "C:/Users/iagoo/PESSOAL/projetos/onde_morar/data_cache/geosampa" `
    --out-dir ".\\runs\\auto\\outputs"
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fiona
import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform, unary_union
from shapely.strtree import STRtree
from shapely.errors import GEOSException
from pyproj import CRS, Transformer

try:
    from shapely.validation import make_valid as shp_make_valid
except Exception:  # pragma: no cover
    shp_make_valid = None

EPSG_WGS84 = "EPSG:4326"
EPSG_UTM_SP = "EPSG:31983"  # SIRGAS 2000 / UTM 23S


def _repair_geom(g):
    if g is None or g.is_empty:
        return g
    if g.is_valid:
        return g
    try:
        if shp_make_valid is not None:
            gg = shp_make_valid(g)
            if gg is not None and (not gg.is_empty):
                return gg
    except Exception:
        pass
    try:
        gg = g.buffer(0)
        if gg is not None and (not gg.is_empty):
            return gg
    except Exception:
        pass
    return None


def _pick_layer(path: Path) -> str:
    layers = fiona.listlayers(str(path))
    if not layers:
        raise RuntimeError(f"Nenhuma layer encontrada em {path}")
    return layers[0]


def _transformer(src_crs: Optional[Any], dst_epsg: str) -> Transformer:
    if src_crs is None:
        src = CRS.from_string(EPSG_WGS84)
    else:
        try:
            src = CRS.from_user_input(src_crs)
        except Exception:
            src = CRS.from_string(EPSG_WGS84)
    dst = CRS.from_string(dst_epsg)
    return Transformer.from_crs(src, dst, always_xy=True)


def _build_tree(geoms: List[Any]) -> STRtree:
    tree = STRtree(geoms) if geoms else STRtree([])
    setattr(tree, "_geoms", geoms)  # compat: query() pode retornar índices
    return tree


def _iter_candidates(tree: STRtree, query_geom) -> List[Any]:
    cand = tree.query(query_geom)
    src = getattr(tree, "_geoms", None)
    out: List[Any] = []
    for obj in cand:
        if isinstance(obj, (int, np.integer)) and src is not None:
            out.append(src[int(obj)])
        else:
            out.append(obj)
    return out


def load_polygons_utm(gpkg_path: Path, layer: Optional[str] = None) -> Tuple[List[Any], STRtree]:
    layer = layer or _pick_layer(gpkg_path)

    with fiona.open(str(gpkg_path), layer=layer) as src:
        to_utm = _transformer(src.crs, EPSG_UTM_SP)
        geoms: List[Any] = []
        for feat in src:
            geom = feat.get("geometry")
            if not geom:
                continue
            g = shape(geom)
            g_utm = shp_transform(lambda x, y, z=None: to_utm.transform(x, y), g)
            g_utm = _repair_geom(g_utm)
            if g_utm is not None and (not g_utm.is_empty):
                geoms.append(g_utm)

    return geoms, _build_tree(geoms)


def union_intersection_area(buffer_utm: Any, tree: STRtree) -> float:
    """Área (m²) da UNIÃO das interseções entre candidatos e o buffer.

    Motivo: somar área feature-a-feature pode duplicar trechos sobrepostos e gerar taxa > 1.
    """
    inter_parts: List[Any] = []
    for g in _iter_candidates(tree, buffer_utm):
        if g is None or g.is_empty:
            continue
        g = _repair_geom(g)
        if g is None or g.is_empty:
            continue
        try:
            intersects = g.intersects(buffer_utm)
        except GEOSException:
            g = _repair_geom(g)
            if g is None or g.is_empty:
                continue
            try:
                intersects = g.intersects(buffer_utm)
            except GEOSException:
                continue
        if not intersects:
            continue
        try:
            inter = g.intersection(buffer_utm)
        except GEOSException:
            g = _repair_geom(g)
            if g is None or g.is_empty:
                continue
            try:
                inter = g.intersection(buffer_utm)
            except GEOSException:
                continue
        if not inter.is_empty:
            inter_parts.append(inter)

    if not inter_parts:
        return 0.0
    if len(inter_parts) == 1:
        return float(inter_parts[0].area)

    # unary_union remove sobreposições antes de medir área
    try:
        u = unary_union(inter_parts)
    except GEOSException:
        repaired = [gg for gg in (_repair_geom(x) for x in inter_parts) if gg is not None and (not gg.is_empty)]
        if not repaired:
            return 0.0
        try:
            u = unary_union(repaired)
        except GEOSException:
            return float(sum(x.area for x in repaired))
    return float(u.area) if not u.is_empty else 0.0


def read_zones_geojson(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("zones.geojson deve ser FeatureCollection")
    return data


def write_geojson(path: Path, fc: Dict[str, Any]) -> None:
    path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")


def enrich_zones(
    zones_fc: Dict[str, Any],
    flood_tree: STRtree,
    green_tree: STRtree,
    r_flood_m: float,
    r_green_m: float,
) -> Dict[str, Any]:
    to_utm = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)

    feats = zones_fc.get("features") or []
    out_feats = []

    for feat in feats:
        props = dict(feat.get("properties") or {})
        lon = props.get("centroid_lon")
        lat = props.get("centroid_lat")

        if lon is None or lat is None:
            geom = feat.get("geometry")
            if geom:
                c = shape(geom).centroid
                lon, lat = float(c.x), float(c.y)
            else:
                out_feats.append(feat)
                continue

        x, y = to_utm.transform(float(lon), float(lat))
        p = Point(float(x), float(y))

        buf_flood = p.buffer(float(r_flood_m))
        buf_green = p.buffer(float(r_green_m))

        flood_area = union_intersection_area(buf_flood, flood_tree)
        green_area = union_intersection_area(buf_green, green_tree)

        props["flood_area_m2_r800"] = flood_area
        props["flood_ratio_r800"] = (flood_area / float(buf_flood.area)) if buf_flood.area else 0.0
        props["green_area_m2_r700"] = green_area
        props["green_ratio_r700"] = (green_area / float(buf_green.area)) if buf_green.area else 0.0

        out_feats.append({"type": "Feature", "properties": props, "geometry": feat.get("geometry")})

    return {"type": "FeatureCollection", "features": out_feats}


def read_csv_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def merge_ranking_with_zone_props(ranking_csv: Path, zones_fc_enriched: Dict[str, Any], out_csv: Path) -> None:
    fields, rows = read_csv_rows(ranking_csv)

    zone_by_id: Dict[str, Dict[str, Any]] = {}
    for feat in zones_fc_enriched.get("features", []):
        props = feat.get("properties") or {}
        zid = props.get("zone_id")
        if zid is not None:
            zone_by_id[str(zid)] = props

    add_cols = ["flood_area_m2_r800", "flood_ratio_r800", "green_area_m2_r700", "green_ratio_r700"]
    new_fields = list(fields)
    for c in add_cols:
        if c not in new_fields:
            new_fields.append(c)

    out_rows: List[Dict[str, Any]] = []
    for r in rows:
        zid = str(r.get("zone_id", ""))
        zp = zone_by_id.get(zid, {})
        rr = dict(r)
        for c in add_cols:
            rr[c] = zp.get(c, "")
        out_rows.append(rr)

    write_csv(out_csv, new_fields, out_rows)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enriquece zonas com métricas de alagamento e área verde.")
    p.add_argument("--runs-dir", required=True, help="Diretório contendo zones.geojson e ranking.csv (outputs do candidate_zones).") 
    p.add_argument("--geodir", required=True, help="Diretório com os GPKGs (geosampa).")
    p.add_argument("--flood-gpkg", default="geoportal_mancha_inundacao_25.gpkg")
    p.add_argument("--green-gpkg", default="SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg")
    p.add_argument("--r-flood-m", type=float, default=800.0)
    p.add_argument("--r-green-m", type=float, default=700.0)
    p.add_argument("--out-dir", required=True, help="Onde salvar zones_enriched.geojson e ranking_enriched.csv")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    runs_dir = Path(args.runs_dir)
    geodir = Path(args.geodir)

    zones_path = runs_dir / "zones.geojson"
    ranking_path = runs_dir / "ranking.csv"
    flood_path = geodir / args.flood_gpkg
    green_path = geodir / args.green_gpkg

    if not zones_path.exists():
        raise FileNotFoundError(f"Não achei {zones_path}")
    if not ranking_path.exists():
        raise FileNotFoundError(f"Não achei {ranking_path}")
    if not flood_path.exists():
        raise FileNotFoundError(f"Não achei {flood_path}")
    if not green_path.exists():
        raise FileNotFoundError(f"Não achei {green_path}")

    print("=== CONFIRMAÇÃO DE ABERTURA ===")
    print(f"- zones: {zones_path}")
    print(f"- ranking: {ranking_path}")
    print(f"- flood: {flood_path}")
    print(f"- green: {green_path}")
    print("==============================")

    print("[1/4] Carregando polígonos de alagamento (UTM) ...")
    flood_geoms, flood_tree = load_polygons_utm(flood_path)
    print(f"  flood polys: {len(flood_geoms):,}")

    print("[2/4] Carregando polígonos de vegetação significativa (UTM) ...")
    green_geoms, green_tree = load_polygons_utm(green_path)
    print(f"  green polys: {len(green_geoms):,}")

    print("[3/4] Enriquecendo zones.geojson usando centroid_lon/centroid_lat ...")
    zones_fc = read_zones_geojson(zones_path)
    zones_enriched = enrich_zones(
        zones_fc,
        flood_tree=flood_tree,
        green_tree=green_tree,
        r_flood_m=float(args.r_flood_m),
        r_green_m=float(args.r_green_m),
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    zones_out = out_dir / "zones_enriched.geojson"
    write_geojson(zones_out, zones_enriched)
    print(f"  OK: {zones_out}")

    print("[4/4] Enriquecendo ranking.csv (join por zone_id) ...")
    rank_out = out_dir / "ranking_enriched.csv"
    merge_ranking_with_zone_props(ranking_path, zones_enriched, rank_out)
    print(f"  OK: {rank_out}")

    print("\n[OK] Concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
