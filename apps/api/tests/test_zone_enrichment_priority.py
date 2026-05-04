from uuid import uuid4

from workers.handlers.enrichment import _pick_next_zone_row


def test_pick_next_zone_row_prioritizes_selected_zone() -> None:
    journey_id = uuid4()
    first_zone_id = uuid4()
    selected_zone_id = uuid4()

    row = _pick_next_zone_row(
        [
            (first_zone_id, journey_id, selected_zone_id),
            (selected_zone_id, journey_id, selected_zone_id),
        ]
    )

    assert row == (selected_zone_id, journey_id, selected_zone_id)


def test_pick_next_zone_row_keeps_original_order_without_selection() -> None:
    journey_id = uuid4()
    first_zone_id = uuid4()
    second_zone_id = uuid4()

    row = _pick_next_zone_row(
        [
            (first_zone_id, journey_id, None),
            (second_zone_id, journey_id, None),
        ]
    )

    assert row == (first_zone_id, journey_id, None)
