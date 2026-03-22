from __future__ import annotations

import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.workers.handlers import listings as listings_handler  # noqa: E402


def test_record_success_rate_degradation_when_below_threshold(monkeypatch) -> None:
    recorded: list[dict[str, object]] = []

    async def _fake_stats(_platform: str):
        return (8, 2, 0.8)

    async def _fake_record(
        platform: str,
        event_type: str,
        trigger_metric: str,
        metric_value: float,
    ):
        recorded.append(
            {
                "platform": platform,
                "event_type": event_type,
                "trigger_metric": trigger_metric,
                "metric_value": metric_value,
            }
        )

    monkeypatch.setattr(listings_handler, "_platform_success_rate_24h", _fake_stats)
    monkeypatch.setattr(listings_handler, "_record_degradation_event", _fake_record)

    asyncio.run(listings_handler._record_success_rate_degradation_if_needed("zapimoveis"))

    assert len(recorded) == 1
    assert recorded[0]["platform"] == "zapimoveis"
    assert recorded[0]["event_type"] == "degraded"
    assert recorded[0]["trigger_metric"] == "success_rate_24h"
    assert recorded[0]["metric_value"] == 0.8


def test_record_success_rate_degradation_not_created_when_healthy(monkeypatch) -> None:
    calls = {"count": 0}

    async def _fake_stats(_platform: str):
        return (9, 1, 0.9)

    async def _fake_record(
        platform: str,
        event_type: str,
        trigger_metric: str,
        metric_value: float,
    ):
        del platform, event_type, trigger_metric, metric_value
        calls["count"] += 1

    monkeypatch.setattr(listings_handler, "_platform_success_rate_24h", _fake_stats)
    monkeypatch.setattr(listings_handler, "_record_degradation_event", _fake_record)

    asyncio.run(listings_handler._record_success_rate_degradation_if_needed("vivareal"))

    assert calls["count"] == 0


def test_record_success_rate_degradation_not_created_without_24h_data(monkeypatch) -> None:
    calls = {"count": 0}

    async def _fake_stats(_platform: str):
        return (0, 0, None)

    async def _fake_record(
        platform: str,
        event_type: str,
        trigger_metric: str,
        metric_value: float,
    ):
        del platform, event_type, trigger_metric, metric_value
        calls["count"] += 1

    monkeypatch.setattr(listings_handler, "_platform_success_rate_24h", _fake_stats)
    monkeypatch.setattr(listings_handler, "_record_degradation_event", _fake_record)

    asyncio.run(listings_handler._record_success_rate_degradation_if_needed("quintoandar"))

    assert calls["count"] == 0
