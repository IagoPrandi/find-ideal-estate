import asyncio
from collections import Counter
import json
import os
from pathlib import Path
from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.runner import Runner
from app.schemas import (
    FinalizeResponse,
    ListingsScrapeRequest,
    ListingsScrapeResponse,
    RunCreateRequest,
    RunCreateResponse,
    RunStatusResponse,
    SimpleMessageResponse,
    ZoneDetailResponse,
    ZoneSelectionRequest,
)
from app.store import RunStore
from core.listings_ops import finalize_run, scrape_zone_listings
from core.zone_ops import build_run_transport_layers, build_transport_stops_for_point, build_zone_detail, get_zone_feature

app = FastAPI(title="Imovel Ideal API", version="0.2.0")

raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
allow_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS_DIR = os.getenv("RUNS_DIR", "runs")
store = RunStore(RUNS_DIR)
runner = Runner(store)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> dict:
    return {"status": "ready"}


@app.post("/runs", response_model=RunCreateResponse)
async def create_run(payload: RunCreateRequest) -> RunCreateResponse:
    run_id = store.create_run(payload)
    asyncio.create_task(runner.run_pipeline(run_id))
    status = store.get_status(run_id)
    return RunCreateResponse(run_id=run_id, status=status)


@app.get("/runs/{run_id}/status", response_model=RunStatusResponse)
async def run_status(run_id: str) -> RunStatusResponse:
    status = store.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    return RunStatusResponse(run_id=run_id, status=status)


@app.get("/runs/{run_id}/zones")
async def run_zones(run_id: str) -> Response:
    zones_path = Path(RUNS_DIR) / run_id / "zones" / "consolidated" / "zones_consolidated.geojson"
    if not zones_path.exists():
        raise HTTPException(status_code=404, detail="zones not found")
    try:
        data = json.loads(zones_path.read_text(encoding="utf-8"))
        features = data.get("features") or []
        if isinstance(features, list):
            for idx, feature in enumerate(features):
                props = feature.get("properties") or {}
                props["zone_name"] = f"Zona {idx + 1}"
                props["zone_index"] = idx + 1
                feature["properties"] = props
        return Response(content=json.dumps(data, ensure_ascii=False), media_type="application/geo+json")
    except Exception:
        return Response(content=zones_path.read_text(encoding="utf-8"), media_type="application/geo+json")


@app.get("/runs/{run_id}/security")
async def run_security(run_id: str) -> Response:
    p = Path(RUNS_DIR) / run_id / "security" / "public_safety.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="security artifact not found")
    return Response(content=p.read_text(encoding="utf-8"), media_type="application/json")


@app.get("/runs/{run_id}/transport/routes")
async def run_transport_routes(run_id: str) -> dict:
    run_dir = Path(RUNS_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    try:
        return build_run_transport_layers(run_dir=run_dir)
    except FileNotFoundError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@app.get("/transport/stops")
async def transport_stops(
    lon: float | None = None,
    lat: float | None = None,
    radius_m: float = 2500.0,
    bbox: str | None = None,
) -> dict:
    """Get bus/train stops. Use bbox (minLon,minLat,maxLon,maxLat) for viewport-based loading, or lon/lat/radius."""
    bbox_tuple = None
    if bbox:
        parts = [float(x.strip()) for x in bbox.split(",") if x.strip()]
        if len(parts) == 4:
            bbox_tuple = (parts[0], parts[1], parts[2], parts[3])
    if bbox_tuple is not None:
        try:
            return build_transport_stops_for_point(lon=0, lat=0, bbox=bbox_tuple)
        except Exception as ex:
            raise HTTPException(status_code=400, detail=str(ex)) from ex
    if lon is None or lat is None:
        raise HTTPException(status_code=400, detail="lon and lat required when bbox not provided")
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        raise HTTPException(status_code=400, detail="invalid lon/lat")
    try:
        return build_transport_stops_for_point(lon=lon, lat=lat, radius_m=radius_m)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@app.post("/runs/{run_id}/zones/select", response_model=SimpleMessageResponse)
async def select_zones(run_id: str, payload: ZoneSelectionRequest) -> SimpleMessageResponse:
    run_dir = Path(RUNS_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    selected_path = run_dir / "selected_zones.json"
    selected_path.write_text(
        json.dumps({"zone_uids": payload.zone_uids}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return SimpleMessageResponse(message=f"{len(payload.zone_uids)} zones selected")


@app.post("/runs/{run_id}/zones/{zone_uid}/detail", response_model=ZoneDetailResponse)
async def zone_detail(run_id: str, zone_uid: str) -> ZoneDetailResponse:
    run_dir = Path(RUNS_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    payload = store.get_input(run_id)
    params = payload.get("params") or {}
    try:
        out = build_zone_detail(run_dir=run_dir, zone_uid=zone_uid, params=params)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    try:
        zone_feature = get_zone_feature(run_dir=run_dir, zone_uid=zone_uid)
        zones_data = json.loads(
            (run_dir / "zones" / "consolidated" / "zones_consolidated.geojson").read_text(encoding="utf-8")
        )
        features = zones_data.get("features") or []
        zone_index = next(
            (
                idx
                for idx, feature in enumerate(features)
                if str(((feature.get("properties") or {}).get("zone_uid") or "")) == zone_uid
            ),
            None,
        )
        zone_name = f"Zona {(zone_index + 1) if zone_index is not None else 1}"

        streets_data = json.loads(out["streets"].read_text(encoding="utf-8")) if out["streets"].exists() else {}
        pois_data = json.loads(out["pois"].read_text(encoding="utf-8")) if out["pois"].exists() else {}
        transport_data = json.loads(out["transport"].read_text(encoding="utf-8")) if out["transport"].exists() else {}

        poi_counter = Counter()
        for item in (pois_data.get("results") or []):
            category = str(item.get("categoria") or item.get("canonical_id") or "outros").strip() or "outros"
            poi_counter[category] += 1

        bus_stops = transport_data.get("bus_stops") or []
        stations = transport_data.get("stations") or []

        zone_props = zone_feature.get("properties") or {}
        trace = zone_props.get("trace") if isinstance(zone_props.get("trace"), dict) else {}
        trace_seed_stop_id = str(trace.get("seed_bus_stop_id") or "").strip()
        trace_downstream_stop_id = str(trace.get("downstream_stop_id") or "").strip()

        lines_used_for_generation = []
        route_id = str(trace.get("route_id") or "").strip()
        line_name = str(trace.get("busline_name") or trace.get("trip_headsign") or "").strip()
        mode = str(zone_props.get("mode") or "").strip() or "bus"
        if route_id or line_name:
            lines_used_for_generation.append(
                {
                    "mode": mode,
                    "route_id": route_id,
                    "line_name": line_name,
                }
            )

        bus_line_ids = set()
        train_line_ids = set()
        if trace_downstream_stop_id and isinstance(features, list):
            for feature in features:
                props = feature.get("properties") or {}
                feature_trace = props.get("trace") if isinstance(props.get("trace"), dict) else {}
                if str(feature_trace.get("downstream_stop_id") or "").strip() != trace_downstream_stop_id:
                    continue
                feature_mode = str(props.get("mode") or "").strip() or "bus"
                feature_route_id = str(feature_trace.get("route_id") or "").strip()
                feature_line_name = str(feature_trace.get("busline_name") or feature_trace.get("trip_headsign") or "").strip()
                line_key = feature_route_id or feature_line_name
                if not line_key:
                    continue
                if feature_mode == "bus":
                    bus_line_ids.add(line_key)
                else:
                    train_line_ids.add(line_key)

        def _find_transport_point_by_id(stop_id: str) -> dict | None:
            if not stop_id:
                return None
            for stop in bus_stops:
                if str(stop.get("id") or "").strip() == stop_id:
                    return {
                        "kind": "bus_stop",
                        "id": stop.get("id"),
                        "name": stop.get("name"),
                        "lat": stop.get("lat"),
                        "lon": stop.get("lon"),
                    }
            for station in stations:
                if str(station.get("id") or "").strip() == stop_id:
                    return {
                        "kind": "station",
                        "id": station.get("id"),
                        "name": station.get("name"),
                        "lat": station.get("lat"),
                        "lon": station.get("lon"),
                    }
            return None

        seed_transport_point = _find_transport_point_by_id(trace_seed_stop_id)
        downstream_transport_point = _find_transport_point_by_id(trace_downstream_stop_id)
        reference_transport_point = seed_transport_point or downstream_transport_point

        transport_points = [
            {
                "kind": "bus_stop",
                "id": stop.get("id"),
                "name": stop.get("name"),
                "lat": stop.get("lat"),
                "lon": stop.get("lon"),
            }
            for stop in bus_stops
            if isinstance(stop, dict)
        ]
        transport_points.extend(
            [
                {
                    "kind": "station",
                    "id": station.get("id"),
                    "name": station.get("name"),
                    "lat": station.get("lat"),
                    "lon": station.get("lon"),
                }
                for station in stations
                if isinstance(station, dict)
            ]
        )

        poi_points = [
            {
                "kind": "poi",
                "id": str(item.get("canonical_id") or "") or None,
                "name": str(item.get("nome") or "POI").strip() or "POI",
                "category": str(item.get("categoria") or "outros").strip() or "outros",
                "lat": float(item.get("latitude")),
                "lon": float(item.get("longitude")),
            }
            for item in (pois_data.get("results") or [])
            if isinstance(item, dict) and item.get("latitude") is not None and item.get("longitude") is not None
        ]

        return ZoneDetailResponse(
            zone_uid=zone_uid,
            zone_name=zone_name,
            green_area_ratio=float(zone_props.get("green_ratio_r700") or zone_props.get("green_ratio") or 0.0),
            flood_area_ratio=float(zone_props.get("flood_ratio_r800") or zone_props.get("flood_ratio") or 0.0),
            poi_count_by_category=dict(sorted(poi_counter.items())),
            bus_lines_count=len(bus_line_ids),
            train_lines_count=len(train_line_ids),
            bus_stop_count=len(bus_stops),
            train_station_count=len(stations),
            lines_used_for_generation=lines_used_for_generation,
            reference_transport_point=reference_transport_point,
            seed_transport_point=seed_transport_point,
            downstream_transport_point=downstream_transport_point,
            transport_points=transport_points,
            poi_points=poi_points,
            streets_count=int(streets_data.get("count") or len(streets_data.get("streets") or [])),
            has_street_data=bool(streets_data.get("streets")),
            has_poi_data=bool(pois_data.get("results")),
            has_transport_data=bool(bus_stops or stations),
        )
    except Exception as ex:
        raise HTTPException(status_code=400, detail=f"zone detail summary failed: {ex}") from ex


@app.get("/runs/{run_id}/zones/{zone_uid}/streets")
async def zone_streets(run_id: str, zone_uid: str) -> dict:
    """Return list of streets for a zone (from streets.json)."""
    run_dir = Path(RUNS_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    streets_path = run_dir / "zones" / "detail" / zone_uid / "streets.json"
    if not streets_path.exists():
        raise HTTPException(status_code=404, detail="streets not found; run zone detail first")
    data = json.loads(streets_path.read_text(encoding="utf-8"))
    streets = data.get("streets") if isinstance(data.get("streets"), list) else []
    return {"zone_uid": zone_uid, "streets": streets}


@app.post("/runs/{run_id}/zones/{zone_uid}/listings", response_model=ListingsScrapeResponse)
async def zone_listings(
    run_id: str,
    zone_uid: str,
    body: ListingsScrapeRequest | None = Body(default=None),
) -> ListingsScrapeResponse:
    run_dir = Path(RUNS_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    payload = store.get_input(run_id)
    params = dict(payload.get("params") or {})
    if body is not None and body.street_filter and body.street_filter.strip():
        params["street_filter"] = body.street_filter.strip()

    try:
        listing_files = scrape_zone_listings(run_dir=run_dir, zone_uid=zone_uid, params=params)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    total_items = 0
    for listing_file in listing_files:
        if not listing_file.exists():
            continue
        try:
            payload = json.loads(listing_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            items = payload.get("items")
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        if isinstance(items, list):
            total_items += len(items)

    return ListingsScrapeResponse(zone_uid=zone_uid, listings_count=len(listing_files))


@app.post("/runs/{run_id}/finalize", response_model=FinalizeResponse)
async def finalize(run_id: str) -> FinalizeResponse:
    run_dir = Path(RUNS_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")

    selected_path = run_dir / "selected_zones.json"
    if not selected_path.exists():
        raise HTTPException(status_code=400, detail="no selected zones")

    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    zone_uids = selected.get("zone_uids") or []
    if not zone_uids:
        raise HTTPException(status_code=400, detail="selected zone_uids is empty")

    payload = store.get_input(run_id)
    params = payload.get("params") or {}
    try:
        out = finalize_run(run_dir=run_dir, selected_zone_uids=zone_uids, params=params)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    return FinalizeResponse(
        listings_final_json=str(out["listings_final_json"]),
        listings_final_csv=str(out["listings_final_csv"]),
        listings_final_geojson=str(out["listings_final_geojson"]),
        zones_final_geojson=str(out["zones_final_geojson"]),
    )


@app.get("/runs/{run_id}/final/listings")
async def final_listings(run_id: str) -> Response:
    p = Path(RUNS_DIR) / run_id / "final" / "listings_final.geojson"
    if not p.exists():
        raise HTTPException(status_code=404, detail="final listings not found")
    return Response(content=p.read_text(encoding="utf-8"), media_type="application/geo+json")


@app.get("/runs/{run_id}/final/listings.csv")
async def final_listings_csv(run_id: str) -> Response:
    p = Path(RUNS_DIR) / run_id / "final" / "listings_final.csv"
    if not p.exists():
        raise HTTPException(status_code=404, detail="final csv not found")
    return Response(content=p.read_text(encoding="utf-8"), media_type="text/csv")


@app.get("/runs/{run_id}/final/listings.json")
async def final_listings_json(run_id: str) -> Response:
    p = Path(RUNS_DIR) / run_id / "final" / "listings_final.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="final json not found")
    return Response(content=p.read_text(encoding="utf-8"), media_type="application/json")
