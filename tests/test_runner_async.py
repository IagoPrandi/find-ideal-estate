import asyncio
import time

from app.runner import Runner
from app.schemas import RunCreateRequest
from app.store import RunStore


def test_runner_pipeline_does_not_block_event_loop(tmp_path, monkeypatch):
    store = RunStore(str(tmp_path / "runs"))
    payload = RunCreateRequest(reference_points=[{"lat": -23.55, "lon": -46.63}], params={})
    run_id = store.create_run(payload)

    def slow_candidate_zones(*args, **kwargs):
        time.sleep(0.35)

    def slow_zone_enrich(*args, **kwargs):
        time.sleep(0.35)

    def slow_consolidate(*args, **kwargs):
        time.sleep(0.35)

    monkeypatch.setattr("app.runner.run_candidate_zones", slow_candidate_zones)
    monkeypatch.setattr("app.runner.run_zone_enrich", slow_zone_enrich)
    monkeypatch.setattr("app.runner.consolidate_zones", slow_consolidate)

    runner = Runner(store)

    async def ticker(window_sec: float = 0.8) -> int:
        ticks = 0
        deadline = time.perf_counter() + window_sec
        while time.perf_counter() < deadline:
            await asyncio.sleep(0.02)
            ticks += 1
        return ticks

    async def scenario() -> int:
        task = asyncio.create_task(runner.run_pipeline(run_id))
        ticks = await ticker()
        await task
        return ticks

    ticks = asyncio.run(scenario())

    # If the pipeline blocks the event loop, ticks remain very low (near zero).
    assert ticks >= 8
