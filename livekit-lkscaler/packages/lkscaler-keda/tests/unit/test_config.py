import pytest
from lkscaler_keda.config import ScalerConfig


def test_defaults_keep_eight_free_slots_of_headroom() -> None:
    config = ScalerConfig.from_metadata({"zookeeperHosts": "zk-0:2181,zk-1:2181"})

    assert config.backend == "zookeeper"
    assert config.namespace == "livekit-lkscaler"
    assert config.zookeeper_hosts == ("zk-0:2181", "zk-1:2181")
    assert config.min_free_slots == 8
    assert config.room_target_n == 2
    assert config.overflow_margin == 1


def test_redis_backend_needs_a_url() -> None:
    with pytest.raises(ValueError, match="redisUrl"):
        ScalerConfig.from_metadata({"backend": "redis"})


def test_zookeeper_backend_needs_hosts() -> None:
    with pytest.raises(ValueError, match="zookeeperHosts"):
        ScalerConfig.from_metadata({"backend": "zookeeper"})


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="backend must be one of"):
        ScalerConfig.from_metadata({"backend": "etcd"})


def test_non_integer_headroom_is_rejected() -> None:
    with pytest.raises(ValueError, match="minFreeSlots must be an integer"):
        ScalerConfig.from_metadata({"zookeeperHosts": "zk:2181", "minFreeSlots": "lots"})


def test_negative_headroom_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        ScalerConfig.from_metadata({"zookeeperHosts": "zk:2181", "minFreeSlots": "-1"})
