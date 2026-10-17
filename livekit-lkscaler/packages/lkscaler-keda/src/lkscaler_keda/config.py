from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

SUPPORTED_BACKENDS = ("zookeeper", "redis")


@dataclass(frozen=True)
class ScalerConfig:
    """Everything the scaler needs, parsed from a trigger's ``metadata`` block."""

    namespace: str
    backend: str
    zookeeper_hosts: tuple[str, ...] = ()
    redis_url: str = ""
    min_free_slots: int = 8
    room_target_n: int = 2
    overflow_margin: int = 1
    pod_state_ttl_sec: int = 30

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, str]) -> ScalerConfig:
        backend = metadata.get("backend", "zookeeper")
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"backend must be one of {SUPPORTED_BACKENDS}, got {backend!r}")

        hosts = tuple(
            host.strip() for host in metadata.get("zookeeperHosts", "").split(",") if host.strip()
        )
        if backend == "zookeeper" and not hosts:
            raise ValueError("zookeeperHosts is required for the zookeeper backend")

        redis_url = metadata.get("redisUrl", "")
        if backend == "redis" and not redis_url:
            raise ValueError("redisUrl is required for the redis backend")

        return cls(
            namespace=metadata.get("namespace", "livekit-lkscaler"),
            backend=backend,
            zookeeper_hosts=hosts,
            redis_url=redis_url,
            min_free_slots=_positive_int(metadata, "minFreeSlots", 8),
            room_target_n=_positive_int(metadata, "roomTargetN", 2),
            overflow_margin=_positive_int(metadata, "overflowMargin", 1),
            pod_state_ttl_sec=_positive_int(metadata, "podStateTtlSec", 30),
        )


def _positive_int(metadata: Mapping[str, str], key: str, default: int) -> int:
    raw = metadata.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{key} must not be negative, got {value}")
    return value
