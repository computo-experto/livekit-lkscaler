from collections.abc import Iterable, Mapping


def min_positive_free_slots(free_slots: Iterable[int]) -> int | None:
    """Return the smallest free slot count that is above zero."""
    positives = [value for value in free_slots if value > 0]
    if not positives:
        return None
    return min(positives)


def pick_winner_pod(free_slots_by_pod: Mapping[str, int]) -> str | None:
    """Return the single pod that should receive the next job.

    Bin packing wants the most loaded pod that still has room, so the winner is the pod
    with the fewest free slots above zero and the pod id breaks ties. The tie-break is the
    load-bearing part: without it every equally free pod reports itself a winner and the
    fleet spreads jobs instead of filling one pod toward its target first.
    """
    candidates = [
        (free_slots, pod_id) for pod_id, free_slots in free_slots_by_pod.items() if free_slots > 0
    ]
    if not candidates:
        return None
    return min(candidates)[1]


def choose_load_signal(*, local_pod_id: str, free_slots_by_pod: Mapping[str, int]) -> float:
    """Return the worker load signal: 0.0 for the winner, 1.0 for every other pod.

    A pod that is not in the view reports 1.0, so a worker only advertises availability
    once its peers can see its slots.
    """
    return 0.0 if local_pod_id == pick_winner_pod(free_slots_by_pod) else 1.0
