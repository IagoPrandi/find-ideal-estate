#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gpkg_grid_tiler_v3_splitmerge.py

Divide uma camada de um GeoPackage grande em partes usando uma malha (grid),
com **split recursivo** para tiles grandes (>= --max-mb) e **merge** para tiles
pequenos (< --min-mb), tentando manter os arquivos finais dentro do intervalo
[min_mb, max_mb].

Saídas:
- <out-dir>/tiles_final/           (arquivos finais por "grupo")
- <out-dir>/tile_index.csv         (arquivo de apoio com bbox + centróide + members + filepath)

Por que tamanhos variam?
- Densidade/complexidade geométrica é heterogênea.
- GeoPackage tem overhead fixo por arquivo.

Recomendação prática (chunk ~20MB):
- Use --min-mb 20 --max-mb 25 (equilíbrio: evita grupos gigantes, permite bater mínimo)
- Se você exige "NENHUM" arquivo > 20MB: use --max-mb 20 --min-mb 0 (mas muitos ficarão <20MB).

PowerShell (exemplo):
python .\gpkg_grid_tiler_v3_splitmerge.py `
  --in-gpkg ".\data_cache\geosampa\SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg" `
  --layer "SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA" `
  --out-dir ".\data_cache\geosampa\green_tiles_v3" `
  --cell-size-m 8000 `
  --min-mb 20 `
  --max-mb 25 `
  --skip-empty `
  -v

Dependências:
- geopandas, shapely
- pyogrio (opcional, recomendado)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Set

try:
    import pyogrio  # type: ignore
    HAVE_PYOGRIO = True
except Exception:
    HAVE_PYOGRIO = False

import geopandas as gpd  # type: ignore

from shapely.geometry import box  # type: ignore
from shapely.prepared import prep  # type: ignore

try:
    from shapely.strtree import STRtree  # type: ignore
    HAVE_STRTREE = True
except Exception:
    HAVE_STRTREE = False


# -------------------- logging --------------------

def _ts() -> str:
    return time.strftime("%H:%M:%S")


def log(level: str, msg: str, verbose: int, min_v: int = 0) -> None:
    if verbose >= min_v:
        print(f"{_ts()} | {level:<7} | {msg}", flush=True)


def fmt_mb(nbytes: int) -> float:
    return nbytes / (1024 * 1024)


def file_size_mb(p: Path) -> float:
    try:
        return fmt_mb(p.stat().st_size)
    except FileNotFoundError:
        return 0.0


# -------------------- metadata helpers --------------------


def detect_layers(gpkg_path: Path) -> List[str]:
    if HAVE_PYOGRIO:
        try:
            res = pyogrio.list_layers(str(gpkg_path))
            if hasattr(res, "columns") and "name" in list(getattr(res, "columns")):
                return [str(x) for x in res["name"].tolist()]
            try:
                import numpy as np  # type: ignore
                if isinstance(res, np.ndarray):
                    res = res.tolist()
            except Exception:
                pass
            if isinstance(res, (list, tuple)):
                out: List[str] = []
                for it in res:
                    if it is None:
                        continue
                    if isinstance(it, str):
                        out.append(it)
                    elif isinstance(it, dict) and "name" in it:
                        out.append(str(it["name"]))
                    elif isinstance(it, (list, tuple)) and len(it) >= 1:
                        out.append(str(it[0]))
                if out:
                    return out
        except Exception:
            pass
    try:
        import fiona  # type: ignore
        return list(fiona.listlayers(str(gpkg_path)))
    except Exception:
        return []


def read_bbox_and_crs(gpkg_path: Path, layer: str, verbose: int) -> Tuple[Tuple[float, float, float, float], str]:
    """Tenta obter bbox + CRS de forma O(1) via SQLite; fallback via driver."""

    # 1) SQLite metadata
    try:
        con = sqlite3.connect(str(gpkg_path))
        cur = con.cursor()

        geom_col: Optional[str] = None
        try:
            cur.execute(
                "SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name=? LIMIT 1;",
                (layer,),
            )
            row = cur.fetchone()
            srs_id = None
            if row:
                geom_col = str(row[0]) if row[0] else None
                srs_id = int(row[1]) if row[1] is not None else None
        except Exception:
            geom_col, srs_id = None, None

        bounds: Optional[Tuple[float, float, float, float]] = None
        cur.execute("SELECT min_x, min_y, max_x, max_y FROM gpkg_contents WHERE table_name=?;", (layer,))
        row = cur.fetchone()
        if row and all(v is not None for v in row):
            bounds = (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
            log("INFO", f"bbox via SQLite(gpkg_contents): {bounds}", verbose, 1)

        if bounds is None and geom_col:
            rtree = f"rtree_{layer}_{geom_col}"
            try:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;",
                    (rtree,),
                )
                if cur.fetchone():
                    cur.execute(f"SELECT MIN(minx), MIN(miny), MAX(maxx), MAX(maxy) FROM {rtree};")
                    rr = cur.fetchone()
                    if rr and all(v is not None for v in rr):
                        bounds = (float(rr[0]), float(rr[1]), float(rr[2]), float(rr[3]))
                        log("INFO", f"bbox via SQLite(rtree): {bounds} | table={rtree}", verbose, 1)
            except Exception:
                pass

        crs_str = ""
        if srs_id is not None:
            try:
                cur.execute(
                    "SELECT organization, organization_coordsys_id, definition FROM gpkg_spatial_ref_sys WHERE srs_id=? LIMIT 1;",
                    (srs_id,),
                )
                srs = cur.fetchone()
                if srs:
                    org, org_id, definition = srs
                    if org and str(org).upper() == "EPSG" and org_id is not None:
                        crs_str = f"EPSG:{int(org_id)}"
                    elif definition:
                        crs_str = str(definition)
            except Exception:
                pass

        con.close()

        if bounds is not None:
            return bounds, crs_str

        log("WARNING", "gpkg_contents sem bounds preenchidos; usando fallback via driver.", verbose, 0)
    except Exception as e:
        log("WARNING", f"Falha SQLite bbox/crs: {e!r} (fallback via driver)", verbose, 0)

    # 2) pyogrio info
    if HAVE_PYOGRIO:
        try:
            info = None
            if hasattr(pyogrio, "read_info"):
                info = pyogrio.read_info(str(gpkg_path), layer=layer)
            elif hasattr(pyogrio, "info"):
                info = pyogrio.info(str(gpkg_path), layer=layer)
            if isinstance(info, dict):
                # keys vary by version
                for k in ("bounds", "total_bounds", "extent", "bbox"):
                    if k in info and info[k] is not None:
                        b = info[k]
                        bounds = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                        crs = info.get("crs", "")
                        log("INFO", f"bbox via pyogrio({k}): {bounds}", verbose, 1)
                        return bounds, str(crs) if crs else ""
                if "layer" in info and isinstance(info["layer"], dict):
                    sub = info["layer"]
                    for k in ("bounds", "total_bounds", "extent", "bbox"):
                        if k in sub and sub[k] is not None:
                            b = sub[k]
                            bounds = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
                            crs = sub.get("crs", info.get("crs", ""))
                            log("INFO", f"bbox via pyogrio(layer.{k}): {bounds}", verbose, 1)
                            return bounds, str(crs) if crs else ""
        except Exception as e:
            log("WARNING", f"Falha pyogrio bbox: {e!r}", verbose, 0)

    # 3) fiona
    try:
        import fiona  # type: ignore
        with fiona.open(str(gpkg_path), layer=layer) as src:
            b = src.bounds
            bounds = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            crs = src.crs_wkt or ""
            log("INFO", f"bbox via fiona: {bounds}", verbose, 1)
            return bounds, crs
    except Exception as e:
        log("WARNING", f"Falha fiona bbox: {e!r} (usando geopandas total_bounds)", verbose, 0)

    # 4) geopandas
    gdf = gpd.read_file(str(gpkg_path), layer=layer)
    b = gdf.total_bounds
    return (float(b[0]), float(b[1]), float(b[2]), float(b[3])), str(gdf.crs) if gdf.crs else ""


# -------------------- IO with bbox pushdown --------------------


def read_by_bbox(
    gpkg_path: Path,
    layer: str,
    bbox: Tuple[float, float, float, float],
    columns: Optional[List[str]] = None,
) -> gpd.GeoDataFrame:
    if HAVE_PYOGRIO:
        return pyogrio.read_dataframe(
            str(gpkg_path),
            layer=layer,
            bbox=bbox,
            columns=columns,
            use_arrow=True,
        )
    return gpd.read_file(str(gpkg_path), layer=layer, bbox=bbox)


def write_gpkg(gdf: gpd.GeoDataFrame, out_path: Path, layer_name: str = "data") -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # garantir overwrite consistente (Windows/SQLite pode manter handle; tentamos remover antes)
    try:
        if out_path.exists():
            out_path.unlink()
    except Exception:
        pass
    if HAVE_PYOGRIO:
        # pyogrio escreve rápido; se arquivo existir, sobrescreve
        pyogrio.write_dataframe(gdf, str(out_path), layer=layer_name, driver="GPKG")
    else:
        gdf.to_file(str(out_path), layer=layer_name, driver="GPKG")


# -------------------- tiling core --------------------

@dataclass
class FinalPart:
    part_id: str
    filepath: Path
    bbox: Tuple[float, float, float, float]
    centroid: Tuple[float, float]
    size_mb: float
    feature_count: int
    members: List[str]


def centroid_of_bbox(b: Tuple[float, float, float, float]) -> Tuple[float, float]:
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def bbox_union(bboxes: Sequence[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    minx = min(b[0] for b in bboxes)
    miny = min(b[1] for b in bboxes)
    maxx = max(b[2] for b in bboxes)
    maxy = max(b[3] for b in bboxes)
    return (minx, miny, maxx, maxy)


def make_grid(bounds: Tuple[float, float, float, float], cell: float) -> List[Tuple[int, int, Tuple[float, float, float, float]]]:
    minx, miny, maxx, maxy = bounds
    nx = max(1, int(math.ceil((maxx - minx) / cell)))
    ny = max(1, int(math.ceil((maxy - miny) / cell)))
    tiles: List[Tuple[int, int, Tuple[float, float, float, float]]] = []
    for iy in range(ny):
        y0 = miny + iy * cell
        y1 = min(y0 + cell, maxy)
        for ix in range(nx):
            x0 = minx + ix * cell
            x1 = min(x0 + cell, maxx)
            tiles.append((ix, iy, (x0, y0, x1, y1)))
    return tiles


def clip_to_bbox(gdf: gpd.GeoDataFrame, bbox: Tuple[float, float, float, float]) -> gpd.GeoDataFrame:
    """Clip rápido: só intersecta geoms que extrapolam bbox."""
    if gdf.empty:
        return gdf

    tile_poly = box(*bbox)
    ptile = prep(tile_poly)

    # bounds numérico para evitar intersection em quem já está dentro
    minx, miny, maxx, maxy = bbox
    gb = gdf.geometry.bounds
    inside = (gb.minx >= minx) & (gb.miny >= miny) & (gb.maxx <= maxx) & (gb.maxy <= maxy)

    # remove geoms que na prática não intersectam (por segurança)
    try:
        inter_mask = gdf.geometry.apply(ptile.intersects)
        gdf = gdf.loc[inter_mask].copy()
        if gdf.empty:
            return gdf
        gb = gdf.geometry.bounds
        inside = (gb.minx >= minx) & (gb.miny >= miny) & (gb.maxx <= maxx) & (gb.maxy <= maxy)
    except Exception:
        pass

    if (~inside).any():
        # intersect apenas no subset
        gdf.loc[~inside, "geometry"] = gdf.loc[~inside, "geometry"].apply(lambda g: g.intersection(tile_poly))

    gdf = gdf[~gdf.geometry.is_empty].copy()
    return gdf


def split_bbox_2x2(b: Tuple[float, float, float, float]) -> List[Tuple[float, float, float, float]]:
    minx, miny, maxx, maxy = b
    mx = (minx + maxx) / 2.0
    my = (miny + maxy) / 2.0
    return [
        (minx, miny, mx, my),
        (mx, miny, maxx, my),
        (minx, my, mx, maxy),
        (mx, my, maxx, maxy),
    ]


def tile_id(depth: int, ix: int, iy: int) -> str:
    return f"tile_d{depth:02d}_x{ix:05d}_y{iy:05d}"


def build_initial_tiles(
    in_gpkg: Path,
    layer: str,
    out_dir: Path,
    grid_tiles: List[Tuple[int, int, Tuple[float, float, float, float]]],
    max_mb: Optional[float],
    min_cell_size: float,
    max_depth: int,
    skip_empty: bool,
    verbose: int,
    progress_every: int,
) -> List[FinalPart]:
    """Gera tiles finais garantindo (quando possível) size <= max_mb via split recursivo."""

    parts: List[FinalPart] = []
    queue: List[Tuple[int, int, int, Tuple[float, float, float, float]]] = []  # ix, iy, depth, bbox

    for ix, iy, bb in grid_tiles:
        queue.append((ix, iy, 0, bb))

    tiles_dir = out_dir / "tiles_raw"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    splits = 0
    while queue:
        ix, iy, depth, bb = queue.pop(0)
        processed += 1

        t0 = time.perf_counter()
        gdf = read_by_bbox(in_gpkg, layer, bb, columns=None)
        t_read = time.perf_counter() - t0

        if gdf.empty:
            if not skip_empty:
                # ainda grava arquivo vazio? (não recomendado)
                pass
            if verbose >= 2:
                log("INFO", f"{tile_id(depth, ix, iy)} vazio | read={t_read:.2f}s", verbose, 2)
            continue

        # mantém CRS
        # clip reduz duplicação entre tiles e tamanho final
        t1 = time.perf_counter()
        gdf = clip_to_bbox(gdf, bb)
        t_clip = time.perf_counter() - t1
        if gdf.empty:
            if verbose >= 2:
                log("INFO", f"{tile_id(depth, ix, iy)} vazio após clip | read={t_read:.2f}s clip={t_clip:.2f}s", verbose, 2)
            continue

        out_path = tiles_dir / f"{tile_id(depth, ix, iy)}.gpkg"
        t2 = time.perf_counter()
        write_gpkg(gdf, out_path, layer_name="data")
        t_write = time.perf_counter() - t2

        size = file_size_mb(out_path)
        feats = int(len(gdf))

        # split se exceder max_mb
        width = bb[2] - bb[0]
        height = bb[3] - bb[1]
        can_split = (depth < max_depth) and (min(width, height) / 2.0 >= min_cell_size)

        if max_mb is not None and size > max_mb and can_split:
            splits += 1
            try:
                out_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
            except Exception:
                try:
                    os.remove(str(out_path))
                except Exception:
                    pass

            kids = split_bbox_2x2(bb)
            # mapeia coordenadas de sub-índice para manter nomes distintos
            for k, kbb in enumerate(kids):
                kix = ix * 2 + (k % 2)
                kiy = iy * 2 + (k // 2)
                queue.append((kix, kiy, depth + 1, kbb))

            log(
                "WARNING",
                f"SPLIT {tile_id(depth, ix, iy)} size={size:.1f}MB feats={feats} (>{max_mb:.1f}) | read={t_read:.2f}s clip={t_clip:.2f}s write={t_write:.2f}s | depth={depth}->{depth+1}",
                verbose,
                0,
            )
            continue

        part = FinalPart(
            part_id=tile_id(depth, ix, iy),
            filepath=out_path,
            bbox=bb,
            centroid=centroid_of_bbox(bb),
            size_mb=size,
            feature_count=feats,
            members=[tile_id(depth, ix, iy)],
        )
        parts.append(part)

        if progress_every > 0 and processed % progress_every == 0:
            log(
                "INFO",
                f"tiles_processados={processed} | parts={len(parts)} | splits={splits} | last={part.part_id} size={size:.1f}MB feats={feats} read={t_read:.2f}s clip={t_clip:.2f}s write={t_write:.2f}s",
                verbose,
                0,
            )

    log("INFO", f"✓ Tiles base gerados: parts={len(parts)} | splits={splits}", verbose, 0)
    return parts


def build_neighbor_index(parts: List[FinalPart], verbose: int) -> Tuple[Optional[STRtree], List]:
    if not HAVE_STRTREE:
        log("WARNING", "STRtree não disponível; merge de vizinhos ficará limitado.", verbose, 0)
        return None, []
    geoms = [box(*p.bbox) for p in parts]
    return STRtree(geoms), geoms


def find_neighbors(idx_tree: STRtree, geom_list: List, parts: List[FinalPart], i: int) -> List[int]:
    """Retorna índices dos parts cujos bboxes tocam/intersectam o bbox do part i."""
    g = geom_list[i]
    cand = idx_tree.query(g)
    out: List[int] = []
    for c in cand:
        # shapely 2 pode devolver geometria; shapely 1 devolve índice? STRtree api varia.
        # Normaliza: se 'c' for int usa como índice; senão procura o índice na lista (fallback)
        if isinstance(c, int):
            j = c
        else:
            # fallback O(n) (raro)
            try:
                j = geom_list.index(c)
            except Exception:
                continue
        if j == i:
            continue
        # vizinhos se intersectam / tocam
        if g.touches(geom_list[j]) or g.intersects(geom_list[j]):
            out.append(j)
    return out


def merge_parts_to_range(
    parts: List[FinalPart],
    min_mb: float,
    max_mb: Optional[float],
    out_dir: Path,
    verbose: int,
) -> List[FinalPart]:
    """Agrupa parts pequenos (<min_mb) com vizinhos tentando não ultrapassar max_mb."""

    if min_mb <= 0:
        # nada a fazer
        final_dir = out_dir / "tiles_final"
        final_dir.mkdir(parents=True, exist_ok=True)
        # move/renomeia para tiles_final
        final_parts: List[FinalPart] = []
        for p in parts:
            newp = final_dir / p.filepath.name
            if newp.resolve() != p.filepath.resolve():
                newp.parent.mkdir(parents=True, exist_ok=True)
                p.filepath.replace(newp)
                p.filepath = newp
            final_parts.append(p)
        return final_parts

    if not HAVE_STRTREE:
        log("WARNING", "Sem STRtree: não vou fazer merge; mantendo tiles individuais.", verbose, 0)
        return parts

    idx_tree, geoms = build_neighbor_index(parts, verbose)
    assert idx_tree is not None

    # ordenar por tamanho (pequenos primeiro)
    order = sorted(range(len(parts)), key=lambda i: parts[i].size_mb)
    used: Set[int] = set()

    final_dir = out_dir / "tiles_final"
    final_dir.mkdir(parents=True, exist_ok=True)

    groups: List[FinalPart] = []

    def group_hash(members: List[str]) -> str:
        h = hashlib.sha1("|".join(sorted(members)).encode("utf-8")).hexdigest()[:8]
        return h

    for i in order:
        if i in used:
            continue
        p0 = parts[i]

        if p0.size_mb >= min_mb:
            # já está ok (e também já deve estar <= max_mb se max configurado)
            used.add(i)
            # move para tiles_final
            newp = final_dir / p0.filepath.name
            if newp.resolve() != p0.filepath.resolve():
                p0.filepath.replace(newp)
                p0.filepath = newp
            groups.append(p0)
            continue

        # começar grupo
        member_idx: List[int] = [i]
        used.add(i)
        total = p0.size_mb

        # conjunto de candidatos vizinhos não usados
        frontier: Set[int] = set(j for j in find_neighbors(idx_tree, geoms, parts, i) if j not in used)

        # tenta crescer até min_mb
        while total < min_mb and frontier:
            # escolha do vizinho: preferir aquele que chega mais perto do min sem estourar max
            best_j = None
            best_score = None
            for j in list(frontier):
                pj = parts[j]
                new_total = total + pj.size_mb
                if max_mb is not None and new_total > max_mb:
                    continue
                score = abs(min_mb - new_total)
                if best_score is None or score < best_score:
                    best_score = score
                    best_j = j

            if best_j is None:
                # não existe vizinho que não estoure max
                break

            frontier.remove(best_j)
            used.add(best_j)
            member_idx.append(best_j)
            total += parts[best_j].size_mb

            # expande fronteira com vizinhos do novo membro
            for nb in find_neighbors(idx_tree, geoms, parts, best_j):
                if nb not in used:
                    frontier.add(nb)

        if total < min_mb:
            log("WARNING", f"Grupo ficou <min_mb: start={p0.part_id} total={total:.1f}MB (min={min_mb:.1f}) | sem vizinhos viáveis (max={max_mb})", verbose, 0)

        # escrever group gpkg concatenando layers "data" dos membros
        t0 = time.perf_counter()
        frames: List[gpd.GeoDataFrame] = []
        feats_total = 0
        for j in member_idx:
            g = read_gpkg_file(parts[j].filepath)
            frames.append(g)
            feats_total += int(len(g))
        import pandas as pd  # type: ignore
        if frames:
            df = pd.concat(frames, ignore_index=True)
            gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=frames[0].crs)
        else:
            gdf = gpd.GeoDataFrame()

        bbox = bbox_union([parts[j].bbox for j in member_idx])
        centroid = centroid_of_bbox(bbox)
        members = [parts[j].part_id for j in member_idx]

        gid = f"group_{len(groups)+1:04d}_{group_hash(members)}"
        out_path = final_dir / f"{gid}.gpkg"

        t1 = time.perf_counter()
        write_gpkg(gdf, out_path, layer_name="data")
        t_write = time.perf_counter() - t1
        total_time = time.perf_counter() - t0
        size = file_size_mb(out_path)

        # se max_mb e ainda estourou (overhead), loga
        if max_mb is not None and size > max_mb + 0.5:
            log("WARNING", f"Grupo excedeu max_mb após write: {gid} size={size:.1f}MB (max={max_mb:.1f}). Sugestão: reduza --cell-size-m ou --max-mb+tol.", verbose, 0)

        groups.append(
            FinalPart(
                part_id=gid,
                filepath=out_path,
                bbox=bbox,
                centroid=centroid,
                size_mb=size,
                feature_count=feats_total,
                members=members,
            )
        )

        log(
            "INFO",
            f"{gid}: members={len(members)} feats={feats_total:,} size={size:.1f}MB total={total:.1f}MB read+concat={total_time - t_write:.2f}s write={t_write:.2f}s",
            verbose,
            0,
        )

    # limpar tiles_raw (opcional é feito no main)
    return groups


def read_gpkg_file(path: Path) -> gpd.GeoDataFrame:
    if HAVE_PYOGRIO:
        return pyogrio.read_dataframe(str(path), layer="data", use_arrow=True)
    return gpd.read_file(str(path), layer="data")


def pd_concat(frames: List[gpd.GeoDataFrame]):
    import pandas as pd  # type: ignore
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def write_index(parts: List[FinalPart], out_csv: Path, verbose: int) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "group_id",
            "filepath",
            "size_mb",
            "feature_count",
            "minx",
            "miny",
            "maxx",
            "maxy",
            "centroid_x",
            "centroid_y",
            "members",
        ])
        for p in parts:
            minx, miny, maxx, maxy = p.bbox
            cx, cy = p.centroid
            w.writerow([
                p.part_id,
                str(p.filepath).replace("\\", "/"),
                f"{p.size_mb:.3f}",
                p.feature_count,
                f"{minx:.6f}",
                f"{miny:.6f}",
                f"{maxx:.6f}",
                f"{maxy:.6f}",
                f"{cx:.6f}",
                f"{cy:.6f}",
                "|".join(p.members),
            ])
    log("INFO", f"✓ tile_index.csv escrito: {out_csv}", verbose, 0)


def cleanup_dir(p: Path, verbose: int) -> None:
    if not p.exists():
        return
    for fp in p.glob("**/*"):
        try:
            if fp.is_file():
                fp.unlink()
        except Exception:
            pass
    # tenta remover dirs vazios
    for dp in sorted([d for d in p.glob("**/*") if d.is_dir()], reverse=True):
        try:
            dp.rmdir()
        except Exception:
            pass
    try:
        p.rmdir()
    except Exception:
        pass
    log("INFO", f"cleanup: removido {p}", verbose, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-gpkg", required=True)
    ap.add_argument("--layer", default="")
    ap.add_argument("--out-dir", required=True)

    ap.add_argument("--cell-size-m", type=float, default=8000.0)
    ap.add_argument("--min-mb", type=float, default=20.0)
    ap.add_argument("--max-mb", type=float, default=0.0, help="0 para desativar cap; recomendado: 25 para min=20")
    ap.add_argument("--min-cell-size-m", type=float, default=1500.0)
    ap.add_argument("--max-depth", type=int, default=6)

    ap.add_argument("--skip-empty", action="store_true")
    ap.add_argument("--cleanup-raw", action="store_true", help="remove tiles_raw ao final")

    ap.add_argument("--progress-every", type=int, default=25)
    ap.add_argument("-v", "--verbose", action="count", default=0)

    args = ap.parse_args()

    in_path = Path(args.in_gpkg)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        raise SystemExit(f"Arquivo não encontrado: {in_path}")

    layer = args.layer.strip()
    layers = detect_layers(in_path)
    if not layer:
        if not layers:
            raise SystemExit("Não consegui detectar layers no GeoPackage.")
        layer = layers[0]
        log("WARNING", f"--layer não informado. Usando primeira layer: {layer}", args.verbose, 0)

    size_mb_in = file_size_mb(in_path)
    log("WARNING", f"Entrada: {in_path} | size={size_mb_in:.1f}MB | layer={layer}", args.verbose, 0)
    log("INFO", f"pyogrio={'ON' if HAVE_PYOGRIO else 'OFF'} | cell={args.cell_size_m} | min_mb={args.min_mb} | max_mb={args.max_mb}", args.verbose, 0)

    bounds, crs_str = read_bbox_and_crs(in_path, layer, args.verbose)
    log("INFO", f"bounds={bounds} | crs={crs_str or 'N/A'}", args.verbose, 0)

    grid = make_grid(bounds, args.cell_size_m)
    log("INFO", f"grid_tiles={len(grid)} (cell={args.cell_size_m})", args.verbose, 0)

    max_mb = args.max_mb if args.max_mb and args.max_mb > 0 else None
    if max_mb is not None and max_mb < args.min_mb:
        log("WARNING", f"max_mb({max_mb}) < min_mb({args.min_mb}). Isso impede alcançar o mínimo por merge. Use max>=min (ex.: min=20 max=25).", args.verbose, 0)

    t_all = time.perf_counter()

    parts = build_initial_tiles(
        in_gpkg=in_path,
        layer=layer,
        out_dir=out_dir,
        grid_tiles=grid,
        max_mb=max_mb,
        min_cell_size=args.min_cell_size_m,
        max_depth=args.max_depth,
        skip_empty=args.skip_empty,
        verbose=args.verbose,
        progress_every=max(1, args.progress_every),
    )

    # estatísticas rápidas
    if parts:
        sizes = sorted(p.size_mb for p in parts)
        p50 = sizes[len(sizes)//2]
        p95 = sizes[int(len(sizes)*0.95)-1] if len(sizes) >= 20 else sizes[-1]
        log("WARNING", f"Tiles base: n={len(parts)} | min={sizes[0]:.2f}MB p50={p50:.2f}MB p95={p95:.2f}MB max={sizes[-1]:.2f}MB", args.verbose, 0)

    # merge para alcançar min_mb sem estourar max_mb
    if args.min_mb > 0:
        parts2 = merge_parts_to_range(
            parts=parts,
            min_mb=args.min_mb,
            max_mb=max_mb,
            out_dir=out_dir,
            verbose=args.verbose,
        )
    else:
        parts2 = parts

    # index
    write_index(parts2, out_dir / "tile_index.csv", args.verbose)

    # opcional: remover tiles_raw
    if args.cleanup_raw:
        cleanup_dir(out_dir / "tiles_raw", args.verbose)

    dt = time.perf_counter() - t_all
    log("WARNING", f"Resumo: parts_final={len(parts2)} | tempo={dt/60.0:.1f} min | out={out_dir}", args.verbose, 0)

    # avisos de limites
    if max_mb is not None:
        over = [p for p in parts2 if p.size_mb > max_mb + 0.5]
        if over:
            log("WARNING", f"⚠ {len(over)} parts excederam max_mb({max_mb}). Normalmente é overhead ou merge; ajuste cell/max.", args.verbose, 0)

    under = [p for p in parts2 if p.size_mb < args.min_mb]
    if args.min_mb > 0 and under:
        log("WARNING", f"⚠ {len(under)} parts ficaram < min_mb({args.min_mb}). Isso acontece em regiões esparsas/isoladas.", args.verbose, 0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
