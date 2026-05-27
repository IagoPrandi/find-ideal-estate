from uuid import uuid4

from workers.handlers.enrichment import _pick_next_zone_row, _zone_requires_enrichment


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


def test_complete_zone_requires_backfill_when_pois_are_missing() -> None:
    enrichments = {"pois": True}

    assert _zone_requires_enrichment("complete", None, [], enrichments) is True
    assert _zone_requires_enrichment(
        "complete",
        {"school": 1, "supermarket": 1, "pharmacy": 1, "park": 0},
        [],
        enrichments,
    ) is True
    assert _zone_requires_enrichment(
        "complete",
        {"school": 1, "supermarket": 1, "pharmacy": 1, "park": 0, "restaurant": 1, "gym": 1},
        None,
        enrichments,
    ) is True


def test_complete_zone_with_full_pois_does_not_require_backfill() -> None:
    assert (
        _zone_requires_enrichment(
            "complete",
            {"school": 1, "supermarket": 1, "pharmacy": 1, "park": 0, "restaurant": 1, "gym": 1},
            [],
            {"pois": True},
        )
        is False
    )
    assert _zone_requires_enrichment("complete", None, None, {"pois": False}) is False
