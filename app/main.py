import asyncio
import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.runner import Runner
from app.schemas import (
    FinalizeResponse,
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
from core.zone_ops import build_run_transport_layers, build_transport_stops_for_point, build_zone_detail

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
async def transport_stops(lon: float, lat: float, radius_m: float = 2500.0) -> dict:
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

    return ZoneDetailResponse(
        zone_uid=zone_uid,
        streets_path=str(out["streets"]),
        pois_path=str(out["pois"]),
        transport_path=str(out["transport"]),
    )


@app.post("/runs/{run_id}/zones/{zone_uid}/listings", response_model=ListingsScrapeResponse)
async def zone_listings(run_id: str, zone_uid: str) -> ListingsScrapeResponse:
    run_dir = Path(RUNS_DIR) / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="run_id not found")
    payload = store.get_input(run_id)
    params = payload.get("params") or {}

    try:
        listing_files = scrape_zone_listings(run_dir=run_dir, zone_uid=zone_uid, params=params)
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    return ListingsScrapeResponse(zone_uid=zone_uid, listing_files=[str(p) for p in listing_files])


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
