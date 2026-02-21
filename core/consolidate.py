from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pyproj import Transformer
from shapely.geometry import shape, mapping

EPSG_WGS84 = "EPSG:4326"
EPSG_UTM_SP = "EPSG:31983"


@dataclass
class ZoneFeature:
    feature: Dict[str, Any]
    centroid_xy: Tuple[float, float]
    score: float
    source_ref: str
    travel_time: float
    buffer_m: float


def _load_features(paths: List[Path]) -> List[ZoneFeature]:
    to_utm = Transformer.from_crs(EPSG_WGS84, EPSG_UTM_SP, always_xy=True)
    feats: List[ZoneFeature] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for feat in data.get("features", []):
            props = feat.get("properties") or {}
            geom = feat.get("geometry")
            if not geom:
                continue
            geom_shape = shape(geom)
            c = geom_shape.centroid
            x, y = to_utm.transform(float(c.x), float(c.y))
            score = float(props.get("score", 0.0))
            travel = float(props.get("travel_time_from_seed_minutes", 0.0))
            source_ref = str(props.get("source_point_id", ""))
            buffer_m = float(props.get("buffer_m", 0.0))
            feats.append(
                ZoneFeature(
                    feature=feat,
                    centroid_xy=(x, y),
                    score=score,
                    source_ref=source_ref,
                    travel_time=travel,
                    buffer_m=buffer_m,
                )
            )
    return feats


def _cluster_features(features: List[ZoneFeature], eps_m: float) -> List[List[ZoneFeature]]:
    clusters: List[List[ZoneFeature]] = []
    r2 = float(eps_m) ** 2
    for feat in sorted(features, key=lambda f: f.score, reverse=True):
        assigned = False
        for cluster in clusters:
            cx, cy = cluster[0].centroid_xy
            dx = feat.centroid_xy[0] - cx
            dy = feat.centroid_xy[1] - cy
            if dx * dx + dy * dy <= r2:
                cluster.append(feat)
                assigned = True
                break
        if not assigned:
            clusters.append([feat])
    return clusters


def _zone_uid(x: float, y: float, buffer_m: float) -> str:
    key = f"{round(x,1)}|{round(y,1)}|{round(buffer_m,1)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def consolidate_zones(run_dir: Path, zone_dedupe_m: float) -> Path:
    by_ref_dir = run_dir / "zones" / "by_ref"
    enriched_paths = list(by_ref_dir.glob("ref_*/enriched/zones_enriched.geojson"))
    if not enriched_paths:
        raise FileNotFoundError("No zones_enriched.geojson files found for consolidation")

    features = _load_features(enriched_paths)
    clusters = _cluster_features(features, eps_m=zone_dedupe_m)

    out_features: List[Dict[str, Any]] = []
    out_rows: List[Dict[str, Any]] = []

    for cluster in clusters:
        best = max(cluster, key=lambda f: f.score)
        cx, cy = best.centroid_xy
        buffer_m = best.buffer_m
        zone_uid = _zone_uid(cx, cy, buffer_m)

        time_by_ref: Dict[str, float] = {}
        for feat in cluster:
            if feat.source_ref:
                current = time_by_ref.get(feat.source_ref)
                if current is None or feat.travel_time < current:
                    time_by_ref[feat.source_ref] = feat.travel_time

        time_agg = max(time_by_ref.values()) if time_by_ref else 0.0
        props = dict(best.feature.get("properties") or {})
        props["zone_uid"] = zone_uid
        props["time_by_ref"] = time_by_ref
        props["time_agg"] = time_agg

        out_features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": best.feature.get("geometry"),
            }
        )
        out_rows.append(
            {
                "zone_uid": zone_uid,
                "score": best.score,
                "time_agg": time_agg,
                "time_by_ref": json.dumps(time_by_ref, ensure_ascii=False),
            }
        )

    consolidated = {"type": "FeatureCollection", "features": out_features}

    out_dir = run_dir / "zones" / "consolidated"
    out_dir.mkdir(parents=True, exist_ok=True)
    geojson_path = out_dir / "zones_consolidated.geojson"
    geojson_path.write_text(json.dumps(consolidated, ensure_ascii=False), encoding="utf-8")

    csv_path = out_dir / "zones_consolidated.csv"
    csv_path.write_text("zone_uid,score,time_agg,time_by_ref\n", encoding="utf-8")
    with csv_path.open("a", encoding="utf-8") as f:
        for row in out_rows:
            f.write(
                f"{row['zone_uid']},{row['score']},{row['time_agg']},\"{row['time_by_ref']}\"\n"
            )

    return geojson_path
