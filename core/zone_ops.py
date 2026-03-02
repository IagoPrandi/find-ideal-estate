from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fiona
from pyproj import CRS, Transformer
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import transform as shp_transform

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


def _guess_prop_key(props: Dict[str, Any], candidates: List[str]) -> str | None:
    if not props:
        return None
    normalized = {re.sub(r"[^a-z0-9]", "", str(k).lower()): k for k in props.keys()}
    for c in candidates:
        nk = re.sub(r"[^a-z0-9]", "", c.lower())
        if nk in normalized:
            return str(normalized[nk])
    return None


def _append_lines_from_gpkg(
    out_features: List[Dict[str, Any]],
    gpkg_path: Path,
    clip_geom: Any,
    mode: str,
    source_name: str,
    max_items: int,
) -> None:
    if not gpkg_path.exists() or len(out_features) >= max_items:
        return

    for layer in fiona.listlayers(str(gpkg_path)):
        if len(out_features) >= max_items:
            return
        with fiona.open(str(gpkg_path), layer=layer) as src:
            src_crs = CRS.from_user_input(src.crs) if src.crs else None
            wgs84 = CRS.from_epsg(4326)
            to_src = (
                Transformer.from_crs(wgs84, src_crs, always_xy=True)
                if src_crs and src_crs.to_epsg() != 4326
                else None
            )
            to_wgs = (
                Transformer.from_crs(src_crs, wgs84, always_xy=True)
                if src_crs and src_crs.to_epsg() != 4326
                else None
            )
            clip_in_src = shp_transform(to_src.transform, clip_geom) if to_src else clip_geom

            sample_feat = src[0] if len(src) > 0 else None
            sample_props = dict((sample_feat.get("properties") if sample_feat else {}) or {})
            route_name_key = _guess_prop_key(
                sample_props,
                [
                    "nm_linha_metro_trem",
                    "nm_linha",
                    "nr_nome_linha",
                    "ln_nome",
                    "nome",
                    "name",
                    "route_long_name",
                    "route_short_name",
                ],
            )
            route_id_key = _guess_prop_key(
                sample_props,
                ["route_id", "cd_identificador_linha", "id", "objectid", "fid", "codigo"],
            )

            for feat in src:
                if not feat:
                    continue
                if len(out_features) >= max_items:
                    return
                geom = feat.get("geometry")
                if not geom:
                    continue
                g = shape(geom)
                if g.is_empty or not g.intersects(clip_in_src):
                    continue

                clipped = g.intersection(clip_in_src)
                if clipped.is_empty:
                    continue
                if clipped.geom_type not in {"LineString", "MultiLineString"}:
                    continue

                clipped_out = shp_transform(to_wgs.transform, clipped) if to_wgs else clipped

                props = feat.get("properties") or {}
                route_name = str(props.get(route_name_key) or "").strip() if route_name_key else ""
                route_id = str(props.get(route_id_key) or "").strip() if route_id_key else ""

                out_features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(clipped_out),
                        "properties": {
                            "mode": mode,
                            "source": source_name,
                            "route_name": route_name,
                            "route_id": route_id,
                        },
                    }
                )


def _append_points_from_gpkg(
    out_features: List[Dict[str, Any]],
    gpkg_path: Path,
    clip_geom: Any,
    point_kind: str,
    max_items: int,
) -> None:
    if not gpkg_path.exists() or len(out_features) >= max_items:
        return

    for layer in fiona.listlayers(str(gpkg_path)):
        if len(out_features) >= max_items:
            return
        with fiona.open(str(gpkg_path), layer=layer) as src:
            src_crs = CRS.from_user_input(src.crs) if src.crs else None
            wgs84 = CRS.from_epsg(4326)
            to_src = (
                Transformer.from_crs(wgs84, src_crs, always_xy=True)
                if src_crs and src_crs.to_epsg() != 4326
                else None
            )
            to_wgs = (
                Transformer.from_crs(src_crs, wgs84, always_xy=True)
                if src_crs and src_crs.to_epsg() != 4326
                else None
            )
            clip_in_src = shp_transform(to_src.transform, clip_geom) if to_src else clip_geom

            sample_feat = src[0] if len(src) > 0 else None
            sample_props = dict((sample_feat.get("properties") if sample_feat else {}) or {})
            name_key = _guess_prop_key(sample_props, ["nm_estacao", "nome", "name", "stop_name", "denominacao"])
            id_key = _guess_prop_key(sample_props, ["stop_id", "id", "objectid", "fid", "codigo"])

            for feat in src:
                if not feat:
                    continue
                if len(out_features) >= max_items:
                    return
                geom = feat.get("geometry")
                if not geom:
                    continue
                g = shape(geom)
                if g.is_empty:
                    continue
                c = g.centroid
                if not c.intersects(clip_in_src):
                    continue

                c_out = shp_transform(to_wgs.transform, c) if to_wgs else c

                props = feat.get("properties") or {}
                out_features.append(
                    {
                        "type": "Feature",
                        "geometry": mapping(c_out),
                        "properties": {
                            "kind": point_kind,
                            "name": str(props.get(name_key) or "").strip() if name_key else "",
                            "id": str(props.get(id_key) or "").strip() if id_key else "",
                        },
                    }
                )


def build_run_transport_layers(run_dir: Path, radius_m: float = 3500.0) -> Dict[str, Any]:
    zones_path = run_dir / "zones" / "consolidated" / "zones_consolidated.geojson"
    if not zones_path.exists():
        raise FileNotFoundError("zones not found for run")

    zones_data = _load_json(zones_path)
    zone_shapes = []
    for feat in zones_data.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        g = shape(geom)
        if not g.is_empty:
            zone_shapes.append(g)

    if not zone_shapes:
        raise ValueError("zones geometry is empty")

    minx = min(g.bounds[0] for g in zone_shapes)
    miny = min(g.bounds[1] for g in zone_shapes)
    maxx = max(g.bounds[2] for g in zone_shapes)
    maxy = max(g.bounds[3] for g in zone_shapes)

    expand_deg = max(radius_m / 111320.0, 0.01)
    clip_geom = box(minx - expand_deg, miny - expand_deg, maxx + expand_deg, maxy + expand_deg)

    geosampa_dir = Path("data_cache") / "geosampa"

    route_features: List[Dict[str, Any]] = []
    _append_lines_from_gpkg(
        out_features=route_features,
        gpkg_path=geosampa_dir / "SIRGAS_GPKG_linhaonibus.gpkg",
        clip_geom=clip_geom,
        mode="bus",
        source_name="geosampa_bus",
        max_items=1200,
    )
    _append_lines_from_gpkg(
        out_features=route_features,
        gpkg_path=geosampa_dir / "geoportal_linha_metro_v4.gpkg",
        clip_geom=clip_geom,
        mode="train",
        source_name="geosampa_metro",
        max_items=1400,
    )
    _append_lines_from_gpkg(
        out_features=route_features,
        gpkg_path=geosampa_dir / "geoportal_linha_trem_v2.gpkg",
        clip_geom=clip_geom,
        mode="train",
        source_name="geosampa_trem",
        max_items=1600,
    )

    stop_features: List[Dict[str, Any]] = []
    _append_points_from_gpkg(
        out_features=stop_features,
        gpkg_path=geosampa_dir / "geoportal_ponto_onibus.gpkg",
        clip_geom=clip_geom,
        point_kind="bus_stop",
        max_items=1200,
    )
    _append_points_from_gpkg(
        out_features=stop_features,
        gpkg_path=geosampa_dir / "geoportal_estacao_metro_v2.gpkg",
        clip_geom=clip_geom,
        point_kind="station",
        max_items=1350,
    )
    _append_points_from_gpkg(
        out_features=stop_features,
        gpkg_path=geosampa_dir / "geoportal_estacao_trem_v2.gpkg",
        clip_geom=clip_geom,
        point_kind="station",
        max_items=1500,
    )

    return {
        "routes": {
            "type": "FeatureCollection",
            "features": route_features,
        },
        "stops": {
            "type": "FeatureCollection",
            "features": stop_features,
        },
    }


def build_transport_stops_for_point(lon: float, lat: float, radius_m: float = 2500.0) -> Dict[str, Any]:
    expand_deg = max(radius_m / 111320.0, 0.005)
    clip_geom = box(lon - expand_deg, lat - expand_deg, lon + expand_deg, lat + expand_deg)

    geosampa_dir = Path("data_cache") / "geosampa"
    stop_features: List[Dict[str, Any]] = []
    _append_points_from_gpkg(
        out_features=stop_features,
        gpkg_path=geosampa_dir / "geoportal_ponto_onibus.gpkg",
        clip_geom=clip_geom,
        point_kind="bus_stop",
        max_items=1800,
    )
    _append_points_from_gpkg(
        out_features=stop_features,
        gpkg_path=geosampa_dir / "geoportal_estacao_metro_v2.gpkg",
        clip_geom=clip_geom,
        point_kind="station",
        max_items=2100,
    )
    _append_points_from_gpkg(
        out_features=stop_features,
        gpkg_path=geosampa_dir / "geoportal_estacao_trem_v2.gpkg",
        clip_geom=clip_geom,
        point_kind="station",
        max_items=2400,
    )

    return {
        "type": "FeatureCollection",
        "features": stop_features,
    }
