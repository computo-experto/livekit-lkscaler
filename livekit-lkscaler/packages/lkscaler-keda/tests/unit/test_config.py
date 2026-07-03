import pytest
from lkscaler_keda.config import KedaAutoscalerConfig
from pydantic import ValidationError


def test_keda_autoscaler_config_defaults() -> None:
    config = KedaAutoscalerConfig(
        namespace="livekit",
        deployment_name="agents",
        zookeeper_hosts=["zk:2181"],
        min_cluster_free_slots=4,
    )

    assert config.scale_down_dwell_sec == 900
    assert config.poll_interval_sec == 15
    assert config.idle_pod_deletion_cost == 0
    assert config.busy_pod_deletion_cost == 100


def test_keda_autoscaler_config_requires_required_fields() -> None:
    with pytest.raises(ValidationError):
        KedaAutoscalerConfig.model_validate({"namespace": "livekit", "deployment_name": "agents"})


def test_keda_autoscaler_config_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        KedaAutoscalerConfig.model_validate(
            {
                "namespace": "livekit",
                "deployment_name": "agents",
                "zookeeper_hosts": ["zk:2181"],
                "min_cluster_free_slots": 4,
                "unknown_field": True,
            }
        )


@pytest.mark.parametrize(
    "field_name, field_value",
    [
        ("min_cluster_free_slots", -1),
        ("scale_down_dwell_sec", 0),
        ("poll_interval_sec", 0),
        ("idle_pod_deletion_cost", -1),
        ("busy_pod_deletion_cost", -1),
    ],
)
def test_keda_autoscaler_config_rejects_invalid_numeric_values(
    field_name: str,
    field_value: int,
) -> None:
    kwargs: dict[str, object] = {
        "namespace": "livekit",
        "deployment_name": "agents",
        "zookeeper_hosts": ["zk:2181"],
        "min_cluster_free_slots": 4,
    }
    kwargs[field_name] = field_value

    with pytest.raises(ValidationError):
        KedaAutoscalerConfig.model_validate(kwargs)


@pytest.mark.parametrize("hosts", [[], [""], [" "]])
def test_keda_autoscaler_config_rejects_empty_zookeeper_hosts(hosts: list[str]) -> None:
    with pytest.raises(ValidationError):
        KedaAutoscalerConfig(
            namespace="livekit",
            deployment_name="agents",
            zookeeper_hosts=hosts,
            min_cluster_free_slots=4,
        )


def test_keda_autoscaler_config_rejects_inverted_deletion_costs() -> None:
    with pytest.raises(ValidationError):
        KedaAutoscalerConfig(
            namespace="livekit",
            deployment_name="agents",
            zookeeper_hosts=["zk:2181"],
            min_cluster_free_slots=4,
            idle_pod_deletion_cost=100,
            busy_pod_deletion_cost=0,
        )
