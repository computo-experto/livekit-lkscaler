from lkscaler_core.load_signal import choose_load_signal, min_positive_free_slots


def test_winner_returns_zero() -> None:
    assert choose_load_signal(local_free_slots=2, min_positive_free_slots=2) == 0.0


def test_non_winner_returns_one() -> None:
    assert choose_load_signal(local_free_slots=3, min_positive_free_slots=2) == 1.0


def test_no_capacity_returns_one() -> None:
    assert choose_load_signal(local_free_slots=0, min_positive_free_slots=1) == 1.0


def test_min_positive_free_slots_none_when_no_positive_values() -> None:
    assert min_positive_free_slots([0, -1, 0]) is None


def test_min_positive_free_slots_returns_smallest_positive_value() -> None:
    assert min_positive_free_slots([3, 1, 2, 0]) == 1
