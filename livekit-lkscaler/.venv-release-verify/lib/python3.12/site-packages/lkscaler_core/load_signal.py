from collections.abc import Iterable


def min_positive_free_slots(free_slots: Iterable[int]) -> int | None:
    """Return the smallest free slot count that is above zero."""
    positives = [value for value in free_slots if value > 0]
    if not positives:
        return None
    return min(positives)


def choose_load_signal(*, local_free_slots: int, min_positive_free_slots: int | None) -> float:
    """Return the worker load signal.

    Winners return 0.0, non-winners return 1.0.
    """
    if local_free_slots <= 0 or min_positive_free_slots is None:
        return 1.0

    if local_free_slots == min_positive_free_slots:
        return 0.0

    return 1.0
