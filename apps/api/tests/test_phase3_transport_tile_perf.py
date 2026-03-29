import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from api.routes.transport import _meters_to_degree_buffer  # noqa: E402


def test_meters_to_degree_buffer_matches_expected_conversion() -> None:
    assert round(_meters_to_degree_buffer(250.0), 6) == 0.002246
    assert round(_meters_to_degree_buffer(45.0), 6) == 0.000404
    assert round(_meters_to_degree_buffer(180.0), 6) == 0.001617