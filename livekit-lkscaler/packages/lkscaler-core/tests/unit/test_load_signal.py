from lkscaler_core.load_signal import (
    choose_load_signal,
    min_positive_free_slots,
    pick_winner_pod,
)


def test_winner_is_the_most_loaded_pod_with_room() -> None:
    view = {"pod-a": 2, "pod-b": 1}

    assert pick_winner_pod(view) == "pod-b"
    assert choose_load_signal(local_pod_id="pod-b", free_slots_by_pod=view) == 0.0
    assert choose_load_signal(local_pod_id="pod-a", free_slots_by_pod=view) == 1.0


def test_ties_resolve_to_exactly_one_winner() -> None:
    """Two equally free pods must not both look available, or jobs spread across them."""
    view = {"pod-b": 2, "pod-a": 2, "pod-c": 0}

    winners = [
        pod_id
        for pod_id in view
        if choose_load_signal(local_pod_id=pod_id, free_slots_by_pod=view) == 0.0
    ]

    assert winners == ["pod-a"]
    assert pick_winner_pod(view) == "pod-a"


def test_the_filling_pod_keeps_winning_until_it_is_full() -> None:
    filling = {"pod-a": 1, "pod-b": 2}

    assert choose_load_signal(local_pod_id="pod-a", free_slots_by_pod=filling) == 0.0

    full = {"pod-a": 0, "pod-b": 2}

    assert choose_load_signal(local_pod_id="pod-a", free_slots_by_pod=full) == 1.0
    assert choose_load_signal(local_pod_id="pod-b", free_slots_by_pod=full) == 0.0


def test_a_full_cluster_has_no_winner() -> None:
    view = {"pod-a": 0, "pod-b": 0}

    assert pick_winner_pod(view) is None
    assert choose_load_signal(local_pod_id="pod-a", free_slots_by_pod=view) == 1.0


def test_a_pod_missing_from_the_view_reports_unavailable() -> None:
    assert choose_load_signal(local_pod_id="pod-z", free_slots_by_pod={"pod-a": 2}) == 1.0
    assert choose_load_signal(local_pod_id="pod-a", free_slots_by_pod={}) == 1.0


def test_min_positive_free_slots_none_when_no_positive_values() -> None:
    assert min_positive_free_slots([0, -1, 0]) is None


def test_min_positive_free_slots_returns_smallest_positive_value() -> None:
    assert min_positive_free_slots([3, 1, 2, 0]) == 1
