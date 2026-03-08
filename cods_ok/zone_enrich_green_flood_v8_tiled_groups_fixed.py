#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zone_enrich_green_flood_v7_tiled_groups.py

Enrichment runner that uses a *tile index* (support file) to load only the required
GeoPackage pieces (tiles / merged groups) for each zone.

This version is compatible with:
- tile_index.csv from gpkg_grid_tiler.py (tile_id, filepath, bbox, centroid, ...)
- tile_index.csv from gpkg_grid_tiler_v2_merge.py (group_id, filepath, bbox, centroid, members, ...)

Key optimizations:
- Tile selection via STRtree on tile bbox polygons (fast).
- Tile GDF cache in-memory (per run) + optional disk cache via --cache-dir.
- Geometry shortcuts: numeric bounds filter, prepared buffer, covers shortcut.
- Detailed logs with timings and per-zone tile counts.

Requirements: geopandas, shapely, pyproj
Optional: pyogrio (faster tile I/O), pickle cache.

"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import geopandas as gpd  # type: ignore
import pandas as pd  # type: ignore
from shapely.geometry import box, shape  # type: ignore
from shapely.prepared import prep  # type: ignore
from shapely.strtree import STRtree  # type: ignore
from pyproj import CRS, Transformer  # type: ignore

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

try:
    # Shapely 2.x
    from shapely import union_all as _union_all  # type: ignore
except Exception:  # pragma: no cover
    _union_all = None

try:
    import pyogrio  # type: ignore
    HAVE_PYOGRIO = True
except Exception:
    HAVE_PYOGRIO = False


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def log(level: str, msg: str, verbose: int, min_v: int = 0) -> None:
    if verbose >= min_v:
        print(f"{_ts()} | {level:<7} | {msg}", flush=True)


def now() -> float:
    return time.perf_counter()


def file_size_mb(p: Path) -> float:
    try:
        return p.stat().st_size / (1024 * 1024)
    except FileNotFoundError:
        return 0.0


@dataclass
class TileRec:
    tile_key: str  # tile_id or group_id
    filepath: Path
    bbox: Tuple[float, float, float, float]  # in same CRS as the tile file
    centroid: Tuple[float, float]
    size_mb: float
    feature_count: int
    members: str


def read_tile_index(csv_path: Path, verbose: int) -> Tuple[List[TileRec], CRS]:
    """Read tile_index.csv and return records + CRS (best effort)."""
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    df = pd.read_csv(csv_path)
    # Normalize columns
    key_col = "tile_id" if "tile_id" in df.columns else ("group_id" if "group_id" in df.columns else None)
    if key_col is None:
        raise ValueError("tile_index.csv must contain tile_id or group_id column")

    required = ["filepath", "minx", "miny", "maxx", "maxy", "centroid_x", "centroid_y"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"tile_index.csv missing column: {c}")

    if "size_mb" not in df.columns:
        df["size_mb"] = 0.0
    if "feature_count" not in df.columns:
        df["feature_count"] = 0
    if "members" not in df.columns:
        df["members"] = ""

    recs: List[TileRec] = []
    for _, r in df.iterrows():
        fp = Path(str(r["filepath"]))
        recs.append(
            TileRec(
                tile_key=str(r[key_col]),
                filepath=fp,
                bbox=(float(r["minx"]), float(r["miny"]), float(r["maxx"]), float(r["maxy"])),
                centroid=(float(r["centroid_x"]), float(r["centroid_y"])),
                size_mb=float(r["size_mb"]),
                feature_count=int(r["feature_count"]),
                members=str(r["members"]) if not pd.isna(r["members"]) else "",
            )
        )

    # CRS: best effort—read from first tile
    crs = None
    for rec in recs:
        if rec.filepath.exists():
            try:
                if HAVE_PYOGRIO:
                    info = pyogrio.read_info(str(rec.filepath))
                    c = info.get("crs", None)
                    if c is not None:
                        crs = CRS.from_user_input(c)
                        break
                else:
                    g = gpd.read_file(str(rec.filepath), rows=1)
                    if g.crs:
                        crs = CRS.from_user_input(g.crs)
                        break
            except Exception:
                continue

    if crs is None:
        log("WARNING", "Não foi possível detectar CRS dos tiles; assumindo EPSG:31983.", verbose, 0)
        crs = CRS.from_epsg(31983)

    log("INFO", f"tile_index: recs={len(recs)} | key_col={key_col} | tiles_crs={crs.to_string()} | pyogrio={'ON' if HAVE_PYOGRIO else 'OFF'}", verbose, 0)
    return recs, crs


def read_gpkg(path: Path, layer: Optional[str], bbox: Optional[Tuple[float, float, float, float]], verbose: int) -> gpd.GeoDataFrame:
    if HAVE_PYOGRIO:
        return pyogrio.read_dataframe(str(path), layer=layer, bbox=bbox, use_arrow=True)
    return gpd.read_file(str(path), layer=layer, bbox=bbox)


def cache_load_pickle(p: Path) -> Optional[object]:
    try:
        with p.open("rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def cache_save_pickle(p: Path, obj: object) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def utm_epsg_from_lonlat(lon: float, lat: float) -> int:
    # UTM zone
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone
    return 32700 + zone


def ensure_utm_crs(zones_gdf: gpd.GeoDataFrame, verbose: int) -> CRS:
    # Use zones CRS if projected, else infer from centroid lon/lat
    if zones_gdf.crs:
        crs = CRS.from_user_input(zones_gdf.crs)
        if crs.is_projected:
            return crs
    # infer from centroid in EPSG:4326
    z_ll = zones_gdf.to_crs(4326)
    # geopandas warns unary_union is deprecated; prefer shapely.union_all when available
    try:
        if _union_all is not None:
            c = _union_all(z_ll.geometry.values).centroid
        else:
            c = z_ll.geometry.unary_union.centroid
    except Exception:
        c = z_ll.geometry.unary_union.centroid
    epsg = utm_epsg_from_lonlat(float(c.x), float(c.y))
    log("WARNING", f"zones CRS não projetado; usando UTM EPSG:{epsg}", verbose, 0)
    return CRS.from_epsg(epsg)


def bounds_intersect(a: Tuple[float,float,float,float], b: Tuple[float,float,float,float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def green_ratio_for_zone(buffer_geom, green_geoms, verbose: int = 0) -> float:
    a = buffer_geom.area
    if a <= 0:
        return 0.0
    pbuf = prep(buffer_geom)
    buf_bounds = buffer_geom.bounds
    inter_area = 0.0
    for g in green_geoms:
        gb = g.bounds
        if not bounds_intersect(buf_bounds, gb):
            continue
        if not pbuf.intersects(g):
            continue
        # shortcut: fully covered
        try:
            if buffer_geom.covers(g):
                inter_area += g.area
                continue
        except Exception:
            pass
        inter_area += g.intersection(buffer_geom).area
        if inter_area >= a:
            inter_area = a
            break
    return float(inter_area / a)


def flood_ratio_for_zone(buffer_geom, flood_geoms) -> float:
    a = buffer_geom.area
    if a <= 0:
        return 0.0
    pbuf = prep(buffer_geom)
    buf_bounds = buffer_geom.bounds
    inter_area = 0.0
    for g in flood_geoms:
        gb = g.bounds
        if not bounds_intersect(buf_bounds, gb):
            continue
        if not pbuf.intersects(g):
            continue
        try:
            if buffer_geom.covers(g):
                inter_area += g.area
                continue
        except Exception:
            pass
        inter_area += g.intersection(buffer_geom).area
        if inter_area >= a:
            inter_area = a
            break
    return float(inter_area / a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", required=True)
    ap.add_argument("--geodir", required=True, help="Directory with flood gpkg and other geodata")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--cache-dir", default=None)

    ap.add_argument("--zones", default="zones.geojson")
    ap.add_argument("--ranking", default="ranking.csv")

    ap.add_argument("--green-tiles-dir", default=None, help="Required unless --skip-green is set.")
    ap.add_argument("--green-tile-index", default=None, help="Required unless --skip-green is set.")

    ap.add_argument("--green-layer", default=None, help="Layer inside each tile gpkg (optional)")
    ap.add_argument("--flood-gpkg", default="geoportal_mancha_inundacao_25.gpkg")
    ap.add_argument("--flood-layer", default=None)

    ap.add_argument("--r-green-m", type=float, default=700.0)
    ap.add_argument("--r-flood-m", type=float, default=800.0)
    ap.add_argument("--progress-every", type=int, default=10)
    ap.add_argument("--fast-area-sum", action="store_true", help="Skip union/dedupe; sum intersections (can overestimate if overlaps).")
    ap.add_argument("--skip-green", action="store_true", help="Skip green area computation; set green_ratio=0 for all zones.")
    ap.add_argument("--skip-flood", action="store_true", help="Skip flood area computation; set flood_ratio=0 for all zones.")
    ap.add_argument("-v", "--verbose", action="count", default=0)

    args = ap.parse_args()
    verbose = int(args.verbose or 0)

    runs_dir = Path(args.runs_dir)
    geodir = Path(args.geodir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        log("INFO", f"Cache dir: {cache_dir}", verbose, 0)

    zones_fp = runs_dir / args.zones
    ranking_fp = runs_dir / args.ranking
    flood_fp = geodir / args.flood_gpkg

    skip_green = bool(args.skip_green)
    skip_flood = bool(args.skip_flood)

    if not skip_green and (not args.green_tiles_dir or not args.green_tile_index):
        ap.error("--green-tiles-dir and --green-tile-index are required unless --skip-green is set")

    # Fast path: both layers disabled — write zeros and exit immediately.
    if skip_green and skip_flood:
        zones = gpd.read_file(str(zones_fp))
        results = [{"zone_id": str(row.get("zone_id", i)), "green_ratio": 0.0, "flood_ratio": 0.0,
                    "tiles_hit": 0, "tiles_loaded": 0, "green_feats_loaded": 0, "dt_s": 0.0}
                   for i, (_, row) in enumerate(zones.iterrows())]
        df = pd.DataFrame(results)
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_dir / "zones_enriched_green_flood.csv", index=False, encoding="utf-8")
        log("WARNING", "skip-green + skip-flood: both disabled, wrote zeros.", verbose, 0)
        return 0

    green_index_fp = Path(args.green_tile_index) if not skip_green else None

    log("WARNING", "Arquivos:", verbose, 0)
    log("WARNING", f"- zones: {zones_fp}", verbose, 0)
    log("WARNING", f"- ranking: {ranking_fp}", verbose, 0)
    if not skip_flood:
        log("WARNING", f"- flood: {flood_fp} ({file_size_mb(flood_fp):.1f} MB)", verbose, 0)
    if not skip_green:
        log("WARNING", f"- tile_index: {green_index_fp}", verbose, 0)

    t0 = now()
    log("INFO", "→ Ler zones.geojson ...", verbose, 0)
    zones = gpd.read_file(str(zones_fp))
    log("INFO", f"✓ Ler zones.geojson ({now()-t0:.2f}s) | zones={len(zones)}", verbose, 0)

    # Ensure UTM CRS for buffers
    utm_crs = ensure_utm_crs(zones, verbose)
    zones_utm = zones.to_crs(utm_crs)

    # Load tiles index (only when green is enabled)
    tile_recs = []
    tiles_crs = None
    tf_utm_to_tiles = None
    tile_boxes = []
    tile_tree = STRtree([])
    tile_box_id_to_idx: Dict[int, int] = {}
    if not skip_green:
        t1 = now()
        tile_recs, tiles_crs = read_tile_index(green_index_fp, verbose)
        log("INFO", f"✓ Ler tile_index.csv ({now()-t1:.2f}s)", verbose, 0)
        tf_utm_to_tiles = Transformer.from_crs(utm_crs, tiles_crs, always_xy=True)
        tile_boxes = [box(*tr.bbox) for tr in tile_recs]
        tile_tree = STRtree(tile_boxes)
        tile_box_id_to_idx = {id(g): i for i, g in enumerate(tile_boxes)}

    # Load flood data (only when flood is enabled)
    flood_geoms: list = []
    if not skip_flood:
        cached_flood = None
        flood_cache_key = None
        if cache_dir:
            flood_cache_key = cache_dir / "flood_geoms.pkl"
            cached_flood = cache_load_pickle(flood_cache_key)
        if cached_flood is not None:
            flood_geoms = cached_flood
            log("INFO", f"Cache HIT flood: {flood_cache_key.name} | geoms={len(flood_geoms):,}", verbose, 0)
        else:
            t2 = now()
            log("INFO", "→ Carregar alagamento ...", verbose, 0)
            flood_gdf = read_gpkg(flood_fp, args.flood_layer, None, verbose)
            flood_utm = flood_gdf.to_crs(utm_crs)
            flood_geoms = list(flood_utm.geometry.values)
            log("INFO", f"✓ Carregar alagamento ({now()-t2:.2f}s) | flood_polys={len(flood_geoms):,}", verbose, 0)
            if cache_dir and flood_cache_key:
                cache_save_pickle(flood_cache_key, flood_geoms)
                log("INFO", f"Cache SAVE flood: {flood_cache_key.name}", verbose, 1)

    # Tile gdf cache (in-memory) by filepath
    tile_gdf_cache: Dict[str, gpd.GeoDataFrame] = {}

    results = []
    t_all = now()
    for i, (idx, row) in enumerate(zones_utm.iterrows(), start=1):
        zid = str(row.get("zone_id", idx))
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        t_zone = now()

        # buffers in UTM
        buf_green = geom.buffer(args.r_green_m)
        buf_flood = geom.buffer(args.r_flood_m)

        if skip_green and skip_flood:
            gr, fr = 0.0, 0.0
            tiles_hit, tiles_loaded, feats_loaded = 0, 0, 0
        elif skip_green:
            gr = 0.0
            fr = flood_ratio_for_zone(buf_flood, flood_geoms)
            tiles_hit, tiles_loaded, feats_loaded = 0, 0, 0
        else:
            # zone bbox in tiles CRS (transform min/max corners)
            minx, miny, maxx, maxy = buf_green.bounds
            x0, y0 = tf_utm_to_tiles.transform(minx, miny)
            x1, y1 = tf_utm_to_tiles.transform(maxx, maxy)
            bb_tiles = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            query_geom = box(*bb_tiles)

            # select tiles by bbox intersect
            # Shapely 2.x STRtree.query returns indices (np.int64), Shapely 1.x returns geometries.
            try:
                cand = tile_tree.query(query_geom, predicate="intersects")
            except TypeError:
                cand = tile_tree.query(query_geom)

            cand_idx: List[int] = []
            if cand is None:
                cand_idx = []
            else:
                # numpy array of indices
                if np is not None and hasattr(cand, "dtype") and str(getattr(cand, "dtype", "")) != "object":
                    cand_idx = [int(x) for x in cand.tolist()]
                else:
                    # list/array of geometries or indices
                    for x in list(cand):
                        if isinstance(x, (int,)) or (np is not None and isinstance(x, getattr(np, "integer", ()))):
                            cand_idx.append(int(x))
                        else:
                            j = tile_box_id_to_idx.get(id(x))
                            if j is not None:
                                cand_idx.append(int(j))

            # dedupe indices, preserve order
            cand_idx = list(dict.fromkeys(cand_idx))
            cand_recs = [tile_recs[j] for j in cand_idx if bounds_intersect(tile_recs[j].bbox, bb_tiles)]

            # Load green geoms from needed tiles
            green_geoms = []
            tiles_loaded = 0
            feats_loaded = 0
            for tr in cand_recs:
                key = str(tr.filepath.resolve())
                if key in tile_gdf_cache:
                    gdf_tile_utm = tile_gdf_cache[key]
                else:
                    tiles_loaded += 1
                    t_load = now()
                    gdf_tile = read_gpkg(tr.filepath, args.green_layer, None, verbose)
                    # ensure tile CRS; project to UTM for geometry operations
                    if gdf_tile.crs:
                        gdf_tile_utm = gdf_tile.to_crs(utm_crs)
                    else:
                        # assume tiles_crs
                        gdf_tile.set_crs(tiles_crs, inplace=True, allow_override=True)
                        gdf_tile_utm = gdf_tile.to_crs(utm_crs)
                    tile_gdf_cache[key] = gdf_tile_utm
                    if verbose >= 2:
                        log("DEBUG", f"tile_load: {Path(key).name} feats={len(gdf_tile_utm):,} dt={now()-t_load:.2f}s", verbose, 2)
                feats_loaded += int(len(gdf_tile_utm))
                green_geoms.extend(list(gdf_tile_utm.geometry.values))

            # Compute ratios
            gr = green_ratio_for_zone(buf_green, green_geoms, verbose)
            fr = flood_ratio_for_zone(buf_flood, flood_geoms) if not skip_flood else 0.0
            tiles_hit = len(cand_recs)

        results.append({
            "zone_id": zid,
            "green_ratio": gr,
            "flood_ratio": fr,
            "tiles_hit": tiles_hit,
            "tiles_loaded": tiles_loaded,
            "green_feats_loaded": feats_loaded,
            "dt_s": now() - t_zone
        })

        if (i % args.progress_every == 0) or verbose >= 2:
            log("INFO", f"[{i}/{len(zones_utm)}] zone={zid} tiles_hit={tiles_hit} tiles_loaded={tiles_loaded} green_ratio={gr:.3f} flood_ratio={fr:.3f} dt={now()-t_zone:.2f}s", verbose, 0)

    df = pd.DataFrame(results)
    out_fp = out_dir / "zones_enriched_green_flood.csv"
    df.to_csv(out_fp, index=False, encoding="utf-8")
    log("WARNING", f"✓ Salvo: {out_fp} | rows={len(df)} | total={now()-t_all:.1f}s", verbose, 0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
