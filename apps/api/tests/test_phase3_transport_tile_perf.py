import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.api.routes.transport import _GREEN_TILE_MIN_ZOOM, _green_tile_simplify_tolerance, _meters_to_degree_buffer  # noqa: E402


def test_meters_to_degree_buffer_matches_expected_conversion() -> None:
    assert round(_meters_to_degree_buffer(250.0), 6) == 0.002246
    assert round(_meters_to_degree_buffer(45.0), 6) == 0.000404
    assert round(_meters_to_degree_buffer(180.0), 6) == 0.001617


def test_green_tile_simplify_tolerance_is_more_aggressive_at_lower_zoom() -> None:
    assert _green_tile_simplify_tolerance(10) == 0.0015
    assert _green_tile_simplify_tolerance(12) == 0.0006
    assert _green_tile_simplify_tolerance(14) == 0.0002
    assert _green_tile_simplify_tolerance(16) == 0.00005


def test_green_tile_min_zoom_blocks_low_zoom_tiles() -> None:
    assert _GREEN_TILE_MIN_ZOOM == 12