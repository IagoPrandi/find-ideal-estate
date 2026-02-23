from __future__ import annotations

import json
import random
import shutil
import traceback
from pathlib import Path

from adapters.candidate_zones_adapter import run_candidate_zones
from adapters.zone_enrich_adapter import run_zone_enrich
from core.consolidate import consolidate_zones
from core.listings_ops import finalize_run, scrape_zone_listings
from core.zone_ops import build_zone_detail

SEED_LAT = -23.585068145112295
SEED_LON = -46.690640014541714
MAX_ATTEMPTS = 3



def log(step: str, message: str) -> None:
    print(f"[STEP={step}] {message}")



def main() -> None:
    params = {
        "max_streets_per_zone": 1,
        "listing_max_pages": 1,
        "listings_headless": True,
    }

    base_runs = Path("/app/runs")
    cache_dir = Path("/app/data_cache")
    geodir = cache_dir / "geosampa"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        run_tag = f"docker_full_noapi_{attempt}"
        run_dir = base_runs / run_tag
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
        run_dir.mkdir(parents=True, exist_ok=True)

        log("create_run", f"RUN_TAG={run_tag} ATTEMPT={attempt}/{MAX_ATTEMPTS}")
        log("params", f"POINT=({SEED_LAT},{SEED_LON}) max_streets_per_zone=1 listing_max_pages=1")

        try:
            # A) zones_by_ref
            log("zones_by_ref", "start")
            ref_raw = run_dir / "zones" / "by_ref" / "ref_0" / "raw"
            ref_raw.mkdir(parents=True, exist_ok=True)
            run_candidate_zones(
                cache_dir=cache_dir,
                out_dir=ref_raw,
                seed_lat=SEED_LAT,
                seed_lon=SEED_LON,
                params=params,
            )
            raw_geojson = ref_raw / "outputs" / "zones.geojson"
            with raw_geojson.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            log("zones_by_ref", f"ok features={len(raw.get('features', []))}")

            # B) zones_enrich
            log("zones_enrich", "start")
            enriched_dir = run_dir / "zones" / "by_ref" / "ref_0" / "enriched"
            enriched_dir.mkdir(parents=True, exist_ok=True)
            run_zone_enrich(
                runs_dir=ref_raw / "outputs",
                geodir=geodir,
                out_dir=enriched_dir,
                params=params,
            )
            enr_geojson = enriched_dir / "zones_enriched.geojson"
            with enr_geojson.open("r", encoding="utf-8") as f:
                enr = json.load(f)
            log("zones_enrich", f"ok features={len(enr.get('features', []))}")

            # C) consolidate
            log("zones_consolidate", "start")
            consolidate_zones(run_dir, zone_dedupe_m=50.0)
            cons_path = run_dir / "zones" / "consolidated" / "zones_consolidated.geojson"
            with cons_path.open("r", encoding="utf-8") as f:
                cons = json.load(f)
            feats = cons.get("features", [])
            if not feats:
                raise RuntimeError("no consolidated zones")
            zone_uid = random.choice(feats)["properties"]["zone_uid"]
            log("zones_consolidate", f"ok consolidated_features={len(feats)}")

            # D) select one zone
            log("select_zone", f"ZONE_UID={zone_uid}")

            # E) detail one zone
            log("detail_zone", "start")
            detail_out = build_zone_detail(run_dir=run_dir, zone_uid=zone_uid, params=params)
            log(
                "detail_zone",
                "ok streets={0} pois={1} transport={2}".format(
                    detail_out["streets"], detail_out["pois"], detail_out["transport"]
                ),
            )

            # F) listings (one street max)
            log("listings", "start")
            listing_files = scrape_zone_listings(run_dir=run_dir, zone_uid=zone_uid, params=params)
            log("listings", f"ok listing_files={len(listing_files)}")

            # G) finalize
            log("finalize", "start")
            out = finalize_run(run_dir=run_dir, selected_zone_uids=[zone_uid], params=params)
            with open(out["listings_final_json"], "r", encoding="utf-8") as f:
                final_list = json.load(f)
            bad_coords = sum(1 for x in final_list if x.get("lat") is None or x.get("lon") is None)
            bad_state = sum(1 for x in final_list if not str(x.get("state") or "").strip())
            log(
                "validate_output",
                f"FINAL_COUNT={len(final_list)} BAD_COORDS={bad_coords} BAD_STATE={bad_state}",
            )

            if len(final_list) <= 0:
                raise RuntimeError("final output empty")
            if bad_coords > 0:
                raise RuntimeError("found listings without real coordinates")
            if bad_state > 0:
                raise RuntimeError("found listings without state")

            log("done", f"PASS RUN_TAG={run_tag}")
            log("artifacts", str(out))
            return

        except Exception as exc:
            log("run_failed", f"RUN_TAG={run_tag} REASON={exc}")
            traceback.print_exc()
            if attempt == MAX_ATTEMPTS:
                raise


if __name__ == "__main__":
    main()
