from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


def _as_path(value: object) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text)


def _resolve_green_inputs(geodir: Path, params: Dict[str, Any]) -> tuple[Path, Path]:
    green_tiles_dir = _as_path(params.get("green_tiles_dir"))
    if green_tiles_dir is None:
        green_tiles_dir = geodir / "green_tiles_v3"

    green_tile_index = _as_path(params.get("green_tile_index"))
    if green_tile_index is None:
        green_tile_index = green_tiles_dir / "tile_index.csv"

    return green_tiles_dir, green_tile_index


def _ensure_green_tile_index(
    geodir: Path,
    green_tile_index: Path,
    green_tiles_dir: Path,
    params: Dict[str, Any],
) -> tuple[Path, Path]:
    if green_tile_index.exists():
        return green_tiles_dir, green_tile_index

    tiler_script = Path("cods_ok") / "gpkg_grid_tiler_v3_splitmerge.py"
    source_gpkg = _as_path(params.get("green_source_gpkg"))
    if source_gpkg is None:
        source_gpkg = geodir / "SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA.gpkg"

    source_layer = str(params.get("green_source_layer") or "SIRGAS_GPKG_VEGETACAO_SIGNIFICATIVA")
    cell_size_m = str(params.get("green_tile_cell_size_m") or 8000)
    min_mb = str(params.get("green_tile_min_mb") or 20)
    max_mb = str(params.get("green_tile_max_mb") or 25)
    tiler_verbose = int(params.get("green_tile_verbose", 1))

    if not source_gpkg.exists():
        raise FileNotFoundError(
            f"Green tile index not found: {green_tile_index}. "
            f"Also missing source green gpkg for auto-generation: {source_gpkg}."
        )

    target_tiles_dir = green_tiles_dir
    target_tile_index = green_tile_index
    try:
        target_tiles_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        target_tiles_dir = Path(params.get("green_tiles_fallback_dir") or (Path("cache") / "green_tiles_v3"))
        target_tiles_dir.mkdir(parents=True, exist_ok=True)
        target_tile_index = target_tiles_dir / "tile_index.csv"

    args = [
        sys.executable,
        str(tiler_script),
        "--in-gpkg",
        str(source_gpkg),
        "--layer",
        source_layer,
        "--out-dir",
        str(target_tiles_dir),
        "--cell-size-m",
        cell_size_m,
        "--min-mb",
        min_mb,
        "--max-mb",
        max_mb,
        "--skip-empty",
    ]
    if tiler_verbose > 0:
        args.extend(["-v"] * tiler_verbose)

    subprocess.run(args, check=True)

    if not target_tile_index.exists():
        raise FileNotFoundError(
            f"Green tile index generation finished but file is still missing: {target_tile_index}."
        )
    return target_tiles_dir, target_tile_index


def _normalize_tile_index_paths(tile_index_path: Path, out_dir: Path) -> Path:
    normalized_path = out_dir / "tile_index.normalized.csv"
    with tile_index_path.open("r", encoding="utf-8", newline="") as src:
        reader = csv.DictReader(src)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    if "filepath" not in fieldnames:
        raise ValueError("tile_index.csv missing required column: filepath")

    base_dir = tile_index_path.parent
    for row in rows:
        raw_fp = (row.get("filepath") or "").strip()
        if not raw_fp:
            continue
        fp = Path(raw_fp)
        if not fp.is_absolute():
            cwd_candidate = (Path.cwd() / fp)
            if cwd_candidate.exists():
                fp = cwd_candidate.resolve()
            else:
                fp = (base_dir / fp).resolve()
        row["filepath"] = str(fp).replace("\\", "/")

    with normalized_path.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return normalized_path


def _merge_enrich_outputs(raw_outputs_dir: Path, out_dir: Path) -> None:
    zones_path = raw_outputs_dir / "zones.geojson"
    ranking_path = raw_outputs_dir / "ranking.csv"
    enrich_path = out_dir / "zones_enriched_green_flood.csv"

    zones_data = json.loads(zones_path.read_text(encoding="utf-8"))
    with enrich_path.open("r", encoding="utf-8", newline="") as f:
        enrich_rows = list(csv.DictReader(f))

    by_zone_id: Dict[str, Dict[str, str]] = {}
    for row in enrich_rows:
        zid = str(row.get("zone_id") or "").strip()
        if zid:
            by_zone_id[zid] = row

    for idx, feat in enumerate(zones_data.get("features", [])):
        props = feat.get("properties") or {}
        zid = str(props.get("zone_id") or idx)
        row = by_zone_id.get(zid)
        if row is None:
            continue

        flood_ratio = float(row.get("flood_ratio") or 0.0)
        green_ratio = float(row.get("green_ratio") or 0.0)

        props["flood_ratio_r800"] = flood_ratio
        props["green_ratio_r700"] = green_ratio
        props["flood_ratio"] = flood_ratio
        props["green_ratio"] = green_ratio
        feat["properties"] = props

    zones_enriched_path = out_dir / "zones_enriched.geojson"
    zones_enriched_path.write_text(json.dumps(zones_data, ensure_ascii=False), encoding="utf-8")

    with ranking_path.open("r", encoding="utf-8", newline="") as src:
        ranking_reader = csv.DictReader(src)
        ranking_rows = list(ranking_reader)
        ranking_fields = list(ranking_reader.fieldnames or [])

    extra_fields = ["flood_ratio_r800", "green_ratio_r700"]
    for field in extra_fields:
        if field not in ranking_fields:
            ranking_fields.append(field)

    for idx, row in enumerate(ranking_rows):
        zid = str(row.get("zone_id") or idx)
        enr = by_zone_id.get(zid)
        row["flood_ratio_r800"] = str(float((enr or {}).get("flood_ratio") or 0.0))
        row["green_ratio_r700"] = str(float((enr or {}).get("green_ratio") or 0.0))

    ranking_enriched_path = out_dir / "ranking_enriched.csv"
    with ranking_enriched_path.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=ranking_fields)
        writer.writeheader()
        writer.writerows(ranking_rows)


def run_zone_enrich(
    runs_dir: Path,
    geodir: Path,
    out_dir: Path,
    params: Dict[str, Any] | None = None,
) -> None:
    params = params or {}
    script_path = Path("cods_ok") / "zone_enrich_green_flood_v8_tiled_groups_fixed.py"
    green_tiles_dir, green_tile_index = _resolve_green_inputs(geodir=geodir, params=params)
    green_tiles_dir, green_tile_index = _ensure_green_tile_index(
        geodir=geodir,
        green_tile_index=green_tile_index,
        green_tiles_dir=green_tiles_dir,
        params=params,
    )

    normalized_index = _normalize_tile_index_paths(tile_index_path=green_tile_index, out_dir=out_dir)

    args = [
        sys.executable,
        str(script_path),
        "--runs-dir",
        str(runs_dir),
        "--geodir",
        str(geodir),
        "--out-dir",
        str(out_dir),
        "--green-tiles-dir",
        str(green_tiles_dir),
        "--green-tile-index",
        str(normalized_index),
    ]

    if "r_flood_m" in params:
        args += ["--r-flood-m", str(params["r_flood_m"])]
    if "r_green_m" in params:
        args += ["--r-green-m", str(params["r_green_m"])]
    if "flood_gpkg" in params:
        args += ["--flood-gpkg", str(params["flood_gpkg"])]
    if "green_layer" in params:
        args += ["--green-layer", str(params["green_layer"])]
    if "flood_layer" in params:
        args += ["--flood-layer", str(params["flood_layer"])]
    if "zone_enrich_cache_dir" in params:
        args += ["--cache-dir", str(params["zone_enrich_cache_dir"])]
    if "zone_enrich_progress_every" in params:
        args += ["--progress-every", str(params["zone_enrich_progress_every"])]
    if bool(params.get("zone_enrich_fast_area_sum", False)):
        args.append("--fast-area-sum")
    enrich_verbose = int(params.get("zone_enrich_verbose", 1))
    if enrich_verbose > 0:
        args.extend(["-v"] * enrich_verbose)

    subprocess.run(args, check=True)
    _merge_enrich_outputs(raw_outputs_dir=runs_dir, out_dir=out_dir)
