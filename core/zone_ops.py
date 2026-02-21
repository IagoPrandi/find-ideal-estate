from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fiona
from shapely.geometry import Point, shape

from adapters.pois_adapter import run_pois
from adapters.streets_adapter import run_streets


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_zone_feature(run_dir: Path, zone_uid: str) -> Dict[str, Any]:
    zones_path = run_dir / "zones" / "consolidated" / "zones_consolidated.geojson"
    data = _load_json(zones_path)
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        if str(props.get("zone_uid")) == zone_uid:
            return feat
    raise KeyError(f"zone_uid not found: {zone_uid}")


def zone_centroid_lonlat(zone_feature: Dict[str, Any]) -> Tuple[float, float]:
    props = zone_feature.get("properties") or {}
    lon = props.get("centroid_lon")
    lat = props.get("centroid_lat")
    if lon is not None and lat is not None:
        return float(lon), float(lat)
    geom = zone_feature.get("geometry")
    c = shape(geom).centroid
    return float(c.x), float(c.y)


def _load_transport(run_dir: Path, lon: float, lat: float, radius_m: float, max_items: int = 200) -> Dict[str, Any]:
    cache_dir = Path("data_cache")
    gtfs_stops = cache_dir / "gtfs" / "stops.txt"
    rows: List[Dict[str, Any]] = []

    if gtfs_stops.exists():
        with gtfs_stops.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    s_lat = float(r.get("stop_lat") or 0)
                    s_lon = float(r.get("stop_lon") or 0)
                except Exception:
                    continue
                dist = haversine_m(lat, lon, s_lat, s_lon)
                if dist <= radius_m:
                    rows.append(
                        {
                            "type": "bus_stop",
                            "id": r.get("stop_id"),
                            "name": r.get("stop_name"),
                            "lat": s_lat,
                            "lon": s_lon,
                            "distance_m": dist,
                        }
                    )

    stations: List[Dict[str, Any]] = []
    geo_dir = cache_dir / "geosampa"
    station_files = [
        geo_dir / "geoportal_estacao_metro_v2.gpkg",
        geo_dir / "geoportal_estacao_trem_v2.gpkg",
    ]
    for sf in station_files:
        if not sf.exists():
            continue
        for layer in fiona.listlayers(str(sf)):
            with fiona.open(str(sf), layer=layer) as src:
                for feat in src:
                    geom = feat.get("geometry")
                    if not geom:
                        continue
                    g = shape(geom)
                    c = g.centroid
                    s_lon, s_lat = float(c.x), float(c.y)
                    dist = haversine_m(lat, lon, s_lat, s_lon)
                    if dist <= radius_m:
                        p = feat.get("properties") or {}
                        stations.append(
                            {
                                "type": "station",
                                "id": p.get("id") or p.get("objectid") or p.get("fid"),
                                "name": p.get("nome") or p.get("name") or p.get("estacao") or "station",
                                "lat": s_lat,
                                "lon": s_lon,
                                "distance_m": dist,
                            }
                        )

    rows = sorted(rows, key=lambda x: x["distance_m"])[:max_items]
    stations = sorted(stations, key=lambda x: x["distance_m"])[:max_items]
    return {"bus_stops": rows, "stations": stations}


def build_zone_detail(run_dir: Path, zone_uid: str, params: Dict[str, Any]) -> Dict[str, Path]:
    zone = get_zone_feature(run_dir, zone_uid)
    lon, lat = zone_centroid_lonlat(zone)

    radius_m = float(params.get("zone_detail_radius_m", 1200))
    streets_path = run_dir / "zones" / "detail" / zone_uid / "streets.json"
    pois_path = run_dir / "zones" / "detail" / zone_uid / "pois.json"
    transport_path = run_dir / "zones" / "detail" / zone_uid / "transport.json"

    run_streets(
        lon=lon,
        lat=lat,
        radius_m=radius_m,
        out_path=streets_path,
        step_m=float(params.get("street_step_m", 150)),
        query_radius_m=float(params.get("street_query_radius_m", 120)),
        max_workers=int(params.get("street_max_workers", 8)),
    )
    run_pois(
        lon=lon,
        lat=lat,
        radius_m=radius_m,
        out_path=pois_path,
        limit=int(params.get("pois_limit", 25)),
    )

    transport = _load_transport(run_dir=run_dir, lon=lon, lat=lat, radius_m=radius_m)
    transport_path.parent.mkdir(parents=True, exist_ok=True)
    transport_path.write_text(json.dumps(transport, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "streets": streets_path,
        "pois": pois_path,
        "transport": transport_path,
    }
