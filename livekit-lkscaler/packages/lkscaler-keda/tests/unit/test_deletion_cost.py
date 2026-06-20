from lkscaler_keda.deletion_cost import choose_deletion_cost


def test_idle_pods_get_lower_deletion_cost() -> None:
    assert choose_deletion_cost(active_rooms=0, reservations=0, idle_cost=0, busy_cost=100) == 0
    assert choose_deletion_cost(active_rooms=0, reservations=1, idle_cost=0, busy_cost=100) == 100
    assert choose_deletion_cost(active_rooms=1, reservations=0, idle_cost=0, busy_cost=100) == 100


def test_choose_deletion_cost_rejects_negative_counters() -> None:
    try:
        choose_deletion_cost(active_rooms=-1, reservations=0, idle_cost=0, busy_cost=100)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative active_rooms")

    try:
        choose_deletion_cost(active_rooms=0, reservations=-1, idle_cost=0, busy_cost=100)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative reservations")