from lkscaler_keda.policy import ScalingPolicy


def test_slots_per_worker_is_the_target_plus_the_overflow_margin() -> None:
    policy = ScalingPolicy(min_free_slots=8, room_target_n=2, overflow_margin=1)

    assert policy.slots_per_worker == 3


def test_required_workers_keeps_the_configured_free_slots() -> None:
    policy = ScalingPolicy(min_free_slots=8, room_target_n=2, overflow_margin=1)

    assert policy.required_workers(used_slots=0) == 3
    assert policy.required_workers(used_slots=4) == 4
    assert policy.required_workers(used_slots=5) == 5


def test_required_workers_rounds_up_so_headroom_is_never_short() -> None:
    policy = ScalingPolicy(min_free_slots=7, room_target_n=2, overflow_margin=1)

    assert policy.required_workers(used_slots=0) == 3
    assert policy.required_workers(used_slots=2) == 3
    assert policy.required_workers(used_slots=3) == 4


def test_required_workers_is_never_zero() -> None:
    policy = ScalingPolicy(min_free_slots=0, room_target_n=2, overflow_margin=1)

    assert policy.required_workers(used_slots=0) == 1
