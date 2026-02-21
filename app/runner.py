from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

from adapters.candidate_zones_adapter import run_candidate_zones
from adapters.zone_enrich_adapter import run_zone_enrich
from app.store import RunStore
from core.consolidate import consolidate_zones


class Runner:
    def __init__(self, store: RunStore) -> None:
        self.store = store

    async def run_pipeline(self, run_id: str) -> None:
        stages: List[str] = ["validate", "zones_by_ref", "zones_enrich", "zones_consolidate", "done"]
        self.store.update_status(run_id, state="running", stage="validate")

        self._stage_mark(run_id, "validate", "running")
        await asyncio.sleep(0.01)
        self._stage_mark(run_id, "validate", "success")

        payload = self.store.get_input(run_id)
        reference_points = payload.get("reference_points") or []
        params = payload.get("params") or {}

        runs_dir = Path(self.store.runs_dir)
        run_dir = runs_dir / run_id
        cache_dir = Path(params.get("cache_dir", "data_cache"))
        geodir = cache_dir / "geosampa"

        # M2: zonas por ponto de referência
        self._stage_mark(run_id, "zones_by_ref", "running")
        for idx, ref in enumerate(reference_points):
            ref_dir = run_dir / "zones" / "by_ref" / f"ref_{idx}" / "raw"
            ref_dir.mkdir(parents=True, exist_ok=True)
            run_candidate_zones(
                cache_dir=cache_dir,
                out_dir=ref_dir,
                seed_lat=float(ref["lat"]),
                seed_lon=float(ref["lon"]),
                params=params,
            )
        self._stage_mark(run_id, "zones_by_ref", "success")

        # M2: enriquecimento por ref
        self._stage_mark(run_id, "zones_enrich", "running")
        for idx, _ref in enumerate(reference_points):
            raw_outputs = run_dir / "zones" / "by_ref" / f"ref_{idx}" / "raw" / "outputs"
            enriched_dir = run_dir / "zones" / "by_ref" / f"ref_{idx}" / "enriched"
            enriched_dir.mkdir(parents=True, exist_ok=True)
            run_zone_enrich(
                runs_dir=raw_outputs,
                geodir=geodir,
                out_dir=enriched_dir,
                params=params,
            )
        self._stage_mark(run_id, "zones_enrich", "success")

        # M3: consolidação
        self._stage_mark(run_id, "zones_consolidate", "running")
        zone_dedupe_m = float(params.get("zone_dedupe_m", 50.0))
        consolidate_zones(run_dir, zone_dedupe_m=zone_dedupe_m)
        self._stage_mark(run_id, "zones_consolidate", "success")

        self.store.update_status(run_id, state="success", stage="done")

    def _stage_mark(self, run_id: str, name: str, state: str) -> None:
        self.store.append_stage(run_id, name=name, state=state)
        self.store.update_status(run_id, state="running", stage=name)
