from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.modules.listings.models import InvalidStateTransition, ZoneCacheStatus  # noqa: E402


def test_transition_to_rejects_pending_to_complete() -> None:
    with pytest.raises(InvalidStateTransition):
        ZoneCacheStatus.transition_to(ZoneCacheStatus.PENDING, ZoneCacheStatus.COMPLETE)


def test_transition_to_accepts_pending_to_scraping() -> None:
    new_state = ZoneCacheStatus.transition_to(ZoneCacheStatus.PENDING, ZoneCacheStatus.SCRAPING)
    assert new_state == ZoneCacheStatus.SCRAPING
