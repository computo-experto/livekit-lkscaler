from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from concurrent import futures
from typing import Any, Protocol

import grpc
from lkscaler_core.state import PodState

from .config import ScalerConfig
from .policy import ScalingPolicy
from .proto import externalscaler_pb2 as pb
from .proto import externalscaler_pb2_grpc as pb_grpc

logger = logging.getLogger(__name__)

METRIC_NAME = "required_workers"


class PodStateSource(Protocol):
    """The slice of the coordination backend the scaler reads."""

    def read_pod_states(self) -> dict[str, PodState]: ...


def build_store(config: ScalerConfig) -> PodStateSource:
    """Open the coordination backend the workers publish to."""
    if config.backend == "zookeeper":
        from lkscaler_core.zookeeper import KazooNodeClient, ZooKeeperStateStore

        client = KazooNodeClient(hosts=list(config.zookeeper_hosts))
        client.start()
        return ZooKeeperStateStore(namespace=config.namespace, client=client)
    from lkscaler_core.redis import RedisClientAdapter, RedisStateStore

    adapter = RedisClientAdapter(url=config.redis_url)
    adapter.connect()
    return RedisStateStore(
        namespace=config.namespace, client=adapter, pod_state_ttl_sec=config.pod_state_ttl_sec
    )


class ExternalScalerServicer(pb_grpc.ExternalScalerServicer):
    """Serve KEDA's ExternalScaler contract from the coordination backend.

    Each ScaledObject passes its `metadata` block in every call, so the backend connection is
    created per distinct configuration and reused across polls.
    """

    def __init__(
        self, *, store_factory: Callable[[ScalerConfig], PodStateSource] = build_store
    ) -> None:
        self._store_factory = store_factory
        self._lock = threading.Lock()
        self._stores: dict[ScalerConfig, PodStateSource] = {}

    def IsActive(self, request: pb.ScaledObjectRef, context: Any) -> pb.IsActiveResponse:
        """There is always demand while the fleet holds slots; the floor is minReplicaCount."""
        _ = (request, context)
        return pb.IsActiveResponse(result=True)

    def StreamIsActive(self, request: pb.ScaledObjectRef, context: Any) -> Any:
        """Only the `external-push` trigger streams activity; this scaler is polled."""
        _ = (request, context)
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "use the external trigger, not external-push")

    def GetMetricSpec(self, request: pb.ScaledObjectRef, context: Any) -> pb.GetMetricSpecResponse:
        _ = (request, context)
        return pb.GetMetricSpecResponse(
            metricSpecs=[pb.MetricSpec(metricName=METRIC_NAME, targetSize=1)]
        )

    def GetMetrics(self, request: pb.GetMetricsRequest, context: Any) -> pb.GetMetricsResponse:
        _ = context
        config = ScalerConfig.from_metadata(dict(request.scaledObjectRef.scalerMetadata))
        required = self.required_workers(config)
        logger.debug("required_workers=%s namespace=%s", required, config.namespace)
        return pb.GetMetricsResponse(
            metricValues=[pb.MetricValue(metricName=METRIC_NAME, metricValue=required)]
        )

    def required_workers(self, config: ScalerConfig) -> int:
        """Workers the fleet needs right now, from the store the workers publish to."""
        policy = ScalingPolicy(
            min_free_slots=config.min_free_slots,
            room_target_n=config.room_target_n,
            overflow_margin=config.overflow_margin,
        )
        states = self._store_for(config).read_pod_states()
        used = sum(state.active_rooms + state.reservations for state in states.values())
        return policy.required_workers(used_slots=used)

    def _store_for(self, config: ScalerConfig) -> PodStateSource:
        with self._lock:
            store = self._stores.get(config)
            if store is None:
                store = self._store_factory(config)
                self._stores[config] = store
            return store


def serve(servicer: ExternalScalerServicer, *, port: int) -> grpc.Server:
    """Start the gRPC server (plaintext, as KEDA's `external` trigger expects by default)."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_ExternalScalerServicer_to_server(  # type: ignore[no-untyped-call]
        servicer, server
    )
    bound = server.add_insecure_port(f"0.0.0.0:{port}")
    if bound == 0:
        raise SystemExit(f"could not bind gRPC port {port}")
    server.start()
    logger.info("lkscaler-keda scaler listening on port %s", port)
    return server


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    port = int(os.environ.get("LKSCALER_KEDA_PORT", "9090"))
    server = serve(ExternalScalerServicer(), port=port)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=1.0)
