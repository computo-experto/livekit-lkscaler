from collections.abc import Iterator
from concurrent import futures
from datetime import UTC, datetime
from typing import Any, cast

import grpc
import pytest
from lkscaler_core.state import PodState
from lkscaler_keda import METRIC_NAME, ExternalScalerServicer
from lkscaler_keda.config import ScalerConfig
from lkscaler_keda.proto import externalscaler_pb2 as pb
from lkscaler_keda.proto import externalscaler_pb2_grpc as pb_grpc

METADATA = {
    "zookeeperHosts": "zk:2181",
    "minFreeSlots": "8",
    "roomTargetN": "2",
    "overflowMargin": "1",
}


class FakeStore:
    def __init__(self, states: dict[str, PodState]) -> None:
        self._states = states

    def read_pod_states(self) -> dict[str, PodState]:
        return dict(self._states)


def _state(pod_id: str, *, rooms: int, reservations: int = 0) -> PodState:
    return PodState(
        pod_id=pod_id,
        free_slots=2 - rooms - reservations,
        active_rooms=rooms,
        reservations=reservations,
        updated_at=datetime.now(UTC),
    )


def _servicer(states: dict[str, PodState]) -> ExternalScalerServicer:
    return ExternalScalerServicer(store_factory=lambda config: FakeStore(states))


@pytest.fixture
def channel() -> Iterator[grpc.Channel]:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_ExternalScalerServicer_to_server(  # type: ignore[no-untyped-call]
        _servicer({}), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        with grpc.insecure_channel(f"127.0.0.1:{port}") as ch:
            yield ch
    finally:
        server.stop(grace=None)


def test_servicer_is_reachable_over_grpc(channel: grpc.Channel) -> None:
    stub = cast("Any", pb_grpc.ExternalScalerStub(channel))  # type: ignore[no-untyped-call]
    ref = pb.ScaledObjectRef(name="agents", namespace="livekit-system", scalerMetadata=METADATA)

    spec = stub.GetMetricSpec(ref)

    assert spec.metricSpecs[0].metricName == METRIC_NAME
    assert spec.metricSpecs[0].targetSize == 1


def test_is_active_keeps_the_floor_to_min_replica_count(channel: grpc.Channel) -> None:
    stub = cast("Any", pb_grpc.ExternalScalerStub(channel))  # type: ignore[no-untyped-call]

    active = stub.IsActive(
        pb.ScaledObjectRef(name="agents", namespace="ns", scalerMetadata=METADATA)
    )

    assert active.result is True


def test_metrics_report_required_workers_from_the_store() -> None:
    servicer = _servicer({"pod-a": _state("pod-a", rooms=3), "pod-b": _state("pod-b", rooms=3)})
    config = ScalerConfig.from_metadata(METADATA)

    # six used slots plus eight free slots needs floor((6+8)/3)+1 = 5 workers
    assert servicer.required_workers(config) == 5


def test_metrics_include_reservations_as_used_slots() -> None:
    servicer = _servicer({"pod-a": _state("pod-a", rooms=2, reservations=1)})
    config = ScalerConfig.from_metadata(METADATA)

    # three used slots plus eight free needs ceil(11/3) = 4 workers
    assert servicer.required_workers(config) == 4


def test_metrics_are_served_from_the_cached_store_per_configuration() -> None:
    calls: list[ScalerConfig] = []

    def factory(config: ScalerConfig) -> FakeStore:
        calls.append(config)
        return FakeStore({"pod-a": _state("pod-a", rooms=1)})

    servicer = ExternalScalerServicer(store_factory=factory)
    config = ScalerConfig.from_metadata(METADATA)

    servicer.required_workers(config)
    servicer.required_workers(config)

    assert len(calls) == 1


def test_missing_backend_configuration_fails_the_call() -> None:
    servicer = _servicer({})
    request = pb.GetMetricsRequest(
        metricName=METRIC_NAME, scaledObjectRef=pb.ScaledObjectRef(scalerMetadata={})
    )

    with pytest.raises(ValueError, match="zookeeperHosts"):
        servicer.GetMetrics(request, context=None)
